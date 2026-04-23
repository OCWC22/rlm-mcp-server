# dspy_rlm

`dspy_rlm` provides a composable DSPy module that wraps **this repository's MCP server** (`run_server.sh` + `rlm_mcp.py`).

> This is **not** DSPy's built-in `dspy.RLM` (which uses a Pyodide runtime). `RLMModule` orchestrates our local MCP toolchain: `rlm_init`, `rlm_peek`, `rlm_grep`, `rlm_exec`, and `rlm_get_buffers`.

## Quick start

```python
import dspy
from dspy_rlm import RLMModule, RLMAnswer

# Configure your outer task LM first.
dspy.configure(lm=dspy.LM("openrouter/openai/gpt-5-mini"))

module = RLMModule(signature=RLMAnswer)
out = module(
    question="Which MFMA variants are listed for this section?",
    corpus_path="/absolute/path/to/corpus.txt",
)
print(out.answer)
print(out.citations)
```

## Composition pattern

Use `RLMModule` as a drop-in sub-module inside larger DSPy programs:

```python
import dspy
from dspy_rlm import RLMModule

class KernelQuery(dspy.Signature):
    question: str = dspy.InputField()
    corpus_path: str = dspy.InputField()
    answer: str = dspy.OutputField()
    citations: list[str] = dspy.OutputField()

class AnalyzeKernel(dspy.Signature):
    prompt: str = dspy.InputField()
    question: str = dspy.OutputField()

kernel_research_agent = dspy.ChainOfThought(AnalyzeKernel) >> RLMModule(signature=KernelQuery)
```

## Notes

- Default timeout is `420` seconds to match the benchmark quadratic budget.
- If MCP `llm_query` enters callback mode, `RLMModule` bridges prompts back through the configured DSPy LM.
- If DSPy is unavailable, constructing `RLMModule` raises a clear installation message.

## Credits

Compositional wrapping pattern inspired by:
- `dspy-agent-skills/skills/dspy-rlm-module/SKILL.md`
