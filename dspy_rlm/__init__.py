"""Composable DSPy wrapper around the local RLM MCP server."""

from .module import RLMModule
from .signatures import RLMAnswer

__all__ = ["RLMModule", "RLMAnswer"]
