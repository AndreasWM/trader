from tradingview_screener.query import Query
from tradingview_screener.column import col
import pandas as pd

class TV_Scanner:
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
                      'close',
                      'exchange',
                      'type',
                      'subtype',
                      'Perf.YTD',
                      'market_cap_basic',
                      'dividends_yield',
                      'MACD.hist|1W',
                    ) \
                    .where(*conditions) \
                    .order_by('Perf.YTD', ascending=False)
                
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
                    "close": "price",
                })
                
                print(f"✅ Insgesamt {len(scanner_data)} Aktien gescannt")
                return scanner_data

def main():
  sc = TV_Scanner()
  stock_list = ['SNDK', 'WDC', 'BE', 'UMC', 'MU', 'STX', 'INTC', 'SIMO', 'DELL', 'MRVL']
  data = sc.scan_list(stock_list=stock_list)
  print(data)

if __name__ == "__main__":
    main()