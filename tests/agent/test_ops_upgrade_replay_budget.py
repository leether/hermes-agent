"""Functional preservation probes for replay-token accounting in aicask HLP-005."""
import pytest


@pytest.mark.parametrize('field,value', [
    ('reasoning','r'*4000),
    ('reasoning_content','r'*4000),
    ('reasoning_details',[{'summary':'r'*4000}]),
    ('codex_reasoning_items',[{'text':'r'*4000}]),
    ('codex_message_items',[{'content':'r'*4000}]),
])
def test_ops_provider_replay_fields_consume_token_budget(field,value):
    from agent.model_metadata import estimate_messages_tokens_rough
    base = {'role':'assistant','content':'visible'}
    assert estimate_messages_tokens_rough([{**base,field:value}]) > estimate_messages_tokens_rough([base]) + 900
