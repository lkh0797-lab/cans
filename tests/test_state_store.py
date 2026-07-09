import json
from pathlib import Path

import config
import state_store


def test_save_and_load_candidates(tmp_path, monkeypatch):
    p = tmp_path / "last_candidates.json"
    monkeypatch.setattr(config, "LAST_CANDIDATES_FILE", p)
    state_store.save_candidates(
        "2026-07-09",
        [{"code": "005930", "name": "삼성전자", "drawdown_pct": -22.0, "op_yoy_pct": 15.0, "market_cap": 1}],
    )
    codes = state_store.load_yesterday_codes()
    assert codes == {"005930"}
