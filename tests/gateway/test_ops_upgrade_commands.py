"""Functional preservation probes for aicask HLP-002."""
from pathlib import Path

import pytest


@pytest.mark.parametrize('text', ['/approve always', '\u2060/APPROVE always\u2060', '\uff0fapprove always'])
def test_ops_unicode_command_retains_name_and_arguments(text):
    from gateway.platforms.base import MessageEvent
    event = MessageEvent(text=text)
    assert event.is_command() is True
    assert event.get_command() == 'approve'
    assert event.get_command_args() == 'always'


@pytest.mark.parametrize('filename', ['长中文文件名_' * 100 + '.docx', '%E8%AE%BA%E8%AF%81' * 100 + '.docx'],ids=['long-unicode','percent-encoded'])
def test_ops_document_cache_preserves_content_without_unsafe_filename(filename):
    from gateway.platforms.base import cache_document_from_bytes
    path = Path(cache_document_from_bytes(b'fixture payload', filename))
    assert path.read_bytes() == b'fixture payload'
    assert path.suffix == '.docx'
    assert path.name.isascii()
    assert len(path.name.encode()) <= 240


def test_ops_opaque_cache_preserves_original_display_name():
    from gateway.platforms.base import cache_media_bytes
    original = '原始附件文件名_' * 30 + '.docx'
    cached = cache_media_bytes(b'fixture document', filename=original, mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert cached.display_name == original
    assert Path(cached.path).name.isascii()
