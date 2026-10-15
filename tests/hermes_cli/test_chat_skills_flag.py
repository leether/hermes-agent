import sys
import types

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

    query_file = tmp_path / "query.txt"
    query_file.write_text("hello from file", encoding="utf-8")
    captured = {}

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


def test_cmd_chat_loads_query_file(monkeypatch, tmp_path):
    import hermes_cli.main as main_mod

    query_file = tmp_path / "query.txt"
    query_file.write_text("hello from file", encoding="utf-8")
    captured = {}

    def fake_cli_main(**kwargs):
        captured.update(kwargs)

    args = types.SimpleNamespace(
        continue_last=None,
        resume=None,
        yolo=False,
        ignore_user_config=False,
        ignore_rules=False,
        source=None,
        query=None,
        query_file=str(query_file),
        tui=False,
        model=None,
        provider=None,
        toolsets=None,
        skills=None,
        verbose=False,
        quiet=True,
        image=None,
        worktree=False,
        checkpoints=False,
        pass_session_id=False,
        max_turns=None,
    )

    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)
    monkeypatch.setattr(main_mod, "_pin_kanban_board_env", lambda: None)
    monkeypatch.setitem(sys.modules, "cli", types.SimpleNamespace(main=fake_cli_main))

    main_mod.cmd_chat(args)

    assert args.query == "hello from file"
    assert captured["query"] == "hello from file"


def test_cmd_chat_rejects_query_and_query_file(monkeypatch, tmp_path, capsys):
    import hermes_cli.main as main_mod

    query_file = tmp_path / "query.txt"
    query_file.write_text("hello from file", encoding="utf-8")
    args = types.SimpleNamespace(
        continue_last=None,
        resume=None,
        yolo=False,
        ignore_user_config=False,
        ignore_rules=False,
        source=None,
        query="hello from argv",
        query_file=str(query_file),
        tui=False,
    )

    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)

    with pytest.raises(SystemExit) as exc:
        main_mod.cmd_chat(args)

    assert exc.value.code == 1
    assert "use either --query or --query-file" in capsys.readouterr().err


def test_cmd_chat_rejects_missing_query_file(monkeypatch, tmp_path, capsys):
    import hermes_cli.main as main_mod

    args = types.SimpleNamespace(
        continue_last=None,
        resume=None,
        yolo=False,
        ignore_user_config=False,
        ignore_rules=False,
        source=None,
        query=None,
        query_file=str(tmp_path / "missing.txt"),
        tui=False,
    )

    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)

    with pytest.raises(SystemExit) as exc:
        main_mod.cmd_chat(args)

    assert exc.value.code == 1
    assert "failed to read --query-file" in capsys.readouterr().err


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
