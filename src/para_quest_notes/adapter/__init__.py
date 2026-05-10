"""Thin runtime that workflows sit on top of.

Phase 1 deliverable. See ``docs/PLAN.md`` for the design.
"""

from para_quest_notes.adapter.config import Config, OllamaConfig, load_config
from para_quest_notes.adapter.errors import (
    AdapterError,
    ConfigError,
    EscalateToUser,
    LLMError,
    VaultError,
)
from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.llm import LLMResponse, OllamaClient
from para_quest_notes.adapter.prompts import Prompt, PromptLoader
from para_quest_notes.adapter.step import Step, StepContext, StepResult, Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter, new_run_path
from para_quest_notes.adapter.vault import find_vault

__all__ = [
    "AdapterError",
    "Config",
    "ConfigError",
    "EscalateToUser",
    "FakeLLM",
    "LLMError",
    "LLMResponse",
    "OllamaClient",
    "OllamaConfig",
    "Prompt",
    "PromptLoader",
    "Step",
    "StepContext",
    "StepResult",
    "TraceWriter",
    "VaultError",
    "Workflow",
    "WorkflowResult",
    "find_vault",
    "load_config",
    "new_run_path",
]
