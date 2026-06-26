from datetime import datetime
import os
import sys
from enum import Enum
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.position import IBKRPosition, ScannerPosition
from lib.stock_util import StockUtil
from lib.state_store import StateStore
from lib.tv_scanner import TV_Scanner
from lib.yfinance_ticker import YfinanceTicker

BASE_DIR = Path(__file__).resolve().parent.parent

ANALYSIS_FILE = BASE_DIR / 'data' / 'Analysis_Prod.txt'
CAPITAL_RESERVE = 0
DIVIDENDS_PERCENT = 3.0
FLAG_LONG = True
FLAG_SHORT = True
LEVERAGE = 1.0
MAX_NUMBER_OF_STOCKS = 20
MIN_MARKET_CAP = 10_000_000_000
NUMBER_OF_STOCKS = 20
THRESHOLD_INCREASE_IN_PERCENTAGE = 2

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
        self._analysis_file = ANALYSIS_FILE
        self._capital_reserve = CAPITAL_RESERVE * self._price_eurusd
        self._dividends_percent = DIVIDENDS_PERCENT
        self._flag_long = FLAG_LONG
        self._flag_short = FLAG_SHORT
        self._leverage: float = LEVERAGE
        self._max_number_of_stocks: int = MAX_NUMBER_OF_STOCKS
        self._min_market_cap = MIN_MARKET_CAP
        self._number_of_stocks: int = NUMBER_OF_STOCKS
    
    def _calculate_capital_per_stock(self):
        self._net_liquidation_euro = self._ibkr.get_net_liquidation()
        net_liquidation = self._net_liquidation_euro * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage / self._max_number_of_stocks
    
    def query_long(self, min_market_cap: int) -> list[ScannerPosition]:
        number_of_stocks = self._number_of_stocks // 2
        self._scanner_positions_high_performance = self._sc.query_us_ytd(
            tickers_to_exclude=self._unwanted_tickers, market_cap=min_market_cap,
            length=number_of_stocks, capital_per_stock=self.capital_per_stock, is_long=True, dividends_percent=None)
        high_performance_symbols = [p.symbol for p in self._scanner_positions_high_performance]
        unwanted_tickers = self._unwanted_tickers + high_performance_symbols
        self._scanner_positions_dividends = self._sc.query_us_ytd(
            unwanted_tickers, market_cap=min_market_cap, length=number_of_stocks,
            capital_per_stock=self.capital_per_stock, is_long=True, dividends_percent=self._dividends_percent)
        scanner_positions = self._scanner_positions_high_performance + self._scanner_positions_dividends
        return scanner_positions

    def query_short(self, min_market_cap: int) -> list[ScannerPosition]:
        scanner_positions: list[ScannerPosition] = self._sc.query_us_ytd(
            tickers_to_exclude=self._unwanted_tickers, market_cap=min_market_cap,
            length=self._number_of_stocks, capital_per_stock=self.capital_per_stock, is_long=False, dividends_percent=None)
        return scanner_positions

    def _set_stock_lists(self):
        self._ibkr_positions: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        self._ibkr_long_positions = [p for p in self._ibkr_positions if p.position > 0]
        self._ibkr_short_positions = [p for p in self._ibkr_positions if p.position < 0]
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(self._util.get_data_dir(trader=self._ibkr)))

        self._scanner_long_positions = self.query_long(min_market_cap=self._min_market_cap)
        self._scanner_short_positions = self.query_short(min_market_cap=self._min_market_cap)
        self._scanner_positions = []
        if self._flag_long:
            self._scanner_positions += self._scanner_long_positions
        if self._flag_short:
            self._scanner_positions += self._scanner_short_positions
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._ibkr_positions]
        self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_positions]]
        self._invest_symbols = [p.symbol for p in self._scanner_positions if p.symbol not in stock_symbols]
        self._update_symbols = [symbol for symbol in stock_symbols if symbol in [s.symbol for s in self._scanner_positions]]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._ibkr_positions}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_positions}
    
    def _ibkr_positions_to_string(self, positions: list[IBKRPosition]) -> str:
        return "+".join(f"{p.exchange}:{p.symbol}*{abs(p.position)}" for p in positions)
    
    def _scanner_positions_to_string(self, positions: list[ScannerPosition]) -> str:
        return "+".join(f"{p.exchange}:{p.symbol}*{round(abs(self.capital_per_stock / p.price))}" for p in positions)
    
    def _create_sum_for_ratio(self, is_long: bool, number_of_stocks: int) -> str:
        scanner_positions = self._sc.query_us_ytd(
            tickers_to_exclude=self._unwanted_tickers, market_cap=self._min_market_cap,
            length=number_of_stocks, capital_per_stock=self.capital_per_stock, is_long=is_long, dividends_percent=None)
        str_sum = "+".join(f"{p.exchange}:{p.symbol}*{round(abs(self.capital_per_stock / p.price))}" for p in scanner_positions)
        return str_sum
    
    def _create_ratio_string(self) -> str:
        str_divisor = self._create_sum_for_ratio(is_long=True, number_of_stocks=5)
        str_dividend = self._create_sum_for_ratio(is_long=False, number_of_stocks=5)
        str_ratio = "(" + str_divisor+ ") / (" + str_dividend + ") * 1000"
        return str_ratio
    
    def _create_analysis_file(self):
        str_ibkr_long_1 = self._ibkr_positions_to_string(positions=self._ibkr_long_positions[:10])
        str_ibkr_long_2 = self._ibkr_positions_to_string(positions=self._ibkr_long_positions[10:20])
        str_scanner_high_performance = self._scanner_positions_to_string(positions=self._scanner_positions_high_performance)
        str_scanner_dividends = self._scanner_positions_to_string(positions=self._scanner_positions_dividends)
        exchange_symbol_pairs_ibkr_long = [f"{l.exchange}:{l.symbol}" for l in self._ibkr_long_positions]
        str_ibkr_short_1 = self._ibkr_positions_to_string(positions=self._ibkr_short_positions[:10])
        str_ibkr_short_2 = self._ibkr_positions_to_string(positions=self._ibkr_short_positions[10:20])
        str_scanner_short_1 = self._scanner_positions_to_string(positions=self._scanner_short_positions[:10])
        str_scanner_short_2 = self._scanner_positions_to_string(positions=self._scanner_short_positions[10:20])
        exchange_symbol_pairs_ibkr_short = [f"{l.exchange}:{l.symbol}" for l in self._ibkr_short_positions]
        index_pairs = ["FX:NAS100", "TVC:SOX", "FX:SPX500"]
        str_ratio = self._create_ratio_string()

        watchlist_text = '\n'.join([str_ibkr_long_1]
                                 + [str_ibkr_long_2]
                                 + [str_scanner_high_performance]
                                 + [str_scanner_dividends]
                                 + exchange_symbol_pairs_ibkr_long
                                 + [str_ibkr_short_1]
                                 + [str_scanner_short_1]
                                 + [str_ibkr_short_2]
                                 + [str_scanner_short_2]
                                 + exchange_symbol_pairs_ibkr_short
                                 + index_pairs
                                 + [str_ratio])
        self._util.create_text_file(text=watchlist_text, filename=self._analysis_file)
    
