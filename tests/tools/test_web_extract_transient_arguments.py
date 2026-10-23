import json
import pytest

from agent.transient_session import transient_scope
from tools import web_tools
from tools.web_tools_extract import _extract_argument_urls


@pytest.mark.parametrize('arguments', [
    {'url': 'https://example.org/page'},
    {'url': '["https://example.org/page"]'},
    {'urls': '["https://example.org/page"]'},
])
def test_transient_alias_dispatch_keeps_original_validation_path(monkeypatch, arguments):
    seen=[]
    async def extract(urls, **kwargs):
        seen.extend(urls)
        return [{'url': url, 'content': 'Public synthetic page. '*10} for url in urls]
    monkeypatch.setattr(web_tools, '_get_extract_backend', lambda: 'fixture')
    monkeypatch.setattr(web_tools, '_ensure_web_plugins_loaded', lambda: None)
    class Provider:
        async def extract(self, urls, **kwargs):return await extract(urls, **kwargs)
    monkeypatch.setattr(web_tools, '_resolve_extract_provider', lambda backend: (Provider(),None))
    async def safe(url):return True
    monkeypatch.setattr(web_tools, 'async_is_safe_url', safe)
    async def dispatch(provider, urls, format):return await provider.extract(urls)
    monkeypatch.setattr(web_tools, '_extract_safe_urls', dispatch)
    with transient_scope(True):
        result=json.loads(web_tools.registry.dispatch('web_extract', arguments))
    assert seen==['https://example.org/page']
    assert result['results'][0]['content'].startswith('Public synthetic')
    assert _extract_argument_urls(arguments)==[]


def test_transient_alias_preserves_private_url_gate(monkeypatch):
    async def unsafe(url):return False
    monkeypatch.setattr(web_tools,'async_is_safe_url',unsafe)
    def forbidden():raise AssertionError('provider must not be consulted')
    monkeypatch.setattr(web_tools,'_get_extract_backend',forbidden)
    with transient_scope(True):
        result=json.loads(web_tools.registry.dispatch('web_extract',{'url':'http://127.0.0.1/private'}))
    assert 'private or internal' in result['results'][0]['error']


@pytest.mark.parametrize('value', ['[broken', None, 17, 'x'*10001])
def test_bad_dialects_do_not_become_fetches(value):
    with transient_scope(True):assert _extract_argument_urls({'url':value})==[]


def test_canonical_list_behavior_and_five_url_cap_are_unchanged():
    items=['https://example.org/'+str(i) for i in range(7)]
    assert _extract_argument_urls({'urls':items})==items[:5]
    with transient_scope(True):
        assert _extract_argument_urls({'url':json.dumps(items)})==items[:5]
