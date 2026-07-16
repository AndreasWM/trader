from datetime import datetime
import os
import sys
from enum import Enum

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.position import IBKRPosition, ScannerPosition
from lib.stock_util import StockUtil
from lib.tv_scanner import TV_Scanner
from lib.yfinance_ticker import YfinanceTicker

class UpdateStatus(Enum):
    CLOSE_ALL = "CLOSE_ALL"
    KEEP = "KEEP"
    UPDATE = "UPDATE"

    def __str__(self):
        return self.value

PFM_SCANNER_FILE = 'PFM_Scanner.txt'
PFM_DEPOT_FILE = 'PFM_Depot.txt'
CAPITAL_RESERVE = 0
LEVERAGE_LONG_OUTPERFORM = 1.0
LEVERAGE_SHORT_OUTPERFORM = 1.0
LEVERAGE_LONG_UNDERPERFORM = 0.0
LEVERAGE_SHORT_UNDERPERFORM = 0.0
MIN_MARKET_CAP = 50_000_000_000
NUMBER_OF_STOCKS = 10

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
        self._write_pfm_scanner_file()
    
    def _zero_if_none(self, leverage: float|None) -> float:
        return 0 if leverage is None else leverage

    def _set_params(self):
        self._pfm_scanner_file = self._util.get_data_dir() + PFM_SCANNER_FILE
        self._pfm_depot_file = self._util.get_data_dir() + PFM_DEPOT_FILE
        self._capital_reserve = CAPITAL_RESERVE * self._price_eurusd
        self._leverage_long_outperform: float|None = LEVERAGE_LONG_OUTPERFORM
        self._leverage_short_outperform: float|None = LEVERAGE_SHORT_OUTPERFORM
        self._leverage_long_underperform: float|None = LEVERAGE_LONG_UNDERPERFORM
        self._leverage_short_underperform: float|None = LEVERAGE_SHORT_UNDERPERFORM
        self._leverage = self._zero_if_none(self._leverage_long_outperform) + self._zero_if_none(self._leverage_short_outperform) + \
                         self._zero_if_none(self._leverage_long_underperform) + self._zero_if_none(self._leverage_short_underperform)
        self._min_market_cap = MIN_MARKET_CAP
        self._number_of_stocks: int = NUMBER_OF_STOCKS
    
    def _calculate_capital_per_stock(self):
        self._net_liquidation_euro = self._ibkr.get_net_liquidation()
        net_liquidation = self._net_liquidation_euro * self._price_eurusd
        investment_capacity=net_liquidation - self._capital_reserve
        self.capital_per_stock = investment_capacity * self._leverage // 4 / self._number_of_stocks
    
    def query(self, leverage: float|None, flag_outperform: bool, flag_is_long: bool) -> list[ScannerPosition]:
        if leverage is not None and leverage > 0:
            scanner_positions: list[ScannerPosition] \
            = self._sc.query_us(tickers_to_exclude=self._unwanted_tickers, market_cap=self._min_market_cap,
                                length=self._number_of_stocks, capital_per_stock=self.capital_per_stock,
                                leverage=leverage, flag_outperform=flag_outperform, flag_is_long=flag_is_long)
        else:
            scanner_positions = []
        return scanner_positions

    def _set_stock_lists(self):
        self._ibkr_positions: list[IBKRPosition] = self._util.ibkr_positions(trader=self._ibkr)
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_do_not_trade_file())

        self._scanner_outperform_positions = self.query(leverage=self._leverage_long_outperform, flag_outperform=True, flag_is_long=True)
        self._scanner_outperform_short_positions = self.query(leverage=self._leverage_short_outperform, flag_outperform=True, flag_is_long=False)
        self._scanner_underperform_positions = self.query(leverage=self._leverage_short_underperform, flag_outperform=False, flag_is_long=False)
        self._scanner_underperform_long_positions = self.query(leverage=self._leverage_long_underperform, flag_outperform=False, flag_is_long=True)
        self._scanner_positions = self._scanner_outperform_positions + self._scanner_outperform_short_positions + \
                                  self._scanner_underperform_positions + self._scanner_underperform_long_positions
    
    def _set_symbol_lists(self):
        stock_symbols = [p.symbol for p in self._ibkr_positions]
        self._close_symbols = [symbol for symbol in stock_symbols if symbol not in [s.symbol for s in self._scanner_positions]]
        self._invest_symbols = [p.symbol for p in self._scanner_positions]

    def _set_lookups(self):
        self.stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self._ibkr_positions}
        self.invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._scanner_positions}
    
    def _scanner_positions_to_string(self, positions: list[ScannerPosition]) -> str:
        return "+".join(f"{p.exchange}:{p.symbol}*{round(abs(self.capital_per_stock / p.price))}" for p in positions)
    
    def _create_pfm_scanner_text(self):
        str_scanner_outperform_positions = self._scanner_positions_to_string(positions=self._scanner_outperform_positions)
        exchange_symbol_pairs_scanner_outperform = [f"{l.exchange}:{l.symbol}" for l in self._scanner_outperform_positions]
        str_scanner_outperform_short_positions = self._scanner_positions_to_string(positions=self._scanner_outperform_short_positions)
        exchange_symbol_pairs_scanner_short_outperform = [f"{l.exchange}:{l.symbol}" for l in self._scanner_outperform_short_positions]
        str_scanner_underperform_long_positions = self._scanner_positions_to_string(positions=self._scanner_underperform_long_positions)
        exchange_symbol_pairs_scanner_long_underperform = [f"{l.exchange}:{l.symbol}" for l in self._scanner_underperform_long_positions]
        str_scanner_underperform_positions = self._scanner_positions_to_string(positions=self._scanner_underperform_positions)
        exchange_symbol_pairs_scanner_underperform = [f"{l.exchange}:{l.symbol}" for l in self._scanner_underperform_positions]
        index_pairs = ["FX:NAS100", "TVC:SOX", "FX:SPX500"]

        self._watchlist_text = '\n'.join([str_scanner_outperform_positions]
                                 + exchange_symbol_pairs_scanner_outperform
                                 + [str_scanner_outperform_short_positions]
                                 + exchange_symbol_pairs_scanner_short_outperform
                                 + [str_scanner_underperform_long_positions]
                                 + exchange_symbol_pairs_scanner_long_underperform
                                 + [str_scanner_underperform_positions]
                                 + exchange_symbol_pairs_scanner_underperform
                                 + index_pairs)
        
    def _write_pfm_scanner_file(self):
        self._create_pfm_scanner_text()
        self._util.create_text_file(text=self._watchlist_text, filename=self._pfm_scanner_file)
    
    def _write_pfm_depot_file(self):
        self._util.create_text_file(text=self._watchlist_text, filename=self._pfm_depot_file)
    
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
        is_executed = self._util.execute_orders(trader=self._ibkr, orders=self._order_list.orders, skip_confirm=self._skip_confirm)
        if is_executed:
            self._stock_list._write_pfm_depot_file()
    
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