"""para-quest-notes: local PARA + Quest notes workflows powered by Ollama."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("para-quest-notes")
except PackageNotFoundError:  # pragma: no cover - only when running uninstalled
    __version__ = "0+unknown"

__all__ = ["__version__"]
