"""Opt-in transient API sessions for hosts which own their own consent-aware memory.

Only Chat Completions is admitted. The host supplies bounded context on every
request; native transcripts, memory providers, trajectories and debug bodies are
not an alternative long-term store. Ordinary API adapters retain their behavior.
"""
import logging
import json
import re
import threading

from aiohttp import web
from agent.transient_session import transient_scope


def configure_adapter(adapter, extra):
    adapter._transient_sessions = extra.get("transient_sessions") is True
    allowed = extra.get("transient_allowed_tools") or []
    if adapter._transient_sessions and (not isinstance(allowed, list) or not allowed
            or any(name not in ("web_search", "web_extract") for name in allowed)):
        raise ValueError("transient-v1 requires an explicit web_search/web_extract allowlist")
    adapter._transient_allowed_tools = tuple(allowed)


def configure_agent_kwargs(adapter, kwargs):
    if not adapter._transient_sessions:
        return
    kwargs.update(session_db=None, memory_manager=None, skip_memory=True,
                  save_trajectories=False, verbose_logging=False, quiet_mode=True,
                  skip_background_review=True, enabled_toolsets=["web"])


def bind_agent(adapter, agent):
    if not adapter._transient_sessions:
        return
    # Set before the first user/tool/summary enters the real turn loop. This also
    # fences the lazy default-state.db recall fallback, not just the main flush.
    agent._transient_session = True
    agent._transient_allowed_tools = frozenset(adapter._transient_allowed_tools)
    agent._persist_disabled = True
    agent._session_db = None
    agent.save_trajectories = False
    agent.suppress_status_output = True
    allowed = frozenset(adapter._transient_allowed_tools)
    agent.tools = [tool for tool in agent.tools if tool.get("function", {}).get("name") in allowed]
    agent.valid_tool_names = {tool["function"]["name"] for tool in agent.tools}


def middleware(adapter):
    @web.middleware
    async def guard(request, handler):
        if not adapter._transient_sessions:
            return await handler(request)
        allowed = {("GET", "/health"), ("GET", "/v1/health"),
                   ("GET", "/v1/models"), ("POST", "/v1/chat/completions")}
        if (request.method, request.path) not in allowed:
            return web.json_response({"error": {"message": "Endpoint disabled for transient sessions"}}, status=403)
        if request.headers.get("X-Hermes-Session-Id") or request.headers.get("X-Hermes-Session-Key"):
            return web.json_response({"error": {"message": "Supply bounded context; session resumption is disabled"}}, status=400)
        if request.headers.get("Idempotency-Key"):
            return web.json_response({"error": {"message": "Host owns replay protection"}}, status=400)
        with transient_scope(True):
            try:
                if request.method == "POST" and (await request.json()).get("stream"):
                    return web.json_response({"error": {"message": "Transient sessions require non-streaming requests"}}, status=400)
                response = await handler(request)
                if response.status >= 400:
                    return web.json_response({"error": {"message": "Transient request failed"}}, status=response.status)
                return response
            except Exception:
                # Never reflect provider messages or request bodies into gateway
                # logs. A caller can retry only under its own delivery contract.
                logging.getLogger(__name__).exception("transient_request_failed")
                return web.json_response({"error": {"message": "Transient request failed"}}, status=500)
    return guard


def final_text(text):
    """No local-file embedding side channel for a tool-restricted transient API."""
    return re.sub(r"MEDIA:\s*\S+", "[local media omitted]", text)


def render_final_text(adapter, text, native_resolver):
    return final_text(text) if adapter._transient_sessions else native_resolver(text)


def decorate_response(adapter, result, data):
    if adapter._transient_sessions:
        data["hermes_read_urls"] = result.get("_transient_read_urls", [])
        data["choices"][0]["message"].pop("reasoning_content", None)


def fetched_urls(raw_result):
    """Parse the raw web_extract completion, before untrusted-data presentation wrapping."""
    try:
        payload = json.loads(raw_result)
    except (ValueError, TypeError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return []
    urls = set()
    for page in payload["results"]:
        if not isinstance(page, dict) or page.get("error") or page.get("success") is False:
            continue
        url, content = page.get("url", ""), page.get("content", "")
        if isinstance(url, str) and url.startswith("https://") and isinstance(content, str) and len(content.strip()) >= 80:
            urls.add(url)
    return sorted(urls)[:20]


async def run_completion(adapter, kwargs):
    """Collect retrieval evidence from real tool completions, not model text/history.

    The turn loop wraps external results and may compact them away. A callback
    receipt remains valid for this request without persisting the fetched body.
    """
    if not adapter._transient_sessions:
        return await adapter._run_agent(**kwargs)
    urls, lock = set(), threading.Lock()
    def completed(call_id, name, args, raw_result):
        if name == "web_extract":
            with lock:
                urls.update(fetched_urls(raw_result))
    result, usage = await adapter._run_agent(**dict(kwargs, tool_complete_callback=completed))
    result["_transient_read_urls"] = sorted(urls)[:20]
    return result, usage
