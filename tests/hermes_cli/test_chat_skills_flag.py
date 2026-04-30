import sys
from types import ModuleType, SimpleNamespace

import pytest


def test_top_level_skills_flag_defaults_to_chat(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    def fake_cmd_chat(args):
        captured["skills"] = args.skills
        captured["command"] = args.command

    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hermes", "-s", "hermes-agent-dev,github-auth"],
    )

    main_mod.main()

    assert captured == {
        "skills": ["hermes-agent-dev,github-auth"],
        "command": None,
    }


def test_chat_subcommand_accepts_skills_flag(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    def fake_cmd_chat(args):
        captured["skills"] = args.skills
        captured["query"] = args.query

    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hermes", "chat", "-s", "github-auth", "-q", "hello"],
    )

    main_mod.main()

    assert captured == {
        "skills": ["github-auth"],
        "query": "hello",
    }


def test_chat_subcommand_accepts_image_flag(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    def fake_cmd_chat(args):
        captured["query"] = args.query
        captured["image"] = args.image

    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hermes", "chat", "-q", "hello", "--image", "~/storage/shared/Pictures/cat.png"],
    )

    main_mod.main()

    assert captured == {
        "query": "hello",
        "image": "~/storage/shared/Pictures/cat.png",
    }


def test_chat_subcommand_accepts_query_file_flag(monkeypatch, tmp_path):
    import hermes_cli.main as main_mod

    captured = {}
    query_file = tmp_path / "query.txt"
    query_file.write_text("hello from file", encoding="utf-8")

    def fake_cmd_chat(args):
        captured["query"] = args.query
        captured["query_file"] = args.query_file

    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hermes", "chat", "--query-file", str(query_file)],
    )

    main_mod.main()

    assert captured == {
        "query": None,
        "query_file": str(query_file),
    }


def _base_chat_args(**overrides):
    defaults = {
        "continue_last": None,
        "resume": None,
        "yolo": False,
        "source": None,
        "model": None,
        "provider": None,
        "toolsets": None,
        "skills": None,
        "verbose": False,
        "quiet": False,
        "query": None,
        "query_file": None,
        "image": None,
        "worktree": False,
        "checkpoints": False,
        "pass_session_id": False,
        "max_turns": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _install_cmd_chat_fakes(monkeypatch, captured):
    import hermes_cli.main as main_mod

    fake_banner = ModuleType("hermes_cli.banner")
    fake_banner.prefetch_update_check = lambda: None

    fake_skills_sync = ModuleType("tools.skills_sync")
    fake_skills_sync.sync_skills = lambda quiet=True: None

    fake_cli = ModuleType("cli")
    fake_cli.main = lambda **kwargs: captured.update(kwargs)

    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)
    monkeypatch.setitem(sys.modules, "hermes_cli.banner", fake_banner)
    monkeypatch.setitem(sys.modules, "tools.skills_sync", fake_skills_sync)
    monkeypatch.setitem(sys.modules, "cli", fake_cli)
    return main_mod


def test_cmd_chat_reads_query_file(monkeypatch, tmp_path):
    captured = {}
    main_mod = _install_cmd_chat_fakes(monkeypatch, captured)

    query_file = tmp_path / "query.txt"
    query_file.write_text("hello\nfrom file", encoding="utf-8")

    main_mod.cmd_chat(_base_chat_args(query_file=str(query_file)))

    assert captured["query"] == "hello\nfrom file"


def test_cmd_chat_rejects_query_and_query_file(monkeypatch, tmp_path, capsys):
    captured = {}
    main_mod = _install_cmd_chat_fakes(monkeypatch, captured)

    query_file = tmp_path / "query.txt"
    query_file.write_text("hello", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main_mod.cmd_chat(_base_chat_args(query="hello", query_file=str(query_file)))

    assert excinfo.value.code == 1
    assert "use either --query or --query-file" in capsys.readouterr().err
    assert captured == {}


def test_cmd_chat_rejects_missing_query_file(monkeypatch, tmp_path, capsys):
    captured = {}
    main_mod = _install_cmd_chat_fakes(monkeypatch, captured)

    missing_file = tmp_path / "missing.txt"

    with pytest.raises(SystemExit) as excinfo:
        main_mod.cmd_chat(_base_chat_args(query_file=str(missing_file)))

    assert excinfo.value.code == 1
    assert "failed to read --query-file" in capsys.readouterr().err
    assert captured == {}


def test_continue_worktree_and_skills_flags_work_together(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    def fake_cmd_chat(args):
        captured["continue_last"] = args.continue_last
        captured["worktree"] = args.worktree
        captured["skills"] = args.skills
        captured["command"] = args.command

    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hermes", "-c", "-w", "-s", "hermes-agent-dev"],
    )

    main_mod.main()

    assert captured == {
        "continue_last": True,
        "worktree": True,
        "skills": ["hermes-agent-dev"],
        "command": "chat",
    }
