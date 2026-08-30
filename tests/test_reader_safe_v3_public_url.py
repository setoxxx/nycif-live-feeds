from scripts.build_maplibre_reader_safe_v03 import safe_public_url


def test_reader_safe_preserves_nested_source_url():
    event = {
        "source": {
            "dataset": "nyc-parks-bigapps-events",
            "source_event_id": "123",
            "source_url": "https://www.nycgovparks.org/events/2026/08/30/example",
        }
    }
    assert safe_public_url(event) == "https://www.nycgovparks.org/events/2026/08/30/example"


def test_reader_safe_prefers_explicit_top_level_public_url():
    event = {
        "public_url": "https://example.org/public-event",
        "source": {"source_url": "https://example.org/source-event"},
    }
    assert safe_public_url(event) == "https://example.org/public-event"


def test_reader_safe_rejects_non_http_source_url():
    event = {"source": {"source_url": "javascript:alert(1)"}}
    assert safe_public_url(event) is None
