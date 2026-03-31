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
    
    def __hash__(self):
        return hash(self.symbol)

class IBKRPosition(Position):
    def __init__(self, symbol: str, position: int = 0):
        super().__init__(symbol)
        self.position = position
    
    def __str__(self):
        return f"IBKRPosition(symbol={self.symbol}, position={self.position})"
    
    def __repr__(self):
        return self.__str__()
    
class ScannerPosition(Position):
    def __init__(self, symbol: str, price: float = 0.0, market_cap: int = 0, is_long: bool = True):
        super().__init__(symbol)
        self.price = price
        self.market_cap = market_cap
        self.is_long = is_long
    
    def __str__(self):
        return f"ScannerPosition(symbol={self.symbol}, price={self.price}, price={self.market_cap})"
    
    def __repr__(self):
        return self.__str__()        
