# Benchmark domains scaffold (v0.7.0)

`bench/` now supports multiple long-context benchmark domains with a shared LM config layer.

## Current domains

- `cdna4-isa/` — full benchmark + GEPA MVP runner (`bench/cdna4-isa/gepa/`)
- `gpu-kernels/` — skeleton domain for HIP/Triton/ISA kernel corpora
- `codebase-triage/` — skeleton domain for repository architecture triage corpora

## Shared config

Use `bench/common/config.py` for DSPy LM wiring:

- `task_lm(...)` reads `RLM_TASK_LM` (default: `openrouter/openai/gpt-5-mini`)
- `reflection_lm(...)` reads `RLM_REFLECTION_LM` (default: `openrouter/openai/gpt-5.4`)

## Add a new domain

1. Create a folder `bench/<domain>/`.
2. Add `config.yaml` with at least:
   - `prompt_template` (`kernel_analysis`, `paper_deep_dive`, `codebase_triage`, or a new prompt)
   - `question_file`
   - `inputs.corpus_path` and `inputs.corpus_path_env`
3. Add `questions.jsonl` with grounded questions and reference answers.
4. Add `inputs/README.md` explaining how to build the user-provided corpus.
5. If needed, add domain-specific runners or GEPA pipeline files under the domain directory.

## Suggested JSONL question schema

Each line can follow the existing benchmark shape:

- `id`
- `section`
- `difficulty`
- `complexity`
- `question`
- `reference_answer`
- `keywords_for_scoring`

## Notes

- Skeleton domains intentionally do **not** ship with prebuilt corpora.
- Users provide corpora at runtime and keep absolute source-path headers for citation quality.
