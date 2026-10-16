"""Bounded compression for a bridge caller with a shorter outer deadline."""
from unittest.mock import MagicMock, AsyncMock
import pytest

@pytest.fixture
def configured(monkeypatch):
    import agent.auxiliary_client as aux
    monkeypatch.setattr(aux,"_get_auxiliary_task_config",lambda task: {"timeout":120,"max_timeout":90})
    monkeypatch.setattr(aux,"_get_task_timeout",lambda task,default=120:120)
    return aux

def client_route(aux,monkeypatch,asynchronous=False):
    client=MagicMock();client.base_url="https://example.invalid/v1"
    client.chat.completions.create=AsyncMock(return_value={"ok":True}) if asynchronous else MagicMock(return_value={"ok":True})
    monkeypatch.setattr(aux,"_resolve_task_provider_model",lambda *a,**k:("openai-codex","fixture",None,None,None))
    monkeypatch.setattr(aux,"_get_cached_client",lambda *a,**k:(client,"fixture"))
    monkeypatch.setattr(aux,"_validate_llm_response",lambda response,*a,**k:response)
    return client

def test_sync_compression_request_uses_profile_maximum(configured,monkeypatch):
    client=client_route(configured,monkeypatch)
    configured.call_llm(task="compression",messages=[{"role":"user","content":"synthetic context"}])
    assert client.chat.completions.create.call_args.kwargs["timeout"] == 90

@pytest.mark.asyncio
async def test_async_compression_request_uses_profile_maximum(configured,monkeypatch):
    client=client_route(configured,monkeypatch,True)
    await configured.async_call_llm(task="compression",messages=[{"role":"user","content":"synthetic context"}],timeout=180)
    assert client.chat.completions.create.call_args.kwargs["timeout"] == 90

def test_context_watchdog_fits_bridge_outer_deadline(configured):
    from agent.conversation_compression import resolve_context_compression_timeouts
    idle,total=resolve_context_compression_timeouts({"context_timeout_seconds":90,"context_total_ceiling_seconds":120})
    assert idle == 90 and total == 120
    assert total < 240

def test_unconfigured_profiles_keep_upstream_compression_floor(monkeypatch):
    import agent.auxiliary_client as aux
    monkeypatch.setattr(aux,"_get_auxiliary_task_config",lambda task:{"timeout":120})
    assert aux._effective_aux_timeout("compression",None) >= 300

@pytest.mark.parametrize("invalid",[0,-1,True,"bad",float("inf"),float("nan")])
def test_invalid_configured_bound_fails_before_request(monkeypatch,invalid):
    import agent.auxiliary_client as aux
    monkeypatch.setattr(aux,"_get_auxiliary_task_config",lambda task:{"max_timeout":invalid})
    with pytest.raises(ValueError,match="max_timeout"):
        aux._effective_aux_timeout("compression",None)


def test_bound_is_read_from_real_profile_config(tmp_path, monkeypatch):
    import json
    import os
    from pathlib import Path
    import agent.auxiliary_client as aux
    profile = Path(os.environ["HERMES_HOME"])
    (profile / "config.yaml").write_text(json.dumps({"auxiliary":{"compression":{"timeout":120,"max_timeout":90}},"compression":{"context_timeout_seconds":90,"context_total_ceiling_seconds":120}}),encoding="utf-8")
    assert aux._get_auxiliary_task_config("compression")["max_timeout"] == 90
    assert aux._effective_aux_timeout("compression",None) == 90
    from agent.conversation_compression import resolve_context_compression_timeouts
    assert resolve_context_compression_timeouts() == (90,120)


def test_fallback_route_and_credential_retry_cannot_raise_profile_bound(configured, monkeypatch):
    aux=configured
    monkeypatch.setattr(aux,"_fallback_entry_timeout",lambda *args:360)
    monkeypatch.setattr(aux,"_fallback_chain_entry",lambda *args:{"timeout":360,"provider":"openai","model":"fixture"})
    destination=aux._FallbackDestination("openai","https://example.invalid/v1",None,"fixture")
    monkeypatch.setattr(aux,"_fallback_destination",lambda *args:destination)
    client=MagicMock()
    _,kwargs,rebuild=aux._plan_fallback_candidate(client,"fixture","fixture",task="compression",effective_timeout=90,apply_fast_lane=False,messages=[{"role":"user","content":"summary"}],temperature=None,max_tokens=None,tools=None,effective_extra_body={},reasoning_config=None)
    assert kwargs["timeout"] == 90
    assert rebuild("openai",client,"fixture")[1]["timeout"] == 90
