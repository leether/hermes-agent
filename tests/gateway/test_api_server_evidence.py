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
