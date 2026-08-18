from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from pathlib import Path
import resource
from typing import Any, Callable, Protocol

from model_profiles import ModelProfile, resolve_model_path


class LocalRuntimeError(RuntimeError):
    """Base class for local runtime failures."""


class MissingModelError(LocalRuntimeError):
    """Raised when the configured model file is missing."""


class InvalidModelPathError(LocalRuntimeError):
    """Raised when the configured model path is invalid for the runtime."""


class IncompatibleRuntimeError(LocalRuntimeError):
    """Raised when the selected runtime cannot load the configured model."""


class ModelLoadError(LocalRuntimeError):
    """Raised when the model cannot be initialized."""


class InferenceError(LocalRuntimeError):
    """Raised when inference fails."""


class InferenceTimeoutError(InferenceError):
    """Raised when inference exceeds the configured timeout."""


class InsufficientMemoryError(ModelLoadError):
    """Raised when the runtime cannot allocate enough memory."""


@dataclass
class LocalRuntimeTelemetry:
    loaded: bool = False
    backend: str | None = None
    device: str | None = None
    model_path: str | None = None
    load_duration_ms: float | None = None
    inference_latency_ms: float | None = None
    ram_usage_mb: float | None = None
    vram_usage_mb: float | None = None
    cpu_usage_percent: float | None = None
    gpu_usage_percent: float | None = None
    last_error_kind: str | None = None
    last_error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompletionBackend(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
        stop: list[str] | None = None,
    ) -> str: ...

    def close(self) -> None: ...


class LocalModelRuntime(ABC):
    """Runtime adapter for local model execution."""

    @abstractmethod
    def initialize(self, profile: ModelProfile, root: Path) -> None:
        """Load or prepare the selected model."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release runtime resources."""

    @abstractmethod
    def telemetry(self) -> dict[str, Any]:
        """Return load/inference telemetry for the runtime."""

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
    """Placeholder runtime used in tests and as a safe fallback."""

    def __init__(self) -> None:
        self._telemetry = LocalRuntimeTelemetry(loaded=False, backend="noop", device="cpu")

    def initialize(self, profile: ModelProfile, root: Path) -> None:
        self.validate(profile, root)

    def shutdown(self) -> None:
        self._telemetry.loaded = False

    def telemetry(self) -> dict[str, Any]:
        return self._telemetry.to_dict()

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
        resolve_model_path(profile, root=root)


class LlamaCppBackend:
    def __init__(self, model_path: Path, profile: ModelProfile) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise IncompatibleRuntimeError(
                "llama-cpp-python is required to run local Qwen GGUF models"
            ) from exc

        try:
            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=profile.context.max_input_tokens + profile.context.max_output_tokens,
                n_threads=profile.runtime.threads,
                n_gpu_layers=profile.runtime.gpu_layers,
                verbose=False,
            )
        except MemoryError as exc:
            raise InsufficientMemoryError("insufficient memory while loading the local Qwen model") from exc
        except Exception as exc:
            raise ModelLoadError(f"failed to load local model from {model_path}") from exc

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
        stop: list[str] | None = None,
    ) -> str:
        try:
            response = self._llm.create_completion(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                stop=stop,
            )
        except Exception as exc:
            raise InferenceError("local Qwen inference failed") from exc

        choices = response.get("choices") or []
        if not choices:
            raise InferenceError("local Qwen runtime returned no completion choices")
        text = str(choices[0].get("text", "")).strip()
        if not text:
            raise InferenceError("local Qwen runtime returned an empty completion")
        return text

    def close(self) -> None:
        close = getattr(self._llm, "close", None)
        if callable(close):
            close()


