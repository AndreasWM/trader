class Position:
    def __init__(self, symbol: str):
        self.symbol = symbol
    
    def __str__(self):
        return f"Position(symbol={self.symbol})"
    
    def __repr__(self):
        return self.__str__()
    
    def __eq__(self, other):
        if not hasattr(other, 'symbol'):
            return False
        return self.symbol == other.symbol
    
    def __lt__(self, other):
        return self.symbol < other.symbol

    def __hash__(self):
        return hash(self.symbol)

class IBKRPosition(Position):
    def __init__(self, symbol: str, exchange: str, position: int = 0):
        super().__init__(symbol)
        self.exchange = exchange
        self.position = position
    
    def __str__(self):
        return f"IBKRPosition(symbol={self.symbol}, exchange={self.exchange}, position={self.position})"
    
    def __repr__(self):
        return self.__str__()
    
class ScannerPosition(Position):
    def __init__(self, symbol: str, leverage: float, flag_is_long: bool, price: float = 0.0, exchange: str = ""):
        super().__init__(symbol)
        self.leverage = leverage
        self.flag_is_long = flag_is_long
        self.price = price
        self.exchange = exchange
    
    def __str__(self):
        return f"""ScannerPosition(symbol={self.symbol}, leverage={self.leverage}, flag_is_long={self.flag_is_long},
                price={self.price}, exchange={self.exchange})"""
    
    def __repr__(self):
        return self.__str__()        
