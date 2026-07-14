# Corpus protocol

## Layers

| Layer | Location | Purpose | Public |
| --- | --- | --- | ---: |
| Classroom raw | `subtitles-raw/` | Lecture evidence and classroom style | Already tracked |
| Short-video private | `local-data/short-video/` | Inventory, audio, raw/clean transcripts, reviews | No |
| Approved hotwords | `ge-hui/references/hotwords-approved.tsv` | Reviewed ASR prompting and contextual correction | Yes |
| Candidate evidence | `local-data/short-video/hotword-candidates.tsv` | Proposed terms, contexts, reviewer decisions | No |
| Aggregate style | `ge-hui/references/` | Non-verbatim behavior and cognitive patterns | Yes |

Keep raw transcripts immutable. Write corrected transcripts separately and retain an audit entry for every replacement.

## Short-video intake

Verify both expected identifiers before collecting:

```text
douyin_id: shibu71947
nickname: 石不说古天珠瓷书画
```

For every clip record `source_id`, canonical URL, captured time, published time when available, title, duration, engagement counts, topic, transcript method, quality, review status, and hashes. Stop rather than bypass a CAPTCHA, login wall, or rate limit.

Keep cookies and Playwright storage state under `local-data/auth/`. Export only Douyin-domain cookies. Never print cookie values or commit authentication files.

## Sampling and promotion

Inventory all visible public clips. Run 10 clips end to end, then select 80 using date, topic, and engagement strata. Do not sample only viral clips. If fewer than 60 transcripts pass the quality gate, extend the selection in coverage-aware batches instead of weakening QC; stop when the gate is met or all public clips are exhausted.

Promote the short-video profile only after all conditions hold:

- at least 60 transcripts have medium-or-better quality;
- at least 30 clips are manually reviewed segment by segment;
- the reviewed set spans at least five topics and three publication-time bands.

If the account has fewer clips or the identity cannot be verified, record the limitation and keep the profile provisional.

Prepare the private human-review queue with `scripts/prepare_review_queue.py`. The generated review JSON copies each raw segment into `corrected_text`, sets every `segment_status` and the clip `review_status` to `pending`, and prioritizes topic/time-band coverage. A human must listen to the linked audio, correct every segment, resolve flagged spans, add notes where needed, set segment statuses, and only then set the clip to `reviewed`. Never infer completion from the presence of a queue file.

## Hotword rule

Generate candidates from titles, hashtags, classroom terms, repeated low-confidence spans, and phonetic similarity. Never apply a candidate automatically. Only rows marked `approved` in the public table may be injected into ASR or applied to clean transcripts, and a contextual rule must match its declared context.

## Citation

- Classroom: `filename, start–end`.
- Short video: `source_id, start–end`.
- Direct quotation: exact corpus text with citation.
- Paraphrase: explicitly paraphrased with citation.
- Persona answer: do not imply it occurred in the corpus.
