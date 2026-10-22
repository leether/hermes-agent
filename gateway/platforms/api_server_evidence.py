"""Bounded request-local extraction receipts; never model-authored provenance."""
import hashlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

SCHEMA = "extracted-pages-v1"
MAX_PAGE_CHARS = 200000
MAX_TOTAL_CHARS = 600000
MAX_PAGES = 12


def extracted_pages(raw_result):
    try:
        payload = json.loads(raw_result)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return []
    pages = []
    for page in payload["results"]:
        if not isinstance(page, dict) or page.get("error") or page.get("success") is False:
            continue
        url, body = page.get("url"), page.get("content")
        if not isinstance(url, str) or not isinstance(body, str) or len(body.strip()) < 80:
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            continue
        content = body[:MAX_PAGE_CHARS]
        pages.append({"url": url, "content": content,
                      "sha256": hashlib.sha256(content.encode()).hexdigest(),
                      "truncated": (len(body) > len(content)
                                    or page.get("truncated") is True
                                    or bool(re.search(r"\[TRUNCATED\].{0,200}Showing \d", body, re.DOTALL))),
                      "retrieved_at": datetime.now(UTC).isoformat()})
    return pages


def merge_pages(existing, incoming):
    """One URL is one receipt; later successful reads replace earlier versions."""
    by_url = {p["url"]: p for p in existing}
    by_url.update({p["url"]: p for p in incoming})
    kept, size = [], 0
    for page in by_url.values():
        if len(kept) >= MAX_PAGES or size + len(page["content"]) > MAX_TOTAL_CHARS:
            continue
        kept.append(page)
        size += len(page["content"])
    return kept
