"""Functional preservation probes for aicask HLP-001; no real network or provider."""
import base64
import importlib

import pytest


def _adapter_class():
    try:
        module = importlib.import_module('gateway.platforms.wecom')
    except ModuleNotFoundError as exc:
        if exc.name != 'gateway.platforms.wecom':
            raise
        module = importlib.import_module('plugins.platforms.wecom.adapter')
    return module.WeComAdapter


@pytest.mark.parametrize('encoding', ['base64', 'hex'])
def test_ops_wecom_decrypts_both_key_encodings(encoding):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = bytes(range(32))
    plaintext = b'functional attachment payload'
    padding = 32 - len(plaintext) % 32
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    ciphertext = encryptor.update(plaintext + bytes([padding]) * padding) + encryptor.finalize()
    encoded = key.hex() if encoding == 'hex' else base64.b64encode(key).decode()
    assert _adapter_class()._decrypt_file_bytes(ciphertext, encoded) == plaintext


@pytest.mark.asyncio
@pytest.mark.parametrize('shape', ['file', 'mixed-file', 'mixed-video', 'quoted-mixed-file', 'quoted-video', 'appmsg-file'])
async def test_ops_wecom_retains_nested_attachments(shape, monkeypatch):
    from gateway.config import PlatformConfig
    adapter = _adapter_class()(PlatformConfig(enabled=True))
    kind = 'video' if 'video' in shape else 'file'
    item = {'msgtype':kind, kind:{'url':'https://example.invalid/fixture'}}
    if shape == 'appmsg-file':
        payload = {'msgtype':'appmsg', 'appmsg':item}
    elif shape.startswith('quoted-mixed'):
        payload = {'msgtype':'text', 'text':{'content':'question'}, 'quote':{'msgtype':'mixed', 'mixed':{'msg_item':[item]}}}
    elif shape.startswith('quoted'):
        payload = {'msgtype':'text', 'text':{'content':'question'}, 'quote':item}
    elif shape.startswith('mixed'):
        payload = {'msgtype':'mixed', 'mixed':{'msg_item':[{'msgtype':'text','text':{'content':'question'}},item]}}
    else:
        payload = item
    calls = []
    async def cache(media_kind, ref, **kwargs):
        calls.append((media_kind,ref['url']))
        return '/isolated/attachment', 'video/mp4' if media_kind == 'video' else 'application/pdf'
    monkeypatch.setattr(adapter, '_cache_media', cache)
    paths, types = await adapter._extract_media(payload)
    assert paths == ['/isolated/attachment']
    assert types == ['video/mp4' if kind == 'video' else 'application/pdf']
    assert calls == [(kind,'https://example.invalid/fixture')]


def test_ops_wecom_retains_quoted_mixed_text():
    text,reply = _adapter_class()._extract_text({'msgtype':'text','text':{'content':'question'},'quote':{'msgtype':'mixed','mixed':{'msg_item':[{'msgtype':'text','text':{'content':'quoted document explanation'}}]}}})
    assert text == 'question'
    assert reply == 'quoted document explanation'


@pytest.mark.asyncio
async def test_ops_media_metadata_never_logs_reference_values(caplog):
    import logging
    from gateway.config import PlatformConfig
    adapter = _adapter_class()(PlatformConfig(enabled=True))
    caplog.set_level(logging.INFO)
    result = await adapter._extract_media({'msgtype':'file','file':{'media_id':'private-media-value','aeskey':'private-aes-value'}})
    assert result == ([],[])
    assert 'has_media_id' in caplog.text and 'has_aeskey' in caplog.text
    assert 'private-media-value' not in caplog.text and 'private-aes-value' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('url',['https://example.invalid/document?secret=private-query-value','http://['],ids=['query','malformed-url'])
async def test_ops_media_download_failure_redacts_query_and_exception(caplog,monkeypatch,url):
    import logging
    from gateway.config import PlatformConfig
    adapter = _adapter_class()(PlatformConfig(enabled=True))
    caplog.set_level(logging.DEBUG)
    async def download(url,max_bytes):
        raise ValueError('transport failure: '+url)
    monkeypatch.setattr(adapter,'_download_remote_bytes',download)
    result = await adapter._cache_media('file',{'url':url})
    assert result is None
    assert 'private-query-value' not in caplog.text
