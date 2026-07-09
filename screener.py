from __future__ import annotations

import config


def run_screen(rows: list[dict]) -> list[dict]:
    passed = []
    for r in rows:
        dd = r.get("drawdown_pct")
        yoy = r.get("op_yoy_pct")
        if dd is None or yoy is None:
            continue
        if dd <= config.DRAWDOWN_MAX and yoy >= config.OP_YOY_MIN:
            passed.append(r)
    passed.sort(key=lambda x: (x["drawdown_pct"], -x["op_yoy_pct"]))
    return passed
