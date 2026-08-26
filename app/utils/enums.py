from enum import Enum


class AuctionRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


class AuctionPlayerStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SOLD = "SOLD"
    UNSOLD = "UNSOLD"


class AuctionResultStatus(str, Enum):
    SOLD = "SOLD"
    UNSOLD = "UNSOLD"
