import os
import sys
import subprocess
from enum import Enum
from datetime import datetime
from sklearn.pipeline import islice
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
class OrderBy(Enum):
    INDUSTRY = "industry"
    MARKET_CAP = "market_cap_basic"
    PERF_Y = "Perf.Y"
    SYMBOL = "name"

    def __str__(self):
        return self.value

class PositionPerf:
    def __init__(self, symbol: str, position: int = 0, price: float = 0.0, perf_y: float = 0.0):
        self.symbol = symbol
        self.position = position
        self.price = price
        self.perf_y = perf_y

    def __str__(self):
        return f"Position(symbol={self.symbol}, position={self.position}, price={self.price}, perf_y={self.perf_y})"
    
    def __repr__(self):
        return self.__str__()
    
    def is_long(self) -> bool:
        return self.perf_y > 0
    
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
            
    def scan_list(self, stock_list: list[str]) -> pd.DataFrame:
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
                        'market_cap_basic',
                        'close',
                        'high|1',
                        'low|1',
                        'Perf.YTD',
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
                    "market_cap_basic": "market_cap",
                    "close": "price",
                    "high|1": "high_1",
                    "low|1": "low_1",
                    "Perf.YTD": "perf_ytd",
                    "Ichimoku.Lead1": "lead1",
                    "Ichimoku.Lead2": "lead2",
                })
                
                print(f"✅ Insgesamt {len(scanner_data)} Aktien gescannt")
                return scanner_data

    def query_usa(self, is_long: bool, tickers_to_exclude: list[str], market_cap: int, capital_per_stock: float = 0.0, limit=100) -> list[ScannerPosition]:
        pos_list = []

        if limit > 0:
            cond_limit_size = Column('close') < capital_per_stock
            cond_stocktype = Column('type') == 'stock'
            cond_typespec = Column('subtype') != 'preferred'
            cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE', 'AMEX', 'CBOE'])
            cond_market_cap = Column('market_cap_basic') > market_cap

            conditions = []
            if is_long:
                cond_perf_Y = Column('Perf.Y') > 150
                cond_perf_1M = Column('Perf.1M') > 0
                ichi_lead1 = Column('close') > Column('Ichimoku.Lead1')
                ichi_lead2 = Column('close') > Column('Ichimoku.Lead2')
                ichi_lead1_lead2_1w = Column('Ichimoku.Lead1|60') > Column('Ichimoku.Lead2|1W')
                ichi_close_lead1_1w = Column('close') > Column('Ichimoku.Lead1|1W')
                ichi_lead1_lead2_240 = Column('Ichimoku.Lead1|60') > Column('Ichimoku.Lead2|240')
                ichi_close_lead1_240 = Column('close') > Column('Ichimoku.Lead1|240')
                ichi_lead1_lead2_60 = Column('Ichimoku.Lead1|60') > Column('Ichimoku.Lead2|60')
                ichi_close_lead1_60 = Column('close') > Column('Ichimoku.Lead1|60')
            else:
                cond_perf_Y = Column('Perf.Y') < -10
                cond_perf_1M = Column('Perf.1M') < 0
                ichi_lead1 = Column('close') < Column('Ichimoku.Lead1')
                ichi_lead2 = Column('close') < Column('Ichimoku.Lead2')
                ichi_lead1_lead2_1w = Column('Ichimoku.Lead1|60') < Column('Ichimoku.Lead2|1W')
                ichi_close_lead1_1w = Column('close') < Column('Ichimoku.Lead1|1W')
                ichi_lead1_lead2_240 = Column('Ichimoku.Lead1|60') < Column('Ichimoku.Lead2|240')
                ichi_close_lead1_240 = Column('close') < Column('Ichimoku.Lead1|240')
                ichi_lead1_lead2_60 = Column('Ichimoku.Lead1|60') < Column('Ichimoku.Lead2|60')
                ichi_close_lead1_60 = Column('close') < Column('Ichimoku.Lead1|60')
            conditions = [
                cond_limit_size,
                cond_stocktype,
                cond_typespec,
                cond_exchange,
                cond_market_cap,
                cond_perf_Y,
                cond_perf_1M,
                ichi_lead1,
                ichi_lead2,
                ichi_lead1_lead2_1w,
                ichi_close_lead1_1w,
                ichi_lead1_lead2_240,
                ichi_close_lead1_240,
                ichi_lead1_lead2_60,
                ichi_close_lead1_60,
            ]
            if tickers_to_exclude:
                conditions.append(Column('name').not_in(tickers_to_exclude))
            
            q = Query() \
                .select(
                    'name',
                    'close',
                    'exchange',
                    'type',
                    'market_cap_basic',
                    'Perf.Y',
                    'Perf.1M',
                    'Ichimoku.Lead1|1W',
                    'Ichimoku.Lead2|1W',
                    'Ichimoku.Lead1',
                    'Ichimoku.Lead2',
                    'Ichimoku.Lead1|60',
                    'Ichimoku.Lead2|60',
                    'Ichimoku.Lead1|240',
                    'Ichimoku.Lead2|240',
                ) \
                .where(*conditions) \
                .order_by(OrderBy.PERF_Y.value, ascending=False if is_long else True) \
                .limit(200)
            
            _, scanner_data = q.get_scanner_data(cookies=self._cookies)
            
            scanner_data = scanner_data.drop(columns=['ticker'])
            scanner_data = scanner_data.rename(columns={
                "name": "symbol",
                "close": "price",
            })
            
            for _, row in scanner_data.iterrows():
                symbol = row['symbol']
                price = float(row['price'])
                pos = ScannerPosition(symbol=symbol, price=price, is_long=is_long)
                pos_list.append(pos)

            print(f"📊 Gefundene {'Long' if is_long else 'Short'}-Positionen: {len(pos_list)} (Limit: {limit})")
            result_list = list(islice(pos_list, limit))
            return result_list
        else:
            print("⚠️  Limit für Abfrage ist 0 oder negativ, keine Daten abgefragt")
            return []

    def query_big_usa(self, is_long: bool, tickers_to_exclude: list[str], market_cap: int, capital_per_stock: float = 0.0) -> list[ScannerPosition]:
        pos_list = []

        cond_limit_size = Column('close') < capital_per_stock
        cond_stocktype = Column('type') == 'stock'
        cond_typespec = Column('subtype') != 'preferred'
        cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE', 'AMEX', 'CBOE'])
        cond_market_cap = Column('market_cap_basic') > market_cap

        conditions = []
        if is_long:
            cond_change_percent = Column('change') > 0
            ichi_lead1 = Column('close') > Column('Ichimoku.Lead1')
            ichi_lead2 = Column('close') > Column('Ichimoku.Lead2')
            ichi_lead1_60 = Column('close') > Column('Ichimoku.Lead1|60')
            ichi_lead2_60 = Column('close') > Column('Ichimoku.Lead2|60')
            ichi_lead1_240 = Column('close') > Column('Ichimoku.Lead1|240')
            ichi_lead2_240 = Column('close') > Column('Ichimoku.Lead2|240')
        else:
            cond_change_percent = Column('change') < 0
            ichi_lead1 = Column('close') < Column('Ichimoku.Lead1')
            ichi_lead2 = Column('close') < Column('Ichimoku.Lead2')
            ichi_lead1_60 = Column('close') < Column('Ichimoku.Lead1|60')
            ichi_lead2_60 = Column('close') < Column('Ichimoku.Lead2|60')
            ichi_lead1_240 = Column('close') < Column('Ichimoku.Lead1|240')
            ichi_lead2_240 = Column('close') < Column('Ichimoku.Lead2|240')
        conditions = [
            cond_limit_size,
            cond_stocktype,
            cond_typespec,
            cond_exchange,
            cond_market_cap,
            cond_change_percent,
            ichi_lead1,
            ichi_lead2,
            ichi_lead1_60,
            ichi_lead2_60,
            ichi_lead1_240,
            ichi_lead2_240,
        ]
        if tickers_to_exclude:
            conditions.append(Column('name').not_in(tickers_to_exclude))
        
        q = Query() \
            .select(
                'name',
                'close',
                'change',
                'exchange',
                'type',
                'subtype',
                'market_cap_basic',
                'Ichimoku.Lead1',
                'Ichimoku.Lead2',
                'Ichimoku.Lead1|60',
                'Ichimoku.Lead2|60',
                'Ichimoku.Lead1|240',
                'Ichimoku.Lead2|240',
            ) \
            .where(*conditions) \
            .order_by(OrderBy.MARKET_CAP.value, ascending=False) \
            .limit(200)
        
        _, scanner_data = q.get_scanner_data(cookies=self._cookies)
        
        scanner_data = scanner_data.drop(columns=['ticker'])
        scanner_data = scanner_data.rename(columns={
            "name": "symbol",
            "close": "price",
            "market_cap_basic": "market_cap",
        })
        
        for _, row in scanner_data.iterrows():
            symbol = row['symbol']
            price = float(row['price'])
            market_cap = int(row['market_cap'])
            pos = ScannerPosition(symbol=symbol, price=price, market_cap=market_cap, is_long=is_long)
            pos_list.append(pos)

        print(f"📊 Gefundene {'Long' if is_long else 'Short'}-Positionen: {len(pos_list)}")
        return pos_list

    def get_ratio_bull_bear(self) -> float:
        print("📡 Scanne AMEX:SPY für Bull/Bear Ratio...")
        min_ratio = 0.2
        max_ratio = 0.8
        
        try:
            q = Query() \
                .select(
                    'name',
                    'exchange',
                    'close',
                    'Ichimoku.Lead1',
                    'Ichimoku.Lead2',
                ) \
                .where(
                    Column('name') == 'SPY',
                    Column('exchange') == 'AMEX'
                )
            
            _, scanner_data = q.get_scanner_data(cookies=self._cookies)
            
            if scanner_data is None or scanner_data.empty:
                print("⚠️  Keine Daten für SPY gefunden, verwende Default {max_ratio}")
                return max_ratio
            
            row = scanner_data.iloc[0]
            price = float(row['close'])
            lead1 = float(row['Ichimoku.Lead1'])
            lead2 = float(row['Ichimoku.Lead2'])
            
            min_lead = min(lead1, lead2)
            max_lead = max(lead1, lead2)
            if price <= min_lead:
                ratio = min_ratio
            elif price >= max_lead:
                ratio = max_ratio
            else:
                ratio = min_ratio + (max_ratio - min_ratio) * (price - min_lead) / (max_lead - min_lead)
            
            print(f"  Price: {price:.2f}")
            print(f"  Lead1: {lead1:.2f}, Lead2: {lead2:.2f}")
            print(f"  {'🐻 Bearish' if ratio <= min_ratio else '🐂 Bullish' if ratio >= max_ratio else '🐂 Neutral'} → Ratio: {ratio}")
            
            return ratio
            
        except Exception as e:
            print(f"⚠️  Fehler beim Scannen von SPX500: {e}")
            return 0.7
