from formatter import format_report


def test_format_report_highlights_new():
    cands = [
        {
            "code": "005930",
            "name": "삼성전자",
            "drawdown_pct": -23.1,
            "op_yoy_pct": 18.0,
            "market_cap": 400_000_000_000_000,
        }
    ]
    text = format_report(
        date="2026-07-09",
        universe_n=248,
        candidates=cands,
        new_codes={"005930"},
        kept_codes=set(),
        exited_codes={"000660"},
        source="CREON",
    )
    assert "신규" in text
    assert "005930" in text
    assert "CREON" in text
    assert "000660" in text
