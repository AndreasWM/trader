import threading
import time
import subprocess

from typing import List, Optional, Deque, Tuple, Callable
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel
from ibapi.common import OrderId
from ibapi.tag_value import TagValue

@dataclass
class IBKROrder:
    symbol: str
    # exchange: str
    # position: int
    qty: int
    action: str

@dataclass
class PositionRecord:
    account: str
    symbol: str
    conId: int
    exchange: str
    currency: str
    position: float
    avgCost: float

class MarketOrder(EClient, EWrapper):
    def __init__(self, auto_close: bool = False, idle_shutdown_secs: float = 2.0):
        EClient.__init__(self, self)
        self._host = "127.0.0.1"
#        self._host = self.detect_ib_host()
#        print(f"IB Host erkannt: {self._host}")
#        self._port = "10.255.255.254"  # Default-Wert, wird in detect_ib_host überschrieben
#        print(f"IB Port gesetzt auf: {self._port}")
        self._port = 7496
        self._client_id = 100

        self._next_valid_id: Optional[OrderId] = None
        self._connected_event = threading.Event()
        self._shutdown_event = threading.Event()

        # Ordersteuerung
        self._order_queue: Deque[Tuple[Order, Contract]] = deque()
        self._current_order_id: Optional[OrderId] = None

        # Kapitalabfrage
        self._capital: float = 0.0
        self._capital_event = threading.Event()

        # Positionsabfrage
        self._positions: List[PositionRecord] = []
        self._positions_done = threading.Event()

        # Order-Tracking (für LimitOrder, aber hier initialisiert)
        self._open_orders: dict[int, Contract] = {}
        self._open_orders_done = threading.Event()

        # Steuerung für automatisches Schließen
        self._auto_close = auto_close               # wenn True: altes Verhalten (schließt, wenn Queue leer)
        self._idle_shutdown_secs = idle_shutdown_secs

        print(f"Versuche Verbindung zu {self._host}:{self._port}...")
            
        # 1. Verbindung NUR EINMAL initiieren
        self.connect(self._host, self._port, self._client_id)
            
        # 2. Den Thread NUR EINMAL starten
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

        # 3. Warten auf Bestätigung durch nextValidId
        if not self._connected_event.wait(timeout=10):
            print(f"DEBUG: Host war {self._host}")
            raise RuntimeError("Verbindung fehlgeschlagen: Timeout beim Warten auf nextValidId.")

    def sleep(self, seconds: float) -> None:
        if False:
            time.sleep(seconds)

    def detect_ib_host(self) -> str:
        # 1. Check: Läuft das Skript in WSL?
        if "microsoft" in subprocess.check_output("uname -a", shell=True).decode().lower():
            try:
                # Hol die IP des Windows-Hosts (das Gateway)
                cmd = "ip route show | grep default | awk '{print $3}'"
                host_ip = subprocess.check_output(cmd, shell=True).decode().strip()
                if host_ip:
                    return host_ip
            except Exception:
                pass
        
        # 2. Fallback: Wenn echter Ubuntu-PC oder WSL-Erkennung fehlschlägt
        return "127.0.0.1"
        
    # -----------------------------
    # Wrapper-Callbacks (Kern)
    # -----------------------------
    def nextValidId(self, orderId: OrderId):
        # print(f"[IB] nextValidId: {orderId}")
        self._next_valid_id = orderId
        self._connected_event.set()
        # Falls bereits Orders in der Queue sind, starten
        self._try_place_next()

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
        errorTime: str = "",
    ):

        """IB Fehler-Callback – unterscheidet Statusmeldungen von echten Fehlern."""

        # Defensive Konvertierung auf String
        msg = str(errorString).strip()

        base_code = None
        try:
            # Versuch, erste "Zahl" aus der Nachricht zu extrahieren
            base_code = int(msg.split()[0])
        except (ValueError, IndexError):
            # Fallback: vielleicht ist errorCode schon direkt die Zahl
            try:
                base_code = int(errorCode)
            except Exception:
                pass

        # Info-Meldungen statt ERROR
        if base_code in {2104, 2106, 2158}:
            # print(f"[IB][INFO] ({base_code}) {msg}")
            # if advancedOrderRejectJson:
            #     print(f"[IB][INFO-ADV] {advancedOrderRejectJson}")
            return

        # Sonst normaler Fehler
        print(f"[IB][ERROR] reqId={reqId} code={errorCode} msg={msg}")
        if advancedOrderRejectJson:
            print(f"[IB][ERROR-ADV] {advancedOrderRejectJson}")
        if errorTime:
            print(f"[IB][ERROR-TIME] at {errorTime}")

        # Falls Order-Kontext offen → abbrechen
        if reqId != -1 and self._current_order_id is not None:
            print(f"[IB][ERROR] Abbruch für OrderId={self._current_order_id}, fahre mit nächster Order fort.")
            self._current_order_id = None
            self.sleep(0.3)
            self._try_place_next()

    def orderStatus(
        self,
        orderId: OrderId,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        # print(f"[IB] orderStatus id={orderId} status={status} filled={filled} remaining={remaining} avgFill={avgFillPrice}")

        if self._current_order_id != orderId:
            return

        if status in ("PreSubmitted", "Submitted", "Filled"):
            self._advance_to_next()

    def openOrder(self, orderId: OrderId, contract: Contract, order: Order, orderState):
        # print(f"[IB] openOrder id={orderId} {contract.symbol} state={orderState.status}")
        self._open_orders[orderId] = contract

    def openOrderEnd(self):
        """Callback signalisiert Ende der offenen Orders"""
        self._open_orders_done.set()

    def execDetails(self, reqId, contract: Contract, execution):
        print(f"[IB] execDetails {contract.symbol} execId={execution.execId} qty={execution.shares}")

    def accountSummary(self, reqId, account: str, tag: str, value: str, currency: str):
        if tag == "NetLiquidation":
            try:
                self._capital = float(value)
            except ValueError:
                self._capital = 0.0
            self._capital_event.set()

    def accountSummaryEnd(self, reqId: int):
        self._capital_event.set()

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        """Callback für Positionsdaten – filtert auf Aktien"""
        if contract.secType == "STK" and position != 0:
            rec = PositionRecord(
                account=account,
                symbol=contract.symbol or contract.localSymbol or "",
                conId=contract.conId,
                exchange=contract.primaryExchange or contract.exchange or "",
                currency=contract.currency or "",
                position=position,
                avgCost=avgCost,
            )
            self._positions.append(rec)

    def positionEnd(self):
        """Callback signalisiert Ende der Positionsdaten"""
        self._positions_done.set()

    # -----------------------------
    # Interne Orchestrierung
    # -----------------------------
    def enqueue_adaptive_market_order(self, symbol: str, qty: int, action: str, priority: str = "Normal", exchange: str = "SMART", currency: str = "USD"):
        """
        Fügt eine Adaptive Market Order (TIF=DAY) in die Queue.
        """
        contract = self._make_stock_contract(symbol, exchange, currency)
        order = self._make_adaptive_market_order(action, qty, priority)
        self._order_queue.append((order, contract))
        self._try_place_next()

    def enqueue_adaptive_close_order(self, symbol: str, qty: int, action: str, priority: str = "Normal"):
        """
        Fügt eine Adaptive Market Order (TIF=DAY) in die Queue.
        """
        # Erst alle bestehenden Orders für dieses Symbol canceln
        self.cancel_orders_for_symbol(symbol)
        # Kurze Pause, damit Cancels durchlaufen
        self.sleep(0.3)
        
        contract = self._make_stock_contract(symbol)
        order = self._make_adaptive_market_order(action, qty, priority)
        self._order_queue.append((order, contract))
        self._try_place_next()

    def _try_place_next(self):
        # Holen wir uns die Version einmal in eine Variable für bessere Lesbarkeit
        v = self.serverVersion()
        
        # Abbrechen, wenn:
        # 1. Noch keine Order ID vom Server da ist
        # 2. ODER die Version noch None ist
        # 3. ODER die Version 0 ist (Handshake noch nicht fertig)
        if self._next_valid_id is None or v is None or v <= 0:
            return
        
        if self._current_order_id is not None:
            return
        if not self._order_queue:
            # Wenn auto_close gesetzt ist, altes Verhalten: sofort schließen.
            if self._auto_close:
                # print("[IB][DEBUG] Queue leer und auto_close aktiv -> graceful shutdown.")
                self._graceful_shutdown()
            # else:
            #     # NEU: einfach warten auf neue Orders; nicht sofort disconnecten.
            #     print("[IB][DEBUG] Queue leer -> warte auf neue Orders (keine automatische Trennung).")
            return

        order, contract = self._order_queue.popleft()
        self._current_order_id = self._next_valid_id
        self._next_valid_id += 1

        print(f"[IB] -> Sende Order {self._current_order_id}: {order.action} {order.totalQuantity} {contract.symbol} (Adaptive={order.algoStrategy})")
        self.placeOrder(self._current_order_id, contract, order)

    def _advance_to_next(self):
        print(f"[IB] <- Order {self._current_order_id} akzeptiert/gefüllt, fahre fort.")
        self._current_order_id = None
        self.sleep(0.3)  # kleine Atempause
        self._try_place_next()

    def _graceful_shutdown(self):
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        # Leichte Verzögerung, damit finale Callbacks noch durchlaufen
        def _close():
            self.sleep(0.5)
            print("[IB] Schließe Verbindung …")
            try:
                self.disconnect()
            except Exception:
                pass
        threading.Thread(target=_close, daemon=True).start()

    # -----------------------------
    # Order-/Contract-Builder
    # -----------------------------
    @staticmethod
    def _make_stock_contract(symbol: str, exchange: str = "SMART", currency: str = "USD") -> Contract:
        c = Contract()
        c.symbol = symbol.upper()
        c.secType = "STK"
        c.exchange = "SMART"
        if exchange != "SMART":
            c.primaryExchange = exchange
        c.currency = currency
        return c
    
    @staticmethod
    def _make_adaptive_market_order(action: str, qty: int, priority: str = "Normal") -> Order:
        """
        Erzeugt eine Adaptive-Market-Order mit TIF=DAY.
        Erlaubte priority: "Normal" | "Patient" | "Urgent"
        """
        if priority not in ("Normal", "Patient", "Urgent"):
            raise ValueError(f"Ungültige adaptivePriority: {priority}")

        o = Order()
        o.action = action.upper()           # BUY | SELL
        o.orderType = "MKT"                 # Market Order
        o.totalQuantity = int(qty)
        o.tif = "GTC"                       # WICHTIG: Adaptive ist in Live-Accounts i.d.R. nur DAY
        o.algoStrategy = "Adaptive"
        o.algoParams = [TagValue("adaptivePriority", priority)]

        # Deprecated Flags explizit leeren (verhindert 10268/Legacy-Felder)
        # (werden von IB historisch teils implizit gesetzt)
        o.eTradeOnly = ""
        o.firmQuoteOnly = ""

        return o

    # -----------------------------
    # Convenience: blockierender Wait
    # -----------------------------
    def wait_until_done(self, timeout: Optional[float] = None):
        """
        Blockiert bis:
          - _shutdown_event gesetzt ist (durch _graceful_shutdown), oder
          - timeout erreicht ist.
        Wenn auto_close=False, warten wir auf 'idle' (keine Queue + keine laufende Order)
        für self._idle_shutdown_secs und schließen dann sauber.
        """
        start = time.time()
        idle_start = None
        while not self._shutdown_event.is_set():
            time.sleep(0.2)

            # Idle detection: keine Orders in Queue und kein laufender Auftrag
            if not self._order_queue and self._current_order_id is None:
                if idle_start is None:
                    idle_start = time.time()
                elif (time.time() - idle_start) >= self._idle_shutdown_secs:
                    print(f"[IB][INFO] Keine Aufträge mehr seit {self._idle_shutdown_secs}s – schließe Verbindung.")
                    self._graceful_shutdown()
                    break
            else:
                idle_start = None

            if timeout is not None and (time.time() - start) > timeout:
                print("[IB][WARN] Timeout erreicht – erzwungener Shutdown.")
                self._graceful_shutdown()
                break

        # Warte auf Netzwerkthread
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def execute(self, orders: List[IBKROrder]):
        for o in orders:
            # Erst alle bestehenden Orders für dieses Symbol canceln
            self.cancel_orders_for_symbol(symbol=o.symbol)
            # Kurze Pause, damit Cancels durchlaufen
            self.sleep(0.3)
            self.enqueue_adaptive_market_order(
                symbol=o.symbol,
                qty=o.qty,
                action=o.action,
                priority="Normal",
            )

        # Blockierend warten, bis alles erledigt ist (optional Timeout setzen)
        self.wait_until_done(timeout=120)
        print("Ready.")

    # -----------------------------
    # Kapitalabfrage
    # -----------------------------
    def get_capital(self, timeout: float = 5.0) -> float:
        self._capital_event.clear()
        self.reqAccountSummary(1, "All", "NetLiquidation")
        if not self._capital_event.wait(timeout=timeout):
            raise TimeoutError("Keine Antwort von IB erhalten")
        self.cancelAccountSummary(1)
        return self._capital

    # -----------------------------
    # Positionsabfrage
    # -----------------------------
    def get_stock_positions(self, timeout: float = 10.0) -> List[PositionRecord]:
        """Lädt alle Aktienpositionen via reqPositions und wartet auf positionEnd."""
        self._positions.clear()
        self._positions_done.clear()
        
        self.reqPositions()
        finished = self._positions_done.wait(timeout)
        
        if not finished:
            print("[IB][WARN] Timeout beim Warten auf positionEnd – gebe evtl. unvollständige Daten zurück.")
        
        return self._positions.copy()
    
    def close(self):
        self.sleep(0.5)
        try:
            if self.isConnected():
                self.disconnect()
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2)
    
    def all_order_ids_for_symbol(self, symbol: str) -> List[int]:
        """Gibt alle offenen Orders für ein bestimmtes Symbol zurück."""
        return [
            order_id for order_id, contract in self._open_orders.items()
            if contract.symbol == symbol
        ]

    def cancel_orders_for_symbol(self, symbol: str):
        """Cancelt alle offenen Orders für ein bestimmtes Symbol"""
        orders_to_cancel = self.all_order_ids_for_symbol(symbol)
        
        for order_id in orders_to_cancel:
            print(f"[IB] Canceling Order {order_id} for {symbol}")
            order_cancel = OrderCancel()  # Optionale Cancel-Parameter hier setzen
            self.cancelOrder(order_id, order_cancel)
            self.sleep(0.1)  # Kleine Pause zwischen Cancels

