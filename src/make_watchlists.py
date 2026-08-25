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
            
    trader.close()
    print(f"Long-Aktien: {long_pos}, Short-Aktien: {short_pos}")
    print("\n✅ Programm beendet.")