import os
import sys
from enum import Enum
from tradingview_screener.query import Or, Query
from tradingview_screener.column import Column, col
import pandas as pd
import rookiepy
import shutil
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.position import ScannerPosition

class TV_Scanner:
    def __init__(self):
        # Erkennung der Umgebung
        if self.is_wsl():
            print("🔍 WSL erkannt. Nutze Windows-Cookie-Mapping...")
            self._cookies = self.load_wsl_cookies()
        else:
            print("🔍 Natives Linux erkannt. Nutze Standardpfade...")
            try:
                cookies_raw = rookiepy.chrome(['.tradingview.com'])
                self._cookies = rookiepy.to_cookiejar(cookies_raw)
            except Exception as e:
                print(f"❌ Fehler beim Laden der nativen Cookies: {e}")
                self._cookies = None

    def is_wsl(self) -> bool:
        """Prüft, ob das Skript innerhalb von WSL läuft."""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except:
            return False

    def load_wsl_cookies(self):
        """Kopiert Windows-Cookies in das WSL-Dateisystem und lädt sie."""
        win_user = "moell"
        # Pfade definieren
        win_cookie_path = Path(f"/mnt/c/Users/{win_user}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies")
        linux_chrome_dir = Path.home() / ".config/google-chrome/Default/Network"
        linux_cookie_file = linux_chrome_dir / "Cookies"

        try:
            # 1. Zielverzeichnis sicherstellen
            linux_chrome_dir.mkdir(parents=True, exist_ok=True)
            
            # 2. Profil-Check (Default vs Profile 1)
            final_win_path = win_cookie_path
            if not final_win_path.exists():
                alt_path = Path(str(win_cookie_path).replace("Default", "Profile 1"))
                if alt_path.exists():
                    final_win_path = alt_path
                else:
                    raise FileNotFoundError(f"Windows Cookie-Datei nicht gefunden unter {win_cookie_path}")

            # 3. Kopieren (shutil.copy2 erhält Metadaten, shutil.copy ist oft unproblematischer bei Rechten)
            # Wir nutzen hier copy, um Schreibrechte-Probleme im Ziel zu minimieren
            shutil.copy(str(final_win_path), str(linux_cookie_file))
            
            # 4. Laden via rookiepy (sucht standardmäßig in ~/.config/google-chrome)
            cookies_raw = rookiepy.chrome([".tradingview.com"])
            return rookiepy.to_cookiejar(cookies_raw)

        except Exception as e:
            print(f"❌ WSL-Cookie-Fehler: {e}")
            return None
        
    def safe_float(self, value, default=0.0):
        return float(value) if value is not None else default
    
    def always_true(self):
        return Column("exchange") != "INVALID"

    def query_us_largecaps(self, tickers_to_exclude: list[str], market_cap: int,
                           length: int, capital_per_stock: float, is_long: bool) -> list[ScannerPosition]:
        column_perf_ytd = 'Perf.YTD'
        cond_limit_size = Column('close') < capital_per_stock
        cond_stocktype = Column('type').isin(['stock','dr'])
        cond_subtype = Column('subtype') != 'preferred'
        cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE', 'AMEX', 'CBOE'])
        cond_market_cap = Column('market_cap_basic') > market_cap
        tech_cond_buy_1h = Column('Recommend.All|60') >= 0.1 if is_long else Column('Recommend.All|60') <= -0.1
        tech_cond_buy_4h = Column('Recommend.All|240') >= 0.1 if is_long else Column('Recommend.All|240') <= -0.1
        tech_cond_buy_1D = Column('Recommend.All') >= 0.1 if is_long else Column('Recommend.All') <= -0.1
        tech_cond_buy_1W = Column('Recommend.All|1W') >= 0.1 if is_long else Column('Recommend.All|1W') <= -0.1
        tech_cond_buy_1M = Column('Recommend.All|1M') >= 0.1 if is_long else Column('Recommend.All|1M') <= -0.1
        cond_perf_ytd = Column(column_perf_ytd) > 0.0 if is_long else Column(column_perf_ytd) < 0.0
        conditions = [
            cond_limit_size,
            cond_stocktype,
            cond_subtype,
            cond_exchange,
            cond_market_cap,
            tech_cond_buy_1h,
            tech_cond_buy_4h,
            tech_cond_buy_1D,
            tech_cond_buy_1W,
            tech_cond_buy_1M,
            cond_perf_ytd
        ]
        if tickers_to_exclude:
            conditions.append(Column('name').not_in(tickers_to_exclude))
        
        premarket_col = Column('premarket_change')
        direction_cond = premarket_col > 0.0 if is_long else premarket_col < 0.0
        q = Query() \
            .select(
                'name',
                'close',
                'premarket_change',
                'postmarket_change',
                'exchange',
                'type',
                'subtype',
                'market_cap_basic',
            ) \
            .where(*conditions) \
            .where2(Or(direction_cond, premarket_col.empty())) \
            .order_by(column_perf_ytd, ascending=False if is_long else True) \
            .limit(length)
        
        _, scanner_data = q.get_scanner_data(cookies=self._cookies)
        
        scanner_data = scanner_data.drop(columns=['ticker'])
        scanner_data = scanner_data.rename(columns={
            "name": "symbol",
            "close": "price",
        })
        
        pos_list = []
        for _, row in scanner_data.iterrows():
            symbol = row['symbol']
            price = self.safe_float(row['price'])
            premarket_change = self.safe_float(row['premarket_change'])
            postmarket_change = self.safe_float(row['postmarket_change'])
            exchange = row['exchange']
            pos = ScannerPosition(symbol=symbol, is_long=is_long, price=price,
                                  premarket_change=premarket_change, postmarket_change=postmarket_change, exchange=exchange)
            pos_list.append(pos)

        return pos_list
