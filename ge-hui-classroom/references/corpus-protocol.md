# Corpus protocol

## Corpus layers

| Layer | Purpose | May support factual course answer? | May influence style rewrite? |
| --- | --- | ---: | ---: |
| `classroom` | Teaching content and classroom pedagogy | Yes, with file-and-time citation | Yes, primary source |
| `short-video` | Public-facing rhetoric and condensed explanations | No, unless independently sourced and cited | Only when explicitly requested |
| `hotwords` | ASR correction candidates | No | No |
| `external-reference` | Fact-checking and scholarly context | Yes, cite the external source | No by itself |

Keep raw files immutable. Store cleaned transcripts, if created, separately and retain a trace from each correction to raw text, rule, and reviewer decision.

## Short-video intake gate

Add a short-video transcript only after recording:

```text
source_id:
source_url:
captured_on:
published_on:
speaker_identity_confidence:
audience: public / students / unknown
topic:
duration:
transcript_method: manual / ASR / platform captions
transcript_quality: high / medium / low
rights_or_permission_note:
use: style-only / factual-source / exclude
```

Exclude clips with uncertain identity, aggressive editing that destroys context, missing provenance, unclear rights, or low transcript quality. Sample broadly across topic and date; do not collect only the most dramatic clips.

## Decision rule for short video

Keep short video out of version 1. It becomes useful in version 2 only if the product has an explicit second mode such as “把这段话改成适合 60 秒公开讲解的版本”. In that mode, state that the register is public-facing and do not cite the clip as evidence of classroom teaching.

## Annotation minimum

For every new transcript, record `source_type`, `date`, `topic`, `audience`, `transcript_quality`, `rights_note`, and `review_status`. For reusable style examples, also tag the rhetorical move and whether the example is safe to imitate.
