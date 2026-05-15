import importlib.util
import json
from pathlib import Path


PLUGIN_PATH = Path(__file__).resolve().parents[2] / "plugins" / "aicask-office-proposal" / "__init__.py"


def load_plugin_module():
    spec = importlib.util.spec_from_file_location("aicask_office_proposal_plugin_test", PLUGIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_args(index: int = 1):
    return {
        "output_filename_hint": f"ai-public-tool-first-{index}.docx",
        "template_family": "structured_docx_v1",
        "title": f"AI Public Tool First {index}",
        "content_spec": {
            "summary": "Tool-first proposal write",
            "sections": [
                {
                    "heading": "Contract",
                    "paragraphs": ["The plugin writes office_action_proposal.json into the bridge artifact dir."],
                }
            ],
        },
    }


def test_create_office_proposal_writes_valid_file(tmp_path, monkeypatch):
    module = load_plugin_module()
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("HERMES_BRIDGE_OFFICE_TEMPLATE_FAMILY", "structured_docx_v1")

    result = json.loads(module.create_office_proposal(valid_args()))
    proposal = json.loads((tmp_path / "office_action_proposal.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["proposal_filename"] == "office_action_proposal.json"
    assert proposal["schema_version"] == "office-action-proposal-v1"
    assert proposal["action"] == "fill_template"
    assert proposal["template_family"] == "structured_docx_v1"
    assert proposal["output_filename_hint"] == "ai-public-tool-first-1.docx"


def test_register_exposes_create_office_proposal_tool():
    module = load_plugin_module()
    registered = {}

    class FakeContext:
        def register_tool(self, name, toolset, schema, handler, **kwargs):
            registered[name] = {
                "toolset": toolset,
                "schema": schema,
                "handler": handler,
                "kwargs": kwargs,
            }

    module.register(FakeContext())

    assert set(registered) == {
        "create_office_proposal",
        "start_office_proposal",
        "append_office_proposal_section",
        "finish_office_proposal",
    }
    create_tool = registered["create_office_proposal"]
    assert create_tool["toolset"] == "aicask-office"
    assert create_tool["schema"]["parameters"]["required"] == [
        "output_filename_hint",
        "artifact_dir",
        "template_family",
        "title",
        "content_spec",
    ]
    assert callable(create_tool["handler"])


def test_create_office_proposal_requires_artifact_dir(monkeypatch):
    module = load_plugin_module()
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_ROOT", raising=False)

    result = json.loads(module.create_office_proposal(valid_args()))

    assert result["ok"] is False
    assert "HERMES_BRIDGE_ARTIFACT_DIR" in result["error"]


def test_create_office_proposal_uses_safe_artifact_dir_from_user_task(tmp_path, monkeypatch):
    module = load_plugin_module()
    artifact_root = tmp_path / "artifacts" / "ai-public"
    artifact_dir = artifact_root / "msg_123"
    artifact_dir.mkdir(parents=True)
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_ROOT", str(artifact_root))
    user_task = (
        "<message_context>{}</message_context>\n"
        f"<artifact_dir>\n{artifact_dir}\n</artifact_dir>\n"
    )

    result = json.loads(module.create_office_proposal(valid_args(), user_task=user_task))
    proposal = json.loads((artifact_dir / "office_action_proposal.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["proposal_path"] == str(artifact_dir / "office_action_proposal.json")
    assert proposal["output_filename_hint"] == "ai-public-tool-first-1.docx"


def test_create_office_proposal_uses_safe_artifact_dir_from_tool_args(tmp_path, monkeypatch):
    module = load_plugin_module()
    artifact_root = tmp_path / "artifacts" / "ai-public"
    artifact_dir = artifact_root / "msg_123"
    artifact_dir.mkdir(parents=True)
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_ROOT", str(artifact_root))
    args = valid_args()
    args["artifact_dir"] = str(artifact_dir)

    result = json.loads(module.create_office_proposal(args))
    proposal = json.loads((artifact_dir / "office_action_proposal.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["proposal_path"] == str(artifact_dir / "office_action_proposal.json")
    assert proposal["output_filename_hint"] == "ai-public-tool-first-1.docx"


def test_create_office_proposal_rejects_user_task_artifact_dir_outside_root(tmp_path, monkeypatch):
    module = load_plugin_module()
    artifact_root = tmp_path / "artifacts" / "ai-public"
    artifact_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_ROOT", str(artifact_root))

    result = json.loads(
        module.create_office_proposal(
            valid_args(),
            user_task=f"<artifact_dir>\n{outside}\n</artifact_dir>\n",
        )
    )

    assert result["ok"] is False
    assert "artifact_dir" in result["error"]
    assert not (outside / "office_action_proposal.json").exists()


def test_create_office_proposal_rejects_tool_arg_artifact_dir_outside_root(tmp_path, monkeypatch):
    module = load_plugin_module()
    artifact_root = tmp_path / "artifacts" / "ai-public"
    artifact_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_ROOT", str(artifact_root))
    args = valid_args()
    args["artifact_dir"] = str(outside)

    result = json.loads(module.create_office_proposal(args))

    assert result["ok"] is False
    assert "artifact_dir" in result["error"]
    assert not (outside / "office_action_proposal.json").exists()


def test_create_office_proposal_rejects_template_mismatch(tmp_path, monkeypatch):
    module = load_plugin_module()
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("HERMES_BRIDGE_OFFICE_TEMPLATE_FAMILY", "structured_docx_v1")
    args = valid_args()
    args["template_family"] = "multi_sheet_table_v1"

    result = json.loads(module.create_office_proposal(args))

    assert result["ok"] is False
    assert result["error"] == "template_family must be structured_docx_v1"
    assert not (tmp_path / "office_action_proposal.json").exists()


def test_create_office_proposal_rejects_path_traversal(tmp_path, monkeypatch):
    module = load_plugin_module()
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_DIR", str(tmp_path))
    args = valid_args()
    args["output_filename_hint"] = "../bad.docx"

    result = json.loads(module.create_office_proposal(args))

    assert result["ok"] is False
    assert "path" in result["error"]
    assert not (tmp_path / "office_action_proposal.json").exists()


def test_chunked_office_proposal_writes_state_then_final_proposal(tmp_path, monkeypatch):
    module = load_plugin_module()
    artifact_root = tmp_path / "artifacts" / "ai-public"
    artifact_dir = artifact_root / "msg_123"
    artifact_dir.mkdir(parents=True)
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("HERMES_BRIDGE_OFFICE_TEMPLATE_FAMILY", "structured_docx_v1")

    start = json.loads(
        module.start_office_proposal(
            {
                "output_filename_hint": "chunked-doc.docx",
                "artifact_dir": str(artifact_dir),
                "template_family": "structured_docx_v1",
                "title": "Chunked Doc",
                "summary": "Chunked proposal write",
            }
        )
    )
    append = json.loads(
        module.append_office_proposal_section(
            {
                "heading": "Part 1",
                "artifact_dir": str(artifact_dir),
                "paragraphs": ["A chunked section avoids one oversized tool call."],
            }
        )
    )
    finish = json.loads(module.finish_office_proposal({"artifact_dir": str(artifact_dir)}))
    state = json.loads((artifact_dir / ".office_action_proposal_state.json").read_text(encoding="utf-8"))
    proposal = json.loads((artifact_dir / "office_action_proposal.json").read_text(encoding="utf-8"))

    assert start["ok"] is True
    assert append["ok"] is True
    assert append["section_count"] == 1
    assert finish["ok"] is True
    assert state["content_spec"]["sections"][0]["heading"] == "Part 1"
    assert proposal["output_filename_hint"] == "chunked-doc.docx"
    assert proposal["content_spec"]["sections"][0]["paragraphs"] == [
        "A chunked section avoids one oversized tool call."
    ]


def test_finish_office_proposal_rejects_empty_state(tmp_path, monkeypatch):
    module = load_plugin_module()
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_DIR", str(tmp_path))
    json.loads(
        module.start_office_proposal(
            {
                "output_filename_hint": "empty-doc.docx",
                "template_family": "structured_docx_v1",
                "title": "Empty Doc",
            }
        )
    )

    result = json.loads(module.finish_office_proposal({}))

    assert result["ok"] is False
    assert "sections" in result["error"]
    assert not (tmp_path / "office_action_proposal.json").exists()


def test_create_office_proposal_accepts_scalar_docx_text_items(tmp_path, monkeypatch):
    module = load_plugin_module()
    monkeypatch.setenv("HERMES_BRIDGE_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("HERMES_BRIDGE_OFFICE_TEMPLATE_FAMILY", "structured_docx_v1")
    args = valid_args()
    args["content_spec"]["sections"] = [
        {
            "heading": "Numbered",
            "numbered": "One scalar item should be tolerated by the controlled backend canonicalizer.",
        }
    ]

    result = json.loads(module.create_office_proposal(args))

    assert result["ok"] is True
    assert (tmp_path / "office_action_proposal.json").is_file()
