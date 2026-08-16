# Tuwaiq AI — Threat Model

## What this system protects against

The core assumption this design is built around: **the model (rule-based
today, an LLM later) is not fully trusted.** LLMs can be prompt-injected,
can hallucinate plausible-looking but wrong tool calls, and — unlike
traditional application code — their exact output isn't something a
developer wrote and reviewed line by line. This threat model treats the
model layer as a source of untrusted input, the same way a web backend
treats a browser's request body as untrusted, even though "the browser" is
usually just running code the same team shipped.

## Assets being protected

- **The OS itself** — process table, filesystem, running applications.
- **User trust** — the assistant must not take a destructive action the
  user didn't actually approve, and must not silently fail in a way that
  looks like success.
- **Availability** — a misbehaving model or a crashed broker must not make
  the assistant (or the OS around it) unusable.

## Threats and mitigations

### T1: Model attempts to run an arbitrary shell command
**Mitigation:** there is no tool, at any layer, that accepts a raw command
string. `ToolRequest.tool` must be one of a fixed enum
(`protocol/schema.json`); `arguments` are typed and validated per-tool.
`launch_application`'s `app_id` is looked up in a compiled-in allowlist,
never passed to a shell. Tested directly:
`launch_application_never_treats_app_id_as_a_shell_command`.

### T2: Model hallucinates or is tricked into requesting an unregistered/unknown tool
**Mitigation:** checked independently in two places (see architecture.md's
"Defense in depth") — Python's `KNOWN_TOOLS` set, and Rust's `registry.rs`
dispatch, which returns `unknown_tool` for anything not explicitly
registered. Tested:
`test_model_requesting_unknown_tool_never_reaches_broker`,
`unknown_tool_is_rejected`.

### T3: Model requests a destructive action (closing a process) without genuine user intent
**Mitigation:** `SENSITIVE_TOOLS` gate — the action is described, not
executed, and only proceeds after an explicit affirmative on a *separate*
turn. An ambiguous reply is treated as neither yes nor no. Tested:
`test_kill_process_requires_confirmation_before_broker_is_called`,
`test_ambiguous_reply_does_not_confirm_or_cancel`.

### T4: A confirmed destructive action still targets something critical
**Mitigation:** the broker enforces its own protected-process floor
(pid 1, and a small set of well-known critical process names)
*independently* of anything Python claims was confirmed. This exists
specifically because Python's confirmation is a UX safety net, not a
security boundary by itself — the broker does not trust that a
"confirmed" flag it receives (implicitly, by Python even calling the tool)
means the target was actually safe to act on. Tested:
`test_broker_independently_refuses_pid_1_even_if_confirmed`,
`kill_process_refuses_pid_1_unconditionally`.

Found during development, not hypothetical: an early version of this check
matched only by process *name* ("init", "systemd"); testing in a real
environment showed pid 1 there was named neither, and would have been
signaled. Fixed to check pid 1 unconditionally, independent of name.

### T5: The AI/model process crashes
**Mitigation:** `Agent._run_reasoning_loop` catches any exception raised
by `ModelProvider.step()` at the outermost boundary and returns a safe
message instead of propagating. The agent process itself keeps running and
remains usable for the next message. Tested:
`test_model_provider_crash_does_not_crash_agent`.

### T6: The Rust broker crashes or is killed
**Mitigation:** `BrokerClient` detects a dead subprocess (via
`Popen.poll()`) on the next call and transparently restarts it, up to
`MAX_RESTART_ATTEMPTS`. The user experiences a possible one-request delay,
not a permanently broken assistant. Tested:
`test_broker_crash_is_recovered_by_automatic_restart`.

### T7: The broker itself is compromised or buggy and could be tricked into unsafe behavior
**Mitigation (partial, by design of this phase):** the broker's own logic
is small, dependency-light, and readable end to end (see `procinfo.rs`'s
module docs on why heavier crates were avoided). It validates every
argument type and range per tool (`registry_tests.rs`). It never runs a
shell. It logs every request, successful or not, before responding
(`audit.rs`) — so even a bug here leaves a trail. **Formal sandboxing of
the broker process itself (seccomp, capabilities, a dedicated low-privilege
user) is out of scope for this phase** and should be revisited before
production use — this threat model does not claim the broker is
un-compromisable, only that it is small enough to review and that its
mistakes are logged.

### T8: Model or user causes an infinite/very long reasoning loop
**Mitigation:** `MAX_STEPS = 5` hard cap per turn, enforced in Python, not
left to the model to self-limit. Tested:
`test_reasoning_loop_never_exceeds_max_steps`.

### T9: Sensitive telemetry (process names, network activity) is exfiltrated
**Not mitigated in this phase; explicitly out of scope.** No network
transmission of any tool result occurs anywhere in this codebase today —
the broker and agent communicate only over a local stdin/stdout pipe. If a
future phase adds any network-facing telemetry export, it needs its own
threat-model update; this document does not currently cover that case
because the capability does not exist yet.

## What this threat model does NOT claim

- It does not claim the `RuleBasedProvider` is a security boundary — it's
  a test/demo stand-in with no adversarial behavior of its own.
- It does not claim protection against a fully compromised OS/kernel below
  the broker — if the OS itself is compromised, the broker's own
  guarantees don't hold either.
- It does not cover GUI-specific threats (this phase is CLI-only, per
  project direction).
