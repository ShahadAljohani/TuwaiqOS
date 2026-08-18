"""ModelProvider abstraction.

The agent core (agent.py) never talks to a specific model API directly --
only through this interface. Swapping a local model, a remote provider, or
(later) a Saudi/enterprise-hosted model for the underlying reasoning never
requires touching agent.py, broker_client.py, or the protocol.

    Tuwaiq AI
       |
       +-- ModelProvider (this file's interface)
       |      |
       |      +-- RuleBasedProvider   (default here: no external deps,
       |      |                        deterministic, used by tests/demo)
       |      +-- LocalModelProvider  (local Qwen profile/runtime wiring)
       |      +-- RemoteModelProvider (stub: wire up a hosted API)
       |
       +-- BrokerClient -> Rust broker

`RuleBasedProvider` exists so this whole prototype is runnable and testable
end-to-end without requiring an API key or a multi-GB local model download --
it is intentionally simple (keyword/intent matching), not a stand-in for the
real reasoning model. Swap it for `LocalModelProvider`/`RemoteModelProvider`
once the real model is wired in; nothing else in the codebase changes.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from local_model_runtime import LocalModelRuntime, LocalRuntimeError, QwenLocalRuntime
from model_profiles import ModelProfile, load_model_profile, resolve_model_path
from protocol import KNOWN_TOOLS


@dataclass
class AgentAction:
    """What the model decided to do in response to one turn."""

    kind: Literal["respond", "call_tool"]
    # Present when kind == "respond": final text to show the user directly,
    # no tool call needed (e.g. "hi", "what can you do").
    text: str | None = None
    # Present when kind == "call_tool":
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    """Interface every model backend implements. Two responsibilities only:
    decide what to do next given the conversation, and explain a tool
    result in natural language. The provider never touches the broker,
    the OS, or the protocol wire format directly -- it only ever returns
    an `AgentAction` or a string; `agent.py` does everything else.
    """

    @abstractmethod
    def decide(self, user_message: str) -> AgentAction:
        """Given the user's message, decide whether to answer directly or
        call exactly one tool. Phase 1 is single-tool-per-turn by design --
        multi-step planning is out of scope until the protocol/broker
        support has been exercised enough to trust it."""

    @abstractmethod
    def explain(self, user_message: str, tool: str, result: dict[str, Any]) -> str:
        """Turn a successful tool result into a natural-language answer for
        the user."""

    @abstractmethod
    def explain_error(self, user_message: str, tool: str, error_code: str, error_message: str) -> str:
        """Turn a tool error into an honest, non-technical explanation for
        the user -- never expose raw error codes or internals to them
        directly; that's what the audit log and logger are for."""


class LocalModelProvider(ModelProvider):
    """Local-model provider for Qwen runtime integration.

    Keeps agent architecture model-agnostic while preserving a deterministic
    fallback path for tool-routing and tests.
    """

    def __init__(
        self,
        profile: str | ModelProfile = "default",
        runtime: LocalModelRuntime | None = None,
        fallback: ModelProvider | None = None,
        require_model_file: bool = False,
    ) -> None:
        self.profile = load_model_profile(profile)
        self.runtime = runtime or QwenLocalRuntime()
        self._fallback = fallback or RuleBasedProvider()
        self._repo_root = Path(__file__).resolve().parent.parent
        self.runtime.validate(self.profile, root=self._repo_root)
        if require_model_file:
            model_path = resolve_model_path(self.profile, self._repo_root)
            if not model_path.exists():
                raise ValueError(f"model file does not exist: {model_path}")

    def initialize(self) -> None:
        self.runtime.initialize(self.profile, root=self._repo_root)

    def shutdown(self) -> None:
        self.runtime.shutdown()

    def telemetry(self) -> dict[str, Any]:
        return self.runtime.telemetry()

    def decide(self, user_message: str) -> AgentAction:
        # Phase 3: try the Qwen runtime first -- it may emit a structured
        # tool call or a natural-language response.  Fall back to the
        # rule-based provider only when the runtime is unavailable or fails.
        try:
            action = self.runtime.decide(user_message=user_message, profile=self.profile)
        except LocalRuntimeError:
            action = None

        if action is not None:
            return action

        return self._fallback.decide(user_message)

    def explain(self, user_message: str, tool: str, result: dict[str, Any]) -> str:
        try:
            explanation = self.runtime.explain(
                user_message=user_message,
                tool=tool,
                result=result,
                profile=self.profile,
            )
        except LocalRuntimeError:
            explanation = None
        if explanation is not None:
            return explanation
        return self._fallback.explain(user_message, tool, result)

    def explain_error(self, user_message: str, tool: str, error_code: str, error_message: str) -> str:
        try:
            explanation = self.runtime.explain_error(
                user_message=user_message,
                tool=tool,
                error_code=error_code,
                error_message=error_message,
                profile=self.profile,
            )
        except LocalRuntimeError:
            explanation = None
        if explanation is not None:
            return explanation
        return self._fallback.explain_error(user_message, tool, error_code, error_message)


