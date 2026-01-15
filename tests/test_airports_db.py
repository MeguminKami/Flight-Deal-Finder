from airports import get_airport_db


def test_airport_db_loads_and_can_lookup_by_iata():
    db = get_airport_db()

    # airports.json in this repo includes ALG on the first lines
    alg = db.get_airport("ALG")
    assert alg is not None
    assert alg.iata == "ALG"
    assert alg.city


def test_airports_dropdown_returns_pairs():
    db = get_airport_db()
    items = db.get_airports_for_dropdown()
    assert isinstance(items, list)
    assert items  # non-empty

    label, value = items[0]
    assert isinstance(label, str)
    assert isinstance(value, str)
    assert len(value) == 3
