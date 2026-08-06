import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import LimitOrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil

def separate_positions(positions):
    long_positions = []
    short_positions = []
    
    for position in positions:
        if position.position > 0:
            long_positions.append(position)
        elif position.position < 0:
            short_positions.append(position)
    
    return long_positions, short_positions

if __name__ == "__main__":
    trader = LimitOrder()
    sc = TV_Scanner()
    
    positions = trader.get_stock_positions(timeout=10.0)
    long_pos, short_pos = separate_positions(positions)
    
    long_pos_symbols = [p.symbol.replace(' ', '.') for p in long_pos]
    short_pos_symbols = [p.symbol.replace(' ', '.') for p in short_pos]

    util = StockUtil()
    watchlist_file = 'data/ibkr_long.txt'
    util.create_watchlist_file(long_pos_symbols, filename=watchlist_file)
    if os.path.exists(watchlist_file):
        print(f"\n📥 Watchlist für Long-Positionen erstellt: {watchlist_file}\n")
    watchlist_file = 'data/ibkr_short.txt'
    util.create_watchlist_file(short_pos_symbols, filename=watchlist_file)
    if os.path.exists(watchlist_file):
        print(f"\n📥 Watchlist für Short-Positionen erstellt: {watchlist_file}\n")

    position_symbols = long_pos_symbols + short_pos_symbols
    results = sc.scan_list(stock_list=position_symbols)
    print(results)
    long_pos, short_pos = 0, 0

    print("\n📤 Erstelle Stop-Loss-Orders:\n")
    for _, row in results.iterrows():
        scanner_symbol = row['symbol']
        ib_symbol = scanner_symbol.replace('.', ' ')
        print(f"row: {row}")
        lead1 = float(row['lead1'])
        lead2 = float(row['lead2'])
        
        pos = next((p for p in positions if p.symbol == ib_symbol), None)
        if pos is None:
            continue
            
        is_long = pos.position > 0
        if is_long:
            stop_price = max(lead1, lead2)
            limit_price = stop_price * 0.99
            action = "SELL"
            long_pos += 1
        else:
            stop_price = min(lead1, lead2)
            limit_price = stop_price * 1.01
            action = "BUY"
            short_pos += 1

        quantity = abs(pos.position)
        trader.enqueue_limit_order_close_position(
            symbol=ib_symbol,
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )
        print(f"✅ {scanner_symbol}: {action} {int(quantity)} Stk. | "
            f"Stop={stop_price:.2f} | Limit={limit_price:.2f}")
            
    trader.wait_until_done(timeout=120)
    trader.close()
    print(f"Long-Aktien: {long_pos}, Short-Aktien: {short_pos}")
    print("\n✅ Programm beendet.")