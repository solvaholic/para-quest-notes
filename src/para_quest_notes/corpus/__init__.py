"""Synthetic corpus / sample vault generator.

Produces realistic-looking PARA + Quest markdown vaults for testing,
demos, and eval fixtures. Reproducible (seed-controlled). No Ollama
dependency — uses Faker for prose.

Public API: :func:`generate_vault`. CLI entry point lives in
``__main__``.
"""

from para_quest_notes.corpus.generate import (
    DEFAULT_COUNTS,
    GenerateOptions,
    GenerateResult,
    generate_vault,
)
from para_quest_notes.corpus.seeds import Seeds, load_seeds
from para_quest_notes.corpus.shapes import (
    FrontmatterKind,
    LocationKind,
    Quirk,
    Shape,
)

__all__ = [
    "DEFAULT_COUNTS",
    "FrontmatterKind",
    "GenerateOptions",
    "GenerateResult",
    "LocationKind",
    "Quirk",
    "Seeds",
    "Shape",
    "generate_vault",
    "load_seeds",
]
