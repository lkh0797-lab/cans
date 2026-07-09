from __future__ import annotations


def drawdown_pct(close: float, high_52w: float) -> float | None:
    if high_52w is None or close is None:
        return None
    if high_52w <= 0:
        return None
    return (float(close) / float(high_52w) - 1.0) * 100.0


def op_yoy_pct(current_op: float, year_ago_op: float) -> float | None:
    if current_op is None or year_ago_op is None:
        return None
    if float(year_ago_op) <= 0:
        return None
    return (float(current_op) / float(year_ago_op) - 1.0) * 100.0


def diff_sets(today: set[str], yesterday: set[str]) -> tuple[set[str], set[str], set[str]]:
    today = set(today)
    yesterday = set(yesterday)
    return today - yesterday, today & yesterday, yesterday - today
