import os
import sys
import csv
import glob
from typing import cast
from pathlib import Path

import pandas_market_calendars as mcal
from datetime import datetime, timedelta
import pytz

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import IBKROrder, MarketOrder
from lib.position import IBKRPosition

class StockUtil:
    def create_text_file(self, text: str, filename: str | Path):
        with open(filename, 'w') as f:
            f.write(text)

    def read_symbols(self, path: str) -> list[str]:
        symbols = []
        
        with open(path, 'r', encoding='utf-8') as datei:
            csv_reader = csv.DictReader(datei)
            
            for line in csv_reader:
                if 'Symbol' in line:
                    symbols.append(line['Symbol'])
        
        return symbols
    
    def get_data_dir_linux(self) -> str:
        return '/home/andreas/github/trader/data'

    def _get_data_dir_windows(self) -> str:
        return '/mnt/c/Users/moell/Downloads/trader/data'

    def get_data_dir(self, trader: MarketOrder) -> str:
        if trader.detect_ib_host() == "127.0.0.1":
            return self.get_data_dir_linux()
        else:
            return self._get_data_dir_windows()

    def get_latest_watchlist_file(self, dir: str) -> str:
        pattern = os.path.join(dir, 'Watchlist*.csv')
        files = glob.glob(pattern)
        
        if not files:
            raise FileNotFoundError(f"Keine Datei mit Muster 'Watchlist*.csv' in {dir}")
        
        return max(files, key=os.path.getmtime)
    
    def ibkr_positions(self, trader: MarketOrder) -> list[IBKRPosition]:
        ibkr_positions = trader.get_stock_positions(timeout=10.0)
        if ibkr_positions is None:
            return []
        else:
            positions = []
            for position in ibkr_positions:
                positions.append(IBKRPosition(symbol=position.symbol.replace(' ', '.'), exchange=position.exchange, position=int(position.position)))
            return positions
        
    def create_invest_order(self, symbol: str, price: float, is_long: bool, capital_per_stock: float) -> IBKROrder:
        symbol=cast(str, symbol).replace('.', ' ')
        qty = round(capital_per_stock / price)
        action = "BUY" if is_long else "SELL"
        print(f"Creating invest order for {symbol}: action={action}, qty={qty:.2f}, capital_per_stock={capital_per_stock:.2f}, price={price:.2f}")
        return IBKROrder(
            symbol=symbol,
            qty=qty,
            action=action
        )
    
    def create_close_order(self, p: IBKRPosition) -> IBKROrder:
        symbol=p.symbol.replace('.', ' ')
        qty = abs(p.position)
        action = "SELL" if p.position > 0 else "BUY"
        print(f"Creating close order for {symbol}: action={action}, quantity={qty}")
        return IBKROrder(
            symbol=symbol,
            qty=qty,
            action=action
        )
    
    def execute_orders(self, trader: MarketOrder, orders: list[IBKROrder], skip_confirm: bool = False):
        if not orders:
            print("\nℹ️ Keine neuen Orders zu erstellen.")
            return
        else:
            print(f"\n📋 Ausführen von {len(orders)} Orders")
            if not skip_confirm:
                response = input("Proceed? [Y]/N: ").strip().upper() or "Y"
            else:
                response = "Y"
            if response == 'Y':
                trader.execute(orders)
            else:
                print("Abgebrochen durch Benutzer.")

    def is_market_open(self, market: str = "NASDAQ") -> bool:
        cal = mcal.get_calendar(market)
        
        ny_tz = pytz.timezone("America/New_York")
        now_ny = datetime.now(ny_tz)
        today = now_ny.date()
        
        schedule = cal.schedule(
            start_date=today.isoformat(),
            end_date=today.isoformat()
        )
        
        if schedule.empty:
            return False
        
        market_open  = schedule.iloc[0]["market_open"].to_pydatetime()
        market_close = schedule.iloc[0]["market_close"].to_pydatetime()
        
        return market_open - timedelta(minutes=15) <= datetime.now(pytz.utc) <= market_close
