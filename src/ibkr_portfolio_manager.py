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
FLAG_LONG = True
FLAG_SHORT = True
LEVERAGE = 1.0
MAX_NUMBER_OF_STOCKS = 10
MIN_MARKET_CAP = 10_000_000_000
NUMBER_OF_STOCKS = 10
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
        self._flag_long = FLAG_LONG
        self._flag_short = FLAG_SHORT
        self._leverage: float = LEVERAGE
        self._max_number_of_stocks: int = MAX_NUMBER_OF_STOCKS
        self._min_market_cap =  MIN_MARKET_CAP
        self._number_of_stocks: int = NUMBER_OF_STOCKS
    
    def _calculate_capital_per_stock(self):
        self._net_liquidation_euro = self._ibkr.get_net_liquidation()
        net_liquidation = self._net_liquidation_euro * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage / self._max_number_of_stocks
    
    def query(self, min_market_cap: int, is_long: bool) -> list[ScannerPosition]:
        scanner_list: list[ScannerPosition] = self._sc.query_us_largecaps(
            tickers_to_exclude=self._unwanted_tickers, market_cap=min_market_cap,
            length=self._number_of_stocks, capital_per_stock=self.capital_per_stock, is_long=is_long)
        return scanner_list

    def _set_stock_lists(self):
        self._ibkr_list: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(self._util.get_data_dir(trader=self._ibkr)))

        self._scanner_long_list = self.query(min_market_cap=self._min_market_cap, is_long=True)
        self._scanner_short_list = self.query(min_market_cap=self._min_market_cap, is_long=False)
        self._scanner_list = []
        if self._flag_long:
            self._scanner_list += self._scanner_long_list
        if self._flag_short:
            self._scanner_list += self._scanner_short_list
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._ibkr_list]
        self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_list]]
        self._invest_symbols = [p.symbol for p in self._scanner_list if p.symbol not in stock_symbols]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._ibkr_list}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_list}
    
    def _ibkr_positions_to_string(self, positions: list[IBKRPosition]) -> str:
        return "+".join(f"{p.exchange}:{p.symbol}*{abs(p.position)}" for p in positions)
    
    def _scanner_positions_to_string(self, positions: list[ScannerPosition]) -> str:
        return "+".join(f"{p.exchange}:{p.symbol}*{round(abs(self.capital_per_stock / p.price))}" for p in positions)
    
    def _positions_to_strings(self, ibkr_list: list[IBKRPosition], scanner_list: list[ScannerPosition]) -> tuple[str, str, str, str]:
        str_ibkr_1 = self._ibkr_positions_to_string(positions=ibkr_list[:5])
        str_ibkr_2 = self._ibkr_positions_to_string(positions=ibkr_list[5:10])
        str_scanner_1 = self._scanner_positions_to_string(positions=scanner_list[:5])
        str_scanner_2 = self._scanner_positions_to_string(positions=scanner_list[5:10])
        return str_ibkr_1, str_ibkr_2, str_scanner_1, str_scanner_2
    
    def _create_analysis_file(self):
        self.long_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_long_list}
        self.short_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_short_list}

        ibkr_long_list = [p for p in self._ibkr_list if p.position > 0]
        str_ibkr_long_1, str_ibkr_long_2, str_scanner_long_1, str_scanner_long_2 \
        = self._positions_to_strings(ibkr_long_list, self._scanner_long_list)
        ibkr_short_list = [p for p in self._ibkr_list if p.position < 0]
        str_ibkr_short_1, str_ibkr_short_2, str_scanner_short_1, str_scanner_short_2 \
        = self._positions_to_strings(ibkr_short_list, self._scanner_short_list)

        exchange_symbol_pairs_ibkr_long = [f"{l.exchange}:{l.symbol}" for l in ibkr_long_list]
        str_ratio_ibkr_1 = "(" + str_ibkr_long_1 + ") / (" + str_ibkr_short_1 + ")"
        str_ratio_scanner_1 = "(" + str_scanner_long_1 + ") / (" + str_scanner_short_1 + ")"
        str_ratio_ibkr_2 = "(" + str_ibkr_long_2 + ") / (" + str_ibkr_short_2 + ")"
        str_ratio_scanner_2 = "(" + str_scanner_long_2 + ") / (" + str_scanner_short_2 + ")"
        exchange_symbol_pairs_ibkr_short = [f"{l.exchange}:{l.symbol}" for l in ibkr_short_list]

        index_pairs = ["FX:NAS100", "TVC:SOX", "FX:SPX500"]

        watchlist_text = '\n'.join(exchange_symbol_pairs_ibkr_long
                                 + [str_ratio_ibkr_1]
                                 + [str_ratio_scanner_1]
                                 + [str_ratio_ibkr_2]
                                 + [str_ratio_scanner_2]
                                 + exchange_symbol_pairs_ibkr_short
                                 + index_pairs)
        self._util.create_text_file(text=watchlist_text, filename=self._analysis_file)
    
class OrderList:
    def __init__(self, capital_per_stock: float):
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def invest(self, scanner_pos: ScannerPosition):
        order = self._util.create_invest_order(symbol=scanner_pos.symbol, price=scanner_pos.price, is_long=scanner_pos.is_long, capital_per_stock=self._capital_per_stock)
        self.orders.append(order)
    
    def close(self, ibkr_pos: IBKRPosition):
        order = self._util.create_close_order(ibkr_pos)
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
    
    def invest(self):
        is_executed = self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders, skip_confirm=self._skip_confirm)
        if is_executed:
            state = StateStore.load()
            state.net_liquidation_eur = self._stock_list._net_liquidation_euro
            state.last_update = datetime.now()
            state.save()
    
    def investing_wanted(self) -> bool:
        state = StateStore.load()
        new_liquidation = self._stock_list._net_liquidation_euro
        if state.last_update is not None:
            if state.is_outdated():
                wanted = True
                print(f"Update kann durchgeführt werden, da bereits mehr als {state.max_age_hours} Stunden seit dem letzten Update vergangen sind.")
            else:
                increase_in_percentage = (new_liquidation - state.net_liquidation_eur) / (state.net_liquidation_eur - CAPITAL_RESERVE) * 100
                print(f"Alter Depotstand: {state.net_liquidation_eur:.2f} € ({state.net_liquidation_eur-CAPITAL_RESERVE:.2f} €)")
                print(f"Neuer Depotstand: {new_liquidation:.2f} € ({new_liquidation-CAPITAL_RESERVE:.2f} €)")
                print(f"Zuwachs: {increase_in_percentage:.2f} %")
                wanted = increase_in_percentage > THRESHOLD_INCREASE_IN_PERCENTAGE
                if wanted:
                    print(f"Update kann durchgeführt werden.")
                else:
                    print(f"Update wird nicht durchgeführt.")
        else:
            wanted = False
            print(f"Update wird nicht durchgeführt.")
        return wanted

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
    manager.create_orders()
    if manager.is_market_open():
        if manager.investing_wanted():
            manager.invest()
    else:
        print("Markt geschlossen")
    manager.disconnect()

if __name__ == "__main__":
    main()