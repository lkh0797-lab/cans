from __future__ import annotations

from typing import Any


def _cap_str(market_cap: float | int | None) -> str:
    if not market_cap:
        return "-"
    uk = float(market_cap) / 1e8  # 억
    if uk >= 10000:
        return f"{uk/10000:.1f}조"
    return f"{uk:.0f}억"


def _line(c: dict[str, Any]) -> str:
    return (
        f"• {c['code']} {c.get('name', '')}  "
        f"고점대비 {c['drawdown_pct']:+.1f}%  "
        f"OP YoY {c['op_yoy_pct']:+.1f}%  "
        f"시총 {_cap_str(c.get('market_cap'))}"
    )


def format_report(
    *,
    date: str,
    universe_n: int,
    candidates: list[dict[str, Any]],
    new_codes: set[str],
    kept_codes: set[str],
    exited_codes: set[str],
    source: str,
) -> str:
    by_code = {c["code"]: c for c in candidates}
    lines = [
        f"📉 어닝+낙폭 스크리닝  {date}",
        f"유니버스 {universe_n} · 후보 {len(candidates)} · 신규 {len(new_codes)}  |  source={source}",
        "",
        "⭐ 신규 진입",
    ]
    new_list = [by_code[c] for c in sorted(new_codes) if c in by_code]
    if new_list:
        lines.extend(_line(c) for c in new_list)
    else:
        lines.append("• (없음)")

    lines += ["", f"📋 유지 ({len(kept_codes)})"]
    kept_list = [by_code[c] for c in sorted(kept_codes) if c in by_code]
    if kept_list:
        lines.extend(_line(c) for c in kept_list)
    else:
        lines.append("• (없음)")

    lines += ["", f"↩ 이탈 ({len(exited_codes)}): " + (", ".join(sorted(exited_codes)) if exited_codes else "없음")]
    return "\n".join(lines)
