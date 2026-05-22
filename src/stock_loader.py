import os
import sys
import yfinance as yf
import pandas as pd
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from lib.ibkr_market_order import MarketOrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil

class StockLoader:
    def __init__(self):
        self._util = StockUtil()
        self._sc = TV_Scanner()
        self._unwanted_tickers = self._util.read_symbols(self._util.get_latest_watchlist_file(self._util.get_data_dir_linux()))
    
    def download_in_batches(self, tickers: list[str], batch_size: int = 200, **kwargs) -> pd.DataFrame:
        all_data = []
        num_batches = (len(tickers) + batch_size - 1) // batch_size
        for i in range(0, len(tickers), batch_size):
            print(f"Downloading batch {i // batch_size + 1} of {num_batches}")
            batch = tickers[i:i + batch_size]
            
            df = yf.download(batch, **kwargs, progress=False)
            
            if df is None or df.empty:
                print(f"  ⚠️  No data for batch {i // batch_size + 1}, skipping...")
                continue
            
            all_data.append(df["Close"])
        if not all_data:
            raise ValueError("No data downloaded for any batch.")
        return pd.concat(all_data, axis=1)

    def load_symbols(self) -> list[str]:
        symbols = self._sc.query_us_symbols(tickers_to_exclude=self._unwanted_tickers, market_cap=10_000_000_000, length=5)
        return symbols

    def load_prices(self, symbols: list[str]) -> pd.DataFrame:
        if not symbols:
            print("⚠️  Keine Symbole zum Laden der Preise")
            return pd.DataFrame()
        
        print(f"📥 Lade Preise für {len(symbols)} Symbole...")
        try:
            close_prices = self.download_in_batches(
                tickers=symbols,
                batch_size=50,
                period="3y",
                auto_adjust=True
            )
            print("✅ Preise erfolgreich geladen")
            return close_prices
        except Exception as e:
            print(f"⚠️  Fehler beim Laden der Preise: {e}")
            return pd.DataFrame()

    def to_long_format(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Wandelt den Wide-DataFrame (Datum x Symbol) in eine Long-Tabelle
        mit den Spalten symbol, date, price um."""
        if prices.empty:
            return pd.DataFrame(columns=["symbol", "date", "price"])

        # Falls der Index noch kein reines Datum ist, normalisieren
        prices.index = pd.to_datetime(prices.index).normalize()

        long_df = (
            prices
            .reset_index()                          # Datum wird zur Spalte
            .rename(columns={"Date": "date"})       # yfinance nennt den Index "Date"
            .melt(id_vars="date",                   # von Wide nach Long
                  var_name="symbol",
                  value_name="price")
            .dropna(subset=["price"])               # Zeilen ohne Kurs entfernen
            [["symbol", "date", "price"]]           # Spaltenreihenfolge festlegen
            .sort_values(["symbol", "date"])
            .reset_index(drop=True)
        )

        return long_df

def main():
    loader = StockLoader()
    symbols = loader.load_symbols()
    prices = loader.load_prices(symbols)

    long_df = loader.to_long_format(prices)

    print(f"\n✅ Tabelle mit {len(long_df):,} Zeilen und {long_df['symbol'].nunique()} Symbolen:")
    print(long_df)

if __name__ == "__main__":
    main()