import os
import sys
from enum import Enum
from tradingview_screener.query import Query
from tradingview_screener.column import Column, col
import pandas as pd
import rookiepy
import shutil
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.position import ScannerPosition

class Performance(Enum):
    Pf_1M = "Perf.1M"
    Pf_1W = "Perf.W"
    Pf_Y = "Perf.Y"

    def __str__(self):
        return self.value
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
            
    def scan_list(self, stock_list: list[str], performance: Performance) -> pd.DataFrame:
        print(f"📡 Scanne {len(stock_list)} Aktien bei TradingView...")
        
        if stock_list is None:
            print("⚠️  Quell-Aktienliste ist leer")
            return pd.DataFrame()
        else:
            all_data = []
            batch_size = 50
            
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                
                conditions = [
                    col('name').isin(batch),
                ]
                q = Query() \
                    .select(
                        'name',
                        'exchange',
                        'close',
                        'change',
                        performance.value,
                        'Recommend.All',
                        'Ichimoku.Lead1',
                        'Ichimoku.Lead2',
                    ) \
                    .where(*conditions)
                
                try:
                    _, scanner_data = q.get_scanner_data(cookies=self._cookies)
                except (TypeError, AttributeError):
                    print(f"  ⚠️  Fehler bei Batch {i//batch_size + 1}")
                    continue
                
                if scanner_data is not None and not scanner_data.empty:
                    all_data.append(scanner_data)
                    print(f"  ✓ Batch {i//batch_size + 1}: {len(scanner_data)} Aktien")
        
            if not all_data:
                print("⚠️  Keine Daten gefunden")
                return pd.DataFrame()
            else:
                scanner_data = pd.concat(all_data, ignore_index=True)
                
                scanner_data = scanner_data.drop(columns=['ticker'], errors='ignore')
                scanner_data = scanner_data.rename(columns={
                    "name": "symbol",
                    "close": "price",
                    performance.value: "perf",
                    "Recommend.All": "tech_rating",
                    "Ichimoku.Lead1": "lead1",
                    "Ichimoku.Lead2": "lead2",
                })
                
                print(f"✅ Insgesamt {len(scanner_data)} Aktien gescannt")
                return scanner_data

    def query_us_largecaps(self, tickers_to_exclude: list[str], market_cap: int, performance: Performance,
                           length: int, capital_per_stock: float, ascending: bool) -> list[ScannerPosition]:
        cond_limit_size = Column('close') < capital_per_stock
        cond_stocktype = Column('type') == 'stock'
        cond_typespec = Column('subtype') != 'preferred'
        cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE', 'AMEX', 'CBOE'])
        cond_market_cap = Column('market_cap_basic') > market_cap

        conditions = [
            cond_limit_size,
            cond_stocktype,
            cond_typespec,
            cond_exchange,
            cond_market_cap,
        ]
        if tickers_to_exclude:
            conditions.append(Column('name').not_in(tickers_to_exclude))
        
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
                performance.value,
            ) \
            .where(*conditions) \
            .order_by(performance.value, ascending=ascending) \
            .limit(length)
        
        _, scanner_data = q.get_scanner_data(cookies=self._cookies)
        
        scanner_data = scanner_data.drop(columns=['ticker'])
        scanner_data = scanner_data.rename(columns={
            "name": "symbol",
            "close": "price",
            performance.value: "perf",
        })
        
        pos_list = []
        for _, row in scanner_data.iterrows():
            symbol = row['symbol']
            price = float(row['price'])
            premarket_change = float(row['premarket_change'])
            postmarket_change = float(row['postmarket_change'])
            perf = float(row['perf'])
            pos = ScannerPosition(symbol=symbol, price=price, premarket_change=premarket_change, postmarket_change=postmarket_change, perf=perf)
            pos_list.append(pos)

        return pos_list
