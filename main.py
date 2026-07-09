"""
Daily earnings-dip orchestration: universe → drawdowns → OP YoY → screen → telegram.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

import config
from earnings import attach_op_yoy
from formatter import format_report
from metrics import diff_sets
from prices import attach_drawdowns
from screener import run_screen
from state_store import (
    already_ran_today,
    load_yesterday_codes,
    save_candidates,
    save_last_run,
)
from telegram_sender import TelegramSender
from universe import build_universe

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Stdout + rotating file under config.LOG_FILE."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)


def _try_telegram_error(msg: str) -> None:
    try:
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            TelegramSender().send_error(msg)
    except Exception as e:
        logger.warning("telegram error notify failed: %s", e)


def _combine_source(uni_source: str, price_source: str) -> str:
    u = (uni_source or "").strip() or "?"
    p = (price_source or "").strip() or "?"
    if u == p:
        return u
    return f"{u}/{p}"


def run() -> int:
    """
    Full daily pipeline. Exit 0 on success or intentional skip; 1 on failure.
    """
    setup_logging()
    logger.info("earnings-dip start")

    if config.SKIP_IF_ALREADY_RAN_TODAY and already_ran_today():
        logger.info("already ran successfully today; skip")
        return 0

    if not config.DART_API_KEY:
        msg = "DART_API_KEY not set"
        logger.error(msg)
        _try_telegram_error(msg)
        try:
            save_last_run({"ok": False, "error": msg, "exit": 1})
        except Exception as e:
            logger.warning("save_last_run failed: %s", e)
        return 1

    try:
        rows, as_of, uni_source = build_universe()
        logger.info("universe n=%s as_of=%s source=%s", len(rows), as_of, uni_source)
        if not rows:
            raise RuntimeError(f"empty universe (last source={uni_source})")

        priced, price_source = attach_drawdowns(rows, uni_source)
        source = _combine_source(uni_source, price_source)
        logger.info("priced n=%s price_source=%s report_source=%s", len(priced), price_source, source)
        if not priced:
            raise RuntimeError(
                f"no price/drawdown data (universe_source={uni_source}, price_source={price_source})"
            )

        # Prefilter drawdown before DART to cut API calls
        pre = [
            r
            for r in priced
            if r.get("drawdown_pct") is not None and float(r["drawdown_pct"]) <= config.DRAWDOWN_MAX
        ]
        logger.info(
            "prefilter drawdown<=%s: %s -> %s",
            config.DRAWDOWN_MAX,
            len(priced),
            len(pre),
        )

        with_yoy = attach_op_yoy(pre)
        candidates = run_screen(with_yoy)
        logger.info("candidates n=%s", len(candidates))

        today_codes = {c["code"] for c in candidates}
        yesterday = load_yesterday_codes()
        new_codes, kept_codes, exited_codes = diff_sets(today_codes, yesterday)

        date_str = datetime.now().strftime("%Y-%m-%d")
        report = format_report(
            date=date_str,
            universe_n=len(rows),
            candidates=candidates,
            new_codes=new_codes,
            kept_codes=kept_codes,
            exited_codes=exited_codes,
            source=source,
        )
        logger.info("report ready (%s chars)", len(report))

        try:
            sender = TelegramSender()
        except ValueError as e:
            raise RuntimeError(f"telegram not configured: {e}") from e

        if not sender.send_long_message(report):
            raise RuntimeError("telegram send failed")

        save_candidates(date_str, candidates)
        save_last_run(
            {
                "ok": True,
                "exit": 0,
                "source": source,
                "universe_n": len(rows),
                "priced_n": len(priced),
                "prefilter_n": len(pre),
                "candidates_n": len(candidates),
                "new_n": len(new_codes),
                "kept_n": len(kept_codes),
                "exited_n": len(exited_codes),
                "as_of": as_of,
            }
        )
        logger.info("earnings-dip done ok candidates=%s new=%s", len(candidates), len(new_codes))
        return 0

    except Exception as e:
        logger.exception("earnings-dip failed: %s", e)
        _try_telegram_error(str(e))
        try:
            save_last_run({"ok": False, "error": str(e)[:500], "exit": 1})
        except Exception as se:
            logger.warning("save_last_run failed: %s", se)
        return 1


if __name__ == "__main__":
    sys.exit(run())
