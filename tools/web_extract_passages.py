"""Optional verbatim windows from an extracted page, without summarization or disk state."""

import re


def select_passages(content: str, terms: list[str], budget: int) -> str:
    """Keep the header and bounded, labelled context around literal matches.

    Terms are data, never regexes. A window is contiguous source text; omissions
    cannot accidentally look like one continuous quotation. Missing terms are
    explicit so callers can refine the query instead of treating this as full text.
    """
    if len(content) <= budget:
        return content
    header_end = min(4000, budget // 3)
    ranges = [(0, header_end)]
    found = {term: list(re.finditer(re.escape(term), content, re.IGNORECASE)) for term in terms}
    # Round-robin terms: a common word must not consume the entire window budget.
    for occurrence in range(3):
        for matches in found.values():
            if len(matches) <= occurrence:
                continue
            match = matches[occurrence]
            start, end = max(0, match.start() - 900), min(len(content), match.end() + 900)
            candidates = sorted([*ranges, (start, end)])
            merged = []
            for left, right in candidates:
                if merged and left <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
                else:
                    merged.append((left, right))
            if sum(right - left for left, right in merged) <= budget:
                ranges = merged
    missing = [term for term, matches in found.items() if not matches]
    prefix = (f"[SELECTED PASSAGES; TRUNCATED] {sum(b-a for a,b in ranges)} of {len(content)} characters. "
              "Verbatim source windows with offsets; omitted text was not supplied. "
              "Absence here does not establish absence in the full document.\n")
    if missing:
        prefix += "Literal terms not found: " + repr(missing) + "\n"
    return prefix + "\n\n[... omitted source text ...]\n\n".join(
        f"[Source characters {start}:{end}]\n{content[start:end]}" for start, end in ranges
    )


def focus_results(results: list[dict], focus: object, budget: int) -> None:
    """Opt-in only; malformed focus leaves the established extraction path intact."""
    if not isinstance(focus, list):
        return
    terms = list(dict.fromkeys(t.strip() for t in focus if isinstance(t, str) and 2 <= len(t.strip()) <= 120))[:8]
    if not terms:
        return
    from tools.web_tools_truncate import _binary_payload_kind, convert_base64_images_to_links

    for result in results:
        if result.get("error"):
            continue
        content = result.get("raw_content") or result.get("content") or ""
        if _binary_payload_kind(content):
            continue  # Let the established truncation path reject binary payloads.
        selected = select_passages(convert_base64_images_to_links(content), terms, budget)
        if selected != content:
            result["content"] = selected
            result.pop("raw_content", None)
            result["truncated"] = True
