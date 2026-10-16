"""Readable replay text accounting; opaque signatures and duplicate thinking are not token text."""
from typing import Any


def reasoning_detail_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    parts = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict):
            texts.extend(text for key in ("thinking", "text", "summary")
                         if isinstance(text := part.get(key), str))
    return texts


def unmirrored_reasoning_detail_tokens(message: Any) -> int:
    if not isinstance(message, dict) or message.get("reasoning") or message.get("reasoning_content"):
        return 0
    from agent.model_metadata import estimate_tokens_rough

    return sum(estimate_tokens_rough(text) for text in reasoning_detail_texts(message.get("reasoning_details")))


def strip_opaque_replay_items(items: Any) -> Any:
    """``codex_reasoning_items`` with ``encrypted_content`` blanked for local token estimation.
    The ciphertext is priced by the provider's own count, never by its bytes (a compaction
    checkpoint alone can be 5M chars, #100611); only real usage prices it."""
    if not isinstance(items, list):
        return items
    return [
        {k: ("" if k == "encrypted_content" else v) for k, v in item.items()} if isinstance(item, dict) else item
        for item in items
    ]