class LimitOrder(MarketOrder):
    def __init__(self, auto_close: bool = False, idle_shutdown_secs: float = 2.0, on_filled: Optional[Callable] = None):
        self._on_filled_hook = on_filled
        
        # Jetzt erst Parent initialisieren (baut Verbindung auf)
        super().__init__(auto_close=auto_close, idle_shutdown_secs=idle_shutdown_secs)

    def openOrder(self, orderId: OrderId, contract: Contract, order: Order, orderState):
        """Überschreibt Parent, um offene Orders zu tracken"""
        super().openOrder(orderId, contract, order, orderState)
        self._open_orders[orderId] = contract

    def openOrderEnd(self):
        """Callback signalisiert Ende der offenen Orders"""
        self._open_orders_done.set()

    def orderStatus(
        self,
        orderId: OrderId,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        print(f"[IB][LIMIT] orderStatus id={orderId} status={status} filled={filled} remaining={remaining} avgFill={avgFillPrice}")

        # Order aus Open-Orders entfernen wenn gefüllt oder gecancelt
        if status in ("Filled", "Cancelled"):
            self._open_orders.pop(orderId, None)

        if self._current_order_id != orderId:
            return

        if status in ("PreSubmitted", "Submitted", "Filled"):
            if status == "Filled" and self._on_filled_hook:
                try:
                    self._on_filled_hook(orderId=orderId, avgFillPrice=avgFillPrice, filled_qty=filled)
                except Exception as e:
                    print(f"[IB][HOOK-ERROR] Fehler im on_filled_hook: {e}")
            
            self._advance_to_next()

    def get_open_orders(self, timeout: float = 5.0) -> dict[int, Contract]:
        """Lädt alle offenen Orders"""
        self._open_orders.clear()
        self._open_orders_done.clear()
        
        self.reqOpenOrders()
        finished = self._open_orders_done.wait(timeout)
        
        if not finished:
            print("[IB][WARN] Timeout beim Warten auf openOrderEnd")
        
        return self._open_orders.copy()

    def enqueue_limit_order_close_position(self, symbol: str, qty: int, action: str, limit_price: float, stop_price: float | None = None):
        """
        Schließt eine Position: Cancelt zuerst alle Orders für das Symbol, 
        dann erstellt es eine neue Stop-Limit-Order.
        """
        # Erst alle bestehenden Orders für dieses Symbol canceln
        self.cancel_orders_for_symbol(symbol)
        
        # Kurze Pause, damit Cancels durchlaufen
        self.sleep(0.3)
        
        # Dann neue Order erstellen
        self.enqueue_limit_order(symbol, qty, action, limit_price, stop_price)

    # -----------------------------
    # Order-/Contract-Builder
    # -----------------------------
    @staticmethod
    def _make_limit_order(action: str, qty: int, limit_price: float, stop_price: float | None = None) -> Order:
        """
        Erzeugt eine Limit Order oder Stop-Limit Order (bleibt bei IB aktiv, auch wenn Programm beendet wird).
        
        Wenn stop_price = None: Einfache Limit Order
        Wenn stop_price angegeben: Stop-Limit Order
            - Bei BUY: Wird ausgelöst, wenn Kurs >= stop_price steigt, dann Limit-Order mit limit_price
            - Bei SELL: Wird ausgelöst, wenn Kurs <= stop_price fällt, dann Limit-Order mit limit_price
        """
        o = Order()
        o.action = action.upper()       # BUY | SELL
        o.totalQuantity = Decimal(qty)  # Menge als Decimal
        o.lmtPrice = float(limit_price) # Limit-Preis
        o.tif = "GTC"                   # Good-Til-Canceled
        o.outsideRth = True             # auch außerhalb der regulären Handelszeiten
        
        if stop_price is not None:
            # Stop-Limit Order
            o.orderType = "STP LMT"
            o.auxPrice = float(stop_price)  # Stop-Preis (Trigger)
        else:
            # Einfache Limit Order
            o.orderType = "LMT"
        
        return o
    
    def enqueue_limit_order(self, symbol: str, qty: int, action: str,
                                  limit_price: float, stop_price: float | None = None, exchange: str = "SMART", currency: str = "USD"):
        """
        Fügt eine Limit Order in die Queue ein.
        """
        contract = self._make_stock_contract(symbol, exchange, currency)
        order = self._make_limit_order(action, qty, limit_price, stop_price)
        self._order_queue.append((order, contract))
        self._try_place_next()

    # -----------------------------
    # Wiederverbinden / Offene Orders abfragen
    # -----------------------------
    def request_open_orders(self):
        """Fordert alle offenen Orders bei IB an."""
        self.reqOpenOrders()

    def request_all_open_orders(self):
        """Fordert alle offenen Orders (aller Clients) bei IB an."""
        self.reqAllOpenOrders()