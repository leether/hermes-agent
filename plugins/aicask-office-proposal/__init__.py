"""AICask Office proposal plugin for WorkTool bridge turns."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "office-action-proposal-v1"
PROPOSAL_FILENAME = "office_action_proposal.json"
TOOL_NAME = "create_office_proposal"
TOOLSET_NAME = "aicask-office"


CREATE_OFFICE_PROPOSAL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Create a WorkTool bridge Office action proposal for the current turn. "
        "Use this instead of write_file when the user asks for a controlled Word "
        "or Excel deliverable in a bridge-provided artifact directory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_filename_hint": {
                "type": "string",
                "description": "Output file name only, with .docx or .xlsx extension. Do not include a path.",
            },
            "template_family": {
                "type": "string",
                "description": "Bridge-selected template family, for example structured_docx_v1.",
            },
            "title": {
                "type": "string",
                "description": "Document title.",
            },
            "content_spec": {
                "type": "object",
                "description": "Template-specific content object.",
            },
        },
        "required": ["output_filename_hint", "template_family", "title", "content_spec"],
    },
}


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _json_ok(payload: Mapping[str, Any]) -> str:
    return json.dumps({"ok": True, **dict(payload)}, ensure_ascii=False)


def _artifact_dir() -> Path | None:
    raw = (os.getenv("HERMES_BRIDGE_ARTIFACT_DIR", "") or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    try:
        resolved = root.resolve()
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def _expected_template_family() -> str:
    return (os.getenv("HERMES_BRIDGE_OFFICE_TEMPLATE_FAMILY", "") or "").strip()


def _safe_filename(value: Any) -> tuple[str, str]:
    name = str(value or "").strip()
    if not name:
        return "", "output_filename_hint is required"
    if "/" in name or "\\" in name:
        return "", "output_filename_hint must be a file name, not a path"
    candidate = Path(name)
    if candidate.is_absolute() or candidate.name != name or ".." in candidate.parts:
        return "", "output_filename_hint must not contain path traversal"
    if not re.search(r"\.(docx|xlsx)$", name, re.IGNORECASE):
        return "", "output_filename_hint must end with .docx or .xlsx"
    return name, ""


def _validate_content_spec(template_family: str, content_spec: Any) -> str:
    if not isinstance(content_spec, dict):
        return "content_spec must be an object"
    if template_family == "structured_docx_v1":
        sections = content_spec.get("sections")
        if not isinstance(sections, list) or not sections:
            return "content_spec.sections must be a non-empty array"
        if len(sections) > 12:
            return "content_spec.sections must contain at most 12 sections"
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                return f"section {index} must be an object"
            if not str(section.get("heading") or "").strip():
                return f"section {index} heading is required"
            has_content = any(
                isinstance(section.get(key), list) and section.get(key)
                for key in ("paragraphs", "bullets", "numbered", "tables")
            )
            if not has_content:
                return f"section {index} must contain paragraphs, bullets, numbered, or tables"
    return ""


def create_office_proposal(args: Mapping[str, Any] | None) -> str:
    """Validate and persist an Office action proposal for the current bridge turn."""
    params = dict(args or {})
    root = _artifact_dir()
    if root is None:
        return _json_error("HERMES_BRIDGE_ARTIFACT_DIR is not configured or is not a directory")

    template_family = str(params.get("template_family") or "").strip()
    if not template_family:
        return _json_error("template_family is required")
    expected_family = _expected_template_family()
    if expected_family and template_family != expected_family:
        return _json_error(f"template_family must be {expected_family}")

    filename, filename_error = _safe_filename(params.get("output_filename_hint"))
    if filename_error:
        return _json_error(filename_error)

    title = str(params.get("title") or "").strip()
    if not title:
        return _json_error("title is required")

    content_spec = params.get("content_spec")
    content_error = _validate_content_spec(template_family, content_spec)
    if content_error:
        return _json_error(content_error)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "action": "fill_template",
        "output_filename_hint": filename,
        "template_family": template_family,
        "title": title,
        "content_spec": content_spec,
    }
    proposal_path = root / PROPOSAL_FILENAME
    tmp_path = root / f".{PROPOSAL_FILENAME}.tmp"
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(proposal_path)
    return _json_ok(
        {
            "schema_version": SCHEMA_VERSION,
            "proposal_path": str(proposal_path),
            "proposal_filename": PROPOSAL_FILENAME,
            "template_family": template_family,
            "output_filename_hint": filename,
        }
    )


def register(ctx: Any) -> None:
    ctx.register_tool(
        TOOL_NAME,
        TOOLSET_NAME,
        CREATE_OFFICE_PROPOSAL_SCHEMA,
        lambda args, **kwargs: create_office_proposal(args),
        description="Create a validated Office action proposal for the WorkTool bridge.",
        emoji="📄",
    )
