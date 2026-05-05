import os
import sys
from typing import Tuple
from matplotlib.pylab import Enum

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder, IBKROrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil
from lib.position import IBKRPosition, ScannerPosition
from lib.yfinance_ticker import YfinanceTicker

class Volatility(Enum):
    HIGH = "high"
    LOW = "low"

class Investor:
    def __init__(self):
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        
        self._number_of_stocks = 67
        self._max_number_of_stocks = 67
        self._min_market_cap = 2000000000
        price_eurusd = YfinanceTicker().get_eurusd()
        net_liquidation = self._ibkr.get_net_liquidation() * price_eurusd
        capital_reserve = 0 * price_eurusd
        self._investment_capacity=net_liquidation - capital_reserve
        self._leverage = 2.0 / self._max_number_of_stocks
        self._capital_per_stock = self._investment_capacity * self._leverage
        self._min_technical_rating = 0.5

    def get_equity_value(self, ibkr_list: list[IBKRPosition], scanner_list: list[ScannerPosition]) -> float:
        scan_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in scanner_list}
        equity_value = sum(p.position * scan_lookup.pop(p.symbol).price for p in ibkr_list)
        return equity_value
    
    def get_free_capital(self, ibkr_list: list[IBKRPosition], scanner_list: list[ScannerPosition], investment_capacity: float) -> float:
        equity_value = self.get_equity_value(ibkr_list=ibkr_list, scanner_list=scanner_list)
        free_capital = investment_capacity * self._leverage * self._number_of_stocks - equity_value
        return free_capital
    
    def create_sell_orders(self, ibkr_list: list[IBKRPosition], scanner_list: list[ScannerPosition],
                           perf_of_last_stock: float, free_capital: float) -> list[IBKROrder]:
        orders: list[IBKROrder] = []
        ibkr_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in ibkr_list}
        for scan_pos in scanner_list:
            ibkr_pos = ibkr_lookup[scan_pos.symbol]
            if scan_pos.perf_y < perf_of_last_stock or free_capital < 0.0:
                orders.append(self._util.create_close_order(ibkr_pos))
                print(f"Verkaufe {ibkr_pos.symbol:<6} perf_y={scan_pos.perf_y:8.2f}%, free_capital={free_capital: 010.2f} USD, perf_of_last_stock={perf_of_last_stock:7.2f}%")
                free_capital += ibkr_pos.position * scan_pos.price
            else:
                print(f" Behalte {ibkr_pos.symbol:<6} perf_y={scan_pos.perf_y:8.2f}%, free_capital={free_capital: 010.2f} USD, perf_of_last_stock={perf_of_last_stock:7.2f}%")
        return orders

    def filter(self, scan_pos: ScannerPosition) -> bool:
        return scan_pos.tech_rating >= self._min_technical_rating and scan_pos.change > 0

    def create_buy_orders(self, ibkr_scanner_list: list[ScannerPosition], buy_scanner_list: list[ScannerPosition],
                          free_capital: float) -> list[IBKROrder]:
        orders: list[IBKROrder] = []
        ibkr_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in ibkr_scanner_list}
        for buy_pos in buy_scanner_list:
            if not buy_pos.symbol in ibkr_lookup:
                if self.filter(buy_pos) and free_capital > self._capital_per_stock:
                    print(f"   Kaufe {buy_pos.symbol:<6} perf_y={buy_pos.perf_y:8.2f}%, free_capital={free_capital: 010.2f} USD")
                    order = self._util.create_invest_order(buy_pos, capital_per_stock=self._capital_per_stock)
                    orders.append(order)
                    free_capital -= self._capital_per_stock
        return orders

    def invest(self):
        sc = TV_Scanner()

        ibkr_list = self._util.ibkr_positions(trader=self._ibkr)
        ibkr_symbols = [p.symbol for p in ibkr_list]
        ibkr_scanner_list = sc.scan_stock_list(stock_list=ibkr_symbols)

        unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(trader=self._ibkr))
        buy_scanner_list = sc.query_usa_highflyer(
            tickers_to_exclude=unwanted_tickers, market_cap=self._min_market_cap,
            max_number=self._max_number_of_stocks, capital_per_stock=self._capital_per_stock)

        free_capital = self.get_free_capital(ibkr_list=ibkr_list, scanner_list=ibkr_scanner_list, investment_capacity=self._investment_capacity)

        least_perf = buy_scanner_list[self._max_number_of_stocks-1].perf_y
        sell_orders = self.create_sell_orders(ibkr_list=ibkr_list, scanner_list=ibkr_scanner_list, perf_of_last_stock=least_perf, free_capital=free_capital)

        buy_orders = self.create_buy_orders(ibkr_scanner_list=ibkr_scanner_list, buy_scanner_list=buy_scanner_list, free_capital=free_capital)

        orders = sell_orders + buy_orders
        self._util.execute_orders(trader=self._ibkr, orders=orders)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    investor = Investor()
    investor.invest()
    investor.disconnect()

if __name__ == "__main__":
    main()