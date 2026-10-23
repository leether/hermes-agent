"""Budget reaches real transient transport without conflicting effort or tools."""
from types import SimpleNamespace

import pytest

from gateway.platforms.api_server_reasoning_budget import bind_reasoning_budget
from gateway.platforms.api_server_transient import bind_agent, transient_scope
from tests.gateway import test_api_server_transient as fixtures

adapter = fixtures.adapter


def test_transient_qwen_budget_reaches_wire_and_other_requests_stay_unchanged(adapter, monkeypatch):
    agent = fixtures.make_real_agent(adapter, monkeypatch)
    agent.model = 'qwen3.8-flash'
    agent.provider = 'custom'
    agent.base_url = 'https://token-plan.cn-beijing.maas.aliyuncs.com/v1'
    bind_agent(adapter, agent, {'tool_choice':'none','thinking_budget':1024})
    client = agent.client
    with transient_scope(True):
        result = agent.run_conversation('Review only the supplied synthetic evidence.', conversation_history=[])
        agent.close()
    assert result['completed'] and not agent.tools
    for call in client.chat.completions.create.call_args_list:
        assert 'reasoning_effort' not in call.kwargs
        assert call.kwargs['extra_body']['enable_thinking'] is True
        assert call.kwargs['extra_body']['thinking_budget'] == 1024
    other = fixtures.make_real_agent(adapter, monkeypatch)
    assert 'extra_body' not in (other.request_overrides or {})
    other.close()


def test_budget_rejects_invalid_values_routes_and_conflicting_effort():
    def agent():
        return SimpleNamespace(model='qwen3.8-flash',provider='custom',base_url='https://example.aliyuncs.com/v1',request_overrides={})
    for value in (True,0,127,8193,'1024'):
        with pytest.raises(ValueError): bind_reasoning_budget(agent(),{'thinking_budget':value})
    with pytest.raises(ValueError): bind_reasoning_budget(agent(),{'thinking_budget':1024,'reasoning_effort':'low'})
    for attribute,value in [('provider','openai'),('model','other-model'),('base_url','https://aliyuncs.com.evil.invalid/v1')]:
        a=agent();setattr(a,attribute,value)
        with pytest.raises(ValueError): bind_reasoning_budget(a,{'thinking_budget':1024})
    a=agent();bind_reasoning_budget(a,{})
    assert a.request_overrides == {}
