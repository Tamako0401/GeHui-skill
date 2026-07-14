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
export_reviewed = load_module("export_reviewed_transcripts")


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

    def test_style_phrase_statistics_count_clips_separately(self):
        reviews = [
            {"video_id": "1", "_text": "大家大家为什么"},
            {"video_id": "2", "_text": "大家看一下"},
        ]
        rows = distill_style.phrase_statistics(reviews)["direct_address"]
        everyone = next(row for row in rows if row["phrase"] == "大家")
        self.assertEqual(3, everyone["count"])
        self.assertEqual(2, everyone["clips"])

    def test_reviewed_srt_timestamp_rounding(self):
        self.assertEqual("00:01:02,346", export_reviewed.timestamp(62.3456))


if __name__ == "__main__":
    unittest.main()
