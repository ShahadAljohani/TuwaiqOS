from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    engine: str
    device: str
    threads: int
    gpu_layers: int


@dataclass(frozen=True)
class QuantizationConfig:
    format: str
    bits: int


@dataclass(frozen=True)
class ContextConfig:
    max_input_tokens: int
    max_output_tokens: int


@dataclass(frozen=True)
class GenerationConfig:
    temperature: float
    top_p: float
    top_k: int


@dataclass(frozen=True)
class HardwareRequirements:
    min_ram_gb: int
    recommended_ram_gb: int
    min_vram_gb: int


@dataclass(frozen=True)
class ModelProfile:
    profile_name: str
    model_id: str
    model_path: str
    runtime: RuntimeConfig
    quantization: QuantizationConfig
    context: ContextConfig
    generation: GenerationConfig
    hardware: HardwareRequirements

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BUILTIN_MODEL_PROFILES: dict[str, ModelProfile] = {
    "lite": ModelProfile(
        profile_name="lite",
        model_id="qwen3.5-4b-instruct",
        model_path="models/local/qwen3.5-4b-quantized.gguf",
        runtime=RuntimeConfig(engine="local", device="auto", threads=4, gpu_layers=0),
        quantization=QuantizationConfig(format="gguf", bits=4),
        context=ContextConfig(max_input_tokens=4096, max_output_tokens=512),
        generation=GenerationConfig(temperature=0.2, top_p=0.9, top_k=40),
        hardware=HardwareRequirements(min_ram_gb=8, recommended_ram_gb=12, min_vram_gb=0),
    ),
    "default": ModelProfile(
        profile_name="default",
        model_id="qwen3.5-9b-instruct",
        model_path="models/local/qwen3.5-9b-quantized.gguf",
        runtime=RuntimeConfig(engine="local", device="auto", threads=6, gpu_layers=0),
        quantization=QuantizationConfig(format="gguf", bits=4),
        context=ContextConfig(max_input_tokens=8192, max_output_tokens=768),
        generation=GenerationConfig(temperature=0.2, top_p=0.9, top_k=40),
        hardware=HardwareRequirements(min_ram_gb=16, recommended_ram_gb=24, min_vram_gb=0),
    ),
    "pro": ModelProfile(
        profile_name="pro",
        model_id="qwen3.5-27b-instruct",
        model_path="models/local/qwen3.5-27b.gguf",
        runtime=RuntimeConfig(engine="local", device="auto", threads=8, gpu_layers=0),
        quantization=QuantizationConfig(format="gguf", bits=4),
        context=ContextConfig(max_input_tokens=8192, max_output_tokens=1024),
        generation=GenerationConfig(temperature=0.2, top_p=0.9, top_k=40),
        hardware=HardwareRequirements(min_ram_gb=48, recommended_ram_gb=64, min_vram_gb=0),
    ),
}


def _validate_profile(profile: ModelProfile) -> None:
    if not profile.model_id.strip():
        raise ValueError("model_id must not be empty")
    if not profile.model_path.strip():
        raise ValueError("model_path must not be empty")
    if profile.runtime.threads <= 0:
        raise ValueError("runtime.threads must be > 0")
    if profile.runtime.gpu_layers < 0:
        raise ValueError("runtime.gpu_layers must be >= 0")
    if profile.quantization.bits <= 0:
        raise ValueError("quantization.bits must be > 0")
    if profile.context.max_input_tokens <= 0 or profile.context.max_output_tokens <= 0:
        raise ValueError("context token limits must be > 0")
    if not 0 <= profile.generation.temperature <= 2:
        raise ValueError("generation.temperature must be in [0, 2]")
    if not 0 < profile.generation.top_p <= 1:
        raise ValueError("generation.top_p must be in (0, 1]")
    if profile.generation.top_k <= 0:
        raise ValueError("generation.top_k must be > 0")
    if profile.hardware.min_ram_gb <= 0:
        raise ValueError("hardware.min_ram_gb must be > 0")
    if profile.hardware.recommended_ram_gb < profile.hardware.min_ram_gb:
        raise ValueError("hardware.recommended_ram_gb must be >= hardware.min_ram_gb")
    if profile.hardware.min_vram_gb < 0:
        raise ValueError("hardware.min_vram_gb must be >= 0")


def _coerce_profile(data: dict[str, Any]) -> ModelProfile:
    return ModelProfile(
        profile_name=str(data["profile_name"]),
        model_id=str(data["model_id"]),
        model_path=str(data["model_path"]),
        runtime=RuntimeConfig(**data["runtime"]),
        quantization=QuantizationConfig(**data["quantization"]),
        context=ContextConfig(**data["context"]),
        generation=GenerationConfig(**data["generation"]),
        hardware=HardwareRequirements(**data["hardware"]),
    )


def load_model_profile(profile: str | ModelProfile | dict[str, Any]) -> ModelProfile:
    if isinstance(profile, ModelProfile):
        _validate_profile(profile)
        return profile
    if isinstance(profile, str):
        try:
            selected = BUILTIN_MODEL_PROFILES[profile]
        except KeyError as exc:
            raise ValueError(f"unknown model profile '{profile}'") from exc
        _validate_profile(selected)
        return selected
    if isinstance(profile, dict):
        selected = _coerce_profile(profile)
        _validate_profile(selected)
        return selected
    raise TypeError("profile must be a profile name, ModelProfile, or profile dict")


def resolve_model_path(profile: ModelProfile, root: Path) -> Path:
    model_path = Path(profile.model_path)
    if model_path.is_absolute():
        return model_path
    return (root / model_path).resolve()
