import os
import sys
from typing import Tuple, cast
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
        self._max_number_of_stocks = 50
        self._leverage = 1.5 * self._number_of_stocks / self._max_number_of_stocks
        self._capital_reserve = 0

    def get_capital(self) -> float:
      capital = self._ibkr.get_capital() - self._capital_reserve
      price_eurusd = YfinanceTicker().get_eurusd()
      capital *= price_eurusd
      return capital

    def capital_per_stock(self) -> float:
        capital = self.get_capital()
        capital_per_stock = (capital * self._leverage) / self._number_of_stocks
        return capital_per_stock
    
    def filter(self, scan_pos: ScannerPosition) -> bool:
        return scan_pos.tech_rating >= 0.5 and scan_pos.change > 0

    def next_step(self, ibkr_remaining: list[IBKRPosition], ibkr_lookup: dict[str, IBKRPosition],
                  scan_pos: ScannerPosition, orders: list[IBKROrder],
                  capital: float, capital_per_stock: float) -> Tuple[float, IBKROrder | None, bool]:
        order = None
        no_more_capital = False
        if scan_pos.symbol in ibkr_lookup:
            ibkr_pos = ibkr_lookup.pop(scan_pos.symbol)
            ibkr_remaining.remove(ibkr_pos)
            capital -= ibkr_pos.position * scan_pos.price
            print(f"{scan_pos.symbol} vorhanden, Kapital: {capital}")
        else:
            if self.filter(scan_pos):
                qty = round(capital_per_stock / scan_pos.price)
                capital -= qty * scan_pos.price
                if capital > 0.0:
                    order = self._util.create_invest_order(scan_pos, capital_per_stock=self.capital_per_stock())
                    print(f"{scan_pos.symbol} kaufen, "
                          f"Preis: {scan_pos.price:.2f}, Tech-Rating: {scan_pos.tech_rating:.3f}, Veränderung: {scan_pos.change:.2f} %")
            if capital < capital_per_stock:
                no_more_capital = True
        return capital, order, no_more_capital
    
    def generate_orders(self,
        ibkr_list: list[IBKRPosition],
        scanner_list: list[ScannerPosition],
        capital: float,
        capital_per_stock: float,
    ) -> list[IBKROrder]:
        orders: list[IBKROrder] = []
        ibkr_remaining = list(ibkr_list)
        ibkr_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in ibkr_remaining}

        no_more_capital = False
        for scan_pos in scanner_list:
            capital, order, no_more_capital = self.next_step(
                ibkr_remaining=ibkr_remaining,
                ibkr_lookup=ibkr_lookup,
                scan_pos=scan_pos,
                orders=orders,
                capital=capital,
                capital_per_stock=capital_per_stock,
            )
            if order is not None:
                orders.append(order)
            if no_more_capital:
                break

        if no_more_capital:
            for ibkr_pos in list(ibkr_remaining):
                orders.insert(0, self._util.create_close_order(ibkr_pos))
                ibkr_remaining.remove(ibkr_pos)

        return orders
    
    def invest(self):
        ibkr_list = self._util.ibkr_positions(trader=self._ibkr)
        print(f"Länge IBKR-Liste: {len(ibkr_list)}")
        unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(trader=self._ibkr))
        scanner_list = TV_Scanner().query_usa_highflyer(
            tickers_to_exclude=unwanted_tickers, market_cap=2000000000, capital_per_stock=self.capital_per_stock())
        print(f"Länge Scanner-Liste: {len(scanner_list)}")
        orders = self.generate_orders(
            ibkr_list=ibkr_list, scanner_list=scanner_list, capital=self.get_capital() * self._leverage, capital_per_stock=self.capital_per_stock())
        self._util.execute_orders(trader=self._ibkr, orders=orders)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    investor = Investor()
    investor.invest()
    investor.disconnect()

if __name__ == "__main__":
    main()