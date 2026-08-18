from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from model_profiles import ModelProfile, resolve_model_path


class LocalModelRuntime(ABC):
    """Runtime adapter for local model execution.

    Phase 1 keeps this interface intentionally small so runtime wiring can
    evolve without touching Agent orchestration.
    """

    @abstractmethod
    def decide(self, user_message: str, profile: ModelProfile) -> Any | None:
        """Return an AgentAction-compatible object or None to delegate."""

    @abstractmethod
    def explain(self, user_message: str, tool: str, result: dict[str, Any], profile: ModelProfile) -> str | None:
        """Return a natural-language explanation or None to delegate."""

    @abstractmethod
    def explain_error(
        self,
        user_message: str,
        tool: str,
        error_code: str,
        error_message: str,
        profile: ModelProfile,
    ) -> str | None:
        """Return an error explanation or None to delegate."""

    @abstractmethod
    def validate(self, profile: ModelProfile, root: Path) -> None:
        """Validate runtime prerequisites for the selected profile."""


class NoOpLocalRuntime(LocalModelRuntime):
    """Phase 1 placeholder runtime.

    Does not perform inference and never executes shell commands.
    """

    def decide(self, user_message: str, profile: ModelProfile) -> Any | None:
        return None

    def explain(self, user_message: str, tool: str, result: dict[str, Any], profile: ModelProfile) -> str | None:
        return None

    def explain_error(
        self,
        user_message: str,
        tool: str,
        error_code: str,
        error_message: str,
        profile: ModelProfile,
    ) -> str | None:
        return None

    def validate(self, profile: ModelProfile, root: Path) -> None:
        # Validation is minimal in Phase 1. Missing model files are expected
        # in development/test environments and are handled by fallback provider.
        resolve_model_path(profile, root=root)
