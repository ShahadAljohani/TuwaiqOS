"""Agent core: the orchestration layer between a ModelProvider and the
BrokerClient.

Security-relevant invariant this file exists to enforce: **this file never
calls subprocess, os.system, os.exec*, or anything else that touches the OS
directly.** The only way anything in this process can affect the outside
world is `self._broker.call(tool, arguments)`, and `tool` is checked against
`KNOWN_TOOLS` before that call is ever made -- so even if a model provider
hallucinated an arbitrary tool name or a shell-command-shaped string, it is
rejected here, in Python, before it would even reach the broker (which
independently re-validates it again on the Rust side -- two layers,
deliberately, not one; see architecture.md's "Defense in depth").

Two other invariants specific to this redesign:

1. **Bounded reasoning.** A single user turn calls `model.step()` at most
   `MAX_STEPS` times before this file forces a stop and returns whatever
   answer it can, rather than trusting the model to always terminate the
   loop itself. A model that never emits `final_answer` cannot hang the
   agent or spam the broker indefinitely.

2. **Sensitive actions never execute on the same turn they were requested.**
   `SENSITIVE_TOOLS` lists tools this file will *describe* to the user but
   will not call the broker for until the user's *next* message is an
   explicit affirmative. Confirmation wording is produced deterministically
   by `ModelProvider.describe_sensitive_action()`, not free-form model
   output, and whether a tool is sensitive at all is decided here, in this
   file's fixed set -- not by anything the model itself claims.
"""

from __future__ import annotations

import logging

from broker_client import BrokerClient, BrokerUnavailableError
from conversation import Conversation, PendingConfirmation, ToolCallRecord
from model_provider import ModelProvider, Step
from protocol import KNOWN_TOOLS

logger = logging.getLogger("tuwaiq_agent.agent")

MAX_STEPS = 5

# Tools that change system state and therefore require an explicit user
# confirmation on a separate turn before the broker is ever called. This
# set is intentionally small, hand-maintained, and independent of anything
# the model or broker themselves claim about a tool's sensitivity.
SENSITIVE_TOOLS = frozenset({"kill_process", "close_application"})

_AFFIRMATIVE = {"yes", "y", "confirm", "proceed", "ok", "okay", "نعم", "أيوه", "تمام"}
_NEGATIVE = {"no", "n", "cancel", "stop", "لا", "الغاء", "إلغاء"}


class Agent:
    def __init__(self, model: ModelProvider, broker: BrokerClient):
        self._model = model
        self._broker = broker
        self._conversation = Conversation()

    def handle(self, user_message: str) -> str:
        if self._conversation.pending_confirmation is not None:
            response = self._handle_confirmation_reply(user_message)
            self._conversation.finish_turn(user_message, response)
            return response

        self._conversation.start_turn()
        response = self._run_reasoning_loop(user_message)
        self._conversation.finish_turn(user_message, response)
        return response

    # --- confirmation handling -----------------------------------------

    def _handle_confirmation_reply(self, user_message: str) -> str:
        pending = self._conversation.pending_confirmation
        assert pending is not None
        reply = user_message.strip().lower()

        if reply in _AFFIRMATIVE:
            self._conversation.pending_confirmation = None
            return self._execute_confirmed_action(pending)

        if reply in _NEGATIVE:
            self._conversation.pending_confirmation = None
            return "Okay, I won't do that."

        # Neither a clear yes nor no -- stay in the pending-confirmation
        # state rather than guessing, and ask again explicitly. This means
        # an ambiguous reply cannot accidentally be treated as consent.
        return f"{pending.description} (please reply yes or no)"

    def _execute_confirmed_action(self, pending: PendingConfirmation) -> str:
        try:
            response = self._broker.call(pending.tool, pending.arguments)
        except BrokerUnavailableError as e:
            logger.error("broker unavailable during confirmed action: %s", e)
            return "System tools are temporarily unavailable. Please try again shortly."

        record = ToolCallRecord(
            tool=pending.tool,
            arguments=pending.arguments,
            ok=response.ok,
            result=response.result,
            error_message=response.error_message,
        )
        self._conversation.record_tool_call(record)

        if not response.ok:
            return f"I couldn't complete that: {response.error_message}"

        # Deterministic success message, not model-generated -- confirming
        # a sensitive action actually happened is exactly the kind of
        # statement that should not depend on model phrasing.
        if pending.tool == "kill_process":
            name = (response.result or {}).get("name", "the process")
            pid = (response.result or {}).get("pid")
            return f"Closed {name} (pid {pid})."
        if pending.tool == "close_application":
            app_id = (response.result or {}).get("app_id", "the application")
            return f"Closed {app_id}."
        return f"Done: {response.result}"

    # --- main reasoning loop --------------------------------------------

    def _run_reasoning_loop(self, user_message: str) -> str:
        for step_index in range(MAX_STEPS):
            try:
                step: Step = self._model.step(user_message, self._conversation)
            except Exception:
                logger.exception("model provider raised during step %d", step_index)
                return "Sorry, I ran into a problem understanding that. Could you try again?"

            if step.kind == "final_answer":
                return step.text or ""

            result = self._handle_tool_step(step)
            if result is not None:
                # A sensitive-action confirmation prompt, or a hard stop
                # (unknown tool / broker unavailable) -- either way, the
                # turn ends here rather than continuing the loop.
                return result
            # Otherwise the tool call succeeded (or failed with an
            # ordinary, recorded error) and was appended to
            # conversation.current_turn_steps; loop again so the model can
            # see that result and decide the next step.

        logger.warning("reasoning loop hit MAX_STEPS=%d without a final_answer", MAX_STEPS)
        return "I looked into a few things but couldn't reach a clear answer. Could you rephrase your question?"

    def _handle_tool_step(self, step: Step) -> str | None:
        """Returns a string to end the turn immediately (confirmation
        prompt or hard stop), or None to let the reasoning loop continue
        with this tool's result now recorded."""
        tool = step.tool or ""

        if tool not in KNOWN_TOOLS:
            logger.warning("model requested unknown tool %r; refusing to call broker", tool)
            return "I don't have a way to do that yet."

        if tool in SENSITIVE_TOOLS:
            description = self._model.describe_sensitive_action(tool, step.arguments)
            self._conversation.pending_confirmation = PendingConfirmation(
                tool=tool, arguments=step.arguments, description=description
            )
            return description

        try:
            response = self._broker.call(tool, step.arguments)
        except BrokerUnavailableError as e:
            logger.error("broker unavailable: %s", e)
            return "System tools are temporarily unavailable. Please try again shortly."

        self._conversation.record_tool_call(
            ToolCallRecord(
                tool=tool,
                arguments=step.arguments,
                ok=response.ok,
                result=response.result,
                error_message=response.error_message,
            )
        )
        return None