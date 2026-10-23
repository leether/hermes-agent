"""Literal source windows must preserve adjacent limitations and extraction guards."""
import asyncio
import copy
import json
import re
from unittest.mock import AsyncMock, patch

from gateway.platforms.api_server_evidence import extracted_pages, merge_pages
from agent.transient_session import transient_scope
from tools.web_extract_passages import focus_results, select_passages
from tools import web_tools as web


def test_windows_are_verbatim_keep_limits_and_do_not_claim_completeness():
    source = "Edition 2026\n" + "background\n" * 2000
    source += "Adults only. TARGET PHRASE is discussed here. Excludes children.\n"
    source += "unrelated appendix\n" * 2000
    output = select_passages(source, ["target phrase"], 13000)
    assert "Adults only. TARGET PHRASE is discussed here. Excludes children." in output
    assert "Edition 2026" in output and "omitted text was not supplied" in output
    for start, end, body in re.findall(r"\[Source characters (\d+):(\d+)\]\n(.*?)(?=\n\n\[\.\.\. omitted|$)", output, re.DOTALL):
        assert body == source[int(start):int(end)]
    assert len(output) < 14000


def test_focus_is_literal_missing_is_explicit_and_short_pages_stay_whole():
    source = "prefix " * 1000 + "a.b" + " tail" * 2000
    out = select_passages(source, ["a.*b"], 6000)
    assert "Literal terms not found: ['a.*b']" in out
    assert select_passages("short source", ["absent"], 6000) == "short source"
    for focus in (None, [], "wrong", [None, "x", "z" * 121]):
        pages = [{"content": source}]
        focus_results(pages, focus, 6000)
        assert pages == [{"content": source}]


def test_real_tool_chain_selects_middle_marks_receipt_and_keeps_no_focus_behavior():
    url = "https://example.org/book"
    source = "Title edition 2026\n" + "filler\n" * 6000 + "EXACT CHAPTER. Limitation nearby." + " appendix\n" * 6000
    async def extract(*args):
        return [{"url": url, "raw_content": source}]
    with patch.object(web, "async_is_safe_url", AsyncMock(return_value=True)), \
         patch.object(web, "_ensure_web_plugins_loaded"), \
         patch.object(web, "_resolve_extract_provider", return_value=(object(), None)), \
         patch.object(web, "_extract_safe_urls", side_effect=extract):
        focused = asyncio.run(web.web_extract_tool([url], char_limit=14000, focus=["EXACT CHAPTER"]))
        normal = asyncio.run(web.web_extract_tool([url], char_limit=14000))
    assert "EXACT CHAPTER. Limitation nearby." in json.loads(focused)["results"][0]["content"]
    assert extracted_pages(focused)[0]["truncated"] is True
    spans = extracted_pages(focused)[0]["quote_spans"]
    assert spans and any("EXACT CHAPTER. Limitation nearby." in quote for quote in spans.values())
    assert not json.loads(normal)["results"][0].get("quote_spans")
    assert "selection_source_sha256" not in json.loads(normal)["results"][0]
    assert "SELECTED PASSAGES" not in normal


def test_binary_and_error_entries_cannot_be_disguised_by_window_prefix():
    pages = [{"url": "https://example.org/x", "content": "SQLite format 3\x00" + "x" * 20000},
             {"error": "blocked", "content": "secret " * 10000}]
    before = copy.deepcopy(pages)
    focus_results(pages, ["secret", "SQLite"], 5000)
    assert pages == before


def test_focus_accepts_unicode_whitespace_without_changing_source_offsets():
    source = 'header\n' * 2000 + 'Aged\u00a0over\t80. Exact adjacent limitation.' + ' tail' * 4000
    out = select_passages(source, ['aged over 80'], 6000)
    assert 'Aged\u00a0over\t80. Exact adjacent limitation.' in out
    assert 'Literal terms not found' not in out
    for start, end, body in re.findall(r'\[Source characters (\d+):(\d+)\]\n(.*?)(?=\n\n\[\.\.\. omitted|$)', out, re.DOTALL):
        assert body == source[int(start):int(end)]


def test_transient_unfocused_read_cannot_erase_same_source_focused_receipt():
    url = 'https://example.org/chapter'
    source = 'Edition 2026\n' + 'filler\n' * 2000 + 'TARGET PARAGRAPH. Adjacent limitation.' + ' appendix\n' * 2000
    revised = source.replace('TARGET PARAGRAPH', 'REVISED PARAGRAPH')
    async def extract(*args):
        return [{'url': url, 'raw_content': source}]
    with patch.object(web, 'async_is_safe_url', AsyncMock(return_value=True)), \
         patch.object(web, '_ensure_web_plugins_loaded'), \
         patch.object(web, '_resolve_extract_provider', return_value=(object(), None)), \
         patch.object(web, '_extract_safe_urls', side_effect=extract), transient_scope(True):
        focused = extracted_pages(asyncio.run(web.web_extract_tool([url], char_limit=14000, focus=['TARGET PARAGRAPH'])))
        head_tail = extracted_pages(asyncio.run(web.web_extract_tool([url], char_limit=6000, focus=['x' * 121])))
        assert 'TARGET PARAGRAPH' not in head_tail[0]['content']
        kept = merge_pages(focused, head_tail)
        assert 'TARGET PARAGRAPH. Adjacent limitation.' in kept[0]['content']
        assert kept[0]['retrieved_at'] == focused[0]['retrieved_at']
        source = revised
        changed = extracted_pages(asyncio.run(web.web_extract_tool([url], char_limit=6000)))
        assert merge_pages(kept, changed) == changed
