import enum

class HyprlandNotifType(enum.Enum):
    WARNING = 0
    INFO = 1
    HINT = 2
    ERROR = 3
    CONFUSED = 4
    OK = 5
    OTHER = -1