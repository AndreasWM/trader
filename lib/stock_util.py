import os
import sys
import csv
import glob
import subprocess
from typing import cast
from pathlib import Path

import pandas_market_calendars as mcal
from datetime import datetime, timedelta
import pytz

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import IBKROrder, MarketOrder
from lib.position import IBKRPosition, ScannerPosition

HOME_DIR_LINUX = '/home/andreas/'
HOME_DIR_WINDOWS = '/mnt/c/Users/moell/'
DATA_DIR = 'Downloads/data/'

class StockUtil:
    def detect_ib_host(self) -> str:
        # 1. Check: Läuft das Skript in WSL?
        if "microsoft" in subprocess.check_output("uname -a", shell=True).decode().lower():
            try:
                # Hol die IP des Windows-Hosts (das Gateway)
                cmd = "ip route show | grep default | awk '{print $3}'"
                host_ip = subprocess.check_output(cmd, shell=True).decode().strip()
                if host_ip:
                    return host_ip
            except Exception:
                pass
        
        # 2. Fallback: Wenn echter Ubuntu-PC oder WSL-Erkennung fehlschlägt
        return "127.0.0.1"
        
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
        return HOME_DIR_LINUX + DATA_DIR

    def _get_data_dir_windows(self) -> str:
        return HOME_DIR_WINDOWS + DATA_DIR

    def get_data_dir(self) -> str:
        if self.detect_ib_host() == "127.0.0.1":
            return self.get_data_dir_linux()
        else:
            return self._get_data_dir_windows()

    def get_latest_file(self, dir: str, pattern: str) -> str:
        pattern = os.path.join(dir, pattern+'*.csv')
        files = glob.glob(pattern)
        
        if not files:
            raise FileNotFoundError(f"Keine Datei mit Muster '{pattern}*.csv' in {dir}")
        
        return max(files, key=os.path.getmtime)
    
    def get_latest_do_not_trade_file(self) -> str:
        return self.get_latest_file(dir=self.get_data_dir(), pattern='DoNotTrade')
    
    def get_latest_watchlist_file(self) -> str:
        return self.get_latest_file(dir=self.get_data_dir(), pattern='Watchlist')
    
    def get_output_file(self, filename: str) -> str:
        return self.get_data_dir() + filename
    
    def ibkr_positions(self, trader: MarketOrder) -> list[IBKRPosition]:
        ibkr_positions = trader.get_stock_positions(timeout=10.0)
        if ibkr_positions is None:
            return []
        else:
            positions = []
            for position in ibkr_positions:
                if position.symbol not in ("WSO B"):
                    positions.append(IBKRPosition(symbol=position.symbol.replace(' ', '.'), exchange=position.exchange, position=int(position.position)))
            return positions
        
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
    
    def calc_qty(self, ibkr_pos: IBKRPosition, scanner_pos: ScannerPosition, capital_per_stock: float) -> int:
        value = abs(ibkr_pos.position) * scanner_pos.price
        capital_diff = capital_per_stock - value
        qty = round(capital_diff / scanner_pos.price)
        return qty

    def create_update_order(self, ibkr_pos: IBKRPosition, scanner_pos: ScannerPosition, capital_per_stock: float, qty: int) -> IBKROrder:
        symbol=cast(str, ibkr_pos.symbol).replace('.', ' ')
        action = "BUY" if ibkr_pos.position * qty > 0 else "SELL"
        qty_abs = abs(qty)
        print(f"Creating update order for {symbol}: action={action}, qty={qty_abs:.2f}, capital_per_stock={capital_per_stock:.2f}, price={scanner_pos.price:.2f}")
        return IBKROrder(
            symbol=symbol,
            qty=qty_abs,
            action=action
        )
    
    def execute_orders(self, trader: MarketOrder, orders: list[IBKROrder], skip_confirm: bool = False) -> bool:
        is_executed = False
        if not orders:
            print("\nℹ️ Keine neuen Orders zu erstellen.")
            return False
        else:
            print(f"\n📋 Ausführen von {len(orders)} Orders")
            if not skip_confirm:
                response = input("Proceed? [Y]/N: ").strip().upper() or "Y"
            else:
                response = "Y"
            if response == 'Y':
                trader.execute(orders)
                is_executed = True
            else:
                print("Abgebrochen durch Benutzer.")
            return is_executed

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
        
        return market_open <= datetime.now(pytz.utc) <= market_close
