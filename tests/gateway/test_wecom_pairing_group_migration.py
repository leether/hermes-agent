"""Preserve a paired WeCom bot without granting open access during migration."""

import json

import pytest

from gateway.config import Platform, load_gateway_config
from gateway.pairing import PairingStore
from gateway.run import GatewayRunner, _own_policy_open_startup_violation
from gateway.session import SessionSource
from plugins.platforms.wecom.adapter import WeComAdapter


@pytest.fixture
def paired_gateway(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    for key in ("GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS",
                "WECOM_ALLOWED_USERS", "WECOM_ALLOW_ALL_USERS",
                "WECOM_DM_POLICY", "WECOM_GROUP_POLICY"):
        monkeypatch.delenv(key, raising=False)
    extra = {
        "bot_id": "synthetic-bot", "secret": "synthetic-secret",
        "dm_policy": "pairing", "group_policy": "open",
        "legacy_pairing_admission": True,
    }
    (home / "config.yaml").write_text(json.dumps({
        "gateway": {"standalone": True, "multiplex_profiles": False},
        "platforms": {"wecom": {"enabled": True, "extra": extra}},
    }))
    config = load_gateway_config()
    adapter = WeComAdapter(config.platforms[Platform.WECOM])
    runner = object.__new__(GatewayRunner)
    runner.config = config
    runner.adapters = {Platform.WECOM: adapter}
    runner._profile_adapters = {}
    runner.pairing_store = PairingStore()
    return runner, adapter


@pytest.mark.parametrize("chat_type", ["dm", "group"])
def test_explicit_migration_starts_but_only_live_pairing_grants_dispatch(paired_gateway, chat_type):
    runner, adapter = paired_gateway
    assert _own_policy_open_startup_violation(runner.config) is None
    source = SessionSource(platform=Platform.WECOM, chat_id="synthetic-chat",
                           chat_type=chat_type, user_id="synthetic-user", user_name="Synthetic")
    assert adapter._admit_inbound(chat_type == "group", source.chat_id, source.user_id)
    assert runner._is_user_authorized(source) is False
    code = runner.pairing_store.generate_code("wecom", source.user_id, source.user_name)
    assert runner.pairing_store.approve_code("wecom", code)
    assert runner._is_user_authorized(source) is True
    assert runner.pairing_store.revoke("wecom", source.user_id)
    assert runner._is_user_authorized(source) is False
    runner.pairing_store = PairingStore()
    assert runner._is_user_authorized(source) is False


@pytest.mark.parametrize("flag", [None, False, 1, "true"])
def test_group_open_still_needs_a_literal_migration_opt_in(paired_gateway, flag):
    runner, _ = paired_gateway
    runner.config.platforms[Platform.WECOM].extra["legacy_pairing_admission"] = flag
    assert _own_policy_open_startup_violation(runner.config) is not None


@pytest.mark.parametrize("change", [
    {"dm_policy": "open"}, {"dm_policy": "allowlist"},
    {"allow_from": ["synthetic-user"]}, {"allowFrom": ["synthetic-user"]},
    {"group_allow_from": ["synthetic-chat"]}, {"groupAllowFrom": ["synthetic-chat"]},
    {"groups": {"*": {"allow_from": ["synthetic-user"]}}},
    {"allowed_users": ["synthetic-user"]}, {"allowedUsers": ["synthetic-user"]},
])
def test_migration_cannot_mask_a_different_permission_contract(paired_gateway, change):
    runner, _ = paired_gateway
    runner.config.platforms[Platform.WECOM].extra.update(change)
    assert _own_policy_open_startup_violation(runner.config) is not None


def test_wecom_migration_cannot_open_another_platform(paired_gateway):
    runner, _ = paired_gateway
    config = runner.config.platforms.pop(Platform.WECOM)
    runner.config.platforms[Platform.WEIXIN] = config
    assert _own_policy_open_startup_violation(runner.config) is not None


def test_pairing_approval_cannot_be_borrowed_from_another_profile(paired_gateway):
    runner, _ = paired_gateway
    user = "synthetic-profile-user"
    code = runner.pairing_store.generate_code("wecom", user, "Synthetic")
    assert runner.pairing_store.approve_code("wecom", code)
    runner.config.multiplex_profiles = True
    runner._profile_adapters = {
        "satellite": {Platform.WECOM: WeComAdapter(runner.config.platforms[Platform.WECOM])},
    }
    satellite = PairingStore(profile="satellite")
    runner.pairing_stores = {"satellite": satellite}
    source = SessionSource(platform=Platform.WECOM, chat_id="synthetic-group",
                           chat_type="group", user_id=user, profile="satellite")
    assert runner._is_user_authorized(source) is False
    code = satellite.generate_code("wecom", user, "Synthetic")
    assert satellite.approve_code("wecom", code)
    assert runner._is_user_authorized(source) is True
    assert satellite.revoke("wecom", user)
    assert runner._is_user_authorized(source) is False
