"""Opt-in tool collection cutoff; an interrupted draft is never returned."""
import math

from gateway.platforms.api_server_deadline import RequestDeadlineExpired, with_deadline


async def collect(adapter, kwargs):
    options = kwargs.get('model_options') or {}
    seconds = options.get('evidence_collection_seconds')
    if seconds is None:
        return await with_deadline(adapter, kwargs)
    wall = options.get('wall_timeout_seconds')
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or type(wall) not in (int, float) or not math.isfinite(wall)
            or not 0 < seconds < wall <= 200 or options.get('tool_choice') == 'none'):
        raise ValueError('invalid_evidence_collection_seconds')
    bounded = dict(kwargs, model_options=dict(options, wall_timeout_seconds=seconds))
    try:
        result, usage = await with_deadline(adapter, bounded)
    except RequestDeadlineExpired:
        # Only this opt-in stage expiry is recoverable as receipts. Cancellation,
        # provider errors and the host's overall deadline remain failures.
        return {'final_response': '{}', 'completed': False, 'partial': True,
                '_collection_status': 'budget_exhausted'}, {}
    return dict(result, _collection_status='completed'), usage
