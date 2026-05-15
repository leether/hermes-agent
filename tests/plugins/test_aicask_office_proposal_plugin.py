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
            registered["name"] = name
            registered["toolset"] = toolset
            registered["schema"] = schema
            registered["handler"] = handler
            registered["kwargs"] = kwargs

    module.register(FakeContext())

    assert registered["name"] == "create_office_proposal"
    assert registered["toolset"] == "aicask-office"
    assert registered["schema"]["parameters"]["required"] == [
        "output_filename_hint",
        "template_family",
        "title",
        "content_spec",
    ]
    assert callable(registered["handler"])


def test_create_office_proposal_requires_artifact_dir(monkeypatch):
    module = load_plugin_module()
    monkeypatch.delenv("HERMES_BRIDGE_ARTIFACT_DIR", raising=False)

    result = json.loads(module.create_office_proposal(valid_args()))

    assert result["ok"] is False
    assert "HERMES_BRIDGE_ARTIFACT_DIR" in result["error"]


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
