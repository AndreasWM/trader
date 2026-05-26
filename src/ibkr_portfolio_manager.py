import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from enum import Enum
from lib.ibkr_market_order import MarketOrder
from lib.tv_scanner import TV_Scanner, Performance
from lib.stock_util import StockUtil
from lib.position import IBKRPosition, ScannerPosition
from lib.yfinance_ticker import YfinanceTicker

class Strategy(Enum):
    LARGE_CAP = "large_cap"
    MID_CAP = "mid_cap"
class StockList:
    def __init__(self, ibkr: MarketOrder):
        self._ibkr = ibkr
        self._util = StockUtil()
        self._sc = TV_Scanner()
        self._price_eurusd = YfinanceTicker().get_eurusd()

        self._set_params()
        self._calculate_capital_per_stock()
        self._set_stock_lists()
        self._set_symbol_lists()
        self._set_lookups()
        self._create_analysis_file()

    def _set_params(self):
        self._strategy = Strategy.MID_CAP
        self._mid_cap_value   = 10000000000
        self._large_cap_value = 100000000000
        self._leverage: float = 1.0
        self._number_of_stocks: int = 20
        self._max_number_of_stocks: int = 20
        self._capital_reserve = 0 * self._price_eurusd
        self._always_short = False
        self._close_all = False
        self._performance_threshold = 5
    
    def _calculate_capital_per_stock(self):
        net_liquidation = self._ibkr.get_net_liquidation() * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage / self._max_number_of_stocks
    
    def query(self, min_market_cap: int, perf_1m_value: float | None, performance: Performance, ascending: bool) -> list[ScannerPosition]:
        scanner_list: list[ScannerPosition] = self._sc.query_us_largecaps(
            tickers_to_exclude=self._unwanted_tickers, market_cap=min_market_cap, perf_1m_value=perf_1m_value, performance=performance,
            length=self._number_of_stocks, capital_per_stock=self.capital_per_stock, ascending=ascending)
        return scanner_list

    def _set_stock_lists(self):
        self._stock_list: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(self._util.get_data_dir(trader=self._ibkr)))

        min_market_cap = self._mid_cap_value if self._strategy == Strategy.MID_CAP else self._large_cap_value if self._strategy == Strategy.LARGE_CAP else 0
        long_perf_value = self._performance_threshold if self._strategy == Strategy.MID_CAP else None
        short_perf_value = -self._performance_threshold if self._strategy == Strategy.MID_CAP else None
        performance = Performance.Pf_YTD if self._strategy == Strategy.MID_CAP else Performance.Pf_1M

        self._scanner_long_list = self.query(min_market_cap=min_market_cap, perf_1m_value=long_perf_value, performance=performance, ascending=False)
        self._scanner_short_list = self.query(min_market_cap=min_market_cap, perf_1m_value=short_perf_value, performance=performance, ascending=True)
        self._scanner_list = self._scanner_long_list + self._scanner_short_list
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._stock_list]
        if self._close_all:
            self._close_symbols = stock_symbols
            self._invest_symbols = []
        else:
            self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_list]]
            self._invest_symbols = [p.symbol for p in self._scanner_list if p.symbol not in stock_symbols]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._stock_list}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_list}
    
    def _create_analysis_file(self):
        self.long_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_long_list}
        str_stocks_long = "+".join(f"{p.exchange}:{p.symbol}*{abs(p.position)}" for p in self._stock_list if p.position > 0)
        exchange_symbol_pairs_long = [f"{l.exchange}:{l.symbol}" for l in self._scanner_long_list]

        self.short_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_short_list}
        str_stocks_short = "+".join(f"{p.exchange}:{p.symbol}*{abs(p.position)}" for p in self._stock_list if p.position < 0)
        exchange_symbol_pairs_short = [f"{l.exchange}:{l.symbol}" for l in self._scanner_short_list]

        index_pairs = ["FX:NAS100", "TVC:SOX", "FX:SPX500"]

        watchlist_text = '\n'.join([str_stocks_long] + exchange_symbol_pairs_long
                                   + [str_stocks_short] + exchange_symbol_pairs_short
                                   + index_pairs)
        self._util.create_text_file(text=watchlist_text, filename='data/Analysis.txt')
    
class OrderList:
    def __init__(self, capital_per_stock: float, always_short: bool):
        self._capital_per_stock = capital_per_stock
        self._always_short = always_short
        self._util = StockUtil()
        self.orders = []

    def invest(self, scanner_pos: ScannerPosition):
        order = self._util.create_invest_order(symbol=scanner_pos.symbol, price=scanner_pos.price, perf=scanner_pos.perf, capital_per_stock=self._capital_per_stock, always_short=self._always_short)
        self.orders.append(order)
    
    def close(self, ibkr_pos: IBKRPosition):
        order = self._util.create_close_order(ibkr_pos)
        self.orders.append(order)

class PortfolioManager:
    def __init__(self, skip_confirm: bool = False):
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        self._stock_list: StockList = StockList(ibkr=self._ibkr)
        self._order_list: OrderList = OrderList(capital_per_stock=self._stock_list.capital_per_stock, always_short=self._stock_list._always_short)
        self._skip_confirm = skip_confirm

    def invest(self):
        self.create_close_orders()
        self.create_invest_orders()
        self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders, skip_confirm=self._skip_confirm)

    def create_close_orders(self):
        for symbol in self._stock_list._close_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            if ibkr_pos is not None:
                self._order_list.close(ibkr_pos=ibkr_pos)

    def create_invest_orders(self):
        for symbol in self._stock_list._invest_symbols:
            scan_pos = self._stock_list.invest_lookup.get(symbol)
            if scan_pos is not None:
                self._order_list.invest(scanner_pos=scan_pos)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    skip_confirm = '-y' in sys.argv or '-Y' in sys.argv
    manager = PortfolioManager(skip_confirm=skip_confirm)
    manager.invest()
    manager.disconnect()

if __name__ == "__main__":
    main()