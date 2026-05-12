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
    def __init__(self, symbol: str, price: float = 0.0, premarket_change: float = 0.0, postmarket_change: float = 0.0, perf: float = 0.0):
        super().__init__(symbol)
        self.price = price
        self.premarket_change = premarket_change
        self.postmarket_change = postmarket_change
        self.perf = perf
    
    def __str__(self):
        return f"ScannerPosition(symbol={self.symbol}, price={self.price}, premarket_change={self.premarket_change}, postmarket_change={self.postmarket_change}, perf={self.perf})"
    
    def __repr__(self):
        return self.__str__()        
