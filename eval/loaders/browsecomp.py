"""BrowseComp loader stub.

Paper reference (§3.1): https://arxiv.org/abs/2512.24601
Reference implementation: https://github.com/alexzhang13/rlm

Expected task shape:
    {"task_id", "query", "context", "gold", "metadata"}
"""

from __future__ import annotations

from typing import Any


BROWSECOMP_DATASET_URL = "https://github.com/alexzhang13/rlm"


def load_tasks(*args: Any, **kwargs: Any):
    _ = (args, kwargs)
    raise NotImplementedError("BrowseComp loader not bundled; see eval/README.md for setup")
