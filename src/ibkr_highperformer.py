import os
import sys
from typing import cast
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
        self._number_of_stocks = 100
        self._max_number_per_day = 10
        self._leverage = 2.0
        self._volatility = Volatility.HIGH

    def get_capital(self) -> float:
      capital = self._ibkr.get_capital()
      price_eurusd = YfinanceTicker().get_eurusd()
      capital *= price_eurusd
      return capital

    def capital_per_stock(self) -> float:
        capital = self.get_capital()
        capital_per_stock = (capital * self._leverage) / self._number_of_stocks
        return capital_per_stock
    
    def buy_performant_stocks(self, long_list: list[str], short_list: list[str], scanner: TV_Scanner,
                              tickers_to_exclude: list[str]) -> list[IBKROrder]:
        ratio = scanner.get_ratio_bull_bear()
        ratio = 0.5
        count_invest_long = max(int(self._number_of_stocks * ratio) - len(long_list), 0)
        count_invest_short = min(int(self._number_of_stocks * (1 - ratio)) - len(short_list), int(self._number_of_stocks / 2))

        scanner_long_list = scanner.query_usa(is_long=True, tickers_to_exclude=tickers_to_exclude,
                                              market_cap=5000000000, capital_per_stock=self.capital_per_stock(), limit=count_invest_long)
        print(f"Länge Scanner-Long-Liste: {len(scanner_long_list)}")

        scanner_short_list = scanner.query_usa(is_long=False, tickers_to_exclude=tickers_to_exclude,
                                               market_cap=10000000000, capital_per_stock=self.capital_per_stock(), limit=count_invest_short)
        print(f"Länge Scanner-Short-Liste: {len(scanner_short_list)}")

        invest_long_orders = [self._util.create_invest_order(cast(ScannerPosition, p), capital_per_stock=self.capital_per_stock())
                              for p in scanner_long_list]
        invest_short_orders = [self._util.create_invest_order(cast(ScannerPosition, p), capital_per_stock=self.capital_per_stock())
                               for p in scanner_short_list]
        all_orders = invest_long_orders + invest_short_orders
        return all_orders
    
    def buy_big_stocks(self, limit: int, scanner: TV_Scanner,
                              tickers_to_exclude: list[str]) -> list[IBKROrder]:
        scanner_long_list = scanner.query_big_usa(is_long=True, tickers_to_exclude=tickers_to_exclude,
                                              market_cap=65000000000, capital_per_stock=self.capital_per_stock())
        print(f"Länge Scanner-Long-Liste: {len(scanner_long_list)}")

        scanner_short_list = scanner.query_big_usa(is_long=False, tickers_to_exclude=tickers_to_exclude,
                                               market_cap=65000000000, capital_per_stock=self.capital_per_stock())
        print(f"Länge Scanner-Short-Liste: {len(scanner_short_list)}")

        scanner_list = scanner_long_list + scanner_short_list
        scanner_list.sort(key=lambda p: p.market_cap, reverse=True)
        scanner_list = list(islice(scanner_list, limit))
        orders = [self._util.create_invest_order(cast(ScannerPosition, p), capital_per_stock=self.capital_per_stock()) for p in scanner_list]
        return orders
    
    def invest(self):
        ibkr_list = self._util.ibkr_positions(trader=self._ibkr)
        print(f"Länge IBKR-Liste: {len(ibkr_list)}")
        long_list = list(p.symbol for p in ibkr_list if p.position > 0)
        short_list = list(p.symbol for p in ibkr_list if p.position < 0)
        print(f"Anzahl Long-Positionen: {len(long_list)}")
        print(f"Anzahl Short-Positionen: {len(short_list)}")

        scanner = TV_Scanner()
        tickers_to_exclude: list[str] = self._util.read_symbols(self._util.get_latest_watchlist_file()) + long_list + short_list
        if self._volatility == Volatility.HIGH:
            limit = min(self._max_number_per_day, self._number_of_stocks - len(long_list+short_list))
            orders = self.buy_big_stocks(limit, scanner=scanner, tickers_to_exclude=tickers_to_exclude)
        else:
            orders = self.buy_performant_stocks(
                long_list=long_list, short_list=short_list, scanner=scanner, tickers_to_exclude=tickers_to_exclude)
        self._util.execute_orders(trader=self._ibkr, orders=orders)
        
    def disconnect(self):
        self._ibkr.disconnect()

def main():
    investor = Investor()
    investor.invest()
    investor.disconnect()

if __name__ == "__main__":
    main()