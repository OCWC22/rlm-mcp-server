"""LongBench loader stub.

Paper reference (§3.1): https://arxiv.org/abs/2512.24601
Upstream benchmark info: https://github.com/THUDM/LongBench

Expected task shape:
    {"task_id", "query", "context", "gold", "metadata"}
"""

from __future__ import annotations

from typing import Any


LONGBENCH_DATASET_URL = "https://github.com/THUDM/LongBench"


def load_tasks(*args: Any, **kwargs: Any):
    _ = (args, kwargs)
    raise NotImplementedError("LongBench loader not bundled; see eval/README.md for setup")
