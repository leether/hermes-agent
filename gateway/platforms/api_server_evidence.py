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


def checked_spans(page, content):
    body = re.sub(r"\s+", " ", content).strip()
    values = page.get("quote_spans", {})
    if not isinstance(values, dict):
        return {}
    return {key: value for key, value in list(values.items())[:48]
            if isinstance(value, str) and 20 <= len(value) <= 600 and value in body
            and key == "@s" + hashlib.sha256(value.encode()).hexdigest()[:20]}


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
        receipt = {"url": url, "content": content,
                      "sha256": hashlib.sha256(content.encode()).hexdigest(),
                      "truncated": (len(body) > len(content)
                                    or page.get("truncated") is True
                                    or bool(re.search(r"\[TRUNCATED\].{0,200}Showing \d", body, re.DOTALL))),
                      "retrieved_at": datetime.now(UTC).isoformat()}
        selection_hash = page.get("selection_source_sha256")
        if isinstance(selection_hash, str) and re.fullmatch(r"[0-9a-f]{64}", selection_hash):
            receipt["selection_source_sha256"] = selection_hash
        receipt["quote_spans"] = checked_spans(page, content)
        pages.append(receipt)
    return pages


def merge_pages(existing, incoming):
    """Keep windows of the SAME full source; changed bodies replace earlier versions."""
    by_url = {p["url"]: p for p in existing}
    for page in incoming:
        previous = by_url.get(page["url"], {})
        same_source = (page.get("selection_source_sha256")
                       and page.get("selection_source_sha256") == previous.get("selection_source_sha256"))
        if same_source and page["content"] in previous["content"]:
            page = dict(previous, quote_spans=checked_spans({"quote_spans": {
                **previous.get("quote_spans", {}), **page.get("quote_spans", {})}}, previous["content"]))
        elif same_source:
            joined = previous["content"] + "\n\n[Separate extraction window from identical source hash]\n\n" + page["content"]
            if len(joined) <= MAX_PAGE_CHARS:
                page = dict(page, content=joined, sha256=hashlib.sha256(joined.encode()).hexdigest(),
                            retrieved_at=previous["retrieved_at"], truncated=True,
                            quote_spans=checked_spans({"quote_spans": {
                                **previous.get("quote_spans", {}), **page.get("quote_spans", {})}}, joined))
        by_url[page["url"]] = page
    kept, size = [], 0
    for page in by_url.values():
        if len(kept) >= MAX_PAGES or size + len(page["content"]) > MAX_TOTAL_CHARS:
            continue
        kept.append(page)
        size += len(page["content"])
    return kept
