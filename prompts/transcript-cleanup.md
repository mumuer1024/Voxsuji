# Transcript cleanup

You are given a raw transcript of spoken audio. Clean it up for reading while preserving meaning and fidelity.

<TRANSCRIPT>

## Instructions

1. Remove filler words and disfluencies (e.g., "um", "uh", "you know", false starts, repeated words) unless they carry meaning.
2. Fix obvious transcription artifacts such as split words, merged sentences, and broken capitalization/punctuation.
3. Do **not** correct the speaker's meaning, add facts, or remove substantive content.
4. When a passage is genuinely unintelligible or uncertain, mark it as `[inaudible]` or `[uncertain: ...]` instead of guessing.
5. Preserve any timestamps or segment breaks the transcript already has, if present.

## Output format

Return the cleaned transcript as plain text (or Markdown with the same paragraph/segment structure as the input).

Rules:
- Keep it faithful: cleanup means readability, not rewriting.
- Preserve named entities, numbers, and quotes exactly.
- If the source language is mixed, do not translate; keep the original language.
