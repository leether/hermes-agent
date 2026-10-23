"""Adjacent concepts can share a bounded quote without stitching omissions."""
from tools.web_extract_quotes import attach_quote_spans, quote_ref


def test_sentence_end_alternative_covers_adjacent_concepts_within_quote_limit():
    body = ('Preface ' * 40 + 'AnchorA names the components. ' + 'intermediate words ' * 24
            + 'AnchorB names the dimensions. ' + 'Unrelated tail ' * 30)
    pages = [{'content': body}]
    attach_quote_spans(pages, ['AnchorA', 'AnchorB'])
    spans = pages[0]['quote_spans']
    assert any('AnchorA' in q and 'AnchorB names the dimensions.' in q for q in spans.values())
    assert all(20 <= len(q) <= 600 and q in body and ref == quote_ref(q) for ref, q in spans.items())


def test_alternatives_never_bridge_an_omission_or_change_no_focus_behavior():
    body = 'AnchorA source sentence. [... omitted source text ...] AnchorB source sentence.'
    pages = [{'content': body}]
    attach_quote_spans(pages, ['AnchorA', 'AnchorB'])
    assert all('[...' not in q for q in pages[0].get('quote_spans', {}).values())
    ordinary = [{'content': 'Source without focus.'}]
    attach_quote_spans(ordinary, None)
    assert ordinary == [{'content': 'Source without focus.'}]
