from creon_client import to_creon_code, from_creon_code


def test_to_creon_code():
    assert to_creon_code("005930") == "A005930"
    assert to_creon_code("A005930") == "A005930"


def test_from_creon_code():
    assert from_creon_code("A005930") == "005930"
    assert from_creon_code("005930") == "005930"
