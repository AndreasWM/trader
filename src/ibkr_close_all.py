import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.stock_util import StockUtil

if __name__ == "__main__":
    trader = MarketOrder()
    util = StockUtil()
    util.ibkr_close_all(trader=trader)
    trader.close()

