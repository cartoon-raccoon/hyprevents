import abc

class Dispatcher(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __init__(self, config: dict):
        pass
    
    @abc.abstractmethod
    def load_config(self, config: dict):
        pass
    
    @abc.abstractmethod
    def handle_event(self, event):
        pass