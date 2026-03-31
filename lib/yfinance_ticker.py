import yfinance as yf
import pandas as pd
import yfinance as yf

class YfinanceTicker:
    def get_price(self, symbol="EURUSD=X") -> float:
        ticker = yf.Ticker(symbol)
        try:
            # Versuch 1: Über history (stabiler als fast_info)
            data = ticker.history(period="1d")
            if not data.empty:
                return data['Close'].iloc[-1]
            
            # Versuch 2: Fallback auf fast_info, falls history leer ist
            price = ticker.fast_info.get("last_price")
            if price is not None:
                return price
                
            raise ValueError(f"Keine Preisdaten für {symbol} gefunden.")
            
        except Exception as e:
            print(f"Warnung: Fehler beim Abrufen von {symbol}: {e}")
            # Optional: Einen festen Fallback-Wert nutzen, damit das Skript nicht stirbt
            if symbol == "EURUSD=X":
                print("Nutze Fallback-Kurs: 1.08")
                return 1.08 
            return 0.0
#    def get_price(self, symbol: str):
#        ticker = yf.Ticker(symbol)
#        price = ticker.fast_info["last_price"]
#        return price

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        """
        Holt aktuelle Schlusskurse (Close) für mehrere Symbole gleichzeitig über yfinance.download().
        Gibt ein Dict {symbol: price} zurück.
        """
        try:
            data = yf.download(
                tickers=symbols,
                period="1d",
                interval="1d",
                group_by="ticker",
                progress=False,
                auto_adjust=False
            )

            if data is None or data.empty:
                return {}

            prices = {}
            for symbol in symbols:
                try:
                    close_series = data[symbol]["Close"]
                    if not close_series.empty:
                        prices[symbol] = float(close_series.iloc[-1])
                except Exception:
                    continue

            return prices

        except Exception:
            return {}
    
    def get_exchange(self, symbol: str):
        ticker = yf.Ticker(symbol)
        match ticker.info.get("exchange"):
            case "NMS":
                exchange = "NASDAQ"
            case "NYQ":
                exchange = "NYSE"
            case _:
                exchange = "unknown"
        return exchange

    def get_eurusd(self):
        return self.get_price(symbol="EURUSD=X")
