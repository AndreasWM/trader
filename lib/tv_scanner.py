import os
import sys
from enum import Enum
from tradingview_screener.query import Or, Query
from tradingview_screener.column import Column, col
import pandas as pd
import rookiepy
import shutil
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.position import ScannerPosition

class TV_Scanner:
    def safe_float(self, value, default=0.0):
        return float(value) if value is not None else default
    
    def always_true(self):
        return Column("exchange") != "INVALID"

    def query_us_ytd(self, tickers_to_exclude: list[str], market_cap: int,
                           length: int, capital_per_stock: float, is_long: bool#, dividends_percent: float|None
                           ) -> list[ScannerPosition]:
        column_perf_ytd = 'Perf.YTD'
        cond_limit_size = Column('close') < capital_per_stock
        cond_stocktype = Column('type').isin(['stock','dr'])
        cond_subtype = Column('subtype') != 'preferred'
        cond_exchange = Column('exchange').isin(['NASDAQ', 'NYSE'])
        cond_market_cap = Column('market_cap_basic') > market_cap
        cond_perf_ytd = Column(column_perf_ytd) > 0.0 if is_long else Column(column_perf_ytd) < 0.0
        # cond_dividends = self.always_true() if dividends_percent is None else Column('dividends_yield') > dividends_percent
        cond_macd_hist = Column('MACD.hist|1W') > 0.0 if is_long else Column('MACD.hist|1W') < 0.0
        conditions = [
            cond_limit_size,
            cond_stocktype,
            cond_subtype,
            cond_exchange,
            cond_market_cap,
            cond_perf_ytd,
            # cond_dividends,
            cond_macd_hist,
        ]
        if tickers_to_exclude:
            conditions.append(Column('name').not_in(tickers_to_exclude))
        
        q = Query() \
            .select(
                'name',
                'close',
                'premarket_change',
                'postmarket_change',
                'exchange',
                'type',
                'subtype',
                'market_cap_basic',
                'dividends_yield',
                'MACD.hist|1W',
            ) \
            .where(*conditions) \
            .order_by(column_perf_ytd, ascending=False if is_long else True) \
            .limit(length)
        
        _, scanner_data = q.get_scanner_data()
        
        scanner_data = scanner_data.drop(columns=['ticker'])
        scanner_data = scanner_data.rename(columns={
            "name": "symbol",
            "close": "price",
        })
        
        pos_list = []
        for _, row in scanner_data.iterrows():
            symbol = row['symbol']
            price = self.safe_float(row['price'])
            premarket_change = self.safe_float(row['premarket_change'])
            postmarket_change = self.safe_float(row['postmarket_change'])
            exchange = row['exchange']
            pos = ScannerPosition(symbol=symbol, is_long=is_long, price=price,
                                  premarket_change=premarket_change, postmarket_change=postmarket_change, exchange=exchange)
            pos_list.append(pos)

        return pos_list
