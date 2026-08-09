import os
import sys
import pandas as pd
from tradingview_screener.query import Query
from tradingview_screener.column import Column, col

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
                           length: int, capital_per_stock: float, leverage: float, flag_init: bool = True) -> list[ScannerPosition]:
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
                'Perf.Y',
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
            symbol = row['symbol']
            exchange = row['exchange']
            price = self.safe_float(row['price'])
            lead1 = self.safe_float(row['Ichimoku.Lead1'])
            lead2 = self.safe_float(row['Ichimoku.Lead2'])
            flag_is_long = True if price > max(lead1, lead2) else False if price < min(lead1, lead2) else None
            if (flag_is_long is None) != flag_init:
                pos = ScannerPosition(symbol=symbol, exchange=exchange, price=price, leverage=leverage,
                                        flag_is_long=flag_is_long, lead1=lead1, lead2=lead2)
                pos_list.append(pos)
                # print(",".join(str(v) for v in row.values))

        return pos_list

    def scan_list(self, stock_list: list[str]) -> pd.DataFrame:
        print(f"📡 Scanne {len(stock_list)} Aktien bei TradingView...")
        
        if stock_list is None:
            print("⚠️  Quell-Aktienliste ist leer")
            return pd.DataFrame()
        else:
            all_data = []
            batch_size = 50
            
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                
                conditions = [
                    col('name').isin(batch),
                ]
                q = Query() \
                    .select(
                        'name',
                        'exchange',
                        'market_cap_basic',
                        'close',
                        'premarket_close',
                        'high|1',
                        'low|1',
                        'Perf.YTD',
                        'Ichimoku.Lead1',
                        'Ichimoku.Lead2',
                    ) \
                    .where(*conditions)
                
                try:
                    _, scanner_data = q.get_scanner_data()
                except (TypeError, AttributeError):
                    print(f"  ⚠️  Fehler bei Batch {i//batch_size + 1}")
                    continue
                
                if scanner_data is not None and not scanner_data.empty:
                    all_data.append(scanner_data)
                    print(f"  ✓ Batch {i//batch_size + 1}: {len(scanner_data)} Aktien")
        
            if not all_data:
                print("⚠️  Keine Daten gefunden")
                return pd.DataFrame()
            else:
                scanner_data = pd.concat(all_data, ignore_index=True)
                
                scanner_data = scanner_data.drop(columns=['ticker'], errors='ignore')
                scanner_data = scanner_data.rename(columns={
                    "name": "symbol",
                    "market_cap_basic": "market_cap",
                    "close": "price",
                    "premarket_close": "premarket_price",
                    "high|1": "high_1",
                    "low|1": "low_1",
                    "Perf.YTD": "perf_ytd",
                    "Ichimoku.Lead1": "lead1",
                    "Ichimoku.Lead2": "lead2",
                })
                
                print(f"✅ Insgesamt {len(scanner_data)} Aktien gescannt")
                return scanner_data
