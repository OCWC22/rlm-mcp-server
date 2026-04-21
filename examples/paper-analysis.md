# Example: long paper deep dive

This walkthrough simulates a long-form analysis pass on a research paper text (for example, the RLM paper text exported to `.txt`).

## Goal

Answer: *"What does the paper claim about why recursive decomposition helps, and where are the limits?"*

## 1) Load the paper text

```json
{"tool":"rlm_init","args":{"path":"/tmp/recursive-language-models.txt","session_id":"paper_case"}}
```

Mock result:

```json
{"session_id":"paper_case","chars":412388,"path":"/tmp/recursive-language-models.txt"}
```

## 2) Grep for topic anchors

```json
{"tool":"rlm_grep","args":{"session_id":"paper_case","pattern":"invariant|limitation|negative results|ablation|recursion|latency|FINAL\\(\\)","max_matches":80,"window":220,"case_insensitive":true}}
```

Mock findings include references in §2, §4 observations, and limitation notes in later sections.

Why: anchor terms create a coverage map before deeper reading.

## 3) Build section-aware plan in `rlm_exec`

```json
{
  "tool":"rlm_exec",
  "args":{
    "session_id":"paper_case",
    "code":"import re\nheaders = list(re.finditer(r'(?m)^\\s*(\\d+(?:\\.\\d+)*)\\s+[A-Z].+$', content))\nprint('header_count', len(headers))\nfor m in headers[:12]:\n    print(m.group(0)[:100])\nadd_buffer(f'Identified {len(headers)} numbered section headers')"
  }
}
```

Mock output reports numbered sections plus early header preview.

Why: section scaffolding improves targeted sub-query quality.

## 4) Section-by-section recursive extraction

For each key section span, issue focused sub-queries:

```json
{"tool":"rlm_sub_query","args":{"session_id":"paper_case","max_tokens":1100,"prompt":"From section 4 only: summarize empirical evidence for recursive decomposition gains, including benchmark context and caveats."}}
```

```json
{"tool":"rlm_sub_query","args":{"session_id":"paper_case","max_tokens":1100,"prompt":"From limitation discussion only: list constraints that prevent immediate production use."}}
```

Mock extracted structure:

- Claimed gains come from decomposition + persistent external context, especially for long-context tasks.
- Limits include recursion depth, async fan-out complexity, and final-answer termination brittleness.

## 5) Capture traceable synthesis

```json
{"tool":"rlm_add_buffer","args":{"session_id":"paper_case","text":"Evidence split captured: confirmed gains vs acknowledged limitations."}}
```

```json
{"tool":"rlm_get_buffers","args":{"session_id":"paper_case"}}
```

Final answer style (host model):

1. **Confirmed by text:** decomposition reduces context pressure and improves task decomposition fidelity.
2. **Inferred from text:** performance wins depend on host model coding/planning strength.
3. **Open questions:** asynchronous recursion and robust finalization semantics for real deployments.

---

### Practical notes

- If paper text is huge, use `rlm_chunk_indices` first to plan deterministic section windows.
- Keep each sub-query scoped to one section to reduce blended hallucinations.