class RuleBasedProvider(ModelProvider):
    """Deterministic, dependency-free provider used as the default so the
    whole system runs without an API key or a local model file. Intent
    matching here is intentionally simple pattern matching, not a
    real language model -- replace with LocalModelProvider or
    RemoteModelProvider for actual natural-language understanding.
    """

    _PERFORMANCE_PATTERNS = [
        r"\bslow\b", r"\bperformance\b", r"how.*(computer|system|pc).*doing",
        r"\bram\b", r"\bmemory\b", r"\bcpu\b", r"\bdisk\b", r"\bstorage\b",
        r"\bspace\b",
    ]
    _PROCESS_PATTERNS = [r"\bprocess(es)?\b", r"what.*running", r"consum(ing|es)"]
    _LAUNCH_PATTERNS = [r"\bopen\b", r"\blaunch\b", r"\bstart\b"]

    # Maps free-text app mentions to the broker's allowlisted app_ids. This
    # is a UX convenience mapping only -- the broker independently enforces
    # its own allowlist regardless of what is sent here, so an unmapped or
    # incorrectly mapped name still cannot launch anything unapproved.
    _APP_ALIASES = {
        "firefox": "firefox",
        "vscode": "vscode",
        "vs code": "vscode",
        "code": "vscode",
        "terminal": "terminal",
        "file manager": "file_manager",
        "files": "file_manager",
    }

    def decide(self, user_message: str) -> AgentAction:
        text = user_message.lower().strip()

        launch_match = self._match_launch(text)
        if launch_match is not None:
            return AgentAction(kind="call_tool", tool="launch_application", arguments={"app_id": launch_match})

        if any(re.search(p, text) for p in self._PROCESS_PATTERNS):
            return AgentAction(kind="call_tool", tool="list_processes")

        if any(re.search(p, text) for p in self._PERFORMANCE_PATTERNS):
            # A general "how's my computer doing" needs more than one
            # signal; Phase 1 keeps the model to one tool call per turn, so
            # this starts with memory (usually the most actionable single
            # signal for "why is it slow") -- see architecture.md's
            # "Multi-tool turns" section for why chaining is deferred.
            if "disk" in text or "space" in text or "storage" in text:
                return AgentAction(kind="call_tool", tool="get_disk_info")
            if "cpu" in text or "processor" in text:
                return AgentAction(kind="call_tool", tool="get_cpu_info")
            return AgentAction(kind="call_tool", tool="get_memory_info")

        if "system" in text or "hostname" in text or "kernel" in text or "uptime" in text:
            return AgentAction(kind="call_tool", tool="get_system_info")

        return AgentAction(
            kind="respond",
            text=(
                "I can check your system info, CPU, memory, disk, running processes, "
                "or open an approved application (Firefox, VS Code, Terminal, File Manager). "
                "What would you like to know?"
            ),
        )

    def _match_launch(self, text: str) -> str | None:
        if not any(re.search(p, text) for p in self._LAUNCH_PATTERNS):
            return None
        for alias, app_id in self._APP_ALIASES.items():
            if alias in text:
                return app_id
        return None

    def explain(self, user_message: str, tool: str, result: dict[str, Any]) -> str:
        if tool == "get_memory_info":
            top = result.get("top_consumers") or []
            top_line = ""
            if top:
                first = top[0]
                gb = first["bytes"] / (1024 ** 3)
                top_line = f" The biggest consumer is {first['name']} at {gb:.1f} GB."
            return f"Memory usage is at {result['used_percent']:.1f}%.{top_line}"

        if tool == "get_cpu_info":
            return f"CPU usage is currently {result['usage_percent']:.1f}% across {result['core_count']} cores."

        if tool == "get_disk_info":
            lines = [
                f"{v['mount_point']}: {v['used_percent']:.1f}% used"
                for v in result.get("volumes", [])
            ]
            return "Disk usage — " + "; ".join(lines) if lines else "No disk volumes found."

        if tool == "list_processes":
            top = result.get("processes", [])[:3]
            names = ", ".join(f"{p['name']} ({p['cpu_percent']:.1f}% CPU)" for p in top)
            return f"Top processes right now: {names}." if names else "No process data available."

        if tool == "get_system_info":
            return (
                f"You're running {result['os_name']} {result['os_version']} "
                f"(kernel {result['kernel_version']}) on host '{result['hostname']}', "
                f"up for {result['uptime_seconds']} seconds."
            )

        if tool == "launch_application":
            return f"Opened {result['app_id']} (pid {result['pid']})."

        return f"Done: {result}"

    def explain_error(self, user_message: str, tool: str, error_code: str, error_message: str) -> str:
        if error_code == "not_allowlisted":
            return (
                "I can only open a small set of approved applications "
                "(Firefox, VS Code, Terminal, File Manager) — that app isn't one of them."
            )
        if error_code == "invalid_arguments":
            return "I wasn't able to form a valid request for that — could you rephrase?"
        if error_code == "internal_error":
            return "Something went wrong talking to the system tools. Please try again in a moment."
        return f"I couldn't complete that: {error_message}"
