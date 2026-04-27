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
    def __init__(self, symbol: str, price: float = 0.0, tech_rating: float = 0.0):
        super().__init__(symbol)
        self.price = price
        self.tech_rating = tech_rating
    
    def __str__(self):
        return f"ScannerPosition(symbol={self.symbol}, price={self.price}, tech_rating={self.tech_rating})"
    
    def __repr__(self):
        return self.__str__()        
