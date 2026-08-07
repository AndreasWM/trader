import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import LimitOrder
from lib.stock_util import StockUtil
from lib.tv_scanner import TV_Scanner

def manage_stalled_orders(limit_trader: LimitOrder):
    stalled = limit_trader.get_stalled_stop_limit_orders()
    for o in stalled:
        print(f"OrderId={o.orderId}, Symbol={o.symbol}, Quantity={o.quantity}, Action={o.action}")
        limit_trader.cancel_orders_for_symbol(o.symbol)
        limit_trader.sleep(0.3)
        limit_trader.enqueue_adaptive_market_order(
            symbol=o.symbol,
            qty=o.quantity,
            action=o.action,
            priority="Normal",
        )

if __name__ == "__main__":
    sc = TV_Scanner()
    limit_trader = LimitOrder()
    util = StockUtil()

    manage_stalled_orders(limit_trader=limit_trader)    

    limit_trader.wait_until_sent(timeout=120)
    limit_trader.close()
    print("\n✅ Programm beendet.")