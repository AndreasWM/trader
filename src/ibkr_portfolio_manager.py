from datetime import datetime
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.position import IBKRPosition, ScannerPosition
from lib.stock_util import StockUtil
from lib.tv_scanner import TV_Scanner
from lib.yfinance_ticker import YfinanceTicker

IBKR_LONG = 'IBKR_Long.txt'
IBKR_SHORT = 'IBKR_Short.txt'
CAPITAL_RESERVE = 0
LEVERAGE = 1.0
MIN_MARKET_CAP = 50_000_000_000
NUMBER_OF_STOCKS = 50

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
        self._write_watchlist_file()
    
    def _zero_if_none(self, leverage: float|None) -> float:
        return 0 if leverage is None else leverage

    def _set_params(self):
        self._ibkr_long = self._util.get_data_dir() + IBKR_LONG
        self._ibkr_short = self._util.get_data_dir() + IBKR_SHORT
        self._capital_reserve = CAPITAL_RESERVE * self._price_eurusd
        self._leverage: float = LEVERAGE
        self._min_market_cap = MIN_MARKET_CAP
        self._number_of_stocks: int = NUMBER_OF_STOCKS
    
    def _calculate_capital_per_stock(self):
        self._net_liquidation_euro = self._ibkr.get_net_liquidation()
        net_liquidation = self._net_liquidation_euro * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage // 2 / self._number_of_stocks
    
    def _set_stock_lists(self):
        self._ibkr_positions: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_do_not_trade_file())
        self._scanner_positions = []
        if self._leverage > 0:
            self._scanner_positions = self._sc.query_us(tickers_to_exclude=self._unwanted_tickers, market_cap=self._min_market_cap,
                                length=self._number_of_stocks, capital_per_stock=self.capital_per_stock, leverage=self._leverage)
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._ibkr_positions]
        self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_positions]]
        self._invest_symbols = [p.symbol for p in self._scanner_positions if p.symbol not in [symbol for symbol in stock_symbols]]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._ibkr_positions}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_positions}
    
    def _create_watchlist_text(self, is_long: bool):
        exchange_symbol_pairs_ibkr = [f"{p.exchange}:{p.symbol}" for p in self._ibkr_positions if p.position > 0 and is_long or p.position < 0 and not is_long]
        self._watchlist_text = '\n'.join(exchange_symbol_pairs_ibkr)
        
    def _write_watchlist_file(self):
        self._create_watchlist_text(is_long=True)
        self._util.create_text_file(text=self._watchlist_text, filename=self._ibkr_long)
        self._create_watchlist_text(is_long=False)
        self._util.create_text_file(text=self._watchlist_text, filename=self._ibkr_short)
    
class OrderList:
    def __init__(self, capital_per_stock: float):
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def close(self, ibkr_pos: IBKRPosition):
        order = self._util.create_close_order(ibkr_pos)
        self.orders.append(order)

    def invest_or_update(self, ibkr_pos: IBKRPosition|None, scanner_pos: ScannerPosition):
        order = self._util.create_order(ibkr_pos=ibkr_pos, scanner_pos=scanner_pos, capital_per_stock=self._capital_per_stock)
        if order != None:
            self.orders.append(order)
    
class PortfolioManager:
    def __init__(self, skip_confirm: bool = False):
        print("#" * 120)
        print(f"Start: {datetime.now()}")
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        self._stock_list: StockList = StockList(ibkr=self._ibkr)
        self._order_list: OrderList = OrderList(capital_per_stock=self._stock_list.capital_per_stock)
        self._skip_confirm = skip_confirm

    def is_market_open(self) -> bool:
        ret = self._util.is_market_open("NYSE") and self._util.is_market_open("NASDAQ")
        ret = True
        return ret

    def create_close_orders(self):
        for symbol in self._stock_list._close_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            if ibkr_pos is not None:
                self._order_list.close(ibkr_pos=ibkr_pos)

    def create_invest_or_update_orders(self):
        for symbol in self._stock_list._invest_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            scanner_pos = self._stock_list.invest_lookup.get(symbol)
            if scanner_pos is not None:
                self._order_list.invest_or_update(ibkr_pos=ibkr_pos, scanner_pos=scanner_pos)

    def invest(self):
        self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders, skip_confirm=self._skip_confirm)
    
    def disconnect(self):
        self._ibkr.disconnect()

def main():
    skip_confirm = '-y' in sys.argv or '-Y' in sys.argv
    manager = PortfolioManager(skip_confirm=skip_confirm)
    manager.create_close_orders()
    manager.create_invest_or_update_orders()

    if manager.is_market_open():
        manager.invest()
    else:
        print("Markt geschlossen")
    manager.disconnect()

if __name__ == "__main__":
    main()