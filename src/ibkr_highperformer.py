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
        self._min_market_cap = 100000000000
        self._leverage: float = 1.0
        self._number_of_stocks: int = 10
        self._max_number_of_stocks: int = 10
        self._performance: Performance = Performance.Pf_1W
        self._capital_reserve = 0 * self._price_eurusd
        self._inverted = True
    
    def _calculate_capital_per_stock(self):
        net_liquidation = self._ibkr.get_net_liquidation() * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage / self._max_number_of_stocks
    
    def _set_stock_lists(self):
        self._stock_list: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(trader=self._ibkr))
        self._scanner_list: list[ScannerPosition] = self._sc.query_us_largecaps(
            tickers_to_exclude=unwanted_tickers, market_cap=self._min_market_cap, performance=self._performance,
            length=self._number_of_stocks, capital_per_stock=self.capital_per_stock, ascending=False)
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._stock_list]
        self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_list]]
        self._invest_symbols = [p.symbol for p in self._scanner_list]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._stock_list}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_list}
    
    def _create_analysis_file(self):
        str_top_stocks = "+".join(f"{l.exchange}:{l.symbol}" for l in self._scanner_list)
        exchange_symbol_pairs = [f"{l.exchange}:{l.symbol}" for l in self._scanner_list]
        watchlist_text = '\n'.join([str_top_stocks] + exchange_symbol_pairs)
        self._util.create_text_file(text=watchlist_text, filename='data/Analysis.txt')
    
class OrderList:
    def __init__(self, capital_per_stock: float):
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def invest(self, ibkr_pos: IBKRPosition | None, scanner_pos: ScannerPosition, inverted: bool):
        order = self._util.create_invest_order(symbol=scanner_pos.symbol, position=ibkr_pos.position if ibkr_pos else 0, inverted=inverted, price=scanner_pos.price, capital_per_stock=self._capital_per_stock)
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
        for symbol in self._stock_list._close_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            if ibkr_pos is not None:
                self._order_list.close(ibkr_pos=ibkr_pos)

    def create_invest_orders(self):
        for symbol in self._stock_list._invest_symbols:
            scan_pos = self._stock_list.invest_lookup.get(symbol)
            if scan_pos is not None:
                ibkr_pos = self._stock_list.stock_lookup.get(symbol)
                if ibkr_pos is not None:
                    self._order_list.invest(ibkr_pos=ibkr_pos, scanner_pos=scan_pos, inverted=self._stock_list._inverted)
                else:
                    self._order_list.invest(ibkr_pos=None, scanner_pos=scan_pos, inverted=self._stock_list._inverted)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    manager = PortfolioManager()
    manager.invest()
    manager.disconnect()

if __name__ == "__main__":
    main()