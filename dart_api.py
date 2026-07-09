"""
Thin DART OpenAPI wrapper: corp codes + single-company accounts.
"""
from __future__ import annotations

import io
import logging
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

DART_API_BASE = "https://opendart.fss.or.kr/api"


class DartClient:
    """DART OpenAPI client for corp_code mapping and financial accounts."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else config.DART_API_KEY
        self.base = DART_API_BASE
        self.session = requests.Session()
        self._stock_to_corp: dict[str, str] = {}
        self._loaded = False

    def download_corp_codes(self, force: bool = False) -> Path:
        """
        Ensure CORPCODE.xml exists at config.CORPCODE_CACHE.
        Downloads ZIP from DART when missing or force=True.
        """
        path = Path(config.CORPCODE_CACHE)
        if path.exists() and not force:
            return path

        if not self.api_key:
            raise ValueError("DART_API_KEY is not set")

        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading CORPCODE.xml from DART…")
        r = self.session.get(
            f"{self.base}/corpCode.xml",
            params={"crtfc_key": self.api_key},
            timeout=60,
        )
        r.raise_for_status()

        content = r.content
        if content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Prefer CORPCODE.xml; otherwise first .xml
                name = None
                for n in zf.namelist():
                    if n.upper().endswith("CORPCODE.XML") or n.endswith("CORPCODE.xml"):
                        name = n
                        break
                if name is None:
                    for n in zf.namelist():
                        if n.lower().endswith(".xml"):
                            name = n
                            break
                if name is None:
                    raise RuntimeError("CORPCODE ZIP has no XML member")
                path.write_bytes(zf.read(name))
        else:
            path.write_bytes(content)

        self._stock_to_corp.clear()
        self._loaded = False
        logger.info("CORPCODE.xml saved to %s", path)
        return path

    def _ensure_map(self) -> None:
        if self._loaded:
            return
        path = self.download_corp_codes(force=False)
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            mapping: dict[str, str] = {}
            for item in root.findall("list"):
                corp_code = (item.findtext("corp_code") or "").strip()
                stock_code = (item.findtext("stock_code") or "").strip()
                if corp_code and stock_code:
                    # stock_code is typically 6 digits for listed firms
                    code6 = stock_code.zfill(6) if stock_code.isdigit() else stock_code
                    mapping[code6] = corp_code
            self._stock_to_corp = mapping
            self._loaded = True
            logger.info("CORPCODE map loaded: %d listed", len(mapping))
        except Exception as e:
            logger.error("Failed to parse CORPCODE.xml: %s", e)
            self._stock_to_corp = {}
            self._loaded = True  # avoid tight retry loops on bad file

    def map_stock_to_corp(self, code6: str) -> Optional[str]:
        """Map 6-digit stock code to DART corp_code, or None."""
        if code6 is None:
            return None
        s = str(code6).strip()
        if s.upper().startswith("A") and len(s) == 7:
            s = s[1:]
        if s.isdigit():
            s = s.zfill(6)
        if not s:
            return None
        self._ensure_map()
        return self._stock_to_corp.get(s)

    def fetch_accounts(
        self,
        corp_code: str,
        bsns_year: int | str,
        reprt_code: str,
    ) -> list[dict]:
        """
        Single-company full accounts (fnlttSinglAcntAll).
        Prefer CFS (consolidated); fall back to OFS.
        Returns list of account dicts, or [] on no data / error.
        """
        if not self.api_key:
            logger.warning("fetch_accounts skipped: no DART_API_KEY")
            return []
        if not corp_code:
            return []

        year = str(bsns_year)
        for fs_div in ("CFS", "OFS"):
            try:
                sleep_sec = float(getattr(config, "DART_SLEEP_SEC", 0.15) or 0)
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                r = self.session.get(
                    f"{self.base}/fnlttSinglAcntAll.json",
                    params={
                        "crtfc_key": self.api_key,
                        "corp_code": corp_code,
                        "bsns_year": year,
                        "reprt_code": str(reprt_code),
                        "fs_div": fs_div,
                    },
                    timeout=20,
                )
                r.raise_for_status()
                data = r.json()
                status = data.get("status")
                if status == "000":
                    items = data.get("list") or []
                    # Tag fs_div so pickers can prefer consolidated if mixed
                    for it in items:
                        if isinstance(it, dict) and "fs_div" not in it:
                            it["fs_div"] = fs_div
                    return items
                if status == "013":
                    # no data for this fs_div — try next
                    continue
                logger.warning(
                    "DART accounts status=%s msg=%s corp=%s year=%s reprt=%s fs=%s",
                    status,
                    data.get("message"),
                    corp_code,
                    year,
                    reprt_code,
                    fs_div,
                )
                return []
            except Exception as e:
                logger.error(
                    "fetch_accounts(%s, %s, %s, %s) failed: %s",
                    corp_code,
                    year,
                    reprt_code,
                    fs_div,
                    e,
                )
                return []
        return []
