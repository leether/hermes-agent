"""First-class provider identity survives an explicit endpoint with an offline catalog."""

import pytest
from unittest.mock import patch

from agent.auxiliary_client import _resolve_task_provider_model


class TestResolveTaskProviderModel:
    @pytest.mark.parametrize(
        "provider",
        [
            "anthropic",
            "minimax-oauth",
            "nous",
            "openai-codex",
            "qwen-oauth",
            "xai-oauth",
        ],
    )
    @patch("agent.models_dev.fetch_models_dev", return_value={})
    def test_explicit_base_url_preserves_first_class_provider_identity(self, _catalog, provider):
        resolved_provider, model, base_url, api_key, api_mode = _resolve_task_provider_model(
            task="moa_reference",
            provider=provider,
            model="test-model",
            base_url="https://provider.example/v1",
            api_key="resolved-token",
        )

        assert resolved_provider == provider
        assert model == "test-model"
        assert base_url == "https://provider.example/v1"
        assert api_key == "resolved-token"
        assert api_mode is None

