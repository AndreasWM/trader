import time
import sys
import os
from decimal import Decimal
from typing import Callable, Optional

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.ibkr_market_order import LimitOrder

def on_limit_filled(orderId: int, avgFillPrice: float, filled_qty: Decimal):
    """
    Diese Funktion wird aufgerufen, sobald eine Limit-Order vollständig ausgeführt ist.
    """
    print(f"✅ HOOK: LimitOrder {orderId} wurde vollständig ausgeführt.")
    print(f"   Preis={avgFillPrice}, Stück={filled_qty}")


if __name__ == "__main__":
    # Trader starten, Hook registrieren
    trader = LimitOrder(on_filled=on_limit_filled)
    trader.enqueue_limit_order(
        symbol="MRVL",
        qty=54,
        action="SELL",
        limit_price=282.00,
        exchange="NASDAQ",
        currency="USD",
    )

    print("📤 LimitOrder wurde an IB gesendet.")
    print("   Hook springt an, wenn die Order vollständig ausgeführt wird.")
    print("   Programm bleibt verbunden … (STRG+C zum Beenden)")

    try:
        while True:
            # Hier könnte man andere Logik laufen lassen (z. B. Monitoring, Logging, etc.)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Programm beendet, Verbindung wird geschlossen …")
        trader.close()
