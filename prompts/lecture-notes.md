# Lecture / talk notes

You are given the transcript of a lecture, talk, or educational video. Produce study-style notes.

<TRANSCRIPT>

## Instructions

1. Read the entire transcript.
2. Identify the structure: the main topic, the sections the speaker walks through, and the conclusion.
3. For each section write:
   - a short heading;
   - the core concept explained in your own words (1–3 sentences);
   - key definitions, formulas, examples, or named things the speaker gives;
   - anything the speaker emphasizes as important.
4. Add a "Questions to review" section listing concepts that a learner would likely need to verify or practice.
5. Add a "References" section for any books, papers, tools, or sources named.

## Output format

```markdown
# Lecture notes: <topic>

## Overview
<2–4 sentences>

## 1. <Section title>
- **Concept:** ...
- Definitions / examples:
  - ...
- **Note:** ...

## ...

## Questions to review
- ...

## References
- ...
```

Rules:
- Distinguish the speaker's claims from objective fact where possible.
- If timestamps exist, you may use them to label long sections.
- Write in the language of the lecture unless the user asks otherwise.
