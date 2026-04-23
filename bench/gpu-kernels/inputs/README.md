# gpu-kernels input corpus

This domain expects a **user-provided concatenated corpus** at runtime.

Suggested source root:

- `/Users/chen/Projects/AMD-MI355X-KERNELS/kernels`

Recommended build process:

1. Collect relevant files from `hip/`, `triton/`, and `isa/`.
2. Concatenate them into a single UTF-8 text file (for example `inputs/kernels_corpus.txt`).
3. Prefix each chunk with the original absolute file path so answer citations are traceable.

Set `RLM_GPU_KERNELS_CORPUS` (or edit `config.yaml`) to point the harness at your generated corpus file.
