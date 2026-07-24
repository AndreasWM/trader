import os
import sys
from tradingview_screener.query import Query
from tradingview_screener.column import Column

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.position import ScannerPosition

class TV_Scanner:
    def safe_float(self, value, default=0.0):
        return float(value) if value is not None else default
    
    def always_true(self):
        return Column("exchange") != "INVALID"

    def query_us(self, tickers_to_exclude: list[str], market_cap: int,
                           length: int, capital_per_stock: float, leverage: float) -> list[ScannerPosition]:
        cond_limit_size = Column('close') < capital_per_stock
        cond_stocktype = Column('type').isin(['stock','dr'])
        cond_subtype = Column('subtype') != 'preferred'
        cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE'])
        cond_market_cap = Column('market_cap_basic') > market_cap
        conditions = [
            cond_limit_size,
            cond_stocktype,
            cond_subtype,
            cond_exchange,
            cond_market_cap,
        ]
        if tickers_to_exclude:
            conditions.append(Column('name').not_in(tickers_to_exclude))
        
        q = Query() \
            .select(
                'name',
                'close',
                'exchange',
                'type',
                'subtype',
                'Perf.YTD',
                'Ichimoku.Lead1',
                'Ichimoku.Lead2',
                'market_cap_basic',
            ) \
            .where(*conditions) \
            .order_by('Perf.Y', ascending=False) \
            .limit(length)
        
        _, scanner_data = q.get_scanner_data()
        
        scanner_data = scanner_data.drop(columns=['ticker'])
        scanner_data = scanner_data.rename(columns={
            "name": "symbol",
            "close": "price",
        })
        
        # print(",".join(scanner_data.columns))
        pos_list = []
        for _, row in scanner_data.iterrows():
            # print(",".join(str(v) for v in row.values))
            symbol = row['symbol']
            exchange = row['exchange']
            price = self.safe_float(row['price'])
            lead1 = self.safe_float(row['Ichimoku.Lead1'])
            lead2 = self.safe_float(row['Ichimoku.Lead2'])
            if price > max(lead1, lead2):
                pos = ScannerPosition(symbol=symbol, exchange=exchange, price=price, leverage=leverage, flag_is_long=True)
                pos_list.append(pos)
            elif price < min(lead1, lead2):
                pos = ScannerPosition(symbol=symbol, exchange=exchange, price=price, leverage=leverage, flag_is_long=False)
                pos_list.append(pos)

        return pos_list
