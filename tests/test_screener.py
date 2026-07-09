import config
from screener import run_screen


def test_run_screen_filters_and_sorts(monkeypatch):
    monkeypatch.setattr(config, "DRAWDOWN_MAX", -20.0)
    monkeypatch.setattr(config, "OP_YOY_MIN", 10.0)
    rows = [
        {"code": "A", "drawdown_pct": -10.0, "op_yoy_pct": 20.0},  # fail dd
        {"code": "B", "drawdown_pct": -25.0, "op_yoy_pct": 5.0},   # fail yoy
        {"code": "C", "drawdown_pct": -30.0, "op_yoy_pct": 12.0},
        {"code": "D", "drawdown_pct": -22.0, "op_yoy_pct": 40.0},
    ]
    out = run_screen(rows)
    assert [r["code"] for r in out] == ["C", "D"]
