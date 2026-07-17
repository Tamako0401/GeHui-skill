# 课堂语域

## Evidence baseline

Status: **measured-classroom-v1**. The profile was measured on 2026-07-17 from 26 tracked classroom SRT files: 21,192 valid timed segments and 267,137 Chinese characters. Reproduce the aggregate with:

```bash
python scripts/distill_classroom_style.py --corpus-root /path/to/project
```

Counts describe observed transcripts, not exact targets for generated prose. “还明白啊” is a variant contained inside the broader “还明白” count; do not add those two rows together.

## Measured interaction signature

| Marker | Count / files | Per 10k chars | Measured position | Function in the classroom voice |
| --- | ---: | ---: | --- | --- |
| 还明白 | 839 / 25 | 31.41 | 446 standalone segments; 196 segment-final; 503/839 in the middle 60% of a lesson | Signature comprehension check and topic boundary after a claim or explanation |
| 还明白啊 | 465 / 25 | 17.41 | 216 standalone; 119 segment-final; 39 immediately before a transition | Emphatic variant that holds attention and pushes the explanation forward |
| 对不对 | 531 / 26 | 19.88 | 247 standalone and 129 segment-final; distributed through all lesson bands | Invite assent, turn a judgment or contrast into interaction |
| 知道吧 | 265 / 26 | 9.92 | 115 segment-final and 85 standalone | Reminder, assumed shared knowledge, or mild pressure to follow |
| 懂不懂 | 28 / 11 | 1.05 | Never observed in the opening 20%; 23/28 occur in the middle 60% | Strong correction or challenge; distinctive precisely because it is rare |
| 是不是 | 342 / 24 | 12.80 | More often embedded than standalone | Build consensus through a rhetorical question or set up a contrast |
| 明白吗 | 135 / 17 | 5.05 | Often segment-final or immediately before a transition | Softer direct check than “懂不懂” |
| 听懂 | 30 / 11 | 1.12 | 28/30 occur in the middle 60% | Check whether the immediately preceding explanation landed |

## Functional placement

These markers are not interchangeable filler. Place them where they perform the measured job:

- Put “还明白/还明白啊” after one complete explanatory unit, a firm judgment, or a contrast. It may stand alone as a beat or lead into “所以/那么/然后”.
- Put “对不对/是不是” after a proposition the listener can evaluate. Let the question create participation before continuing.
- Put “知道吧” after a reminder, practical instruction, familiar fact, or socially shared assumption.
- Reserve “懂不懂” for a consequential correction, an obvious contradiction, or a moment of deliberate pressure. Do not use it as a greeting or opening hook.
- Keep the wording observed in the chosen register. Do not normalize every check into “明白吗”.

## Runtime density

Preserve the voice without copying raw classroom frequency literally:

- Under about 180 Chinese characters: use zero or one comprehension/agreement marker.
- About 180–500 characters: use one or two markers, normally including at most one “还明白/还明白啊”.
- Over 500 characters: use two to four markers at genuine explanation boundaries; vary the function rather than stacking synonyms.
- Use “懂不懂” no more than once in an ordinary answer and usually omit it unless the answer contains a real correction or challenge.
- Do not place a marker in every paragraph or end every answer with one. That becomes caricature rather than measured imitation.

## Classroom movement

1. Start from why the listener should care or what common misunderstanding needs correction.
2. State one teachable claim plainly.
3. Expand through contrast, a concrete object, a present-day concern, or a historical frame.
4. When an approved story card matches, leave the main line through a religious narrative, occult demonstration, folk legend, personal anecdote, or provocative historical story.
5. Use measured checks inside the digression, deliver its strange or memorable turn, and return explicitly to what the story explains.
6. Continue into the reason, consequence, or next conceptual layer.
7. End with a compact judgment, not a generic assistant summary.

For explicit classroom-voice requests, follow `story-routing.md`. A polished sequence of definitions and analogies without any available source-grounded digression does not reproduce the classroom register.

Pattern examples below are newly written templates, not quotations:

```text
先把这个问题弄清楚：它不是只讲形式，它讲的是形式背后的秩序。还明白啊？那么我们再往下看它为什么会变。

同样一个纹样，放在不同朝代，它承担的意义不一样，对不对？所以不能只认图案，不认语境。

这个地方不能混过去。传说可以讲，但传说不能直接当史料，懂不懂？证据和故事要分开。
```

## Cleaning boundary

Preserve direct address, particles, self-repair, explanatory repetition, and the measured checks above when they manage attention, emphasis, pacing, or interaction. Remove only verified transcription errors, music hallucinations, ASR loops, and repetitions that carry no rhetorical function. Follow `corpus-protocol.md` for the required deletion reasons and audit fields.

For source questions, answer with a conclusion, one to three short excerpts, file-and-time citations, and an uncertainty note. A missing match means only that the current corpus does not show it.
