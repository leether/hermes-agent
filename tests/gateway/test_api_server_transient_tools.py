"""Per-request tool reduction survives actual turn validation and a forged refresh."""
import json
import pytest

from openai.types.chat import ChatCompletion

from tests.gateway import test_api_server_transient as fixtures
from gateway.platforms.api_server_transient import transient_scope

adapter = fixtures.adapter
make_real_agent = fixtures.make_real_agent


@pytest.mark.parametrize('output_format', [
    {'type': 'json_object'},
    {'type': 'json_schema', 'json_schema': {'name': 'fixture', 'strict': True, 'schema': {
        'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}}}])
def test_request_without_tools_cannot_execute_even_model_requested_web(adapter, monkeypatch, output_format):
    agent = make_real_agent(adapter, monkeypatch, {"tool_choice": "none", "response_format": output_format})
    assert not agent.tools and not agent.valid_tool_names
    client = agent.client
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
    for call in client.chat.completions.create.call_args_list:
        assert call.kwargs['response_format'] == output_format
    other = make_real_agent(adapter, monkeypatch)
    assert other.valid_tool_names == {"web_search", "web_extract"}
    assert 'response_format' not in other.request_overrides
    other.close()


def test_schema_rejects_external_refs_oversize_and_nonstrict_requests():
    from gateway.platforms.api_server_output_format import request_output_format
    for spec in [
        {'name': 'fixture', 'strict': False, 'schema': {}},
        {'name': 'fixture', 'strict': True, 'schema': {'$ref': 'https://example.org/schema'}},
        {'name': 'fixture', 'strict': True, 'schema': {'description': 'x' * 17000}},
    ]:
        with pytest.raises(ValueError):
            request_output_format({'response_format': {'type': 'json_schema', 'json_schema': spec}})
