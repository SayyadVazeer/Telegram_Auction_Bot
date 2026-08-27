class AuctionError(Exception):
    """Base exception for auction errors."""


class AuctionNotFoundError(AuctionError):
    """Auction does not exist."""


class AuctionNotRunningError(AuctionError):
    """Auction is not currently running."""


class AuctionAlreadyRunningError(AuctionError):
    """Auction is already running."""


class NoPlayersAvailableError(AuctionError):
    """No players are available for auction."""


class InvalidBidError(AuctionError):
    """Bid is invalid."""


class TeamNotEligibleError(AuctionError):
    """Team cannot place this bid."""


class PlayerAlreadySoldError(AuctionError):
    """Player has already been sold."""


class PlayerNotActiveError(AuctionError):
    """Player is not currently active."""
