"""MoA resolves context from the configured aggregator, without live metadata calls."""

from unittest.mock import patch

import hermes_yaml as yaml

from agent.model_metadata import get_model_context_length


class TestMoAContextLength:
    """MoA virtual provider resolves context from the aggregator slot, not 256K default."""

    def _write_moa_config(
        self, home, aggregator, custom_providers=None, providers=None
    ):
        import os
        os.makedirs(home, exist_ok=True)
        payload = {
            "moa": {
                "default_preset": "p",
                "presets": {
                    "p": {
                        "enabled": True,
                        "reference_models": [
                            {"provider": "openrouter", "model": "openai/gpt-5.5"}
                        ],
                        "aggregator": aggregator,
                    }
                },
            }
        }
        if custom_providers is not None:
            payload["custom_providers"] = custom_providers
        if providers is not None:
            payload["providers"] = providers
        with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f)

    def test_moa_resolves_from_aggregator(self, tmp_path, monkeypatch):
        home = str(tmp_path / ".hermes")
        monkeypatch.setenv("HERMES_HOME", home)
        self._write_moa_config(home, {"provider": "openrouter", "model": "anthropic/claude-opus-4.8"})
        # Provider metadata is a transport dependency, not the MoA resolution subject.
        monkeypatch.setattr("agent.model_metadata.fetch_model_metadata", lambda **_: {})

        # The MoA preset name + virtual base_url would otherwise fall through to
        # the 256K default; instead it mirrors the aggregator's real window.
        agg_ctx = get_model_context_length(
            "anthropic/claude-opus-4.8", base_url="https://openrouter.ai/api/v1", provider="openrouter"
        )
        moa_ctx = get_model_context_length("p", base_url="http://127.0.0.1/v1", provider="moa")
        assert moa_ctx == agg_ctx


    def test_moa_custom_context_configures_compressor_threshold(
        self, tmp_path, monkeypatch
    ):
        from agent.context_compressor import ContextCompressor

        configured_context = 600_000
        home = str(tmp_path / ".hermes")
        monkeypatch.setenv("HERMES_HOME", home)
        self._write_moa_config(
            home,
            {"provider": "custom:example", "model": "example-model"},
            providers={
                "example": {
                    "api": "http://127.0.0.1:1/v1",
                    "default_model": "example-model",
                    "models": {
                        "example-model": {
                            "context_length": configured_context,
                        },
                    },
                }
            },
        )

        with patch(
            "agent.model_metadata._resolve_endpoint_context_length",
            return_value=None,
        ) as endpoint_probe:
            compressor = ContextCompressor(
                model="p",
                base_url="http://127.0.0.1/v1",
                provider="moa",
                threshold_percent=0.50,
                quiet_mode=True,
            )

        assert compressor.context_length == configured_context
        assert compressor.threshold_tokens == configured_context // 2
        endpoint_probe.assert_not_called()

