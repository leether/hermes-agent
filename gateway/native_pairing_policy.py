"""Explicit migration of a WeCom intake policy with central caller authorization."""


def paired_group_startup(platform, extra, dm_policy, group_policy):
    """Admit startup only; the live pairing store still gates every DM/group turn.

    Older WeCom adapters accepted group traffic before central pairing checked
    its sender. Requiring ALLOW_ALL_USERS to retain that intake would instead
    authorize strangers. This opt-in retains central authorization and uses the
    normal pairing DM intake, without trusting an adapter-owned allowlist.
    """
    return (
        getattr(platform, "value", None) == "wecom"
        and extra.get("legacy_pairing_admission") is True
        and (dm_policy, group_policy) == ("pairing", "open")
        and not any(extra.get(key) for key in (
            "allow_from", "allowFrom", "group_allow_from", "groupAllowFrom", "groups",
            "allowed_users", "allowedUsers",
        ))
    )
