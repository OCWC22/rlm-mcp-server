"""Shared DSPy LM helpers for benchmark domains.

Set `RLM_TASK_LM` and `RLM_REFLECTION_LM` to control model selection.
"""

import os
from typing import Optional

TASK_ENV = "RLM_TASK_LM"
REFLECTION_ENV = "RLM_REFLECTION_LM"
TASK_DEFAULT = "openrouter/openai/gpt-5-mini"
REFLECTION_DEFAULT = "openrouter/openai/gpt-5.4"


def _resolve_model(env_name: str, default: str) -> str:
    value = os.getenv(env_name, "").strip()
    return value or default


def task_lm(model: Optional[str] = None, **overrides):
    """Return the task LM configured from explicit arg, env, or default."""
    import dspy

    chosen = model or _resolve_model(TASK_ENV, TASK_DEFAULT)
    return dspy.LM(
        chosen,
        temperature=overrides.pop("temperature", 0.0),
        max_tokens=overrides.pop("max_tokens", 2000),
        **overrides,
    )


def reflection_lm(model: Optional[str] = None, **overrides):
    """Return GEPA reflection LM configured from explicit arg, env, or default."""
    import dspy

    chosen = model or _resolve_model(REFLECTION_ENV, REFLECTION_DEFAULT)
    return dspy.LM(
        chosen,
        temperature=overrides.pop("temperature", 1.0),
        max_tokens=overrides.pop("max_tokens", 8000),
        **overrides,
    )
