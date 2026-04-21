"""Evaluation harness package for rlm-mcp-server."""

__all__ = ["run_eval"]


def run_eval(*args, **kwargs):
    from .harness import run_eval as _run_eval

    return _run_eval(*args, **kwargs)
