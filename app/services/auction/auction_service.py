from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.auction import (
    AuctionPlayer,
    AuctionResult,
    AuctionRun,
)
from app.database.models.player import Player
from app.database.models.team import Team
from app.database.models.tournament import Tournament

from app.services.auction.exceptions import (
    AuctionAlreadyRunningError,
    AuctionNotFoundError,
    AuctionNotRunningError,
    InvalidBidError,
    NoPlayersAvailableError,
    PlayerAlreadySoldError,
    PlayerNotActiveError,
    TeamNotEligibleError,
)


class AuctionService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_tournament(
        self,
        tournament_id: int,
    ) -> Tournament:
        tournament = await self.session.get(
            Tournament,
            tournament_id,
        )

        if tournament is None:
            raise AuctionNotFoundError(
                f"Tournament {tournament_id} not found."
            )

        return tournament

    async def get_auction_run(
        self,
        auction_run_id: int,
    ) -> AuctionRun:
        auction_run = await self.session.get(
            AuctionRun,
            auction_run_id,
        )

        if auction_run is None:
            raise AuctionNotFoundError(
                f"Auction run {auction_run_id} not found."
            )

        return auction_run

    async def get_active_auction(
        self,
        tournament_id: int,
    ) -> AuctionRun | None:

        result = await self.session.execute(
            select(AuctionRun)
            .where(
                AuctionRun.tournament_id == tournament_id,
                AuctionRun.status.in_(
                    ["PENDING", "RUNNING", "PAUSED"]
                ),
            )
            .order_by(AuctionRun.id.desc())
        )

        return result.scalars().first()

    async def create_auction_run(
        self,
        tournament_id: int,
        set_number: int,
        bid_timer_seconds: int,
    ) -> AuctionRun:

        existing = await self.get_active_auction(
            tournament_id
        )

        if existing is not None:
            raise AuctionAlreadyRunningError(
                "An auction already exists for this tournament."
            )

        auction_run = AuctionRun(
            tournament_id=tournament_id,
            set_number=set_number,
            bid_timer_seconds=bid_timer_seconds,
            status="PENDING",
        )

        self.session.add(auction_run)

        await self.session.flush()

        return auction_run

    async def populate_players(
        self,
        auction_run_id: int,
    ) -> int:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        existing_result = await self.session.execute(
            select(AuctionPlayer.id)
            .where(
                AuctionPlayer.auction_run_id
                == auction_run.id
            )
            .limit(1)
        )

        if existing_result.scalar_one_or_none() is not None:
            return 0

        result = await self.session.execute(
            select(Player)
            .where(
                Player.set_number
                == auction_run.set_number
            )
            .order_by(Player.id)
        )

        players = result.scalars().all()

        if not players:
            raise NoPlayersAvailableError(
                f"No players found for set {auction_run.set_number}."
            )

        auction_players = [
            AuctionPlayer(
                auction_run_id=auction_run.id,
                player_id=player.id,
                status="PENDING",
            )
            for player in players
        ]

        self.session.add_all(auction_players)

        await self.session.flush()

        return len(auction_players)

    async def start_auction(
        self,
        auction_run_id: int,
    ) -> AuctionRun:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status == "RUNNING":
            raise AuctionAlreadyRunningError(
                "Auction is already running."
            )

        if auction_run.status not in {"PENDING", "PAUSED"}:
            raise AuctionNotRunningError(
                f"Cannot start auction in status "
                f"{auction_run.status}."
            )

        if auction_run.status == "PENDING":
            await self.populate_players(
                auction_run.id
            )

        auction_run.status = "RUNNING"

        if auction_run.started_at is None:
            auction_run.started_at = datetime.utcnow()

        auction_run.paused_at = None

        await self.session.flush()

        return auction_run


    async def get_current_player(
        self,
        auction_run_id: int,
    ) -> AuctionPlayer | None:
        result = await self.session.execute(
            select(AuctionPlayer)
            .where(
                AuctionPlayer.auction_run_id == auction_run_id,
                AuctionPlayer.status == "LIVE",
            )
            .order_by(AuctionPlayer.id)
            .limit(1)
        )

        return result.scalars().first()

    async def get_next_player(
        self,
        auction_run_id: int,
    ) -> AuctionPlayer | None:
        result = await self.session.execute(
            select(AuctionPlayer)
            .where(
                AuctionPlayer.auction_run_id == auction_run_id,
                AuctionPlayer.status == "PENDING",
            )
            .order_by(AuctionPlayer.id)
            .limit(1)
        )

        return result.scalars().first()

    async def start_next_player(
        self,
        auction_run_id: int,
    ) -> AuctionPlayer:
        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status != "RUNNING":
            raise AuctionNotRunningError(
                "Auction is not running."
            )

        current_player = await self.get_current_player(
            auction_run_id
        )

        if current_player is not None:
            raise PlayerNotActiveError(
                "A player is already active."
            )

        auction_player = await self.get_next_player(
            auction_run_id
        )

        if auction_player is None:
            auction_run.status = "COMPLETED"
            auction_run.completed_at = datetime.utcnow()

            await self.session.flush()

            raise NoPlayersAvailableError(
                "No players remaining in this auction."
            )

        auction_player.status = "LIVE"
        auction_player.started_at = datetime.utcnow()
        auction_player.current_bid_cr = None
        auction_player.current_team_id = None

        await self.session.flush()

        return auction_player

    

    async def pause_auction(
        self,
        auction_run_id: int,
    ) -> AuctionRun:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status != "RUNNING":
            raise AuctionNotRunningError(
                "Auction is not running."
            )

        auction_run.status = "PAUSED"
        auction_run.paused_at = datetime.utcnow()

        await self.session.flush()

        return auction_run

    async def stop_auction(
        self,
        auction_run_id: int,
    ) -> AuctionRun:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status not in {
            "RUNNING",
            "PAUSED",
        }:
            raise AuctionNotRunningError(
                "Auction is not active."
            )

        auction_run.status = "STOPPED"
        auction_run.stopped_at = datetime.utcnow()

        await self.session.flush()

        return auction_run


    async def place_bid(
        self,
        auction_run_id: int,
        auction_player_id: int,
        team_id: int,
        bid_cr: Decimal,
    ) -> AuctionPlayer:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status != "RUNNING":
            raise AuctionNotRunningError(
                "Auction is not running."
            )

        auction_player = await self.session.get(
            AuctionPlayer,
            auction_player_id,
        )

        if auction_player is None:
            raise AuctionNotFoundError(
                f"Auction player "
                f"{auction_player_id} not found."
            )

        if auction_player.auction_run_id != auction_run.id:
            raise AuctionNotFoundError(
                "Auction player does not belong "
                "to this auction."
            )

        if auction_player.status != "LIVE":
            raise PlayerNotActiveError(
                "This player is not currently active."
            )

        team = await self.session.get(
            Team,
            team_id,
        )

        if team is None:
            raise TeamNotEligibleError(
                "Team not found."
            )

        if team.tournament_id != auction_run.tournament_id:
            raise TeamNotEligibleError(
                "Team does not belong to this tournament."
            )

        tournament = await self.get_tournament(
            auction_run.tournament_id
        )

        player = await self.session.get(
            Player,
            auction_player.player_id,
        )

        if player is None:
            raise AuctionNotFoundError(
                "Master player not found."
            )

        bid_cr = Decimal(str(bid_cr))

        if bid_cr <= 0:
            raise InvalidBidError(
                "Bid must be greater than zero."
            )

        if auction_player.current_bid_cr is None:
            minimum_bid = Decimal(
                str(player.base_price_cr)
            )
        else:
            minimum_bid = (
                auction_player.current_bid_cr
                + tournament.minimum_bid_increment_cr
            )

        if bid_cr < minimum_bid:
            raise InvalidBidError(
                f"Minimum valid bid is "
                f"{minimum_bid:.2f} Cr."
            )

        auction_player.current_bid_cr = bid_cr
        auction_player.current_team_id = team.id

        await self.session.flush()

        return auction_player

    async def sell_player(
        self,
        auction_run_id: int,
        auction_player_id: int,
    ) -> AuctionResult:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status != "RUNNING":
            raise AuctionNotRunningError(
                "Auction is not running."
            )

        auction_player = await self.session.get(
            AuctionPlayer,
            auction_player_id,
        )

        if auction_player is None:
            raise AuctionNotFoundError(
                "Auction player not found."
            )

        if auction_player.auction_run_id != auction_run.id:
            raise AuctionNotFoundError(
                "Auction player does not belong "
                "to this auction."
            )

        if auction_player.status != "LIVE":
            raise PlayerNotActiveError(
                "Player is not currently active."
            )

        if (
            auction_player.current_team_id is None
            or auction_player.current_bid_cr is None
        ):
            raise InvalidBidError(
                "Cannot sell a player without a bid."
            )

        result = AuctionResult(
            tournament_id=auction_run.tournament_id,
            auction_run_id=auction_run.id,
            auction_player_id=auction_player.id,
            player_id=auction_player.player_id,
            result_status="SOLD",
            winning_team_id=auction_player.current_team_id,
            final_bid_cr=auction_player.current_bid_cr,
        )

        auction_player.status = "SOLD"
        auction_player.completed_at = datetime.utcnow()

        self.session.add(result)

        await self.session.flush()

        return result

    async def mark_unsold(
        self,
        auction_run_id: int,
        auction_player_id: int,
    ) -> AuctionResult:

        auction_run = await self.get_auction_run(
            auction_run_id
        )

        if auction_run.status != "RUNNING":
            raise AuctionNotRunningError(
                "Auction is not running."
            )

        auction_player = await self.session.get(
            AuctionPlayer,
            auction_player_id,
        )

        if auction_player is None:
            raise AuctionNotFoundError(
                "Auction player not found."
            )

        if auction_player.auction_run_id != auction_run.id:
            raise AuctionNotFoundError(
                "Auction player does not belong "
                "to this auction."
            )

        if auction_player.status != "LIVE":
            raise PlayerNotActiveError(
                "Player is not currently active."
            )

        result = AuctionResult(
            tournament_id=auction_run.tournament_id,
            auction_run_id=auction_run.id,
            auction_player_id=auction_player.id,
            player_id=auction_player.player_id,
            result_status="UNSOLD",
            winning_team_id=None,
            final_bid_cr=None,
        )

        auction_player.status = "UNSOLD"
        auction_player.completed_at = datetime.utcnow()

        self.session.add(result)

        await self.session.flush()

        return result

