# CDNA4 ISA benchmark (RLM vs baseline)

This benchmark measures answer quality on **CDNA4 ISA technical questions** when the corpus is long (~920KB text / ~230k tokens):

- **Baseline path** (single-pass / context-limited prompting)
- **RLM path** (tool-mediated retrieval + recursive synthesis)

## What this benchmark is testing

The core question is whether RLM-style decomposition can preserve quality on long-context technical QA where naive prompting degrades.

Hypothesis (paper-aligned): **arXiv:2512.24601 §3.1 and §4** predict stronger performance on high-coverage and cross-section questions when retrieval/programmatic loops replace monolithic prompting.

- Paper: https://arxiv.org/abs/2512.24601

## Corpus input

- Canonical input file: `inputs/cdna4_isa.txt`
- This path is a symlink to:
  `/Users/chen/Projects/AMD-MI355X-KERNELS/research/processed/amd-instinct-cdna4-instruction-set-architecture.txt`

## Dataset

- `questions.jsonl`: 20 grounded questions from chapter-split ISA markdown
- Per-question fields:
  - `id`, `section`, `difficulty`, `complexity`
  - `question`, `reference_answer`, `keywords_for_scoring`

Complexity tags follow the benchmark framing:

- `constant`: direct lookup
- `linear`: single-section synthesis
- `quadratic`: cross-table / cross-section aggregation

## Harness layout

- `runners/common.py` contains shared helpers for loading questions and writing per-question result JSON files.
- `runners/baseline.py` and `runners/rlm.py` are intentionally left as stubs for **Item 2**.
- `scoring/llm_judge.py` is intentionally left as a stub for **Item 3**.

## Expected result paths

Runner outputs should be written to:

- `results/baseline/<question_id>.json`
- `results/rlm/<question_id>.json`

`results/demo/` is tracked for small committed demos; other generated results are gitignored.