class OrderList:
    def __init__(self, capital_per_stock: float):
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def close(self, ibkr_pos: IBKRPosition):
        order = self._util.create_close_order(ibkr_pos)
        self.orders.append(order)

    def invest(self, scanner_pos: ScannerPosition):
        order = self._util.create_invest_order(symbol=scanner_pos.symbol, price=scanner_pos.price, is_long=scanner_pos.is_long, capital_per_stock=self._capital_per_stock)
        self.orders.append(order)
    
    def update(self, ibkr_pos: IBKRPosition, scanner_pos: ScannerPosition):
        qty = self._util.calc_qty(ibkr_pos=ibkr_pos, scanner_pos=scanner_pos, capital_per_stock=self._capital_per_stock)
        if qty != 0:
            order = self._util.create_update_order(ibkr_pos=ibkr_pos, scanner_pos=scanner_pos, capital_per_stock=self._capital_per_stock, qty=qty)
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
        return ret

    def create_orders(self):
        self.create_close_orders()
        self.create_invest_orders()
        self.create_update_orders()

    def create_close_orders(self):
        for symbol in self._stock_list._close_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            if ibkr_pos is not None:
                self._order_list.close(ibkr_pos=ibkr_pos)

    def create_invest_orders(self):
        for symbol in self._stock_list._invest_symbols:
            scanner_pos = self._stock_list.invest_lookup.get(symbol)
            if scanner_pos is not None:
                self._order_list.invest(scanner_pos=scanner_pos)

    def create_update_orders(self):
        for symbol in self._stock_list._update_symbols:
            ibkr_pos = self._stock_list.stock_lookup.get(symbol)
            scanner_pos = self._stock_list.invest_lookup.get(symbol)
            if ibkr_pos is not None and scanner_pos is not None:
                self._order_list.update(ibkr_pos=ibkr_pos, scanner_pos=scanner_pos)

    def invest(self):
        is_executed = self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders, skip_confirm=self._skip_confirm)
        if is_executed:
            state = StateStore.load()
            state.net_liquidation_eur = self._stock_list._net_liquidation_euro
            state.last_update = datetime.now()
            state.save()
    
    def disconnect(self):
        self._ibkr.disconnect()

def main():
    skip_confirm = '-y' in sys.argv or '-Y' in sys.argv
    manager = PortfolioManager(skip_confirm=skip_confirm)
    manager.create_orders()
    if manager.is_market_open():
        manager.invest()
    else:
        print("Markt geschlossen")
    manager.disconnect()

if __name__ == "__main__":
    main()