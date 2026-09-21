# Structured notes

You are given the transcript of an online video. Convert it into structured notes that are easy to scan, search, and reuse.

<TRANSCRIPT>

## Instructions

1. Read the entire transcript.
2. Reorganize the content into a logical outline with headings and subheadings.
3. Under each heading, capture the main idea in one or two sentences, plus supporting details as bullets.
4. Preserve specific facts: names, numbers, dates, definitions, and quoted terminology.
5. Mark anything that is ambiguous or unclear as `[?]` rather than guessing.

## Output format

```markdown
# Notes

## 1. <Topic>
- **Main idea:** ...
- Details:
  - ...
  - ...

## 2. <Topic>
- ...
```

Rules:
- Do not paraphrase into something that changes meaning; prefer concise quotation for key definitions.
- Keep the structure driven by the actual content, not by assumptions about the topic.
- If a section of the transcript is off-topic or unimportant, drop it or mark it as a brief aside.
