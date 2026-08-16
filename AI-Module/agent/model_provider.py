"""ModelProvider abstraction -- stepwise interface.

The agent core (agent.py) never talks to a specific model API directly --
only through this interface. Swapping a local model, a remote provider, or
a Saudi/enterprise-hosted model for the underlying reasoning never requires
touching agent.py, broker_client.py, conversation.py, or the protocol.

    Tuwaiq AI
       |
       +-- ModelProvider (this file's interface)
       |      |
       |      +-- RuleBasedProvider   (default here: no external deps,
       |      |                        deterministic, used by tests/CLI
       |      |                        default until a real model lands)
       |      +-- LocalModelProvider  (NOT implemented here -- out of
       |      |                        scope for this piece of work; see
       |      |                        architecture.md's "Model provider"
       |      |                        section for the intended shape)
       |      +-- RemoteModelProvider (also not implemented here)
       |
       +-- BrokerClient -> Rust broker

Stepwise design: `step()` is called up to `Agent.MAX_STEPS` times per user
turn (see agent.py), each time seeing everything decided/observed so far
this turn via `conversation.current_turn_steps`. This is what lets a
question like "why is my computer slow" chain multiple tool calls (memory,
then processes) before answering, instead of being limited to exactly one
tool per user message.

`RuleBasedProvider` is intentionally simple (keyword/intent matching plus
one pronoun-resolution rule), not a stand-in for real natural-language
understanding -- it exists so the *agent loop, confirmation gate, and
conversation context* can be built and tested end to end before a real
model is wired in. Swapping it for a real provider changes zero lines
outside this file.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from conversation import Conversation


@dataclass
class Step:
    """One decision from the model within a single turn's reasoning loop."""

    kind: Literal["tool_call", "final_answer"]
    # Present when kind == "tool_call":
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    # Present when kind == "final_answer":
    text: str | None = None


class ModelProvider(ABC):
    """Interface every model backend implements. One responsibility:
    given the conversation so far (including this turn's tool results up
    to now), decide the next step -- call one more tool, or give a final
    answer. The provider never touches the broker, the OS, or the
    protocol wire format directly.
    """

    @abstractmethod
    def step(self, user_message: str, conversation: Conversation) -> Step:
        """Decide the next step for the turn currently being handled.
        Called once before any tool call (with `current_turn_steps`
        empty), then again after each tool result, until it returns a
        `final_answer` step or `Agent.MAX_STEPS` is reached."""

    @abstractmethod
    def describe_sensitive_action(self, tool: str, arguments: dict[str, Any]) -> str:
        """Produce the natural-language description shown to the user
        *before* a sensitive action executes (see agent.py's
        SENSITIVE_TOOLS gate). Deliberately a separate, narrow method
        rather than folded into `step()`'s free-form reasoning: the
        confirmation text is safety-relevant and benefits from staying
        simple and predictable rather than emerging from open-ended model
        output."""


