"""Exact source quote references for opt-in focused extraction, not model citations."""
import hashlib
import re


def quote_ref(quote):
    return "@s" + hashlib.sha256(quote.encode()).hexdigest()[:20]


def attach_quote_spans(results, focus):
    if not isinstance(focus, list):
        return
    terms = list(dict.fromkeys(t.strip() for t in focus if isinstance(t, str) and 2 <= len(t.strip()) <= 120))[:8]
    for page in results:
        if not terms or page.get("error") or not isinstance(page.get("content"), str):
            continue
        body = re.sub(r"\s+", " ", page["content"]).strip()
        spans = {}
        for term in terms:
            matches = re.finditer(re.escape(term), body, re.IGNORECASE)
            for _, match in zip(range(2), matches):
                left, right = max(0, match.start() - 200), min(len(body), match.end() + 350)
                quote = body[left:right][:580]
                # Never offer a quotation across an extraction omission boundary.
                if len(quote) >= 20 and not any(marker in quote for marker in ("[...", "[Source characters", "[SELECTED")):
                    spans[quote_ref(quote)] = quote
                if len(spans) >= 12:
                    break
        if spans:
            page["quote_spans"] = dict(list(spans.items())[:12])
