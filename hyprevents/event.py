class HyprEvent:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        
    def __repr__(self):
        return f"HyprEvent(name='{self.name}', data='{self.data}')"