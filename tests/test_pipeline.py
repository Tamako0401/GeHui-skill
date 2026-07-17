from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ge-hui" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cookies = load_module("cookies_from_storage")
inventory = load_module("douyin_inventory")
hotwords = load_module("hotword_workflow")
transcribe = load_module("transcribe_whisper")
review_queue = load_module("prepare_review_queue")
corpus_status = load_module("corpus_status")
distill_style = load_module("distill_style")
distill_classroom = load_module("distill_classroom_style")
export_reviewed = load_module("export_reviewed_transcripts")
prepare_stories = load_module("prepare_classroom_stories")
promote_stories = load_module("promote_classroom_stories")
persona_eval = load_module("evaluate_persona_response")


class PipelineTests(unittest.TestCase):
    def test_cookie_export_filters_non_douyin_domains(self):
        storage = {
            "cookies": [
                {"domain": ".douyin.com", "path": "/", "name": "dy", "value": "secret"},
                {"domain": ".example.com", "path": "/", "name": "other", "value": "leak"},
            ]
        }
        output = "\n".join(cookies.netscape_lines(storage))
        self.assertIn("secret", output)
        self.assertNotIn("leak", output)

    def test_profile_verification_requires_both_identifiers(self):
        inventory.verify_profile("石不说古天珠瓷书画 抖音号 shibu71947", "shibu71947", "石不说古天珠瓷书画")
        with self.assertRaises(ValueError):
            inventory.verify_profile("抖音号 shibu71947", "shibu71947", "石不说古天珠瓷书画")

    def test_inventory_deduplicates_video_ids(self):
        captured = "2026-07-14T00:00:00+00:00"
        first = inventory.normalize_link("https://www.douyin.com/video/123", captured)
        second = inventory.normalize_link({"url": "https://www.douyin.com/video/123", "title": "更新"}, captured)
        merged = inventory.merge_records([], [first, second])
        self.assertEqual(1, len(merged))
        self.assertEqual("更新", merged[0]["title"])

    def test_inventory_extracts_card_metadata(self):
        record = inventory.normalize_link(
            {
                "url": "https://www.douyin.com/video/7659552926227064057",
                "title": "置顶 1.2万  石不的画半壶砂 #中国画笔墨趣味",
            },
            "2026-07-14T00:00:00+00:00",
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(12000, record["digg_count"])
        self.assertTrue(record["pinned"])
        self.assertEqual("书画艺术", record["topic"])
        self.assertEqual("video-id-inference", record["published_on_source"])
        self.assertGreaterEqual(record["speech_score"], 1)

    def test_stratified_sample_interleaves_topics(self):
        records = []
        for index in range(12):
            records.append(
                {
                    "video_id": str(7000000000000000000 + index),
                    "topic": "书画艺术" if index < 6 else "瓷器鉴定",
                    "published_on": f"202{index % 3}-01-01",
                    "digg_count": index,
                }
            )
        selected = inventory.stratified_sample(records, 6)
        self.assertEqual(6, len(selected))
        self.assertNotEqual(selected[0]["topic"], selected[1]["topic"])

    def test_document_level_qc_rejects_common_hallucinations(self):
        result = {
            "text": "字幕志愿者 李宗盛",
            "segments": [
                {
                    "id": 0,
                    "start": 0,
                    "end": 3,
                    "text": "字幕志愿者 李宗盛",
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.1,
                }
            ],
        }
        report = transcribe.qc_report(result)
        self.assertEqual("low", report["quality"])
        self.assertIn("known-hallucination-template", report["document_flags"])

    def test_hotword_candidates_skip_low_quality_transcripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            qc = root / "qc"
            raw.mkdir()
            qc.mkdir()
            approved = root / "approved.tsv"
            approved.write_text(
                "canonical\tvariants\tpinyin\tdomains\tcontext_regex\tevidence\tstatus\treviewer\tupdated_at\n"
                "葛辉\t葛徽\tge hui\tname\t老师\ttest\tapproved\towner\t2026-07-14\n",
                encoding="utf-8",
            )
            payload = {
                "source_id": "douyin-1",
                "segments": [
                    {
                        "start": 0,
                        "end": 1,
                        "text": "葛徽老师",
                        "avg_logprob": -1.2,
                        "compression_ratio": 1.0,
                    }
                ],
            }
            (raw / "1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (qc / "1.json").write_text('{"quality":"low"}', encoding="utf-8")
            self.assertEqual([], hotwords.scan_candidates(raw, approved, qc))

    def test_only_approved_contextual_hotwords_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved = root / "approved.tsv"
            approved.write_text(
                "canonical\tvariants\tpinyin\tdomains\tcontext_regex\tevidence\tstatus\treviewer\tupdated_at\n"
                "葛辉\t葛徽\tge hui\tname\t老师\ttest\tapproved\towner\t2026-07-14\n"
                "雨课堂\t语课堂\tyu ke tang\tclassroom\t课程\ttest\tcandidate\t\t2026-07-14\n",
                encoding="utf-8",
            )
            raw = root / "raw.srt"
            raw.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n葛徽老师打开语课堂\n",
                encoding="utf-8",
            )
            clean = root / "clean.srt"
            audit = root / "audit.json"
            changes = hotwords.apply_rules(raw, clean, audit, approved)
            self.assertEqual(1, changes)
            self.assertIn("葛辉老师", clean.read_text(encoding="utf-8"))
            self.assertIn("语课堂", clean.read_text(encoding="utf-8"))
            self.assertIn("葛徽老师", raw.read_text(encoding="utf-8"))
            self.assertEqual(1, len(json.loads(audit.read_text(encoding="utf-8"))["changes"]))

    def test_review_selection_covers_topics_and_time_bands(self):
        records = []
        for topic_index in range(5):
            for band in ("early", "middle", "recent"):
                records.append(
                    {
                        "video_id": f"{topic_index}-{band}",
                        "topic": f"topic-{topic_index}",
                        "time_band": band,
                        "quality": "high",
                        "digg_count": topic_index,
                    }
                )
        selected = review_queue.select_for_review(records, 10)
        self.assertEqual(10, len(selected))
        self.assertEqual(5, len({row["topic"] for row in selected}))
        self.assertEqual(3, len({row["time_band"] for row in selected}))

    def test_batch_clean_skips_low_quality_transcripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            qc = root / "qc"
            clean = root / "clean"
            audit = root / "audit"
            raw.mkdir()
            qc.mkdir()
            approved = root / "approved.tsv"
            approved.write_text(
                "canonical\tvariants\tpinyin\tdomains\tcontext_regex\tevidence\tstatus\treviewer\tupdated_at\n",
                encoding="utf-8",
            )
            for name, quality in (("usable", "high"), ("rejected", "low")):
                (raw / f"{name}.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:01,000\n原文\n", encoding="utf-8"
                )
                (qc / f"{name}.json").write_text(
                    json.dumps({"quality": quality}), encoding="utf-8"
                )
            processed, changes = hotwords.batch_apply(raw, qc, clean, audit, approved)
            self.assertEqual((1, 0), (processed, changes))
            self.assertTrue((clean / "usable.srt").exists())
            self.assertFalse((clean / "rejected.srt").exists())

    def test_review_gate_rejects_inconsistent_segment_decisions(self):
        review = {
            "reviewer": "owner",
            "reviewed_on": "2026-07-14",
            "segments": [
                {
                    "raw_text": "原文",
                    "corrected_text": "改文",
                    "segment_status": "verified",
                }
            ],
        }
        errors = corpus_status.review_validation_errors(review)
        self.assertIn("segment-0-verified-text-changed", errors)

    def test_review_gate_allows_zero_duration_blank_machine_segments(self):
        review = {
            "reviewer": "owner",
            "reviewed_on": "2026-07-14",
            "segments": [
                {"raw_text": "", "corrected_text": "", "segment_status": "verified"}
            ],
        }
        self.assertEqual([], corpus_status.review_validation_errors(review))

    def test_review_gate_allows_only_evidenced_noise_deletion(self):
        accepted = {
            "reviewer": "owner",
            "reviewed_on": "2026-07-17",
            "segments": [
                {
                    "raw_text": "字幕志愿者反复循环",
                    "corrected_text": "",
                    "segment_status": "corrected",
                    "correction_kind": "noise_asr_loop",
                    "notes": "复听音频后确认该段无人声",
                }
            ],
        }
        self.assertEqual([], corpus_status.review_validation_errors(accepted))

        flattened_voice = {
            **accepted,
            "segments": [
                {
                    "raw_text": "还明白啊",
                    "corrected_text": "",
                    "segment_status": "corrected",
                    "correction_kind": "filler",
                    "notes": "认为是口头语",
                }
            ],
        }
        errors = corpus_status.review_validation_errors(flattened_voice)
        self.assertIn("segment-0-blank-without-approved-noise-kind", errors)

    def test_style_phrase_statistics_count_clips_separately(self):
        reviews = [
            {"video_id": "1", "_text": "大家大家为什么"},
            {"video_id": "2", "_text": "大家看一下"},
        ]
        rows = distill_style.phrase_statistics(reviews)["direct_address"]
        everyone = next(row for row in rows if row["phrase"] == "大家")
        self.assertEqual(3, everyone["count"])
        self.assertEqual(2, everyone["clips"])

    def test_classroom_style_models_frequency_function_and_position(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            classroom = root / "subtitles-raw"
            classroom.mkdir()
            (classroom / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n这个问题，还明白啊，所以继续\n\n"
                "2\n00:00:02,000 --> 00:00:03,000\n对不对\n\n"
                "3\n00:00:03,000 --> 00:00:04,000\n你到底懂不懂\n",
                encoding="utf-8",
            )
            report = distill_classroom.build_report(root)
            self.assertEqual("measured-classroom-v1", report["profile"])
            self.assertEqual(1, report["phrases"]["还明白"]["count"])
            self.assertEqual(
                1,
                report["phrases"]["还明白"]["local_positions"]["before_transition"],
            )
            self.assertEqual(
                1,
                report["phrases"]["对不对"]["local_positions"]["standalone"],
            )
            self.assertEqual(
                "较强的理解检查，用于挑战、纠偏或强调后果",
                report["phrases"]["懂不懂"]["function"],
            )

    def test_measured_classroom_v1_matches_tracked_baseline(self):
        report = distill_classroom.build_report(ROOT)
        self.assertEqual(26, report["documents"])
        self.assertEqual(267137, report["characters"])
        self.assertEqual(839, report["phrases"]["还明白"]["count"])
        self.assertEqual(465, report["phrases"]["还明白啊"]["count"])
        self.assertEqual(531, report["phrases"]["对不对"]["count"])
        self.assertEqual(265, report["phrases"]["知道吧"]["count"])
        self.assertEqual(28, report["phrases"]["懂不懂"]["count"])

    def test_reviewed_srt_timestamp_rounding(self):
        self.assertEqual("00:01:02,346", export_reviewed.timestamp(62.3456))

    def test_reviewed_export_preserves_noise_omission_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = root / "review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "video_id": "1",
                        "review_status": "reviewed",
                        "reviewer": "owner",
                        "reviewed_on": "2026-07-17",
                        "segments": [
                            {
                                "id": 0,
                                "start": 0,
                                "end": 1,
                                "raw_text": "还明白啊",
                                "corrected_text": "还明白啊",
                                "segment_status": "verified",
                                "correction_kind": "none",
                                "notes": "",
                            },
                            {
                                "id": 1,
                                "start": 1,
                                "end": 2,
                                "raw_text": "字幕循环",
                                "corrected_text": "",
                                "segment_status": "corrected",
                                "correction_kind": "noise_asr_loop",
                                "notes": "复听确认无人声",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            _, json_path, count = export_reviewed.export_review(review_path, root / "out")
            exported = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(1, count)
            self.assertEqual("还明白啊", exported["segments"][0]["text"])
            self.assertEqual(
                "noise_asr_loop",
                exported["omitted_segments"][0]["correction_kind"],
            )

    def test_classroom_story_extraction_balances_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            classroom = root / "subtitles-raw"
            classroom.mkdir()
            (classroom / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:20,000\n我给你们讲一个佛陀的故事\n\n"
                "2\n00:00:20,000 --> 00:00:40,000\n后来地藏菩萨发愿救度地狱众生\n\n"
                "3\n00:05:00,000 --> 00:05:20,000\n想不想听东北出马仙的故事\n\n"
                "4\n00:05:20,000 --> 00:05:40,000\n狐黄白这些动物仙后来怎么了\n",
                encoding="utf-8",
            )
            candidates = prepare_stories.extract_candidates(
                root,
                per_category=2,
                before_seconds=0,
                after_seconds=60,
            )
            self.assertEqual(
                {"buddhism", "folk_supernatural"},
                {row["category"] for row in candidates},
            )

    def test_classroom_story_queue_never_overwrites_human_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = {
                "category": "buddhism",
                "source_file": "sample.srt",
                "seed_start": 10.0,
                "suggested_start": 0.0,
                "suggested_end": 60.0,
                "score": 20,
                "category_score": 15,
                "anchor_score": 5,
                "matched_terms": {"佛陀": 1},
                "matched_anchors": {"故事": 1},
                "source_segments": [
                    {
                        "start_timestamp": "00:00:00,000",
                        "end_timestamp": "00:00:20,000",
                        "text": "佛陀的故事",
                    }
                ],
            }
            paths = prepare_stories.write_review_queue([candidate], root)
            review = json.loads(paths[0].read_text(encoding="utf-8"))
            review["title"] = "人工标题"
            paths[0].write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            prepare_stories.write_review_queue([candidate], root)
            preserved = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual("人工标题", preserved["title"])

    def test_classroom_story_human_gate_checks_approved_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            classroom = root / "subtitles-raw"
            review_root = root / "local" / "story-reviews" / "buddhism"
            classroom.mkdir()
            review_root.mkdir(parents=True)
            (classroom / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:20,000\n佛陀的故事\n",
                encoding="utf-8",
            )
            review = {
                "story_id": "CLS-BUD-TEST",
                "review_status": "approved",
                "title": "人工标题",
                "source_file": "sample.srt",
                "start": "00:00:00,000",
                "end": "00:00:20,000",
            }
            (review_root / "story.json").write_text(
                json.dumps(review, ensure_ascii=False), encoding="utf-8"
            )
            report = prepare_stories.review_status_report(root / "local", root)
            self.assertTrue(report["human_gate_ready"])
            self.assertEqual({"approved": 1}, report["status"])

    def test_story_promotion_requires_spine_and_emits_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            classroom = root / "subtitles-raw"
            reviews = root / "reviews" / "buddhism"
            output = root / "public"
            classroom.mkdir()
            reviews.mkdir(parents=True)
            (classroom / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:20,000\n佛陀当时讲了一个故事\n",
                encoding="utf-8",
            )
            payload = {
                "story_id": "CLS-BUD-TEST",
                "review_status": "approved",
                "category": "buddhism",
                "title": "佛陀说法",
                "source_file": "sample.srt",
                "start": "00:00:00,000",
                "end": "00:00:20,000",
                "trigger_topics": ["佛家", "佛陀"],
                "story_type": "religious_narrative",
                "truth_status": "religious_narrative",
                "narrative_spine": "佛陀以一段说法引出修行问题。",
                "return_point": "回到佛家如何理解苦。",
            }
            (reviews / "story.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            paths = promote_stories.promote(root / "reviews", root, output)
            self.assertTrue((output / "story-index.tsv").exists())
            self.assertTrue((output / "stories-buddhism.md").exists())
            self.assertIn("CLS-BUD-TEST", (output / "story-index.tsv").read_text(encoding="utf-8"))
            self.assertEqual(2, len(paths))

    def test_introduce_buddhism_regression_rejects_definition_only_answer(self):
        case = persona_eval.load_case(
            ROOT / "tests" / "persona_cases.json",
            "introduce-buddhism-classroom",
        )
        definition_only = (
            "佛家主要讨论苦、缘起和无常。还明白啊？它分析人的执念，"
            "再说明人为什么会烦恼，对不对？所以佛家是一套认识内心的方法。" * 4
        )
        self.assertFalse(persona_eval.evaluate_response(definition_only, case)["passed"])

        story_answer = (
            "佛家先讲苦和缘起，这个根要先立住，还明白啊？" * 4
            + "\n\n佛教故事里有一个佛陀初次说法的场景，当时他先向身边的人讲苦。"
            "当时人们面对疾病、衰老和死亡，并没有今天这么多解释工具，"
            "所以这个宗教叙事先把所有人都逃不开的经验摆出来，再问人为什么执着。"
            "这个故事说明，佛家不是先求保佑，而是先正视苦。"
            + "\n\n我跟你讲，课堂里有个玄一点的说法，后来又会从地藏菩萨讲到地狱救度。"
            "按这个说法，地藏发愿不是为了展示神通，而是把救度众生讲成一件不能半途而废的事。"
            "这类故事可以讲得很玄，但不能直接拿来替代史料。讲完以后，我们再回到佛家的因果和无常，"
            "绕了一圈还是这个道理：它要处理的是人怎样面对变化、执念和失去。知道吧？"
        )
        self.assertTrue(persona_eval.evaluate_response(story_answer, case)["passed"])


if __name__ == "__main__":
    unittest.main()
