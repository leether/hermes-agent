"""API liveness and readiness readbacks; maintenance admission remains explicit."""
import os
import time

from aiohttp import web

from gateway.platforms.api_server_profile_writer import profile_admission_status


async def handle_health(adapter, request: web.Request) -> web.Response:
    """GET /health — simple health check."""
    from gateway.platforms.api_server import _hermes_version
    return web.json_response({"status": "ok", "platform": "hermes-agent", "version": _hermes_version(),
                              "profile_admission": profile_admission_status(adapter),
                              "extraction_evidence": "extracted-pages-v1" if getattr(adapter, "_transient_sessions", False) else None,
                              "transient_tool_choice": "none-v1" if getattr(adapter, "_transient_sessions", False) else None,
                              "transient_response_format": "json-object-v1" if getattr(adapter, "_transient_sessions", False) else None,
                              "transient_json_schema": "json-schema-v1" if getattr(adapter, "_transient_sessions", False) else None,
                              "session_storage": "transient-v1" if getattr(adapter, "_transient_sessions", False) else "native"})


async def handle_health_detailed(adapter, request: web.Request) -> web.Response:
    """GET /health/detailed — gateway state, platforms, PID for dashboard probing (Bearer auth)."""
    from gateway.platforms.api_server import _hermes_version, collect_runtime_readiness
    from gateway.status import (
        derive_gateway_busy, derive_gateway_drainable, normalize_updated_at, parse_active_agents,
        read_runtime_status)
    runtime = read_runtime_status() or {}
    gw_state = runtime.get("gateway_state")
    gw_active = parse_active_agents(runtime.get("active_agents", 0))
# Serve the live adapter's own metrics alongside the persisted platform map: the
    # heartbeat loop keeps the file fresh, but a just-booted or wedged writer would
    # otherwise show boot-time values here too (#52323).
    platforms = runtime.get("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
    platforms = dict(platforms)
    api_status = adapter._api_server_status_payload(heartbeat_at=time.time())
    api_platform = dict(platforms.get("api_server", {}))
    api_platform.setdefault("state", "connected" if adapter.is_connected else "disconnected")
    api_platform["metrics"] = api_status
    platforms["api_server"] = api_platform
    # Served BY the gateway process, so gateway_running is True by definition; busy/
    # drainable use the same shared contract as /api/status so the two never disagree.
    active_api_runs, process_depth, active_delegations = adapter._readiness_work_counts()
    from gateway.run import _resolve_gateway_model
    readiness = collect_runtime_readiness(
        configured_model=_resolve_gateway_model(), runtime_status=runtime,
        active_api_runs=active_api_runs, process_completion_queue_depth=process_depth,
        active_delegations=active_delegations)
    return web.json_response({
"status": readiness["status"], "readiness": readiness, "platform": "hermes-agent",
            "profile_admission": profile_admission_status(adapter),
        "version": _hermes_version(), "gateway_state": gw_state,
        "platforms": platforms,
        "api_server": api_status,
        "metrics_today": api_status["metrics_today"],
        "last_heartbeat": api_status["last_heartbeat"],
        "active_agents": gw_active,
        "gateway_busy": derive_gateway_busy(
            gateway_running=True, gateway_state=gw_state, active_agents=gw_active),
        "gateway_drainable": derive_gateway_drainable(
            gateway_running=True, gateway_state=gw_state),
        "exit_reason": runtime.get("exit_reason"),
        # Contract: RFC3339 string | null, never a number (legacy epoch floats exist).
        "updated_at": normalize_updated_at(runtime.get("updated_at")), "pid": os.getpid()})