class RuleBasedProvider(ModelProvider):
    """Deterministic, dependency-free provider. See module docstring."""

    _PERFORMANCE_PATTERNS = [
        r"\bslow\b", r"\bperformance\b", r"how.*(computer|system|pc).*doing",
        r"\bram\b", r"\bmemory\b", r"\bcpu\b",
    ]
    _DISK_PATTERNS = [r"\bdisk\b", r"\bstorage\b", r"\bspace\b"]
    _PROCESS_PATTERNS = [r"\bprocess(es)?\b", r"what.*running", r"consum(ing|es)", r"top program"]
    _NETWORK_PATTERNS = [r"\bnetwork\b", r"\binternet\b", r"\bwifi\b", r"\bconnection\b"]
    _LAUNCH_PATTERNS = [r"\bopen\b", r"\blaunch\b", r"\bstart\b"]
    _CLOSE_PATTERNS = [r"\bclose\b", r"\bkill\b", r"\bstop\b", r"\bend\b"]
    _PRONOUN_PATTERNS = [r"\bit\b", r"\bthat\b", r"\bthis one\b", r"\bthe top one\b"]

    _APP_ALIASES = {
        "firefox": "firefox",
        "vscode": "vscode",
        "vs code": "vscode",
        "code": "vscode",
        "terminal": "terminal",
        "konsole": "terminal",
        "file manager": "file_manager",
        "files": "file_manager",
        "dolphin": "file_manager",
    }

    def step(self, user_message: str, conversation: Conversation) -> Step:
        text = user_message.lower().strip()
        already_called = {s.tool for s in conversation.current_turn_steps}

        # --- Close/kill a process, including pronoun resolution ---
        if any(re.search(p, text) for p in self._CLOSE_PATTERNS):
            pid = self._resolve_target_pid(text, conversation)
            if pid is not None:
                return Step(kind="tool_call", tool="kill_process", arguments={"pid": pid})
            return Step(
                kind="final_answer",
                text="Which process would you like me to close? You can ask me to list processes first.",
            )

        # --- Launch an application ---
        launch_app = self._match_launch(text)
        if launch_app is not None:
            return Step(kind="tool_call", tool="launch_application", arguments={"app_id": launch_app})

        # --- Process listing ---
        if any(re.search(p, text) for p in self._PROCESS_PATTERNS):
            if "list_processes" not in already_called:
                return Step(kind="tool_call", tool="list_processes")
            return Step(kind="final_answer", text=self._explain_processes(conversation))

        # --- Network ---
        if any(re.search(p, text) for p in self._NETWORK_PATTERNS):
            if "get_network_status" not in already_called:
                return Step(kind="tool_call", tool="get_network_status")
            return Step(kind="final_answer", text=self._explain_network(conversation))

        # --- Disk ---
        if any(re.search(p, text) for p in self._DISK_PATTERNS):
            if "get_disk_info" not in already_called:
                return Step(kind="tool_call", tool="get_disk_info")
            return Step(kind="final_answer", text=self._explain_disk(conversation))

        # --- General performance ("why is my computer slow") ---
        # Chains up to two tool calls in one turn -- memory first, then
        # processes -- before answering, demonstrating the multi-step loop
        # rather than being limited to a single tool per turn.
        if any(re.search(p, text) for p in self._PERFORMANCE_PATTERNS):
            if "get_memory_info" not in already_called:
                return Step(kind="tool_call", tool="get_memory_info")
            memory_result = self._last_result(conversation, "get_memory_info")
            if memory_result and memory_result.get("used_percent", 0) > 70 and "list_processes" not in already_called:
                return Step(kind="tool_call", tool="list_processes")
            return Step(kind="final_answer", text=self._explain_performance(conversation))

        if any(re.search(p, text) for p in self._PRONOUN_PATTERNS) and conversation.top_process():
            top = conversation.top_process()
            return Step(
                kind="final_answer",
                text=f"You mean {top['name']} (pid {top['pid']}, {top['cpu_percent']:.1f}% CPU)? "
                "Say 'close it' if you'd like me to close it.",
            )

        if "system" in text or "hostname" in text or "kernel" in text or "uptime" in text:
            if "get_system_info" not in already_called:
                return Step(kind="tool_call", tool="get_system_info")
            return Step(kind="final_answer", text=self._explain_system(conversation))

        return Step(
            kind="final_answer",
            text=(
                "I can check your system info, CPU, memory, disk, running processes, "
                "network status, or open/close an approved application. What would you like to know?"
            ),
        )

    def describe_sensitive_action(self, tool: str, arguments: dict[str, Any]) -> str:
        if tool == "kill_process":
            return f"This will close process pid {arguments.get('pid')}. Proceed?"
        return f"This will run '{tool}' with {arguments}. Proceed?"

    # --- helpers -----------------------------------------------------

    def _resolve_target_pid(self, text: str, conversation: Conversation) -> int | None:
        explicit_pid = re.search(r"\bpid\s+(\d+)\b", text)
        if explicit_pid:
            return int(explicit_pid.group(1))
        if any(re.search(p, text) for p in self._PRONOUN_PATTERNS) or "top" in text:
            top = conversation.top_process()
            if top:
                return int(top["pid"])
        return None

    def _match_launch(self, text: str) -> str | None:
        if not any(re.search(p, text) for p in self._LAUNCH_PATTERNS):
            return None
        for alias, app_id in self._APP_ALIASES.items():
            if alias in text:
                return app_id
        return None

    def _last_result(self, conversation: Conversation, tool: str) -> dict[str, Any] | None:
        for record in reversed(conversation.current_turn_steps):
            if record.tool == tool and record.ok:
                return record.result
        return None

    def _explain_performance(self, conversation: Conversation) -> str:
        mem = self._last_result(conversation, "get_memory_info")
        if not mem:
            return "I wasn't able to read memory info."
        pct = mem.get("used_percent", 0)
        parts = [f"Memory usage is at {pct:.1f}%."]
        procs = self._last_result(conversation, "list_processes")
        if procs and procs.get("processes"):
            top = procs["processes"][0]
            parts.append(f"The top consumer right now is {top['name']} ({top['cpu_percent']:.1f}% CPU).")
        return " ".join(parts)

    def _explain_processes(self, conversation: Conversation) -> str:
        result = self._last_result(conversation, "list_processes")
        if not result or not result.get("processes"):
            return "No process data available."
        top = result["processes"][:3]
        names = ", ".join(f"{p['name']} ({p['cpu_percent']:.1f}% CPU)" for p in top)
        return f"Top processes right now: {names}."

    def _explain_network(self, conversation: Conversation) -> str:
        result = self._last_result(conversation, "get_network_status")
        if not result or not result.get("interfaces"):
            return "No network interfaces found."
        lines = [
            f"{i['name']} ({'up' if i['is_up'] else 'down'}): "
            f"{i['rx_kbps']:.1f} KB/s in, {i['tx_kbps']:.1f} KB/s out"
            for i in result["interfaces"]
        ]
        return "Network status — " + "; ".join(lines)

    def _explain_disk(self, conversation: Conversation) -> str:
        result = self._last_result(conversation, "get_disk_info")
        if not result or not result.get("volumes"):
            return "No disk volumes found."
        lines = [f"{v['mount_point']}: {v['used_percent']:.1f}% used" for v in result["volumes"]]
        return "Disk usage — " + "; ".join(lines)

    def _explain_system(self, conversation: Conversation) -> str:
        result = self._last_result(conversation, "get_system_info")
        if not result:
            return "No system info available."
        return (
            f"You're running {result['os_name']} {result['os_version']} "
            f"(kernel {result['kernel_version']}) on host '{result['hostname']}', "
            f"up for {result['uptime_seconds']} seconds."
        )
