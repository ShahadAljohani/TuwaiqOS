# Tuwaiq AI — Architecture

## Overview

```
User
  |
  v
Tuwaiq AI (Python) ──────────────► tuwaiq-agent-broker (Rust)
  - ModelProvider (reasoning)         - validates every request
  - Agent (orchestration loop)        - enforces the allowlist
  - Conversation (context)            - is the only process that
  - BrokerClient (subprocess mgmt)      touches the OS
                                       - audit-logs everything
                                     |
                                     v
                                Linux / KDE / OS APIs
```

The split is deliberate and load-bearing: **Python decides what to do,
Rust is the only thing allowed to actually do it.** The model — rule-based
today, a real local LLM later — never receives shell access, never
constructs a command string, and never talks to the OS directly. Every
effect on the system happens through one of a small, fixed set of typed
tools the Rust broker implements and validates independently of whatever
Python claims.

## Components

### Protocol (`protocol/`)
A versioned JSON schema (`schema.json`) defining `ToolRequest`/
`ToolResponse` and the exact argument/result shape of every tool
(`tools.md`). Both the Python and Rust sides implement this schema
independently — Python's `protocol.py` and Rust's `protocol.rs` are kept in
sync by hand today; see "Known limitations" below for the risk this carries
and how it's mitigated.

### Rust broker (`broker/`)
- `main.rs` — reads newline-delimited JSON requests from stdin, one at a
  time; never blocks indefinitely; never lets a bad request crash the
  process (every code path returns a `ToolResponse`, even for malformed
  input).
- `registry.rs` — the single dispatch table mapping a tool name to its
  implementation. Flat and exhaustive by design, not a plugin system: the
  full set of things this process can be asked to do is visible in one
  file.
- `tools.rs` — one function per tool. Read-only tools (`get_system_info`,
  `get_cpu_info`, `get_memory_info`, `get_disk_info`, `list_processes`,
  `get_network_status`) never mutate anything. `launch_application` and
  `kill_process` are the only tools that change system state.
- `allowlist.rs` — the *only* place an `app_id` maps to a real binary path.
  No PATH lookup, no fuzzy matching, no fallback.
- `procinfo.rs` — direct `/proc` reads for system telemetry. Kept
  dependency-light deliberately (see its module docs) since this is
  trusted, security-adjacent code worth being able to read end to end.
- `audit.rs` — every request, successful or not, is logged with its
  outcome before the response is even sent.

### Python agent (`agent/`)
- `protocol.py` — mirrors the Rust wire types; `KNOWN_TOOLS` is checked
  *before* any request reaches the broker (first of two independent
  enforcement layers — see "Defense in depth" below).
- `broker_client.py` — owns the broker subprocess. Detects a dead broker
  and transparently restarts it on the next call (bounded to
  `MAX_RESTART_ATTEMPTS`, after which it reports unavailability rather than
  retrying forever).
- `model_provider.py` — the `ModelProvider` interface and the default
  `RuleBasedProvider`. A real model backend (`LocalModelProvider`) is a
  planned addition that implements the same interface; nothing else in the
  codebase needs to change when it lands.
- `conversation.py` — per-agent-instance memory: turn history, the last
  `list_processes` result (for pronoun resolution — "close it" needs to
  know what "it" is), and any pending confirmation.
- `agent.py` — the orchestration loop. See "Reasoning loop" and
  "Confirmation gate" below.
- `cli.py` — minimal REPL. No GUI in this phase, per project direction.

## Reasoning loop

A single user message can require more than one tool before it can be
answered — "why is my computer slow" may need memory *and* process data.
`Agent._run_reasoning_loop` calls `ModelProvider.step()` up to `MAX_STEPS`
(5) times per turn:

```
step() -> tool_call  ──► broker.call() ──► result recorded in Conversation
step() -> tool_call  ──► broker.call() ──► result recorded in Conversation
step() -> final_answer ──► returned to user, loop ends
```

The bound exists so a model that never terminates the loop (buggy or
adversarial) cannot hang the agent or flood the broker — after `MAX_STEPS`
the loop force-stops and returns a generic "couldn't reach a clear answer"
message rather than continuing indefinitely.

## Confirmation gate

`SENSITIVE_TOOLS` (currently `kill_process` and `close_application`) never executes on the turn it's requested. Instead:


1. `Agent` asks the provider for a description
   (`describe_sensitive_action`) — deliberately a separate, narrow method
   rather than folded into the model's free-form reasoning, so the exact
   wording shown before a destructive action stays simple and predictable
   rather than depending on open-ended model output.
2. The description is returned to the user; the pending action is stored
   in `Conversation.pending_confirmation`.
3. The *next* user message is checked against a fixed affirmative/negative
   word list. An affirmative executes the action for real; a negative
   cancels; anything else (ambiguous) re-asks rather than guessing —
   nothing is ever inferred as consent.

## Defense in depth

Every tool name is checked twice, independently:

1. **Python** (`agent.py`, via `protocol.KNOWN_TOOLS`) — rejects unknown
   tools before a request is ever sent to the broker at all.
2. **Rust** (`registry.rs`'s `dispatch`) — re-validates independently; a
   Python bug or compromise that somehow bypassed step 1 still cannot
   reach an unregistered tool, because the broker does not trust anything
   about what Python claims.

The same principle applies to `kill_process`'s protected-process check:
Python's confirmation gate is a UX/safety layer, but the broker refuses
pid 1 and a small set of critical process names *unconditionally*,
regardless of whether Python claims the user confirmed. A test
(`test_broker_independently_refuses_pid_1_even_if_confirmed`) verifies this
specifically — a "confirmed" request for a protected pid is still denied.

`close_application` is also protected by the Python confirmation gate,
so closing an approved application requires explicit user confirmation
before the broker is called.

## Known limitations

- **RuleBasedProvider is not natural-language understanding.** It is
  pattern-matching, sufficient to prove the architecture (loop,
  confirmation, context) end to end, and used by the CLI/tests until a real
  `LocalModelProvider` lands.
- **Protocol schema is maintained by hand in two languages.** `protocol.py`
  and `protocol.rs` must be kept consistent manually; there is precedent in
  this project for this drifting silently (see the `telemetry-provider`
  schema bugfix, where a similar Python/JSON-schema pair had drifted) —
  worth the same kind of regression test if this protocol grows.
- **`error_event_count`-style OS-level telemetry is Linux-only today**
  (`dmesg`-based); Windows/other-platform equivalents are unimplemented,
  documented as such rather than silently returning a fake value.
- **Allowlist binary paths are unconfirmed** against a real TuwaiqOS/KDE
  install (see `allowlist.rs`'s inline `UNCONFIRMED` notes) — verify before
  relying on this in production.
- **No named service discovery, no shared-memory IPC** — out of scope for
  this phase, consistent with the project's own phased rollout notes
  elsewhere in the repo.
