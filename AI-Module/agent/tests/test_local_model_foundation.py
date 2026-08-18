from __future__ import annotations

import pytest

from agent import Agent
from model_profiles import BUILTIN_MODEL_PROFILES, ModelProfile, load_model_profile
from model_provider import LocalModelProvider, ModelProvider, RuleBasedProvider
from protocol import ToolResponse


class _FakeBroker:
    def call(self, tool: str, arguments: dict | None = None) -> ToolResponse:
        if tool == "get_cpu_info":
            return ToolResponse(
                protocol_version="1.0",
                request_id="req-1",
                timestamp="now",
                status="ok",
                result={"usage_percent": 20.0, "core_count": 8},
            )
        return ToolResponse(
            protocol_version="1.0",
            request_id="req-1",
            timestamp="now",
            status="error",
            error={"code": "internal_error", "message": "unsupported in test broker"},
        )


def test_rule_based_provider_still_works() -> None:
    provider = RuleBasedProvider()
    action = provider.decide("what is my cpu usage?")
    assert action.kind == "call_tool"
    assert action.tool == "get_cpu_info"


def test_local_model_provider_can_be_instantiated() -> None:
    provider = LocalModelProvider(profile="default")
    assert isinstance(provider, ModelProvider)
    assert provider.profile.profile_name == "default"


def test_agent_depends_on_model_provider_abstraction() -> None:
    broker = _FakeBroker()
    provider: ModelProvider = LocalModelProvider(profile="lite")
    agent = Agent(model=provider, broker=broker)  # type: ignore[arg-type]
    response = agent.handle("show cpu")
    assert "CPU usage is currently" in response


def test_switching_providers_requires_no_agent_code_changes() -> None:
    broker = _FakeBroker()
    for provider in (RuleBasedProvider(), LocalModelProvider(profile="default")):
        agent = Agent(model=provider, broker=broker)  # type: ignore[arg-type]
        assert "CPU usage is currently" in agent.handle("cpu")


def test_model_profiles_can_be_selected_and_loaded() -> None:
    default_profile = load_model_profile("default")
    assert default_profile == BUILTIN_MODEL_PROFILES["default"]

    custom = load_model_profile(
        {
            "profile_name": "custom",
            "model_id": "custom-local-model",
            "model_path": "models/local/custom.gguf",
            "runtime": {"engine": "local", "device": "cpu", "threads": 2, "gpu_layers": 0},
            "quantization": {"format": "gguf", "bits": 4},
            "context": {"max_input_tokens": 2048, "max_output_tokens": 256},
            "generation": {"temperature": 0.1, "top_p": 0.95, "top_k": 40},
            "hardware": {"min_ram_gb": 4, "recommended_ram_gb": 8, "min_vram_gb": 0},
        }
    )
    assert isinstance(custom, ModelProfile)
    assert custom.profile_name == "custom"


def test_invalid_model_configuration_is_handled_safely() -> None:
    with pytest.raises(ValueError):
        load_model_profile(
            {
                "profile_name": "bad",
                "model_id": "bad-model",
                "model_path": "models/local/bad.gguf",
                "runtime": {"engine": "local", "device": "cpu", "threads": 0, "gpu_layers": 0},
                "quantization": {"format": "gguf", "bits": 4},
                "context": {"max_input_tokens": 2048, "max_output_tokens": 256},
                "generation": {"temperature": 0.1, "top_p": 0.95, "top_k": 40},
                "hardware": {"min_ram_gb": 4, "recommended_ram_gb": 8, "min_vram_gb": 0},
            }
        )