class QwenLocalRuntime(LocalModelRuntime):
    """Local GGUF runtime for Qwen profiles via llama.cpp."""

    _SUPPORTED_ENGINES = {"llama.cpp", "llama_cpp"}
    _STOP_TOKENS = ["<|im_end|>", "<|endoftext|>"]
    _SYSTEM_PROMPT = (
        "You are Tuwaiq AI running fully offline on the local machine. "
        "Answer directly and never claim to run shell commands or access the OS yourself."
    )

    def __init__(
        self,
        backend_factory: Callable[[Path, ModelProfile], CompletionBackend] | None = None,
    ) -> None:
        self._backend_factory = backend_factory or self._create_backend
        self._backend: CompletionBackend | None = None
        self._loaded_profile: ModelProfile | None = None
        self._root: Path | None = None
        self._telemetry = LocalRuntimeTelemetry(loaded=False, backend="llama.cpp", device="cpu")

    def initialize(self, profile: ModelProfile, root: Path) -> None:
        self.validate(profile, root)
        model_path = resolve_model_path(profile, root=root)
        if not model_path.exists():
            self._record_error("missing_model", f"model file does not exist: {model_path}")
            raise MissingModelError(f"model file does not exist: {model_path}")
        if not model_path.is_file():
            self._record_error("invalid_model_path", f"model path is not a file: {model_path}")
            raise InvalidModelPathError(f"model path is not a file: {model_path}")
        if (
            self._backend is not None
            and self._loaded_profile == profile
            and self._telemetry.model_path == str(model_path)
        ):
            return

        self.shutdown()
        started = self._snapshot()
        started_at = time.perf_counter()
        try:
            self._backend = self._backend_factory(model_path, profile)
        except LocalRuntimeError as exc:
            self._record_error(self._error_kind_for_exception(exc), str(exc))
            raise
        except MemoryError as exc:
            wrapped = InsufficientMemoryError("insufficient memory while loading the local Qwen model")
            self._record_error("insufficient_memory", str(wrapped))
            raise wrapped from exc
        except Exception as exc:
            wrapped = ModelLoadError(f"failed to load local model from {model_path}")
            self._record_error("model_loading_failure", str(wrapped))
            raise wrapped from exc

        self._loaded_profile = profile
        self._root = root
        self._telemetry.loaded = True
        self._telemetry.backend = profile.runtime.engine
        self._telemetry.device = profile.runtime.device
        self._telemetry.model_path = str(model_path)
        self._telemetry.load_duration_ms = (time.perf_counter() - started_at) * 1000.0
        self._update_metrics(started)
        self._clear_error()

    def shutdown(self) -> None:
        if self._backend is not None:
            self._backend.close()
        self._backend = None
        self._loaded_profile = None
        self._root = None
        self._telemetry.loaded = False

    def telemetry(self) -> dict[str, Any]:
        return self._telemetry.to_dict()

    def decide(self, user_message: str, profile: ModelProfile) -> Any | None:
        if not user_message.strip():
            return None
        prompt = self._build_prompt(user_message)
        text = self._complete(prompt, profile)
        from model_provider import AgentAction

        return AgentAction(kind="respond", text=text)

    def explain(self, user_message: str, tool: str, result: dict[str, Any], profile: ModelProfile) -> str | None:
        prompt = self._build_tool_result_prompt(user_message, tool, result)
        return self._complete(prompt, profile)

    def explain_error(
        self,
        user_message: str,
        tool: str,
        error_code: str,
        error_message: str,
        profile: ModelProfile,
    ) -> str | None:
        prompt = self._build_tool_error_prompt(user_message, tool, error_code, error_message)
        return self._complete(prompt, profile)

    def validate(self, profile: ModelProfile, root: Path) -> None:
        resolve_model_path(profile, root=root)
        if profile.runtime.engine not in self._SUPPORTED_ENGINES:
            raise IncompatibleRuntimeError(
                f"runtime engine '{profile.runtime.engine}' is not compatible with GGUF Qwen profiles"
            )
        model_path = Path(profile.model_path)
        if model_path.suffix.lower() != ".gguf":
            raise InvalidModelPathError("Qwen local runtime expects a .gguf model file")

    def _complete(self, prompt: str, profile: ModelProfile) -> str:
        root = self._root or Path(__file__).resolve().parent.parent
        self.initialize(profile, root=root)
        if self._backend is None:
            raise ModelLoadError("local Qwen runtime is not initialized")

        started = self._snapshot()
        started_at = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._backend.generate,
            prompt,
            max_tokens=profile.context.max_output_tokens,
            temperature=profile.generation.temperature,
            top_p=profile.generation.top_p,
            top_k=profile.generation.top_k,
            stop=self._STOP_TOKENS,
        )
        try:
            text = future.result(timeout=profile.runtime.timeout_seconds)
        except FutureTimeoutError as exc:
            self._telemetry.inference_latency_ms = (time.perf_counter() - started_at) * 1000.0
            self._update_metrics(started)
            self._record_error("timeout", "local Qwen inference timed out")
            raise InferenceTimeoutError("local Qwen inference timed out") from exc
        except LocalRuntimeError as exc:
            self._telemetry.inference_latency_ms = (time.perf_counter() - started_at) * 1000.0
            self._update_metrics(started)
            self._record_error(self._error_kind_for_exception(exc), str(exc))
            raise
        except Exception as exc:
            self._telemetry.inference_latency_ms = (time.perf_counter() - started_at) * 1000.0
            self._update_metrics(started)
            wrapped = InferenceError("local Qwen inference failed")
            self._record_error("inference_failure", str(wrapped))
            raise wrapped from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        self._telemetry.inference_latency_ms = (time.perf_counter() - started_at) * 1000.0
        self._update_metrics(started)
        self._clear_error()
        return text

    def _build_prompt(self, user_message: str) -> str:
        return (
            f"{self._SYSTEM_PROMPT}\n\n"
            f"User: {user_message.strip()}\n"
            "Assistant:"
        )

    def _build_tool_result_prompt(self, user_message: str, tool: str, result: dict[str, Any]) -> str:
        return (
            f"{self._SYSTEM_PROMPT}\n\n"
            "Summarize the tool output for the user in one short answer.\n"
            f"User request: {user_message.strip()}\n"
            f"Tool: {tool}\n"
            f"Tool result: {result}\n"
            "Assistant:"
        )

    def _build_tool_error_prompt(
        self,
        user_message: str,
        tool: str,
        error_code: str,
        error_message: str,
    ) -> str:
        return (
            f"{self._SYSTEM_PROMPT}\n\n"
            "Explain the tool failure honestly without exposing internals.\n"
            f"User request: {user_message.strip()}\n"
            f"Tool: {tool}\n"
            f"Error code: {error_code}\n"
            f"Error message: {error_message}\n"
            "Assistant:"
        )

    def _snapshot(self) -> tuple[float, float]:
        return time.perf_counter(), self._cpu_seconds()

    def _update_metrics(self, started: tuple[float, float]) -> None:
        started_at, started_cpu = started
        wall_delta = max(time.perf_counter() - started_at, 1e-6)
        cpu_delta = max(self._cpu_seconds() - started_cpu, 0.0)
        self._telemetry.ram_usage_mb = self._ram_usage_mb()
        self._telemetry.cpu_usage_percent = (cpu_delta / wall_delta) * 100.0
        self._telemetry.vram_usage_mb = None
        self._telemetry.gpu_usage_percent = None

    def _record_error(self, kind: str, message: str) -> None:
        self._telemetry.last_error_kind = kind
        self._telemetry.last_error_message = message

    def _clear_error(self) -> None:
        self._telemetry.last_error_kind = None
        self._telemetry.last_error_message = None

    def _cpu_seconds(self) -> float:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_utime + usage.ru_stime

    def _ram_usage_mb(self) -> float:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            return rss / (1024.0 * 1024.0)
        return rss / 1024.0

    def _error_kind_for_exception(self, exc: LocalRuntimeError) -> str:
        if isinstance(exc, MissingModelError):
            return "missing_model"
        if isinstance(exc, InvalidModelPathError):
            return "invalid_model_path"
        if isinstance(exc, IncompatibleRuntimeError):
            return "incompatible_runtime"
        if isinstance(exc, InsufficientMemoryError):
            return "insufficient_memory"
        if isinstance(exc, InferenceTimeoutError):
            return "timeout"
        if isinstance(exc, ModelLoadError):
            return "model_loading_failure"
        if isinstance(exc, InferenceError):
            return "inference_failure"
        return "runtime_error"

    def _create_backend(self, model_path: Path, profile: ModelProfile) -> CompletionBackend:
        return LlamaCppBackend(model_path, profile)
