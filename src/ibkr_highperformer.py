import os
import sys
from typing import cast
from matplotlib.pylab import Enum
from sklearn.pipeline import islice

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder, IBKROrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil
from lib.position import Position, IBKRPosition, ScannerPosition
from lib.yfinance_ticker import YfinanceTicker

class Volatility(Enum):
    HIGH = "high"
    LOW = "low"

class Investor:
    def __init__(self):
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        self._number_of_stocks = 50
        self._leverage = 1.5

    def get_capital(self) -> float:
      capital = self._ibkr.get_capital()
      price_eurusd = YfinanceTicker().get_eurusd()
      capital *= price_eurusd
      return capital

    def capital_per_stock(self) -> float:
        capital = self.get_capital()
        capital_per_stock = (capital * self._leverage) / self._number_of_stocks
        return capital_per_stock
    
    def buy_usa_highflyer(self, scanner: TV_Scanner, tickers_to_exclude: list[str]) -> list[IBKROrder]:
        scanner_list: list[ScannerPosition] = scanner.query_usa_highflyer(tickers_to_exclude=tickers_to_exclude,
                                                   market_cap=2000000000, capital_per_stock=self.capital_per_stock())
        print(f"Länge Scanner-Liste: {len(scanner_list)}")

        invest_orders = [self._util.create_invest_order(cast(ScannerPosition, p), capital_per_stock=self.capital_per_stock())
                              for p in scanner_list]
        return invest_orders
    
    def generate_orders(self,
        ibkr_list: list[IBKRPosition],
        scanner_list: list[ScannerPosition],
        capital: float,
        capital_per_stock: float,
    ) -> list[IBKROrder]:
        orders: list[IBKROrder] = []

        # Work on mutable copies
        ibkr_remaining = list(ibkr_list)
        ibkr_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in ibkr_remaining}

        last_checked_index = -1

        for i, scan_pos in enumerate(scanner_list):
            last_checked_index = i

            if capital < capital_per_stock:
                break

            if scan_pos.symbol in ibkr_lookup:
                ibkr_pos = ibkr_lookup.pop(scan_pos.symbol)
                ibkr_remaining.remove(ibkr_pos)
                capital -= ibkr_pos.position * scan_pos.price
            else:
                qty = round(capital_per_stock / scan_pos.price)
                capital -= qty * scan_pos.price
                orders.append(self._util.create_invest_order(scan_pos, capital_per_stock=self.capital_per_stock()))

        for ibkr_pos in list(ibkr_remaining):
            price = next(
                (sp.price for sp in scanner_list if sp.symbol == ibkr_pos.symbol),
                0.0,
            )
            orders.append(self._util.create_close_order(ibkr_pos))
            capital += ibkr_pos.position * price
            ibkr_remaining.remove(ibkr_pos)

        for scan_pos in scanner_list[last_checked_index + 1:]:
            if capital < capital_per_stock:
                break

            qty = round(capital_per_stock / scan_pos.price)
            cost = qty * scan_pos.price

            sell_order = next(
                (o for o in orders if o.symbol == scan_pos.symbol and o.action == "SELL"),
                None,
            )

            if sell_order is not None:
                sell_price = next(
                    (sp.price for sp in scanner_list if sp.symbol == scan_pos.symbol),
                    0.0,
                )
                reclaimed = sell_order.qty * sell_price
                if capital - reclaimed >= 0:
                    capital -= reclaimed
                    orders.remove(sell_order)
                else:
                    break
            else:
                capital -= cost
                orders.append(self._util.create_invest_order(scan_pos, capital_per_stock=self.capital_per_stock()))

        return orders
    
    def invest(self):
        ibkr_list: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        print(f"Länge IBKR-Liste: {len(ibkr_list)}")
        share_list = list(p.symbol for p in ibkr_list if p.position > 0)

        scanner = TV_Scanner()
        unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(trader=self._ibkr))
        tickers_to_exclude: list[str] = unwanted_tickers + share_list
        scanner_list = scanner.query_usa_highflyer(
            tickers_to_exclude=tickers_to_exclude, market_cap=2000000000, capital_per_stock=self.capital_per_stock())
        print(f"Länge gefilterte Scanner-Liste: {len(scanner_list)}")
        orders = self.generate_orders(
            ibkr_list=ibkr_list, scanner_list=scanner_list, capital=self.get_capital(), capital_per_stock=self.capital_per_stock())
        self._util.execute_orders(trader=self._ibkr, orders=orders)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    investor = Investor()
    investor.invest()
    investor.disconnect()

if __name__ == "__main__":
    main()