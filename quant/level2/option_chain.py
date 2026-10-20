"""Validated option-symbol master loading and deterministic contract resolution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from typing import Any, Optional
from urllib.request import Request, urlopen

import pandas as pd

DEFAULT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

@dataclass(frozen=True)
class OptionContract:
    exchange: str
    underlying: str
    expiry: date
    strike: float
    option_type: str
    symbol: str
    token: str
    lot_size: int
    tick_size: float

class AngelSymbolMaster:
    def __init__(self, cache_path: str = "angel_scrip_master.json", url: str = DEFAULT_MASTER_URL, timeout: int = 30):
        self.cache_path, self.url, self.timeout = cache_path, url, timeout
        self._frame: Optional[pd.DataFrame] = None

    def load(self, force_refresh: bool = False) -> pd.DataFrame:
        if self._frame is not None and not force_refresh: return self._frame.copy()
        payload = None
        if not force_refresh and os.path.isfile(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as stream: payload = json.load(stream)
            except (OSError, ValueError): payload = None
        if payload is None:
            request = Request(self.url, headers={"User-Agent": "AI-TRADING/1.0"})
            with urlopen(request, timeout=self.timeout) as response: payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list) or not payload: raise ValueError("symbol master response is empty or malformed")
            directory = os.path.dirname(os.path.abspath(self.cache_path))
            os.makedirs(directory, exist_ok=True)
            temp = self.cache_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as stream: json.dump(payload, stream)
            os.replace(temp, self.cache_path)
        if not isinstance(payload, list) or not payload: raise ValueError("symbol master cache is empty or malformed")
        self._frame = pd.DataFrame(payload)
        return self._frame.copy()

    @staticmethod
    def _expiry(value: Any) -> Optional[date]:
        if value is None or pd.isna(value) or not str(value).strip(): return None
        text = str(value).strip()
        for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y"):
            try: return datetime.strptime(text.upper(), fmt).date()
            except ValueError: pass
        try: return pd.Timestamp(text).date()
        except (ValueError, TypeError): return None

    def options(self, exchange: str, underlying: str) -> pd.DataFrame:
        frame = self._frame if self._frame is not None else self.load()
        aliases = {"exchange": ("exch_seg", "exchange"), "underlying": ("name", "symbol"),
                   "expiry": ("expiry",), "strike": ("strike",), "option_type": ("instrumenttype", "optiontype"),
                   "symbol": ("symbol", "tradingsymbol"), "token": ("token", "symboltoken"),
                   "lot_size": ("lotsize", "lot_size"), "tick_size": ("tick_size", "ticksize")}
        cols = {}
        for target, candidates in aliases.items():
            cols[target] = next((c for c in candidates if c in frame.columns), None)
        required = ("exchange", "underlying", "expiry", "strike", "option_type", "symbol", "token", "lot_size")
        missing = [key for key in required if cols[key] is None]
        if missing: raise ValueError("symbol master missing required columns: " + ",".join(missing))
        out = pd.DataFrame({key: frame[col] for key, col in cols.items() if col is not None})
        out["exchange"] = out["exchange"].astype(str).str.upper()
        out["underlying"] = out["underlying"].astype(str).str.upper()
        out["option_type"] = out["option_type"].astype(str).str.upper().str.replace("OPT", "", regex=False)
        out["expiry_date"] = out["expiry"].map(self._expiry)
        out["strike"] = pd.to_numeric(out["strike"], errors="coerce") / 100
        out["lot_size"] = pd.to_numeric(out["lot_size"], errors="coerce")
        out = out[(out.exchange == exchange.upper()) & (out.underlying == underlying.upper())]
        out = out[out.option_type.isin(["CE", "PE"]) & out.expiry_date.notna() & out.strike.notna() & (out.lot_size > 0)]
        return out.reset_index(drop=True)

    def nearest_expiry(self, exchange: str, underlying: str, on_date: Optional[date] = None) -> Optional[date]:
        today = on_date or date.today()
        expiries = sorted({d for d in self.options(exchange, underlying).expiry_date if d >= today})
        return expiries[0] if expiries else None

    def resolve(self, exchange: str, underlying: str, expiry: date, strike: float, option_type: str) -> Optional[OptionContract]:
        frame = self.options(exchange, underlying)
        match = frame[(frame.expiry_date == expiry) & (frame.strike.sub(float(strike)).abs() < 0.001) & (frame.option_type == option_type.upper())]
        if match.empty: return None
        row = match.iloc[0]
        tick = row.get("tick_size", 0.05)
        return OptionContract(str(row.exchange), str(row.underlying), row.expiry_date, float(row.strike), str(row.option_type),
                              str(row.symbol), str(row.token), int(row.lot_size), float(tick) if pd.notna(tick) else 0.05)

    @staticmethod
    def atm_strike(spot: float, strike_step: float) -> float:
        if spot <= 0 or strike_step <= 0: raise ValueError("spot and strike step must be positive")
        return round(spot / strike_step) * strike_step
