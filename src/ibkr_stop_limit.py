import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder, LimitOrder
from lib.position import IBKRPosition, ScannerPosition
from lib.stock_util import StockUtil
from lib.tv_scanner import TV_Scanner
from lib.yfinance_ticker import YfinanceTicker

LEVERAGE = 2.0
MIN_MARKET_CAP = 50_000_000_000
MIN_DIFF_PERCENT = 1.0
NUMBER_OF_STOCKS = 50
SPREAD = 0.005
CAPITAL_RESERVE = 0.0

def calculate_capital_per_stock(market_trader: MarketOrder) -> float:
    net_liquidation_euro = market_trader.get_net_liquidation()
    price_eurusd = YfinanceTicker().get_eurusd()
    net_liquidation = net_liquidation_euro * price_eurusd
    investment_capacity=net_liquidation - CAPITAL_RESERVE
    capital_per_stock: float = investment_capacity * LEVERAGE / NUMBER_OF_STOCKS
    return capital_per_stock

def enqueue_stop_limit_order(limit_trader: LimitOrder, scanner_pos: ScannerPosition, capital_per_stock: float):
    ib_symbol = scanner_pos.symbol
    if scanner_pos.leverage is not None:
        quantity = round(capital_per_stock * scanner_pos.leverage / scanner_pos.price)

        action = "BUY"
        stop_price = max(scanner_pos.lead1, scanner_pos.lead2)
        if stop_price / scanner_pos.price > (1 + MIN_DIFF_PERCENT/100):
            spread_factor = 1 + SPREAD
            limit_price = stop_price * spread_factor
            limit_trader.enqueue_limit_order_close_position(
                symbol=ib_symbol,
                qty=int(quantity),
                action=action,
                limit_price=round(limit_price, 2),
                stop_price=round(stop_price, 2)
            )

        action = "SELL"
        stop_price = min(scanner_pos.lead1, scanner_pos.lead2)
        if stop_price / scanner_pos.price < (1 - MIN_DIFF_PERCENT/100):
            spread_factor = 1 - SPREAD
            limit_price = stop_price * spread_factor
            limit_trader.enqueue_limit_order_close_position(
                symbol=ib_symbol,
                qty=int(quantity),
                action=action,
                limit_price=round(limit_price, 2),
                stop_price=round(stop_price, 2)
            )

def buy(limit_trader: LimitOrder):
    unwanted_tickers = util.read_symbols(util.get_latest_do_not_trade_file())
    capital_per_stock = calculate_capital_per_stock(market_trader=limit_trader)
    scanner_positions = sc.query_us(tickers_to_exclude=unwanted_tickers, market_cap=MIN_MARKET_CAP,
                                    length=NUMBER_OF_STOCKS, capital_per_stock=capital_per_stock, leverage=LEVERAGE, flag_init=False)
    extra_symbols = ["AXTI"]
    extra_positions = sc.scan_list(stock_list=extra_symbols, leverage=LEVERAGE)
    selected_positons = extra_positions + scanner_positions
    ibkr_positions: list[IBKRPosition] = util.ibkr_positions(trader=limit_trader)
    stock_symbols = [p.symbol for p in ibkr_positions]
    invest_symbols = [p.symbol for p in selected_positons
                            if p.symbol not in [symbol for symbol in stock_symbols]]
    cnt_stocks = len(stock_symbols)
    cnt_new_stocks = max(NUMBER_OF_STOCKS - cnt_stocks, 0)
    invest_symbols = invest_symbols[:cnt_new_stocks]
    invest_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in selected_positons}
    for symbol in invest_symbols:
        scanner_pos = invest_lookup.get(symbol)
        if scanner_pos is not None:
            enqueue_stop_limit_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)

def hedge(limit_trader: LimitOrder):
    positions = limit_trader.get_stock_positions(timeout=10.0)
    position_symbols = [p.symbol.replace(' ', '.') for p in positions]
    hedge_positions = sc.scan_list(stock_list=position_symbols)

    long_pos, short_pos = 0, 0
    print("\n📤 Erstelle Stop-Loss-Orders:\n")
    for position in hedge_positions:
        scanner_symbol = position.symbol
        ib_symbol = scanner_symbol.replace('.', ' ')
        print(f"Position: {position}")
        price = position.price
        lead1 = position.lead1
        lead2 = position.lead2
        
        pos = next((p for p in positions if p.symbol == ib_symbol), None)
        if pos is None:
            continue
            
        is_long = pos.position > 0
        if is_long:
            next_stop = price * (1 - MIN_DIFF_PERCENT/100)
            stop_price = min(next_stop, max(lead1, lead2))
            limit_price = stop_price * (1 - SPREAD)
            action = "SELL"
            long_pos += 1
        else:
            next_stop = price * (1 + MIN_DIFF_PERCENT/100)
            stop_price = max(next_stop, min(lead1, lead2))
            limit_price = stop_price * (1 + SPREAD)
            action = "BUY"
            short_pos += 1

        quantity = abs(pos.position)
        limit_trader.enqueue_limit_order_close_position(
            symbol=ib_symbol,
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )
        print(f"✅ {scanner_symbol}: {action} {int(quantity)} Stk. | "
            f"Stop={stop_price:.2f} | Limit={limit_price:.2f}")
            
    print(f"Long-Aktien: {long_pos}, Short-Aktien: {short_pos}")

if __name__ == "__main__":
    sc = TV_Scanner()
    limit_trader = LimitOrder()
    util = StockUtil()
    
    limit_trader.cancel_all_orders()
    limit_trader.sleep(0.3)

    hedge(limit_trader=limit_trader)

    if LEVERAGE > 0:
        buy(limit_trader=limit_trader)

    limit_trader.wait_until_sent(timeout=120)
    limit_trader.close()
    print("\n✅ Programm beendet.")