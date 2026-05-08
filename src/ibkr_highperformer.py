import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil
from lib.position import IBKRPosition, ScannerPosition
from lib.yfinance_ticker import YfinanceTicker

class OrderList:
    def __init__(self, free_capital: float, capital_per_stock: float):
        self.free_capital = free_capital
        self._capital_per_stock = capital_per_stock
        self._util = StockUtil()
        self.orders = []

    def buy(self, buy_pos: ScannerPosition):
        order = self._util.create_invest_order(buy_pos, capital_per_stock=self._capital_per_stock)
        self.orders.append(order)
        self.free_capital -= order.qty * buy_pos.price
    
    def sell(self, ibkr_pos: IBKRPosition, scan_pos: ScannerPosition):
        order = self._util.create_close_order(ibkr_pos)
        self.orders.append(order)
        self.free_capital += ibkr_pos.position * scan_pos.price

class StockList:
    def __init__(self, ibkr: MarketOrder):
        ibkr = ibkr
        util = StockUtil()
        sc = TV_Scanner()

        self.number_of_stocks = 1
        self.max_number_of_stocks = 50
        self.leverage = 1.0 / self.max_number_of_stocks
        self.min_market_cap = 10000000000
        self.min_technical_rating = 0.5
        self.reduce = False

        self.stock_list: list[IBKRPosition] = util.ibkr_positions(trader=ibkr)
        self._stock_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in self.stock_list}

        ibkr_symbols = [p.symbol for p in self.stock_list]
        self.scanner_list: list[ScannerPosition] = sc.scan_stock_list(stock_list=ibkr_symbols)

        price_eurusd = YfinanceTicker().get_eurusd()
        net_liquidation = ibkr.get_net_liquidation() * price_eurusd
        capital_reserve = 0 * price_eurusd

        self.investment_capacity=net_liquidation - capital_reserve
        self.capital_per_stock = self.investment_capacity * self.leverage

    def get_position(self, scan_pos: ScannerPosition) -> IBKRPosition | None:
        ibkr_pos = self._stock_lookup.get(scan_pos.symbol)
        return ibkr_pos
        
    def get_equity_value(self) -> float:
        scan_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self.scanner_list}
        equity_value = sum(p.position * scan_lookup.pop(p.symbol).price for p in self.stock_list)
        return equity_value

    def get_free_capital(self) -> float:
        equity_value = self.get_equity_value()
        free_capital = self.investment_capacity * self.leverage * self.number_of_stocks - equity_value
        return free_capital
    
    def min_position_perf_y(self) -> ScannerPosition | None:
        min_position = min(self.scanner_list, key=lambda p: p.perf_y, default=None)
        return min_position

class InvestList:
    def __init__(self, ibkr: MarketOrder, stock_list: StockList):
        self._ibkr = ibkr
        util = StockUtil()
        sc = TV_Scanner()

        unwanted_tickers = util.read_symbols(util.get_latest_watchlist_file(trader=self._ibkr))
        self._buy_scanner_list: list[ScannerPosition] = sc.query_usa_highflyer(
            tickers_to_exclude=unwanted_tickers, market_cap=stock_list.min_market_cap,
            max_number=stock_list.max_number_of_stocks, capital_per_stock=stock_list.capital_per_stock)
        self.least_perf = self._buy_scanner_list[stock_list.max_number_of_stocks-1].perf_y

class Strategy:
    def __init__(self, ibkr: MarketOrder):
        self._stock_list: StockList = StockList(ibkr=ibkr)
        self._invest_list: InvestList = InvestList(ibkr=ibkr, stock_list=self._stock_list)
        self._order_list: OrderList = OrderList(free_capital=self.get_free_capital(), capital_per_stock=self._stock_list.capital_per_stock)

    def get_equity_value(self) -> float:
        scan_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._stock_list.scanner_list}
        equity_value = sum(p.position * scan_lookup.pop(p.symbol).price for p in self._stock_list.stock_list)
        return equity_value

    def get_free_capital(self) -> float:
        equity_value = self.get_equity_value()
        free_capital = self._stock_list.investment_capacity * self._stock_list.leverage * self._stock_list.number_of_stocks - equity_value
        return free_capital

    def sell_filter(self, scan_pos: ScannerPosition) -> bool:
        cond1 = scan_pos.perf_y < self._invest_list.least_perf
        cond2 = self._order_list.free_capital < 0.0
        cond3 = self._stock_list.reduce and scan_pos.tech_rating < self._stock_list.min_technical_rating
        return cond1 or cond2 or cond3

    def create_sell_orders(self):
        for scan_pos in self._stock_list.scanner_list:
            ibkr_pos = self._stock_list.get_position(scan_pos)
            if ibkr_pos is not None:
                if self.sell_filter(scan_pos):
                    self._order_list.sell(ibkr_pos=ibkr_pos, scan_pos=scan_pos)
                    print(f" Verkaufe ", end="")
                else:
                    print(f"  Behalte ", end="")
                print(f"{ibkr_pos.symbol:<6} perf_y={scan_pos.perf_y:8.2f}%, "
                      f"free_capital={self._order_list.free_capital: 010.2f} USD, perf_of_last_stock={self._invest_list.least_perf:7.2f}%")
    
    def buy_filter(self, scan_pos: ScannerPosition) -> bool:
        cond1 = scan_pos.tech_rating >= self._stock_list.min_technical_rating
        cond2 = scan_pos.change > 0
        return cond1 and cond2

    def create_buy_orders(self):
        ibkr_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in self._stock_list.scanner_list}
        for buy_pos in self._invest_list._buy_scanner_list:
            if not buy_pos.symbol in ibkr_lookup:
                if self._order_list.free_capital > self._stock_list.capital_per_stock:
                    min_position = self._stock_list.min_position_perf_y()
                    if min_position is not None:
                        if self.buy_filter(buy_pos) and min_position.perf_y < buy_pos.perf_y:
                            ibkr_pos = self._stock_list.get_position(min_position)
                            if ibkr_pos is not None:
                                self._order_list.sell(ibkr_pos=ibkr_pos, scan_pos=min_position)
                            self._order_list.buy(buy_pos=buy_pos)
                            print(f"    Kaufe ", end="")
                else:
                    if self.buy_filter(buy_pos):
                        self._order_list.buy(buy_pos=buy_pos)
                        print(f"    Kaufe ", end="")
                    else:
                        print(f"Ignoriere ", end="")
                    print(f"{buy_pos.symbol:<6} perf_y={buy_pos.perf_y:8.2f}%, free_capital={self._order_list.free_capital: 010.2f} USD, "
                        f"tech_rating={buy_pos.tech_rating: 010.2f}, change={buy_pos.change: 010.2f} %")

class Investor:
    def __init__(self):
        self._ibkr = MarketOrder()
        self._util = StockUtil()
        self._strategy = Strategy(ibkr=self._ibkr)

    def invest(self):
        self._strategy.create_sell_orders()
        self._strategy.create_buy_orders()
        self._util.execute_orders(trader=self._ibkr, orders=self._strategy._order_list.orders)

    def disconnect(self):
        self._ibkr.disconnect()

def main():
    investor = Investor()
    investor.invest()
    investor.disconnect()

if __name__ == "__main__":
    main()