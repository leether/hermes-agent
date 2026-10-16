"""Preserve the new upstream distinction between readable, opaque and duplicated replay."""
import pytest


@pytest.mark.parametrize('field', ['data','signature','encrypted_content'])
def test_opaque_reasoning_details_do_not_trigger_byte_based_compaction(field):
    from agent.model_metadata import estimate_messages_tokens_rough
    from agent.context_compressor import _estimate_msg_budget_tokens
    base={'role':'assistant','content':'visible'}
    opaque={**base,'reasoning_details':[{'type':'reasoning.encrypted',field:'x'*50000}]}
    assert estimate_messages_tokens_rough([opaque]) == estimate_messages_tokens_rough([base])
    assert _estimate_msg_budget_tokens(opaque) == _estimate_msg_budget_tokens(base)


def test_readable_reasoning_details_are_charged_by_both_budget_readers():
    from agent.model_metadata import estimate_messages_tokens_rough
    from agent.context_compressor import _estimate_msg_budget_tokens
    base={'role':'assistant','content':'visible'}
    readable={**base,'reasoning_details':[{'type':'reasoning.text','text':'r'*4000}]}
    assert estimate_messages_tokens_rough([readable]) > estimate_messages_tokens_rough([base])+900
    assert _estimate_msg_budget_tokens(readable) > _estimate_msg_budget_tokens(base)+900


def test_mirrored_reasoning_details_are_not_charged_twice():
    from agent.model_metadata import estimate_messages_tokens_rough
    from agent.context_compressor import _estimate_msg_budget_tokens
    base={'role':'assistant','content':'visible','reasoning_content':'r'*4000}
    duplicate={**base,'reasoning_details':[{'type':'reasoning.text','text':'r'*4000}]}
    assert estimate_messages_tokens_rough([duplicate]) == estimate_messages_tokens_rough([base])
    assert _estimate_msg_budget_tokens(duplicate) == _estimate_msg_budget_tokens(base)

def test_readable_details_follow_newest_turn_replay_policy_without_mutating_history():
    from agent.model_metadata import estimate_messages_tokens_rough

    base = {"role": "assistant", "content": "visible"}
    carrier = {**base, "reasoning_details": [
        {"type": "thinking", "thinking": "r" * 4000, "signature": "signed_fixture"},
    ]}
    tail = [{"role": "user", "content": "next"}, {"role": "assistant", "content": "answer"}]
    assert (estimate_messages_tokens_rough([carrier, *tail], charge_stale_thinking=False)
            == estimate_messages_tokens_rough([base, *tail], charge_stale_thinking=False))
    assert estimate_messages_tokens_rough([carrier]) > estimate_messages_tokens_rough([base]) + 900
    assert len(carrier["reasoning_details"][0]["thinking"]) == 4000
