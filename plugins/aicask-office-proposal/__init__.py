"""AICask Office proposal plugin for WorkTool bridge turns."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "office-action-proposal-v1"
PROPOSAL_FILENAME = "office_action_proposal.json"
STATE_FILENAME = ".office_action_proposal_state.json"
TOOL_NAME = "create_office_proposal"
START_TOOL_NAME = "start_office_proposal"
APPEND_SECTION_TOOL_NAME = "append_office_proposal_section"
FINISH_TOOL_NAME = "finish_office_proposal"
TOOLSET_NAME = "aicask-office"
ARTIFACT_DIR_TAG_RE = re.compile(r"<artifact_dir>\s*(?P<path>.*?)\s*</artifact_dir>", re.DOTALL)


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
            "artifact_dir": {
                "type": "string",
                "description": (
                    "Bridge-provided artifact directory copied exactly from the request context. "
                    "Required when HERMES_BRIDGE_ARTIFACT_DIR is not set."
                ),
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
        "required": ["output_filename_hint", "artifact_dir", "template_family", "title", "content_spec"],
    },
}

START_OFFICE_PROPOSAL_SCHEMA = {
    "name": START_TOOL_NAME,
    "description": (
        "Start a chunked structured Word proposal in the bridge artifact directory. "
        "Use this for long Word documents so the full document body is not placed "
        "inside one large tool call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_filename_hint": {
                "type": "string",
                "description": "Output file name only, with .docx extension. Do not include a path.",
            },
            "artifact_dir": {
                "type": "string",
                "description": "Bridge-provided artifact directory copied exactly from the request context.",
            },
            "template_family": {
                "type": "string",
                "description": "Must be structured_docx_v1.",
            },
            "title": {"type": "string", "description": "Document title."},
            "subtitle": {"type": "string", "description": "Optional subtitle."},
            "summary": {"type": "string", "description": "Optional short document summary."},
        },
        "required": ["output_filename_hint", "artifact_dir", "template_family", "title"],
    },
}

APPEND_OFFICE_SECTION_SCHEMA = {
    "name": APPEND_SECTION_TOOL_NAME,
    "description": (
        "Append one section to a chunked structured Word proposal. Keep each call "
        "small; for long chapters, split the chapter into multiple sections."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "description": "Section heading."},
            "artifact_dir": {
                "type": "string",
                "description": "Bridge-provided artifact directory copied exactly from the request context.",
            },
            "paragraphs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paragraphs for this section.",
            },
            "bullets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional bullet list items.",
            },
            "numbered": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional numbered list items.",
            },
            "tables": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional simple tables with title, headers, rows.",
            },
        },
        "required": ["heading", "artifact_dir"],
    },
}

FINISH_OFFICE_PROPOSAL_SCHEMA = {
    "name": FINISH_TOOL_NAME,
    "description": (
        "Finalize a chunked structured Word proposal by copying the accumulated "
        "state to office_action_proposal.json."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_dir": {
                "type": "string",
                "description": "Bridge-provided artifact directory copied exactly from the request context.",
            },
        },
        "required": ["artifact_dir"],
    },
}


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _json_ok(payload: Mapping[str, Any]) -> str:
    return json.dumps({"ok": True, **dict(payload)}, ensure_ascii=False)


def _resolve_dir(raw: str) -> Path | None:
    text = (raw or "").strip()
    if not text:
        return None
    root = Path(text).expanduser()
    try:
        resolved = root.resolve()
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def _artifact_root() -> Path | None:
    root = _resolve_dir(os.getenv("HERMES_BRIDGE_ARTIFACT_ROOT", ""))
    return root


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _artifact_dir_from_user_task(user_task: Any) -> Path | None:
    text = str(user_task or "")
    if not text:
        return None
    matches = ARTIFACT_DIR_TAG_RE.findall(text)
    if not matches:
        return None
    candidate = _resolve_dir(matches[-1])
    if candidate is None:
        return None
    root = _artifact_root()
    if root is not None and not _path_is_within(candidate, root):
        return None
    return candidate


def _artifact_dir_from_tool_args(args: Mapping[str, Any] | None) -> Path | None:
    if not isinstance(args, Mapping):
        return None
    candidate = _resolve_dir(str(args.get("artifact_dir") or ""))
    if candidate is None:
        return None
    root = _artifact_root()
    if root is not None and not _path_is_within(candidate, root):
        return None
    return candidate


def _artifact_dir(user_task: Any = None, args: Mapping[str, Any] | None = None) -> Path | None:
    raw = (os.getenv("HERMES_BRIDGE_ARTIFACT_DIR", "") or "").strip()
    direct = _resolve_dir(raw)
    if direct is not None:
        return direct
    from_args = _artifact_dir_from_tool_args(args)
    if from_args is not None:
        return from_args
    return _artifact_dir_from_user_task(user_task)


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


def _validate_docx_section(section: Any) -> str:
    if not isinstance(section, dict):
        return "section must be an object"
    if not str(section.get("heading") or "").strip():
        return "section heading is required"
    has_content = any(
        isinstance(section.get(key), list) and section.get(key)
        for key in ("paragraphs", "bullets", "numbered", "tables")
    )
    if not has_content:
        return "section must contain paragraphs, bullets, numbered, or tables"
    return ""


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _state_path(root: Path) -> Path:
    return root / STATE_FILENAME


def _load_state(root: Path) -> tuple[dict[str, Any], str]:
    state_path = _state_path(root)
    if not state_path.is_file():
        return {}, "office proposal state is missing"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"office proposal state is not valid json: {exc}"
    if not isinstance(payload, dict):
        return {}, "office proposal state root must be an object"
    return payload, ""


def create_office_proposal(args: Mapping[str, Any] | None, **kwargs: Any) -> str:
    """Validate and persist an Office action proposal for the current bridge turn."""
    params = dict(args or {})
    root = _artifact_dir(kwargs.get("user_task"), params)
    if root is None:
        return _json_error(
            "HERMES_BRIDGE_ARTIFACT_DIR is not configured, and no safe bridge artifact_dir was found in the request context"
        )

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
    _write_json_atomic(proposal_path, payload)
    return _json_ok(
        {
            "schema_version": SCHEMA_VERSION,
            "proposal_path": str(proposal_path),
            "proposal_filename": PROPOSAL_FILENAME,
            "template_family": template_family,
            "output_filename_hint": filename,
        }
    )


def start_office_proposal(args: Mapping[str, Any] | None, **kwargs: Any) -> str:
    params = dict(args or {})
    root = _artifact_dir(kwargs.get("user_task"), params)
    if root is None:
        return _json_error(
            "HERMES_BRIDGE_ARTIFACT_DIR is not configured, and no safe bridge artifact_dir was found in the request context"
        )

    template_family = str(params.get("template_family") or "").strip()
    if template_family != "structured_docx_v1":
        return _json_error("chunked office proposal currently supports structured_docx_v1 only")
    expected_family = _expected_template_family()
    if expected_family and template_family != expected_family:
        return _json_error(f"template_family must be {expected_family}")

    filename, filename_error = _safe_filename(params.get("output_filename_hint"))
    if filename_error:
        return _json_error(filename_error)
    if not filename.lower().endswith(".docx"):
        return _json_error("output_filename_hint must end with .docx for structured_docx_v1")

    title = str(params.get("title") or "").strip()
    if not title:
        return _json_error("title is required")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "action": "fill_template",
        "output_filename_hint": filename,
        "template_family": template_family,
        "title": title,
        "content_spec": {
            "subtitle": str(params.get("subtitle") or "").strip(),
            "summary": str(params.get("summary") or "").strip(),
            "sections": [],
        },
    }
    _write_json_atomic(_state_path(root), payload)
    return _json_ok(
        {
            "state_filename": STATE_FILENAME,
            "template_family": template_family,
            "output_filename_hint": filename,
            "section_count": 0,
        }
    )


def append_office_proposal_section(args: Mapping[str, Any] | None, **kwargs: Any) -> str:
    params = dict(args or {})
    root = _artifact_dir(kwargs.get("user_task"), params)
    if root is None:
        return _json_error(
            "HERMES_BRIDGE_ARTIFACT_DIR is not configured, and no safe bridge artifact_dir was found in the request context"
        )
    state, state_error = _load_state(root)
    if state_error:
        return _json_error(state_error)
    if str(state.get("template_family") or "").strip() != "structured_docx_v1":
        return _json_error("office proposal state is not structured_docx_v1")

    section = {
        "heading": str(params.get("heading") or "").strip(),
        "paragraphs": params.get("paragraphs") or [],
        "bullets": params.get("bullets") or [],
        "numbered": params.get("numbered") or [],
        "tables": params.get("tables") or [],
    }
    section_error = _validate_docx_section(section)
    if section_error:
        return _json_error(section_error)

    content_spec = state.get("content_spec")
    if not isinstance(content_spec, dict):
        return _json_error("office proposal state content_spec must be an object")
    sections = content_spec.get("sections")
    if not isinstance(sections, list):
        return _json_error("office proposal state content_spec.sections must be an array")
    if len(sections) >= 12:
        return _json_error("structured_docx_v1 supports at most 12 sections")
    sections.append(section)
    _write_json_atomic(_state_path(root), state)
    return _json_ok({"state_filename": STATE_FILENAME, "section_count": len(sections)})


def finish_office_proposal(args: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
    params = dict(args or {})
    root = _artifact_dir(kwargs.get("user_task"), params)
    if root is None:
        return _json_error(
            "HERMES_BRIDGE_ARTIFACT_DIR is not configured, and no safe bridge artifact_dir was found in the request context"
        )
    state, state_error = _load_state(root)
    if state_error:
        return _json_error(state_error)
    template_family = str(state.get("template_family") or "").strip()
    content_error = _validate_content_spec(template_family, state.get("content_spec"))
    if content_error:
        return _json_error(content_error)

    proposal_path = root / PROPOSAL_FILENAME
    _write_json_atomic(proposal_path, state)
    section_count = len((state.get("content_spec") or {}).get("sections") or [])
    return _json_ok(
        {
            "schema_version": SCHEMA_VERSION,
            "proposal_path": str(proposal_path),
            "proposal_filename": PROPOSAL_FILENAME,
            "template_family": template_family,
            "output_filename_hint": str(state.get("output_filename_hint") or "").strip(),
            "section_count": section_count,
        }
    )


def register(ctx: Any) -> None:
    ctx.register_tool(
        TOOL_NAME,
        TOOLSET_NAME,
        CREATE_OFFICE_PROPOSAL_SCHEMA,
        lambda args, **kwargs: create_office_proposal(args, **kwargs),
        description="Create a validated Office action proposal for the WorkTool bridge.",
        emoji="📄",
    )
    ctx.register_tool(
        START_TOOL_NAME,
        TOOLSET_NAME,
        START_OFFICE_PROPOSAL_SCHEMA,
        lambda args, **kwargs: start_office_proposal(args, **kwargs),
        description="Start a chunked Office proposal for long structured Word documents.",
        emoji="📝",
    )
    ctx.register_tool(
        APPEND_SECTION_TOOL_NAME,
        TOOLSET_NAME,
        APPEND_OFFICE_SECTION_SCHEMA,
        lambda args, **kwargs: append_office_proposal_section(args, **kwargs),
        description="Append one section to a chunked structured Word proposal.",
        emoji="➕",
    )
    ctx.register_tool(
        FINISH_TOOL_NAME,
        TOOLSET_NAME,
        FINISH_OFFICE_PROPOSAL_SCHEMA,
        lambda args, **kwargs: finish_office_proposal(args, **kwargs),
        description="Finalize a chunked structured Word proposal.",
        emoji="✅",
    )
