import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.tv_scanner import TV_Scanner, Performance
from lib.stock_util import StockUtil
from lib.position import IBKRPosition, ScannerPosition
from lib.yfinance_ticker import YfinanceTicker

class StockList:
    def __init__(self, ibkr: MarketOrder):
        ibkr = ibkr
        util = StockUtil()
        sc = TV_Scanner()

        min_market_cap = 100000000000
        leverage: float = 1.0
        number_of_stocks: int = 10
        max_number_of_stocks: int = 10
        max_length_scanner_list: int = 200
        performance: Performance = Performance.Pf_1M
        self.inverted: bool = True

        price_eurusd = YfinanceTicker().get_eurusd()
        capital_reserve = 0 * price_eurusd

        net_liquidation = ibkr.get_net_liquidation() * price_eurusd
        investment_capacity=net_liquidation - capital_reserve
        self.capital_per_stock = investment_capacity * leverage / max_number_of_stocks

        self.stock_list: list[IBKRPosition] = util.ibkr_positions(trader=ibkr)
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self.stock_list}
        stock_long_symbols = [p.symbol for p in self.stock_list if p.position > 0]
        stock_short_symbols = [p.symbol for p in self.stock_list if p.position < 0]

        unwanted_tickers = util.read_symbols(util.get_latest_watchlist_file(trader=ibkr))
        self.scanner_invest_list: list[ScannerPosition] = sc.query_us_largecaps(
            tickers_to_exclude=unwanted_tickers, market_cap=min_market_cap,
            performance=performance, max_length=max_length_scanner_list, capital_per_stock=self.capital_per_stock)
        self.scanner_invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self.scanner_invest_list}
        
        scanner_top10 = self.scanner_invest_list[:number_of_stocks]
        scanner_bottom10 = self.scanner_invest_list[-number_of_stocks:]
        self.top_close_symbols = [symbol for symbol in stock_long_symbols if symbol not in [s.symbol for s in scanner_top10]]
        self.bottom_close_symbols = [symbol for symbol in stock_short_symbols if symbol not in [s.symbol for s in scanner_bottom10]]
        self.top_invest_symbols = [p.symbol for p in scanner_top10 if p.symbol not in stock_long_symbols]
        self.bottom_invest_symbols = [p.symbol for p in scanner_bottom10 if p.symbol not in stock_short_symbols]
        self.top_inverted_symbols = [symbol for symbol in stock_long_symbols if symbol in [s.symbol for s in scanner_top10]]
        self.bottom_inverted_symbols = [symbol for symbol in stock_short_symbols if symbol in [s.symbol for s in scanner_bottom10]]

class OrderList:
    def __init__(self, capital_per_stock: float):
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def invest(self, scanner_pos: ScannerPosition, inverted: bool):
        order = self._util.create_invest_order(scanner_pos, capital_per_stock=self._capital_per_stock, inverted=inverted)
        self.orders.append(order)
    
    def close(self, ibkr_pos: IBKRPosition):
        order = self._util.create_close_order(ibkr_pos)
        self.orders.append(order)

class PortfolioManager:
    def __init__(self):
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        self._stock_list: StockList = StockList(ibkr=self._ibkr)
        self._order_list: OrderList = OrderList(capital_per_stock=self._stock_list.capital_per_stock)

    def invest(self):
        self.create_close_orders()
        self.create_invest_orders()
        self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders)

    def create_close_orders(self):
        for symbol in self._stock_list.top_close_symbols + self._stock_list.bottom_close_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            if ibkr_pos is not None:
                self._order_list.close(ibkr_pos=ibkr_pos)
                print(f"  Schließe "f"{ibkr_pos.symbol:<6} position={ibkr_pos.position: 010.2f}")

    def create_invest_orders(self):
        for symbol in self._stock_list.top_invest_symbols + self._stock_list.bottom_invest_symbols:
            scan_pos = self._stock_list.scanner_invest_lookup.get(symbol)
            if scan_pos is not None:
                self._order_list.invest(scanner_pos=scan_pos, inverted=self._stock_list.inverted)
                print(f"Investiere "f"{scan_pos.symbol:<6} perf={scan_pos.perf: 010.2f}% price={scan_pos.price: 010.2f} USD")

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    manager = PortfolioManager()
    manager.invest()
    manager.disconnect()

if __name__ == "__main__":
    main()