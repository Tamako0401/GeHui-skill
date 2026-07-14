# Ge Hui Skill

`ge-hui` is an immersive Chinese-culture persona skill built from two deliberately separated registers: classroom lectures and public short videos. It supports a focused culture mode and an explicitly activated global mode that can connect ordinary topics to folklore, Buddhism, Daoism, ghosts, painting, and ceramics.

## Repository contents

- `ge-hui/`: the installable Skill package, including persona instructions, retrieval utilities, collection/transcription scripts, reviewed hotwords, and aggregated style references.
- `subtitles-raw/`: the existing classroom SRT corpus.
- `local-data/`: ignored private short-video inventory, authentication state, audio, raw transcripts, review queues, and correction evidence.
- `prompt.txt`: the working project charter and milestone checkpoint.

## Data boundary

Do not publish downloaded videos, audio, cookies, raw short-video transcripts, student information, or review evidence. Public skill references contain only reviewed hotwords and aggregate behavior. Any source-backed answer must identify the underlying file or source ID and timestamp; a missing match means only that the present local corpus has no match.

## Current status

The private inventory contains 254 canonical public-video URLs. The current local corpus has 125 audio/transcript pairs; document-level QC accepts 66 (44 high and 22 medium) and rejects 59 likely music, repetition, low-content, or hallucination-heavy clips. Thirty clips and 3,758 segments have passed manual review across five topics and three time bands, so the measured-v1 public register is now promoted. Complete transcripts remain private; the public skill contains only aggregate counts, behavior rules, and minimal short phrases.

Collection first tries `yt-dlp`. If Douyin returns an empty detail response despite a valid visible login, the Playwright helper may capture only the media responses loaded by the public page; it does not solve CAPTCHAs, reverse signatures, or bypass rate limits. Run `prepare_review_queue.py` to prepare private review files and `hotword_workflow.py batch-apply` to create traceable clean copies from high/medium transcripts using approved rules only.
