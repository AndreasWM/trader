import os
import sys
import yfinance as yf
import pandas as pd
import oracledb
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import MarketOrder
from lib.tv_scanner import TV_Scanner
from lib.stock_util import StockUtil

# ── Verbindungsparameter ────────────────────────────────────────────────────────
DB_USER     = "dein_user"
DB_PASSWORD = "dein_passwort"
DB_DSN      = "localhost:1521/XEPDB1"   # host:port/service_name

# Tuning-Parameter
CHUNK_SIZE       = 50_000   # Zeilen pro executemany-Aufruf
COMMIT_EVERY     = 500_000  # Zeilen zwischen Commits
POOL_MIN         = 2        # Minimale Verbindungen im Pool
POOL_MAX         = 5        # Maximale Verbindungen im Pool


class StockLoader:
    def __init__(self):
        self._util = StockUtil()
        self._sc   = TV_Scanner()
        self._unwanted_tickers = self._util.read_symbols(
            self._util.get_latest_watchlist_file(self._util.get_data_dir_linux())
        )
        self._pool: oracledb.ConnectionPool | None = None

    # ── Connection Pool ─────────────────────────────────────────────────────────

    def _get_pool(self) -> oracledb.ConnectionPool:
        """Erstellt den Connection-Pool beim ersten Aufruf (lazy)."""
        if self._pool is None:
            self._pool = oracledb.create_pool(
                user=DB_USER,
                password=DB_PASSWORD,
                dsn=DB_DSN,
                min=POOL_MIN,
                max=POOL_MAX,
                increment=1,
            )
        return self._pool

    def close_pool(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    # ── Download ────────────────────────────────────────────────────────────────

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
        return self._sc.query_us_symbols(
            tickers_to_exclude=self._unwanted_tickers,
            market_cap=10_000_000_000,
            length=5
        )

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

    # ── Transformation ──────────────────────────────────────────────────────────

    def to_long_format(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Wide → Long mit den Spalten symbol, date, price."""
        if prices.empty:
            return pd.DataFrame(columns=["symbol", "date", "price"])
        prices.index = pd.to_datetime(prices.index).normalize()
        long_df = (
            prices
            .reset_index()
            .rename(columns={"Date": "date"})
            .melt(id_vars="date", var_name="symbol", value_name="price")
            .dropna(subset=["price"])
            [["symbol", "date", "price"]]
            .sort_values(["symbol", "date"])
            .reset_index(drop=True)
        )
        return long_df

    # ── Oracle Bulk-Insert ──────────────────────────────────────────────────────

    @staticmethod
    def _iter_chunks(iterable, size: int):
        """Liefert den Iterator in Blöcken der gewünschten Größe."""
        it = iter(iterable)
        while True:
            chunk = list(islice(it, size))
            if not chunk:
                break
            yield chunk

    def _prepare_rows(self, long_df: pd.DataFrame) -> list[tuple]:
        """Konvertiert den DataFrame in eine Liste von (symbol, date, price)-Tupeln."""
        return [
            (row.symbol, row.date.date(), float(row.price))
            for row in long_df.itertuples(index=False)
        ]

    def save_to_oracle(
        self,
        long_df: pd.DataFrame,
        table_name: str = "stock_prices",
        truncate_first: bool = False,
    ) -> None:
        """
        Schreibt Millionen von Zeilen effizient per Bulk-Insert in Oracle.

        Strategie:
        - oracledb native (kein SQLAlchemy-Overhead)
        - executemany() mit vorbereiteten Tupeln (CHUNK_SIZE Zeilen pro Aufruf)
        - Commit alle COMMIT_EVERY Zeilen (kein riesiges Undo-Segment)
        - setinputsizes() für maximale Bind-Performance
        - Optional: TRUNCATE vor dem Insert (schneller als DELETE)
        """
        if long_df.empty:
            print("⚠️  Keine Daten zum Speichern.")
            return

        total = len(long_df)
        print(f"💾 Schreibe {total:,} Zeilen in Tabelle '{table_name}' …")

        rows = self._prepare_rows(long_df)
        sql  = f"INSERT INTO {table_name} (symbol, date, price) VALUES (:1, :2, :3)"

        pool = self._get_pool()
        with pool.acquire() as conn:
            conn.autocommit = False
            cursor = conn.cursor()

            # Bind-Typen einmalig deklarieren → weniger Overhead pro Zeile
            cursor.setinputsizes(
                oracledb.DB_TYPE_VARCHAR,   # symbol
                oracledb.DB_TYPE_DATE,      # date
                oracledb.DB_TYPE_BINARY_DOUBLE,  # price
            )

            if truncate_first:
                cursor.execute(f"TRUNCATE TABLE {table_name}")
                print(f"  🗑️  Tabelle '{table_name}' geleert.")

            inserted  = 0
            committed = 0

            for chunk in self._iter_chunks(rows, CHUNK_SIZE):
                cursor.executemany(sql, chunk, batcherrors=True)

                # Fehlerhafte Einzelzeilen protokollieren, aber weiterlaufen
                for err in cursor.getbatcherrors():
                    print(f"  ⚠️  Zeile {err.offset}: {err.message}")

                inserted += len(chunk)

                # Commit in definierten Intervallen
                if inserted - committed >= COMMIT_EVERY:
                    conn.commit()
                    committed = inserted
                    pct = inserted / total * 100
                    print(f"  ✔  {inserted:>10,} / {total:,} Zeilen committed ({pct:.1f} %)")

            conn.commit()   # Rest-Zeilen committen
            cursor.close()

        print(f"✅ Fertig – {inserted:,} Zeilen erfolgreich in '{table_name}' geschrieben.")


# ── DDL (zur Referenz) ──────────────────────────────────────────────────────────
CREATE_TABLE_SQL = """
CREATE TABLE stock_prices (
    symbol  VARCHAR2(20)        NOT NULL,
    date    DATE                NOT NULL,
    price   BINARY_DOUBLE,
    CONSTRAINT pk_stock_prices PRIMARY KEY (symbol, date)
);

-- Optional: Index für Datumsabfragen
CREATE INDEX ix_stock_prices_date ON stock_prices (date);
"""


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    loader = StockLoader()
    try:
        symbols  = loader.load_symbols()
        prices   = loader.load_prices(symbols)
        long_df  = loader.to_long_format(prices)

        print(f"\n📊 Tabelle: {len(long_df):,} Zeilen, {long_df['symbol'].nunique()} Symbole")

        loader.save_to_oracle(
            long_df,
            table_name="stock_prices",
            truncate_first=False,   # True = Tabelle vorher leeren
        )
    finally:
        loader.close_pool()


if __name__ == "__main__":
    main()