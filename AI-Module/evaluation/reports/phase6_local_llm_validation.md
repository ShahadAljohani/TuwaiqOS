# Phase 6 Local LLM Validation and Benchmarking Report

- Timestamp: 2026-08-24T21:37:03.179325Z
- Local LLM layer status for Tuwaiq AI V1: **NOT READY**
- Why: not all required local Qwen models were benchmarked with real files in this environment; one or more final security confirmations are not yet satisfied by the active local-LLM path

## 1. Test report

### lite — qwen3.5-4b-instruct-quantized
- Status: not_run
- Response quality: not_run
- Context handling: not_run
- Stability: not_run
- Issues:
  - Model file unavailable for profile 'lite' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-4b-quantized.gguf; benchmark not run.

### default — qwen3.5-9b-instruct-quantized
- Status: not_run
- Response quality: not_run
- Context handling: not_run
- Stability: not_run
- Issues:
  - Model file unavailable for profile 'default' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-9b-quantized.gguf; benchmark not run.

### pro — qwen3.5-27b-instruct
- Status: not_run
- Response quality: not_run
- Context handling: not_run
- Stability: not_run
- Issues:
  - Model file unavailable for profile 'pro' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-27b.gguf; benchmark not run.

## 2. Model benchmark report

### lite
- Startup time (ms): None
- Model loading time (ms): None
- Inference latency (ms): None
- RAM usage (MB): None
- VRAM usage (MB): None
- CPU usage (%): None
- GPU usage (%): None
- Tool-calling success: None

### default
- Startup time (ms): None
- Model loading time (ms): None
- Inference latency (ms): None
- RAM usage (MB): None
- VRAM usage (MB): None
- CPU usage (%): None
- GPU usage (%): None
- Tool-calling success: None

### pro
- Startup time (ms): None
- Model loading time (ms): None
- Inference latency (ms): None
- RAM usage (MB): None
- VRAM usage (MB): None
- CPU usage (%): None
- GPU usage (%): None
- Tool-calling success: None

## 3. Security test report

- no shell access: PASS — Tool schemas expose only typed tool arguments and no raw shell-command parameter.
- no unrestricted subprocess execution: PASS — Rust launches only compiled-in allowlisted applications and does not invoke a shell.
- no root: PASS — No tool requests privilege escalation or root acquisition.
- no direct OS access: PASS — The Python agent loop does not shell out or read host state directly.
- no cloud AI dependency: PASS — The agent/model stack is implemented around LocalModelProvider + llama.cpp only.
- no bypass around Rust broker: PASS — Tool execution in the Python agent is routed through BrokerClient, preserving the Rust boundary.
- sensitive operations require confirmation: FAIL — The current Phase 6 audit expects sensitive close/kill actions to be model-visible and confirmation-gated. This check fails if the Qwen-exposed tool schema omits them or the active agent loop lacks a confirmation path.
- TuwaiqOS remains usable if AI crashes: PASS — Phase 5 crash-isolation and restart hooks are present for the local runtime.

## 4. End-to-end CLI demo results

- lite: CLI demo not run because the configured model file was unavailable.
- default: CLI demo not run because the configured model file was unavailable.
- pro: CLI demo not run because the configured model file was unavailable.

## 5. Known limitations

- Real Phase 6 benchmarks were not available for: default, lite, pro.
- The current Qwen-exposed tool schema/agent path does not yet prove the required confirmation-gated close action for the acceptance demo.
- VRAM/GPU metrics remain unavailable on CPU-only or not-run validations and must be re-collected on target hardware.

## 6. Recommendation for default model

- Keep Qwen3.5-9B Quantized as the intended default profile label for now, but do not promote any model as the Tuwaiq AI V1 default until the new Phase 6 runner is executed against all three real local model files on target hardware.

## 7. List of issues discovered

- Model file unavailable for profile 'lite' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-4b-quantized.gguf; benchmark not run.
- Model file unavailable for profile 'default' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-9b-quantized.gguf; benchmark not run.
- Model file unavailable for profile 'pro' at /home/runner/work/TuwaiqOS/TuwaiqOS/AI-Module/models/local/qwen3.5-27b.gguf; benchmark not run.
- Security confirmation failed: sensitive operations require confirmation. The current Phase 6 audit expects sensitive close/kill actions to be model-visible and confirmation-gated. This check fails if the Qwen-exposed tool schema omits them or the active agent loop lacks a confirmation path.

## Final security confirmations

- no shell access: confirmed
- no unrestricted subprocess execution: confirmed
- no root: confirmed
- no direct OS access: confirmed
- no cloud AI dependency: confirmed
- no bypass around Rust broker: confirmed
- sensitive operations require confirmation: not yet confirmed
- TuwaiqOS remains usable if AI crashes: confirmed

## Ready verdict: NOT READY

not all required local Qwen models were benchmarked with real files in this environment; one or more final security confirmations are not yet satisfied by the active local-LLM path
