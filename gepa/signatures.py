from __future__ import annotations

TOOL_DESCRIPTIONS_TEMPLATE = """\
rlm_init: Load a file into session memory.
rlm_status: Show session stats.
rlm_peek: Slice context text by range.
rlm_grep: Regex search snippets in context.
rlm_chunk_indices: Compute chunk boundaries.
rlm_write_chunks: Materialize chunk files.
rlm_add_buffer: Append a scratch note.
rlm_get_buffers: Read scratch notes.
rlm_clear_buffers: Clear scratch notes.
rlm_exec: Execute persistent Python over session state.
rlm_sub_query: Ask sub-LLM (sampling-first, callback fallback).
rlm_sub_query_result: Provide callback sub-query results.
rlm_reset: Delete a session state file.
rlm_list_sessions: List active sessions.
"""

try:
    import dspy as _dspy
except Exception:
    _dspy = None


if _dspy is not None:

    class RLMToolSelection(_dspy.Signature):
        """Given query+context metadata, choose the most useful first RLM tool."""

        query: str = _dspy.InputField()
        context_length: int = _dspy.InputField()
        tool_descriptions: str = _dspy.InputField()
        first_tool: str = _dspy.OutputField()
        rationale: str = _dspy.OutputField(desc="why")

else:

    class RLMToolSelection:  # pragma: no cover - fallback stub
        """Placeholder used when dspy is not installed."""



def make_student_module():
    if _dspy is None:
        raise RuntimeError("dspy is not installed. Install optional extra: pip install 'rlm-repl-mcp[gepa]'")
    return _dspy.ChainOfThought(RLMToolSelection)
