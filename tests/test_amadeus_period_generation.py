from datetime import datetime

from api_amadeus import AmadeusClient


def _client_without_init() -> AmadeusClient:
    # _generate_periods doesn't depend on any instance state; bypass __init__ so
    # tests don't touch cache/airports/config.
    return AmadeusClient.__new__(AmadeusClient)


def test_generate_periods_clamps_and_splits_by_month():
    c = _client_without_init()

    start = datetime(2026, 1, 10)
    end = datetime(2026, 3, 5)

    assert c._generate_periods(start, end) == [
        "2026-01-10,2026-01-31",
        "2026-02-01,2026-02-28",
        "2026-03-01,2026-03-05",
    ]


def test_generate_periods_single_month_keeps_window():
    c = _client_without_init()

    start = datetime(2026, 2, 5)
    end = datetime(2026, 2, 20)

    assert c._generate_periods(start, end) == ["2026-02-05,2026-02-20"]


def test_generate_periods_end_before_start_returns_empty():
    c = _client_without_init()

    start = datetime(2026, 2, 5)
    end = datetime(2026, 2, 4)

    assert c._generate_periods(start, end) == []

