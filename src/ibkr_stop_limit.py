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
MIN_DIFF_PERCENT = 1.0
MIN_MARKET_CAP = 50_000_000_000
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

def create_long_order(limit_trader: LimitOrder, scanner_pos: ScannerPosition, capital_per_stock: float):
    if scanner_pos.leverage > 0:
        quantity = round(capital_per_stock * scanner_pos.leverage / scanner_pos.price)

        action = "BUY"
        stop_price = max(scanner_pos.lead1, scanner_pos.lead2)
        spread_factor = 1 + SPREAD
        limit_price = stop_price * spread_factor
        limit_trader.enqueue_limit_order(
            symbol=scanner_pos.symbol,
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )

def create_sell_order(limit_trader: LimitOrder, ibkr_pos: IBKRPosition, scanner_pos: ScannerPosition):
    stop_price = max(scanner_pos.lead1, scanner_pos.lead2)
    limit_price = stop_price * (1 - SPREAD)
    action = "SELL"
    quantity = abs(ibkr_pos.position)
    if abs(scanner_pos.price - stop_price) / scanner_pos.price > MIN_DIFF_PERCENT/100:
        limit_trader.enqueue_limit_order(
            symbol=scanner_pos.symbol.replace('.', ' '),
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )
        print(f"✅ {scanner_pos.symbol}: {action} {int(quantity)} Stk. | "
            f"Stop={stop_price:.2f} | Limit={limit_price:.2f}")

def create_short_order(limit_trader: LimitOrder, scanner_pos: ScannerPosition, capital_per_stock: float):
    if scanner_pos.leverage > 0:
        quantity = round(capital_per_stock * scanner_pos.leverage / scanner_pos.price)

        action = "SELL"
        stop_price = min(scanner_pos.lead1, scanner_pos.lead2)
        spread_factor = 1 - SPREAD
        limit_price = stop_price * spread_factor
        limit_trader.enqueue_limit_order(
            symbol=scanner_pos.symbol,
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )

def create_cover_order(limit_trader: LimitOrder, ibkr_pos: IBKRPosition, scanner_pos: ScannerPosition):
    stop_price = min(scanner_pos.lead1, scanner_pos.lead2)
    limit_price = stop_price * (1 + SPREAD)
    action = "BUY"
    quantity = abs(ibkr_pos.position)
    if abs(scanner_pos.price - stop_price) / scanner_pos.price > MIN_DIFF_PERCENT/100:
        limit_trader.enqueue_limit_order(
            symbol=scanner_pos.symbol.replace('.', ' '),
            qty=int(quantity),
            action=action,
            limit_price=round(limit_price, 2),
            stop_price=round(stop_price, 2)
        )
        print(f"✅ {scanner_pos.symbol}: {action} {int(quantity)} Stk. | "
            f"Stop={stop_price:.2f} | Limit={limit_price:.2f}")

def hedge(limit_trader: LimitOrder, ibkr_positions: list[IBKRPosition], scanner_positions: list[ScannerPosition]):
    position_symbols = [p.symbol.replace(' ', '.') for p in ibkr_positions]
    hedge_positions = sc.scan_list(stock_list=position_symbols)
    scanner_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in scanner_positions}
    hedge_lookup: dict[str, ScannerPosition] = {p.symbol: p for p in hedge_positions}

    for ibkr_pos in ibkr_positions:
        scanner_pos = scanner_lookup.get(ibkr_pos.symbol)
        if scanner_pos is None:
            hedge_pos = hedge_lookup.get(ibkr_pos.symbol)
            if hedge_pos is not None:
                if hedge_pos.flag_is_long is None:
                    print(f"  ⚠️  Fehler: {ibkr_pos.symbol} ist im Depot, aber der Kurs ist auf der Ichimoku-Wolke.")
                elif ibkr_pos.position > 0:
                    create_sell_order(limit_trader=limit_trader, ibkr_pos=ibkr_pos, scanner_pos=hedge_pos)
                else:
                    create_cover_order(limit_trader=limit_trader, ibkr_pos=ibkr_pos, scanner_pos=hedge_pos)

def trade(limit_trader: LimitOrder,
          ibkr_positions: list[IBKRPosition], scanner_positions: list[ScannerPosition],
          capital_per_stock: float):
    ibkr_lookup: dict[str, IBKRPosition] = {p.symbol: p for p in ibkr_positions}
    for scanner_pos in scanner_positions:
        ibkr_pos = ibkr_lookup.get(scanner_pos.symbol)
        if ibkr_pos is not None:
            if ibkr_pos.position > 0:
                create_sell_order(limit_trader=limit_trader, ibkr_pos=ibkr_pos, scanner_pos=scanner_pos)
                create_short_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)
            else:
                create_cover_order(limit_trader=limit_trader, ibkr_pos=ibkr_pos, scanner_pos=scanner_pos)
                create_long_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)
        else:
            if scanner_pos.flag_is_long is None:
                create_long_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)
                create_short_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)
            elif scanner_pos.flag_is_long:
                create_short_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)
            else:
                create_long_order(limit_trader=limit_trader, scanner_pos=scanner_pos, capital_per_stock=capital_per_stock)

def trade_and_hedge(limit_trader: LimitOrder):
    unwanted_tickers = util.read_symbols(util.get_latest_do_not_trade_file())
    capital_per_stock = calculate_capital_per_stock(market_trader=limit_trader)
    ibkr_positions: list[IBKRPosition] = util.ibkr_positions(trader=limit_trader)
    scanner_positions = sc.query_us(tickers_to_exclude=unwanted_tickers, market_cap=MIN_MARKET_CAP,
                                    length=NUMBER_OF_STOCKS, capital_per_stock=capital_per_stock, leverage=LEVERAGE, flag_init=False)
    hedge(limit_trader=limit_trader, ibkr_positions=ibkr_positions, scanner_positions=scanner_positions)
    trade(limit_trader=limit_trader,
          ibkr_positions=ibkr_positions, scanner_positions=scanner_positions, capital_per_stock=capital_per_stock)

if __name__ == "__main__":
    sc = TV_Scanner()
    limit_trader = LimitOrder()
    util = StockUtil()
    
    limit_trader.cancel_all_orders()
    limit_trader.sleep(0.3)

    trade_and_hedge(limit_trader=limit_trader)

    limit_trader.wait_until_sent(timeout=120)
    limit_trader.close()
    print("\n✅ Programm beendet.")