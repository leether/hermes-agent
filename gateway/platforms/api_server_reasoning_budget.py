"""Opt-in bounded thinking for transient Qwen requests on the DashScope wire."""
from urllib.parse import urlsplit


def bind_reasoning_budget(agent, options):
    if not isinstance(options, dict) or 'thinking_budget' not in options:
        return
    budget = options['thinking_budget']
    if type(budget) is not int or not 128 <= budget <= 8192:
        raise ValueError('thinking_budget must be an integer in 128..8192')
    if 'reasoning_effort' in options or 'reasoning' in options:
        raise ValueError('thinking_budget and reasoning effort are mutually exclusive')
    host = urlsplit(str(getattr(agent, 'base_url', '') or '')).hostname or ''
    if (getattr(agent, 'provider', None) != 'custom'
            or not str(agent.model).lower().startswith('qwen3.8-')
            or not (host == 'aliyuncs.com' or host.endswith('.aliyuncs.com'))):
        raise ValueError('thinking_budget unsupported by this configured route')
    # Qwen 3.8 rejects effort + budget together. The custom profile emits no
    # effort when it is unset; keep thinking enabled and set its native budget.
    agent.reasoning_config = {'enabled': True}
    overrides = dict(getattr(agent, 'request_overrides', {}) or {})
    body = dict(overrides.get('extra_body') or {})
    body.update(enable_thinking=True, thinking_budget=budget)
    overrides['extra_body'] = body
    agent.request_overrides = overrides
