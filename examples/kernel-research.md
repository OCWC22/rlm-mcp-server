# Example: kernel research workflow (GPU kernels)

This walkthrough simulates analyzing a **public-style** kernel file (think CUDA/HIP reduction or tiled matmul kernels).

> Source style referenced: common kernels like `reduction_kernel.cu` or tiled GEMM kernels in public CUDA/HIP samples.

## Goal

Answer: *"Where are the main occupancy and memory-divergence risks, and what should be profiled first?"*

## 1) Load kernel source

```json
{"tool":"rlm_init","args":{"path":"/tmp/public_reduction_kernel.cu","session_id":"kernel_case"}}
```

Mock result:

```json
{"session_id":"kernel_case","path":"/tmp/public_reduction_kernel.cu","chars":18342,"state_file":"~/.cache/rlm-mcp/kernel_case.pkl"}
```

Why: `rlm_init` establishes a reusable context so every later step avoids re-sending source.

## 2) Find structural anchors

```json
{"tool":"rlm_grep","args":{"session_id":"kernel_case","pattern":"__global__|dim3|__shared__|atomicAdd|threadIdx|blockIdx|__syncthreads","max_matches":40,"window":180}}
```

Mock highlights:

- `__global__ void reduce_sum(...)`
- `extern __shared__ float smem[];`
- `if (tid < 32) { ... }`
- `atomicAdd(out, block_sum);`

Why: this quickly maps launch semantics, shared-memory usage, sync points, and atomic pressure.

## 3) Run programmable analysis loop with `rlm_exec`

```json
{
  "tool":"rlm_exec",
  "args":{
    "session_id":"kernel_case",
    "code":"import re\ntext = content\nfuncs = re.findall(r'__global__\\s+void\\s+(\\w+)\\s*\\(', text)\nprint('kernels:', funcs)\nfor name in funcs:\n    body_hits = grep(name + r'.*?\\{', max_matches=1, window=600)\n    print('candidate', name, 'hits', len(body_hits))\nadd_buffer('Found %d kernel entrypoints' % len(funcs))"
  }
}
```

Mock result:

```json
{"stdout":"kernels: ['reduce_sum', 'reduce_sum_warp']\ncandidate reduce_sum hits 1\ncandidate reduce_sum_warp hits 1\n","stderr":""}
```

Why: `rlm_exec` lets you keep iterative state and produce repeatable structure checks without leaving the MCP workflow.

## 4) Recursive semantic review of hotspots

```json
{"tool":"rlm_sub_query","args":{"session_id":"kernel_case","max_tokens":900,"prompt":"Given the located kernel snippets, identify top two correctness/perf risks around atomics, bank conflicts, and warp divergence. Keep each risk under 4 bullets."}}
```

Mock model summary:

1. Atomic contention on global accumulator dominates tail latency for high block counts.
2. Warp-tail branch (`tid < 32`) risks divergence/port pressure depending on architecture and compiler unrolling.

Why: use sub-queries for focused interpretation once spans are narrowed.

## 5) Persist findings and synthesize

```json
{"tool":"rlm_add_buffer","args":{"session_id":"kernel_case","text":"Profile plan: start with atomic throughput + shared-memory bank conflict metrics."}}
```

```json
{"tool":"rlm_get_buffers","args":{"session_id":"kernel_case"}}
```

Mock final synthesis (host model):

- **Primary risk:** `atomicAdd` serialization under high occupancy.
- **Secondary risk:** shared-memory bank pressure in reduction stages.
- **First profiling pass:** occupancy, atomic throughput, achieved memory bandwidth, warp execution efficiency.

---

### Practical notes

- If `rlm_sub_query` returns `{"need_subquery": true, ...}`, provide the callback answer via `rlm_sub_query_result` and retry.
- Keep short evidence quotes in buffers so final summaries stay traceable to source spans.
