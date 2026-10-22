"""Per-request tool reduction survives actual turn validation and a forged refresh."""
import json

from openai.types.chat import ChatCompletion

from tests.gateway import test_api_server_transient as fixtures
from gateway.platforms.api_server_transient import transient_scope

adapter = fixtures.adapter
make_real_agent = fixtures.make_real_agent


def test_request_without_tools_cannot_execute_even_model_requested_web(adapter, monkeypatch):
    agent = make_real_agent(adapter, monkeypatch, {"tool_choice": "none"})
    assert not agent.tools and not agent.valid_tool_names
    final = agent.client.chat.completions.create.return_value
    agent.client.chat.completions.create.side_effect = [ChatCompletion(
        id="forged-tool", model="synthetic-model", created=1, object="chat.completion", choices=[{
            "index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "read", "type": "function", "function": {
                "name": "web_extract", "arguments": json.dumps({"urls": ["https://example.org"]})}}]}}]), final]
    agent.valid_tool_names.add("web_extract")
    executed = []
    monkeypatch.setattr("model_tools.handle_function_call", lambda name, *a, **kw: executed.append(name))
    with transient_scope(True):
        result = agent.run_conversation("Review supplied synthetic evidence only", conversation_history=[])
        agent.close()
    assert result["completed"] and executed == [] and not agent.valid_tool_names
    other = make_real_agent(adapter, monkeypatch)
    assert other.valid_tool_names == {"web_search", "web_extract"}
    other.close()
