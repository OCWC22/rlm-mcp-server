"""Reusable DSPy signatures for composing the local RLM MCP module."""

try:
    import dspy
except Exception:
    dspy = None


if dspy is not None:

    class RLMAnswer(dspy.Signature):
        """Answer a question from a corpus path via RLM MCP orchestration."""

        question: str = dspy.InputField(desc="Question to answer from the corpus")
        corpus_path: str = dspy.InputField(desc="Absolute path to corpus text")
        answer: str = dspy.OutputField(desc="Grounded synthesized answer")
        citations: list[str] = dspy.OutputField(
            desc="Evidence spans as path:start-end strings"
        )


    class RLMChunkQuery(dspy.Signature):
        """Extract chunk-local evidence for one question."""

        question: str = dspy.InputField(desc="Question being answered")
        chunk: str = dspy.InputField(desc="Candidate chunk text")
        extracted: str = dspy.OutputField(desc="Relevant extracted evidence")
        hit: bool = dspy.OutputField(desc="Whether the chunk contains useful evidence")

else:

    class RLMAnswer:
        """Fallback placeholder when DSPy is unavailable."""


    class RLMChunkQuery:
        """Fallback placeholder when DSPy is unavailable."""
