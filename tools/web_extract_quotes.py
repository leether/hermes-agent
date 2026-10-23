"""Exact source quote references for opt-in focused extraction, not model citations."""
import hashlib
import re


def quote_ref(quote):
    return "@s" + hashlib.sha256(quote.encode()).hexdigest()[:20]


def sentence_ending_window(body, match):
    """An alternative ending at the focus sentence, never a joined quotation."""
    ending = re.search(r'[。！？]|[.!?](?=\s|$)', body[match.end():match.end() + 600])
    if ending is None:
        return ''
    right = match.end() + ending.end()
    left = max(0, right - 600)
    if left and not body[left - 1].isspace():
        boundary = body.find(' ', left, match.start())
        if boundary < 0:
            return ''
        left = boundary + 1
    return body[left:right] if left <= match.start() else ''


def candidate_windows(body, terms):
    primary, alternatives, secondary = [], [], []
    for term in terms:
        matches = list(re.finditer(re.escape(term), body, re.IGNORECASE))[:2]
        for i, match in enumerate(matches):
            left, right = max(0, match.start() - 200), min(len(body), match.end() + 350)
            (primary if i == 0 else secondary).append(body[left:right][:580])
            if i == 0:
                alternatives.append(sentence_ending_window(body, match))
    # Preserve one original choice for every term before filling alternatives.
    return primary + alternatives + secondary


def attach_quote_spans(results, focus):
    if not isinstance(focus, list):
        return
    terms = list(dict.fromkeys(t.strip() for t in focus if isinstance(t, str) and 2 <= len(t.strip()) <= 120))[:8]
    for page in results:
        if not terms or page.get("error") or not isinstance(page.get("content"), str):
            continue
        body = re.sub(r"\s+", " ", page["content"]).strip()
        spans = {}
        for quote in candidate_windows(body, terms):
            # Never offer a quotation across an extraction omission boundary.
            if 20 <= len(quote) <= 600 and not any(marker in quote for marker in ("[...", "[Source characters", "[SELECTED")):
                spans[quote_ref(quote)] = quote
            if len(spans) >= 12:
                break
        if spans:
            page["quote_spans"] = dict(list(spans.items())[:12])
