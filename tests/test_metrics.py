from metrics import drawdown_pct, op_yoy_pct, diff_sets


def test_drawdown_pct_basic():
    assert abs(drawdown_pct(80.0, 100.0) - (-20.0)) < 1e-9


def test_drawdown_pct_invalid():
    assert drawdown_pct(100.0, 0.0) is None
    assert drawdown_pct(100.0, -1.0) is None


def test_op_yoy_pct_basic():
    assert abs(op_yoy_pct(110.0, 100.0) - 10.0) < 1e-9


def test_op_yoy_pct_nonpositive_base():
    assert op_yoy_pct(50.0, 0.0) is None
    assert op_yoy_pct(50.0, -10.0) is None


def test_diff_sets():
    new, kept, exited = diff_sets({"A", "B", "C"}, {"B", "C", "D"})
    assert new == {"A"}
    assert kept == {"B", "C"}
    assert exited == {"D"}
