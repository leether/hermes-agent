"""Extraction provenance is tool-owned, bounded and request-local."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from gateway.platforms.api_server_evidence import extracted_pages, merge_pages, MAX_PAGE_CHARS, MAX_TOTAL_CHARS
from gateway.platforms.api_server_transient import run_completion, decorate_response


def test_receipts_reject_failure_and_preserve_exact_bounded_body_hash():
    body = 'source body ' * MAX_PAGE_CHARS
    raw = json.dumps({'results': [
        {'url':'https://example.org/ok','content':body},
        {'url':'https://example.org/error','content':body,'error':'denied'},
        {'url':'https://user:password@example.org/private','content':body}]})
    pages=extracted_pages(raw)
    assert len(pages)==1 and pages[0]['truncated']
    assert len(pages[0]['content'])==MAX_PAGE_CHARS
    assert pages[0]['sha256']==hashlib.sha256(pages[0]['content'].encode()).hexdigest()
    capped=merge_pages([], [dict(pages[0],url=f'https://example.org/{i}') for i in range(20)])
    assert sum(len(p['content']) for p in capped)<=MAX_TOTAL_CHARS


def test_receipt_preserves_upstream_excerpt_truncation():
    body = 'Actual extracted source paragraph. ' * 5
    for extra in ({'truncated': True}, {'content': body + '\n── [TRUNCATED] ──\nShowing 100 chars (head) + 30 chars (tail) of 5000 total clean characters.'}):
        source = dict(url='https://example.org/source', content=body)
        source.update(extra)
        receipt = extracted_pages(json.dumps({'results': [source]}))[0]
        assert receipt['truncated'] is True
        assert receipt['content'] == source['content']


def test_quote_refs_require_matching_body_and_hash_and_drop_after_revision():
    quote = 'A literal source statement with sufficient context.'
    absent = 'A forged statement absent from the extracted source.'
    ref = lambda text: '@s' + hashlib.sha256(text.encode()).hexdigest()[:20]
    def receipt(body, spans, digest):
        return extracted_pages(json.dumps({'results': [{
            'url': 'https://example.org/source', 'content': body * 4,
            'quote_spans': spans, 'selection_source_sha256': digest}]}))[0]
    first = receipt(quote, {ref(quote): quote, ref(absent): absent, '@s' + '0' * 20: quote}, 'a' * 64)
    assert first['quote_spans'] == {ref(quote): quote}
    changed = receipt(absent, {ref(quote): quote, ref(absent): absent}, 'b' * 64)
    merged = merge_pages([first], [changed])[0]
    assert merged['quote_spans'] == {ref(absent): absent}


def test_multiple_passages_keep_earlier_quotes_only_when_full_source_hash_matches():
    def receipt(body, source_hash):
        return extracted_pages(json.dumps({'results': [{'url': 'https://example.org/source',
            'content': body * 10, 'selection_source_sha256': source_hash, 'truncated': True}]}))[0]
    first = receipt('Early selected paragraph. ', 'a' * 64)
    second = receipt('Later selected limitation. ', 'a' * 64)
    combined = merge_pages([first], [second])[0]
    assert first['content'] in combined['content'] and second['content'] in combined['content']
    assert combined['sha256'] == hashlib.sha256(combined['content'].encode()).hexdigest()
    assert combined['retrieved_at'] == first['retrieved_at']
    assert merge_pages([combined], [first]) == [combined]
    changed = receipt('A newly revised source document. ', 'b' * 64)
    assert merge_pages([combined], [changed]) == [changed]


@pytest.mark.asyncio
async def test_each_request_collects_only_real_extract_callbacks_and_normal_is_unchanged():
    async def run(**kwargs):
        if kwargs.get('tool_complete_callback'):
            cb=kwargs['tool_complete_callback']
            raw=json.dumps({'results':[{'url':'https://example.org/source','content':'source body '*20}]})
            cb('search','web_search',{},raw)
            if kwargs.get('fetch'):
                cb('extract','web_extract',{},raw)
        return {'final_response':'https://example.org/forged'}, {}
    adapter=SimpleNamespace(_transient_sessions=True,_run_agent=run)
    first,_=await run_completion(adapter,{'fetch':True})
    second,_=await run_completion(adapter,{'fetch':False})
    assert len(first['_transient_pages'])==1 and second['_transient_pages']==[]
    data={'choices':[{'message':{'reasoning_content':'private'}}]}
    decorate_response(adapter,first,data)
    assert data['hermes_evidence']['pages'][0]['url']=='https://example.org/source'
    adapter._transient_sessions=False
    normal,_=await run_completion(adapter,{})
    assert '_transient_pages' not in normal
