from __future__ import annotations

from types import SimpleNamespace

import requests

from api_amadeus import AmadeusClient


class _DummyCache:
    def get(self, endpoint, params):
        return None

    def set(self, endpoint, params, data):
        return None


def _client_without_init() -> AmadeusClient:
    c = AmadeusClient.__new__(AmadeusClient)
    c.cache = _DummyCache()
    c.config = SimpleNamespace(
        base_url="https://test.api.amadeus.com",
        timeout=1.0,
        max_retries=1,
        backoff_factor=0.0,
        verify_ssl=True,
        min_delay_seconds=0.0,
    )
    c._session = requests.Session()
    c._rate_limit = lambda: None
    c._get_access_token = lambda: "dummy"
    return c


def test_get_cheapest_date_search_uses_currency_and_duration(monkeypatch):
    c = _client_without_init()

    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None, verify=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": []}

        return _Resp()

    monkeypatch.setattr(c._session, "request", fake_request)

    c._get_cheapest_date_search(
        origin="BOS",
        destination="CHI",
        period="2026-01-10,2026-01-31",
        currency="EUR",
        min_days=1,
        max_days=15,
    )

    assert captured["method"] == "GET"
    assert captured["url"].endswith("/v1/shopping/flight-dates")
    assert captured["params"]["currency"] == "EUR"
    assert captured["params"]["duration"] == "1,15"
    assert captured["params"]["departureDate"] == "2026-01-10,2026-01-31"


def test_get_cheapest_date_search_omits_duration_when_not_provided(monkeypatch):
    c = _client_without_init()

    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None, verify=None):
        captured["params"] = params

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": []}

        return _Resp()

    monkeypatch.setattr(c._session, "request", fake_request)

    c._get_cheapest_date_search(
        origin="BOS",
        destination="CHI",
        period="2026-01-10,2026-01-31",
        currency="EUR",
    )

    assert "duration" not in captured["params"]
    assert captured["params"]["currency"] == "EUR"

