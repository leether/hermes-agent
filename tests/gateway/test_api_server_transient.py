"""A host-owned memory store must not acquire a second raw native transcript."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from openai.types.chat import ChatCompletion

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
from gateway.platforms.api_server_transient import middleware, transient_scope

SENTINEL = "synthetic-private-glucose-19.876"


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return APIServerAdapter(PlatformConfig(enabled=True, extra={
        "key": "synthetic-local-key", "transient_sessions": True,
        "transient_allowed_tools": ["web_search", "web_extract"]}))


def make_real_agent(adapter, monkeypatch):
    cfg = {"memory": {"memory_enabled": False, "user_profile_enabled": False},
           "checkpoints": {"enabled": False}, "agent": {},
           "compression": {"enabled": True, "threshold": .5, "target_ratio": .2},
           "context": {"engine": "default"}}
    for name in ["load_config", "load_config_readonly"]:
        monkeypatch.setattr("hermes_cli.config." + name, lambda **kw: cfg)
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: cfg)
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda: "synthetic-model")
    monkeypatch.setattr("gateway.run._resolve_runtime_agent_kwargs", lambda: {
        "api_key": "synthetic-key-123456789", "provider": "custom",
        "base_url": "http://127.0.0.1:1/v1", "api_mode": "chat_completions"})
    monkeypatch.setattr("gateway.run._current_max_iterations", lambda: 4)
    monkeypatch.setattr("gateway.run.GatewayRunner._load_fallback_model", lambda: None)
    monkeypatch.setattr("gateway.run.GatewayRunner._load_reasoning_config", lambda model: None)
    monkeypatch.setattr("hermes_cli.tools_config._get_platform_tools", lambda cfg, platform: ["web"])
    monkeypatch.setattr("agent.model_metadata.get_model_context_length", lambda *a, **kw: 32768)
    tool = lambda name: {"type": "function", "function": {"name": name, "description": "fixture", "parameters": {"type": "object", "properties": {}}}}
    monkeypatch.setattr("model_tools.get_tool_definitions", lambda *a, **kw: [tool("web_search"), tool("web_extract"), tool("terminal")])
    monkeypatch.setattr("model_tools.check_toolset_requirements", dict)
    client = MagicMock()
    client.chat.completions.create.return_value = ChatCompletion(
        id="local-stub", model="synthetic-model", created=1, object="chat.completion",
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "合成回答 " + SENTINEL}}],
        usage={"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42})
    monkeypatch.setattr("agent.process_bootstrap.OpenAI", lambda **kwargs: client)
    with transient_scope(True):
        agent = adapter._create_agent(ephemeral_system_prompt=SENTINEL, session_id="transient-test")
    return agent


def test_real_agent_loop_and_all_transcript_roles_leave_no_durable_content(adapter, tmp_path, monkeypatch, caplog):
    agent = make_real_agent(adapter, monkeypatch)
    assert agent._session_db is None and agent._memory_manager is None
    assert agent.valid_tool_names == {"web_search", "web_extract"}
    assert adapter._ensure_session_db() is None
    with transient_scope(True), caplog.at_level(logging.INFO):
        result = agent.run_conversation(SENTINEL, conversation_history=[])
        assert SENTINEL in result["final_response"]
        # Same persistence entry used after a tool round and context compaction.
        messages = [{"role": role, "content": SENTINEL, "reasoning": SENTINEL,
                     "_compressed_summary": role == "user"} for role in ["user", "assistant", "tool"]]
        agent._persist_session(messages)
        agent._save_trajectory(messages, SENTINEL, True)
        assert agent._dump_api_request_debug({"messages": messages}, reason="fixture", error=ValueError(SENTINEL)) is None
        logging.getLogger("fixture.tool").error("tool echo %s", SENTINEL, exc_info=ValueError(SENTINEL))
        assert agent._get_session_db_for_recall() is None
        agent.close()
    assert SENTINEL not in caplog.text
    for file in tmp_path.rglob("*"):
        if file.is_file():
            assert SENTINEL.encode() not in file.read_bytes(), file
    assert not (tmp_path / "state.db").exists()
    assert not (tmp_path / "memories" / "MEMORY.md").exists()


@pytest.mark.asyncio
async def test_transient_http_route_denies_resume_and_other_profile_apis(adapter):
    app = web.Application(middlewares=[middleware(adapter)])
    calls = []
    async def handle(request):
        calls.append(request.path)
        return web.json_response({"ok": True})
    app.router.add_route("*", "/{path:.*}", handle)
    async with TestClient(TestServer(app)) as client:
        for path in ["/v1/responses", "/api/sessions/x/chat", "/p/other/v1/chat/completions", "/api/jobs"]:
            assert (await client.post(path, json={})).status == 403
        assert (await client.post("/v1/chat/completions", headers={"X-Hermes-Session-Id": "old"}, json={})).status == 400
        assert (await client.post("/v1/chat/completions", headers={"Idempotency-Key": "old"}, json={})).status == 400
        assert (await client.post("/v1/chat/completions", json={"stream": True})).status == 400
        assert (await client.post("/v1/chat/completions", json={})).status == 200
    assert calls == ["/v1/chat/completions"]


@pytest.mark.asyncio
async def test_health_advertises_storage_contract_and_fresh_profile_cannot_resume(adapter):
    response = await adapter._handle_health(SimpleNamespace())
    assert json.loads(response.body)["session_storage"] == "transient-v1"
    assert await adapter._ensure_session_db_async() is None


def test_normal_profile_retains_native_store(tmp_path):
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "synthetic-key"}))
    db = adapter._ensure_session_db()
    assert db is not None
    db.create_session("normal", "api_server", model="fixture")
    db.append_message("normal", "user", "ordinary history")
    assert "ordinary history" in str(db.get_messages_as_conversation("normal"))
    adapter._close_cached_session_dbs()


def test_transient_logging_does_not_mute_another_context(caplog):
    with caplog.at_level(logging.WARNING):
        with transient_scope(True):
            logging.getLogger("fixture").warning(SENTINEL)
        logging.getLogger("fixture").warning("ordinary diagnostic")
    assert SENTINEL not in caplog.text
    assert "ordinary diagnostic" in caplog.text


def test_real_compaction_and_tool_spill_stay_transient(adapter, tmp_path, monkeypatch):
    from tools.tool_result_storage import maybe_persist_tool_result
    from tools.web_tools_truncate import _store_full_text
    from tools.web_result_cache import extract_cache_put
    from tools import web_tools
    agent = make_real_agent(adapter, monkeypatch)
    calls = []
    def summary(*args, **kwargs):
        calls.append(True)
        return "Summary of synthetic discussion and unresolved follow up. " * 20 + SENTINEL
    monkeypatch.setattr(agent.context_compressor, "_call_summary_llm", summary)
    web_debug = MagicMock()
    monkeypatch.setattr(web_tools, "_debug", web_debug)
    with transient_scope(True):
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": SENTINEL * 120} for i in range(60)]
        compressed = agent.context_compressor.compress(messages, current_tokens=30000, force=True)
        assert calls and len(compressed) < len(messages) and SENTINEL in str(compressed)
        agent._persist_session(compressed)
        assert maybe_persist_tool_result(SENTINEL * 2000, "web_extract", "fixture", threshold=20) == SENTINEL * 2000
        assert _store_full_text("https://example.org/fixture", SENTINEL) is None
        extract_cache_put("https://example.org/fixture", {"url": "https://example.org/fixture", "content": SENTINEL})
        web_tools._finish_debug("fixture", {"query": SENTINEL})
        assert not web_debug.log_call.called and not web_debug.save.called
        agent.close()
    for file in tmp_path.rglob("*"):
        if file.is_file():
            assert SENTINEL.encode() not in file.read_bytes(), file


@pytest.mark.asyncio
async def test_real_chat_route_receipts_and_no_local_media_expansion(adapter, tmp_path, monkeypatch):
    url = "https://www.who.int/fixture"
    secret = tmp_path / "private.png"
    secret.write_text(SENTINEL)
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "read", "function": {"name": "web_extract"}}]},
        {"role": "tool", "tool_call_id": "read", "content": json.dumps({"results": [
            {"url": url, "content": "synthetic original source " * 12},
            {"url": "https://example.org/failed", "content": SENTINEL * 10, "error": "fetch failed"}]})},
    ]
    async def run(**kwargs):
        kwargs["tool_complete_callback"]("read", "web_extract", {}, messages[-1]["content"])
        return {"final_response": f"Answer {url} MEDIA:{secret}", "messages": messages,
                "completed": True, "session_id": "fresh"}, {}
    monkeypatch.setattr(adapter, "_run_agent", run)
    app = web.Application(middlewares=[middleware(adapter)])
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer synthetic-local-key"}, json={
            "messages": [{"role": "user", "content": SENTINEL}]})
        data = await response.json()
    assert response.status == 200
    assert data["hermes_read_urls"] == [url]
    assert SENTINEL not in json.dumps(data) and "MEDIA:" not in json.dumps(data)
    assert "reasoning_content" not in data["choices"][0]["message"]
    for file in tmp_path.rglob("*"):
        if file.is_file() and file != secret:
            assert SENTINEL.encode() not in file.read_bytes(), file


def test_real_tool_round_cannot_expand_allowlist_or_spill_result(adapter, tmp_path, monkeypatch, capsys):
    agent = make_real_agent(adapter, monkeypatch)
    final = agent.client.chat.completions.create.return_value
    agent.client.chat.completions.create.side_effect = [ChatCompletion(
        id="tools", model="synthetic-model", created=1, object="chat.completion", choices=[{
            "index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": name, "type": "function", "function": {
                "name": name, "arguments": json.dumps({"query": "generic dietary evidence"})}}
                for name in ("web_extract", "terminal")]}}]), final]
    # Simulate a later toolset refresh: turn validation must restore the boundary.
    agent.valid_tool_names.add("terminal")
    executed = []
    def tool(name, *args, **kwargs):
        executed.append(name)
        return json.dumps({"results": [{"url": "https://www.who.int/fixture", "content": SENTINEL * 2000}]})
    monkeypatch.setattr("model_tools.handle_function_call", tool)
    from gateway.platforms.api_server_transient import fetched_urls
    read_urls = []
    agent.tool_complete_callback = lambda call_id, name, args, raw: read_urls.extend(fetched_urls(raw))
    with transient_scope(True):
        result = agent.run_conversation("read only synthetic evidence", conversation_history=[])
        agent.close()
    assert executed == ["web_extract"] and result["completed"]
    assert read_urls == ["https://www.who.int/fixture"]
    assert any("<untrusted_tool_result" in str(m.get("content")) for m in result["messages"] if m.get("role") == "tool")
    assert "terminal" not in agent.valid_tool_names
    assert SENTINEL not in capsys.readouterr().out
    for file in tmp_path.rglob("*"):
        if file.is_file():
            assert SENTINEL.encode() not in file.read_bytes(), file
