from earnings import pick_operating_profit, compute_yoy_from_ops


def test_pick_operating_profit():
    items = [
        {"account_nm": "매출액", "thstrm_amount": "100", "sj_div": "IS"},
        {"account_nm": "영업이익", "thstrm_amount": "1,000", "sj_div": "IS"},
    ]
    assert pick_operating_profit(items) == 1000.0


def test_compute_yoy():
    assert abs(compute_yoy_from_ops(110, 100) - 10.0) < 1e-9
    assert compute_yoy_from_ops(110, 0) is None
