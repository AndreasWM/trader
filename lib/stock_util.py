import os
import sys
import pandas as pd
import csv
import glob
from typing import cast

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.tv_scanner import TV_Scanner
from lib.ibkr_market_order import IBKROrder, MarketOrder
from lib.position import IBKRPosition, ScannerPosition

class StockUtil:
    def get_exchanges(self, symbols: list[str]) -> list[dict]:
        sc = TV_Scanner()
        results = sc.scan_list(stock_list=symbols)
        if isinstance(results, pd.DataFrame) and not results.empty:
            return results[['symbol', 'exchange']].to_dict('records')
        else:
            return []
        
    def create_watchlist_file(self, symbols: list[str], filename: str = 'watchlist.txt'):
        watchlist_lines = []
        if symbols:
            pairs = self.get_exchanges(symbols)
            
            # TradingView Format: EXCHANGE:SYMBOL
            watchlist_lines = [f"{pair['exchange']}:{pair['symbol']}" for pair in pairs]
            
            # In Datei schreiben
            with open(filename, 'w') as f:
                f.write('\n'.join(watchlist_lines))
            
        return watchlist_lines

    def read_symbols(self, path: str) -> list[str]:
        symbols = []
        
        with open(path, 'r', encoding='utf-8') as datei:
            csv_reader = csv.DictReader(datei)
            
            for line in csv_reader:
                if 'Symbol' in line:
                    symbols.append(line['Symbol'])
        
        return symbols

    def get_latest_watchlist_file(self, trader: MarketOrder) -> str:
        if trader.detect_ib_host() == "127.0.0.1":
            directory = '/home/andreas/github/trading_batch/data'
        else:
            directory = '/mnt/c/Users/moell/Downloads/trading_batch/data'
        pattern = os.path.join(directory, 'Watchlist*.csv')
        files = glob.glob(pattern)
        
        if not files:
            raise FileNotFoundError(f"Keine Datei mit Muster 'Watchlist*.csv' in {directory}")
        
        return max(files, key=os.path.getmtime)
    
    def ibkr_positions(self, trader: MarketOrder) -> list[IBKRPosition]:
        ibkr_positions = trader.get_stock_positions(timeout=10.0)
        if ibkr_positions is None:
            return []
        else:
            positions = []
            for position in ibkr_positions:
                positions.append(IBKRPosition(symbol=position.symbol.replace(' ', '.'), position=int(position.position)))
            return positions
        
    def create_invest_order(self, p: ScannerPosition, capital_per_stock: float) -> IBKROrder:
        symbol=cast(str, p.symbol).replace('.', ' ')
        quantity = round(capital_per_stock / p.price)
        action = "BUY"
        # print(f"Creating invest order for {symbol}: action={action}, quantity={quantity:.2f}")
        return IBKROrder(
            symbol=symbol,
            qty=quantity,
            action=action
        )
    
    def create_close_order(self, p: IBKRPosition) -> IBKROrder:
        symbol=p.symbol.replace('.', ' ')
        quantity = abs(p.position)
        action = "SELL" if p.position > 0 else "BUY"
        print(f"Creating close order for {symbol}: action={action}, quantity={quantity}")
        return IBKROrder(
            symbol=symbol,
            qty=quantity,
            action=action
        )
    
    def execute_orders(self, trader: MarketOrder, orders: list[IBKROrder]):
        if not orders:
            print("\nℹ️ Keine neuen Orders zu erstellen.")
            return
        else:
            print(f"\n📋 Ausführen von {len(orders)} Orders")
            response = input("Proceed? [Y]/N: ").strip().upper() or "Y"
            if response == 'Y':
                trader.execute(orders)
            else:
                print("Abgebrochen durch Benutzer.")

    def ibkr_close_all(self, trader: MarketOrder):

        close_orders = [self.create_close_order(cast(IBKRPosition, p)) for p in self.ibkr_positions(trader=trader)]
        if not close_orders:
            print("ℹ️  Keine offenen Positionen gefunden.")
        else:
            print(f"📊 {len(close_orders)} Position(en) werden geschlossen.\n")
            self.execute_orders(trader=trader, orders=close_orders)
