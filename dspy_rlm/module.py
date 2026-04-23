"""DSPy module that wraps the local RLM MCP server orchestration flow."""

import json
import re
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import dspy
except Exception as exc:
    dspy = None
    _DSPY_IMPORT_ERROR = exc
else:
    _DSPY_IMPORT_ERROR = None

from .signatures import RLMAnswer

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "what",
    "which",
    "with",
}


class _ModuleBase:
    pass


if dspy is not None:
    _ModuleBase = dspy.Module


def _load_anyio():
    try:
        import anyio
    except Exception as exc:
        raise RuntimeError(
            "RLMModule requires `anyio` (installed with this repo's base dependencies). "
            "Install project dependencies before using the module."
        ) from exc
    return anyio


def _load_mcp_client_class():
    try:
        from eval.runners.mcp_client import MCPClient
    except Exception:
        from eval.runners.mcp_client import MCPToolClient as MCPClient
    return MCPClient


class RLMModule(_ModuleBase):
    """Composable DSPy module that runs Appendix C.1-style RLM MCP orchestration."""

    def __init__(
        self,
        signature=RLMAnswer,
        session_prefix: str = "dspy-rlm",
        timeout_seconds: float = 420,
    ):
        if dspy is None:
            raise RuntimeError(
                "RLMModule requires optional dependency `dspy-ai>=3.2,<3.3`. "
                "Install with `pip install .[dspy]` or `pip install .[gepa]`."
            ) from _DSPY_IMPORT_ERROR

        super().__init__()
        self.signature = signature
        self.session_prefix = (session_prefix or "dspy-rlm").strip() or "dspy-rlm"
        self.timeout_seconds = float(timeout_seconds)
        self._callback_predictor = dspy.Predict("prompt -> response")

        self._repo_root = Path(__file__).resolve().parents[1]
        self._run_server = self._repo_root / "run_server.sh"

    def forward(self, *, question: str, corpus_path: str):
        """Run MCP orchestration for one question and return answer+citation spans."""
        anyio = _load_anyio()
        try:
            answer, citations = anyio.run(self._forward_async, question, corpus_path)
            return dspy.Prediction(answer=answer, citations=citations)
        except Exception as exc:
            return dspy.Prediction(
                answer=f"RLMModule error: {exc}",
                citations=[],
            )

    async def _forward_async(self, question: str, corpus_path: str) -> tuple[str, list[str]]:
        corpus = Path(corpus_path).expanduser().resolve()
        if not corpus.exists():
            raise FileNotFoundError(f"corpus_path does not exist: {corpus}")

        session_id = self._make_session_id()
        grep_pattern = self._build_grep_pattern(question)

        mcp_client_cls = _load_mcp_client_class()

        async with mcp_client_cls(
            command="/bin/bash",
            args=[str(self._run_server)],
            cwd=str(self._repo_root),
            timeout_seconds=self.timeout_seconds,
            env={"RLM_TRACE_DISABLE": "1"},
        ) as client:
            await client.call_tool(
                "rlm_init",
                {"path": str(corpus), "session_id": session_id},
            )
            await client.call_tool(
                "rlm_peek",
                {"start": 0, "end": 2000, "session_id": session_id},
            )

            grep_hits = await client.call_tool(
                "rlm_grep",
                {
                    "pattern": grep_pattern,
                    "max_matches": 40,
                    "window": 240,
                    "case_insensitive": True,
                    "session_id": session_id,
                },
            )

            loop_code = self._build_chunk_exec_code(question=question, pattern=grep_pattern)
            await self._run_exec_with_callback_bridge(
                client=client,
                session_id=session_id,
                code=loop_code,
            )

            buffers = await client.call_tool("rlm_get_buffers", {"session_id": session_id})
            synth_code = self._build_synthesis_exec_code(question=question, buffers=buffers)
            synth_result = await self._run_exec_with_callback_bridge(
                client=client,
                session_id=session_id,
                code=synth_code,
            )

        answer = self._extract_answer(synth_result)
        citations = self._extract_citations(corpus, grep_hits)
        return answer, citations

    def _make_session_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = uuid.uuid4().hex[:8]
        return f"{self.session_prefix}-{stamp}-{suffix}"

    def _build_grep_pattern(self, question: str) -> str:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", question.lower())
        deduped: list[str] = []
        for token in tokens:
            if token in _STOPWORDS or token in deduped:
                continue
            deduped.append(token)

        if not deduped:
            trimmed = question.strip()
            return re.escape(trimmed[:40]) if trimmed else r"[A-Za-z0-9_]+"

        return "|".join(re.escape(token) for token in deduped[:10])

    def _build_chunk_exec_code(self, *, question: str, pattern: str) -> str:
        return textwrap.dedent(
            f"""
            question = {json.dumps(question)}
            pattern = {json.dumps(pattern)}

            hits = grep(pattern, max_matches=40, window=240, case_insensitive=True)
            if not hits:
                add_buffer("No grep hits for pattern: " + pattern)

            for i, hit in enumerate(hits, start=1):
                start, end = hit["span"]
                chunk = content[max(0, start - 500):min(len(content), end + 2000)]
                extracted = llm_query(
                    f"Question: {{question}}\\n\\n"
                    "Extract every fact from this excerpt that helps answer the question. "
                    "Keep details and qualifiers.\\n\\n"
                    f"Excerpt {{i}}/{{len(hits)}} (span {{start}}-{{end}}):\\n{{chunk}}",
                    max_tokens=500,
                )
                add_buffer(f"[hit {{i}} span {{start}}-{{end}}]\\n{{extracted}}")

            print(f"buffered={{len(hits)}}")
            """
        ).strip()

    def _build_synthesis_exec_code(self, *, question: str, buffers: Any) -> str:
        if not isinstance(buffers, list):
            buffers = []

        trimmed: list[str] = []
        for raw in buffers[:80]:
            text = str(raw).strip()
            if not text:
                continue
            if len(text) > 1600:
                text = text[:1600].rstrip() + " ..."
            trimmed.append(text)

        findings = "\n\n---\n\n".join(trimmed)

        return textwrap.dedent(
            f"""
            question = {json.dumps(question)}
            findings = {json.dumps(findings)}
            final = llm_query(
                "Synthesize a complete grounded answer to the question. "
                "Merge duplicates, keep distinct facts, and mention uncertainty if evidence is thin.\\n\\n"
                f"Question: {{question}}\\n\\n"
                f"Per-chunk findings:\\n{{findings}}",
                max_tokens=900,
            )
            print(final.strip())
            """
        ).strip()

    async def _run_exec_with_callback_bridge(
        self,
        *,
        client: Any,
        session_id: str,
        code: str,
    ) -> dict[str, Any]:
        for _ in range(40):
            result = await client.call_tool(
                "rlm_exec",
                {"code": code, "session_id": session_id},
            )

            if not isinstance(result, dict):
                return {"stdout": str(result), "stderr": ""}

            callback = result.get("callback_required")
            if not isinstance(callback, dict):
                return result

            request_id = str(callback.get("request_id", "")).strip()
            prompt = str(callback.get("prompt", "")).strip()
            if not request_id or not prompt:
                raise RuntimeError("rlm_exec callback request was missing request_id or prompt")

            callback_answer = self._resolve_callback_prompt(prompt)
            await client.call_tool(
                "rlm_sub_query_result",
                {
                    "request_id": request_id,
                    "result": callback_answer,
                    "session_id": session_id,
                },
            )

        raise RuntimeError("Exceeded callback bridge limit while running rlm_exec")

    def _resolve_callback_prompt(self, prompt: str) -> str:
        try:
            prediction = self._callback_predictor(prompt=prompt)
        except Exception as exc:
            raise RuntimeError(
                "RLM callback bridge needs a configured DSPy task LM. "
                "Call dspy.configure(lm=dspy.LM(...)) before running RLMModule."
            ) from exc

        text = str(getattr(prediction, "response", "")).strip()
        if text:
            return text

        return "No additional evidence extracted for this callback prompt."

    def _extract_answer(self, exec_result: Any) -> str:
        if isinstance(exec_result, dict):
            stdout = str(exec_result.get("stdout", "")).strip()
            stderr = str(exec_result.get("stderr", "")).strip()
        else:
            stdout = str(exec_result).strip()
            stderr = ""

        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if lines:
                return lines[-1]
            return stdout

        if stderr:
            raise RuntimeError(f"synthesis failed: {stderr[:400]}")

        return "UNKNOWN"

    def _extract_citations(self, corpus_path: Path, grep_hits: Any) -> list[str]:
        if not isinstance(grep_hits, list):
            return [f"{corpus_path}:0-2000"]

        citations: list[str] = []
        for hit in grep_hits[:12]:
            if not isinstance(hit, dict):
                continue
            span = hit.get("span")
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                continue
            try:
                start = int(span[0])
                end = int(span[1])
            except Exception:
                continue
            citations.append(f"{corpus_path}:{start}-{end}")

        if citations:
            return citations

        return [f"{corpus_path}:0-2000"]
