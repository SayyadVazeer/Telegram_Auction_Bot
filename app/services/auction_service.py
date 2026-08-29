from datetime import datetime
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession


from app.database.models.auction import (
    AuctionPlayer,
    AuctionResult,
    AuctionRun,
)
from app.database.models.player import Player
from app.database.models.team import Team
from app.utils.enums import (
    AuctionPlayerStatus,
    AuctionResultStatus,
    AuctionRunStatus,
)

from app.database.models.tournament import Tournament


class BidValidationError(ValueError):
    pass

from app.services.auction_runtime import ActiveAuctionState


class AuctionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_auction_run(
        self,
        tournament_id: int,
        set_number: int,
        bid_timer_seconds: int,
    ) -> AuctionRun:
        auction_run = AuctionRun(
            tournament_id=tournament_id,
            set_number=set_number,
            bid_timer_seconds=bid_timer_seconds,
            status=AuctionRunStatus.PENDING.value,
        )

        self.session.add(auction_run)

        await self.session.flush()

        return auction_run

    async def start_auction_run(
        self,
        auction_run: AuctionRun,
    ) -> None:
        if auction_run.status != AuctionRunStatus.PENDING.value:
            raise ValueError(
                "Only a pending auction can be started."
            )

        auction_run.status = AuctionRunStatus.RUNNING.value
        auction_run.started_at = datetime.utcnow()

        await self.session.flush()

    async def pause_auction_run(
        self,
        auction_run: AuctionRun,
    ) -> None:
        if auction_run.status != AuctionRunStatus.RUNNING.value:
            raise ValueError(
                "Only a running auction can be paused."
            )

        auction_run.status = AuctionRunStatus.PAUSED.value
        auction_run.paused_at = datetime.utcnow()

        await self.session.flush()

    async def resume_auction_run(
        self,
        auction_run: AuctionRun,
    ) -> None:
        if auction_run.status != AuctionRunStatus.PAUSED.value:
            raise ValueError(
                "Only a paused auction can be resumed."
            )

        auction_run.status = AuctionRunStatus.RUNNING.value

        await self.session.flush()

    async def stop_auction_run(
        self,
        auction_run: AuctionRun,
    ) -> None:
        if auction_run.status != AuctionRunStatus.RUNNING.value:
            raise ValueError(
                "Only a running auction can be stopped."
            )

        result = await self.session.execute(
            select(AuctionPlayer)
            .where(
                AuctionPlayer.auction_run_id == auction_run.id,
                AuctionPlayer.status
                == AuctionPlayerStatus.ACTIVE.value,
            )
        )

        active_player = result.scalar_one_or_none()

        if active_player is not None:
            raise ValueError(
                "Cannot stop auction while a player is active."
            )

        auction_run.status = AuctionRunStatus.STOPPED.value
        auction_run.stopped_at = datetime.utcnow()

        await self.session.flush()
    async def get_next_player(
        self,
        auction_run: AuctionRun,
    ) -> Player | None:
        sold_exists = exists(
            select(AuctionResult.id).where(
                AuctionResult.tournament_id
                == auction_run.tournament_id,
                AuctionResult.player_id
                == Player.id,
                AuctionResult.result_status
                == AuctionResultStatus.SOLD.value,
            )
        )

        processed_in_run = exists(
            select(AuctionPlayer.id).where(
                AuctionPlayer.auction_run_id
                == auction_run.id,
                AuctionPlayer.player_id
                == Player.id,
            )
        )

        query = (
            select(Player)
            .where(
                Player.set_number == auction_run.set_number,
                ~sold_exists,
                ~processed_in_run,
            )
            .order_by(func.random())
            .limit(1)
        )

        result = await self.session.execute(query)

        return result.scalar_one_or_none()

    async def prepare_next_player(
        self,
        auction_run: AuctionRun,
    ) -> AuctionPlayer | None:
        player = await self.get_next_player(auction_run)

        if player is None:
            return None

        auction_player = AuctionPlayer(
            auction_run_id=auction_run.id,
            player_id=player.id,
            status=AuctionPlayerStatus.PENDING.value,
        )

        self.session.add(auction_player)

        await self.session.flush()

        return auction_player
    async def activate_player(
        self,
        auction_player: AuctionPlayer,
    ) -> None:
        if auction_player.status != AuctionPlayerStatus.PENDING.value:
            raise ValueError(
                "Only a pending player can be activated."
            )

        auction_player.status = AuctionPlayerStatus.ACTIVE.value
        auction_player.started_at = datetime.utcnow()

        await self.session.flush()

    async def complete_player_sold(
        self,
        auction_player: AuctionPlayer,
        winning_team: Team,
        final_bid_cr: Decimal,
    ) -> AuctionResult:
        if auction_player.status != AuctionPlayerStatus.ACTIVE.value:
            raise ValueError(
                "Only an active player can be marked as sold."
            )

        if final_bid_cr <= Decimal("0"):
            raise ValueError(
                "Final bid must be greater than zero."
            )

        auction_player.status = AuctionPlayerStatus.SOLD.value
        auction_player.current_bid_cr = final_bid_cr
        auction_player.current_team_id = winning_team.id
        auction_player.completed_at = datetime.utcnow()

        result = AuctionResult(
            tournament_id=auction_player.auction_run.tournament_id,
            auction_run_id=auction_player.auction_run_id,
            auction_player_id=auction_player.id,
            player_id=auction_player.player_id,
            result_status=AuctionResultStatus.SOLD.value,
            winning_team_id=winning_team.id,
            final_bid_cr=final_bid_cr,
        )

        self.session.add(result)

        await self.session.flush()

        return result
    async def complete_player_unsold(
        self,
        auction_player: AuctionPlayer,
    ) -> AuctionResult:
        if auction_player.status != AuctionPlayerStatus.ACTIVE.value:
            raise ValueError(
                "Only an active player can be marked as unsold."
            )

        auction_player.status = AuctionPlayerStatus.UNSOLD.value
        auction_player.current_bid_cr = None
        auction_player.current_team_id = None
        auction_player.completed_at = datetime.utcnow()

        result = AuctionResult(
            tournament_id=auction_player.auction_run.tournament_id,
            auction_run_id=auction_player.auction_run_id,
            auction_player_id=auction_player.id,
            player_id=auction_player.player_id,
            result_status=AuctionResultStatus.UNSOLD.value,
            winning_team_id=None,
            final_bid_cr=None,
        )

        self.session.add(result)

        await self.session.flush()

        return result
    async def complete_auction_run(
        self,
        auction_run: AuctionRun,
    ) -> None:
        if auction_run.status not in (
            AuctionRunStatus.RUNNING.value,
            AuctionRunStatus.STOPPED.value,
        ):
            raise ValueError(
                "Only a running or stopped auction can be completed."
            )

        auction_run.status = AuctionRunStatus.COMPLETED.value
        auction_run.completed_at = datetime.utcnow()

        await self.session.flush()

    async def validate_bid(
        self,
        auction_player: AuctionPlayer,
        team: Team,
        bid_cr: Decimal,
        minimum_increment_cr: Decimal,
    ) -> None:
        if auction_player.status != AuctionPlayerStatus.ACTIVE.value:
            raise BidValidationError(
                "There is no active player accepting bids."
            )

        if bid_cr <= Decimal("0"):
            raise BidValidationError(
                "Bid must be greater than zero."
            )

        player = await self.session.get(
            Player,
            auction_player.player_id,
        )

        if player is None:
            raise BidValidationError(
                "Player not found."
            )

        base_price = Decimal(str(player.base_price_cr))

        if bid_cr < base_price:
            raise BidValidationError(
                f"Bid must be at least ₹{base_price:.2f} Cr."
            )

        current_bid = (
            auction_player.current_bid_cr
            if auction_player.current_bid_cr is not None
            else Decimal("0")
        )

        minimum_allowed = current_bid + minimum_increment_cr

        if bid_cr < minimum_allowed:
            raise BidValidationError(
                f"Minimum valid bid is "
                f"₹{minimum_allowed:.2f} Cr."
            )

    async def place_bid(
        self,
        auction_player: AuctionPlayer,
        team: Team,
        tournament: Tournament,
        bid_cr: Decimal,
        minimum_increment_cr: Decimal,
        bidder_telegram_id: int,
    ) -> None:

        result = await self.session.execute(
            select(AuctionPlayer)
            .where(
                AuctionPlayer.id == auction_player.id,
            )
            .with_for_update()
        )

        locked_player = result.scalar_one_or_none()

        if locked_player is None:
            raise BidValidationError(
                "Active auction player not found."
            )

        if team.owner_telegram_id != bidder_telegram_id:
            raise BidValidationError(
                "You are not the owner of this team."
            )

        await self.validate_bid(
            auction_player=locked_player,
            team=team,
            bid_cr=bid_cr,
            minimum_increment_cr=minimum_increment_cr,
        )

        player = await self.session.get(
            Player,
            locked_player.player_id,
        )

        if player is None:
            raise BidValidationError(
                "Player not found."
            )

        await self.validate_team_for_bid(
            tournament=tournament,
            team=team,
            player=player,
            bid_cr=bid_cr,
        )

        locked_player.current_bid_cr = bid_cr
        locked_player.current_team_id = team.id

        await self.session.flush()

        auction_player.current_bid_cr = locked_player.current_bid_cr
        auction_player.current_team_id = locked_player.current_team_id


    async def get_team_by_owner(
    self,
    telegram_user_id: int,
    tournament_id: int,
    ) -> Team | None:
        result = await self.session.execute(
            select(Team).where(
                Team.owner_telegram_id == telegram_user_id,
                Team.tournament_id == tournament_id,
            )
        )

        return result.scalar_one_or_none()

    
    async def get_active_auction_player(
        self,
        tournament_id: int,
    ) -> AuctionPlayer | None:

        result = await self.session.execute(
            select(AuctionPlayer)
            .options(
                selectinload(AuctionPlayer.player),
                selectinload(AuctionPlayer.current_team),
            )
            .join(
                AuctionRun,
                AuctionRun.id == AuctionPlayer.auction_run_id,
            )
            .where(
                AuctionRun.tournament_id == tournament_id,
                AuctionRun.status == AuctionRunStatus.RUNNING.value,
                AuctionPlayer.status == AuctionPlayerStatus.ACTIVE.value,
            )
            .order_by(AuctionPlayer.started_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()



    async def validate_team_for_bid(
        self,
        tournament: Tournament,
        team: Team,
        player: Player,
        bid_cr: Decimal,
    ) -> None:
        if team.tournament_id != tournament.id:
            raise BidValidationError(
                "This team does not belong to this tournament."
            )

        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(AuctionResult.final_bid_cr),
                    0,
                ),
                func.count(AuctionResult.id),
            )
            .where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status
                == AuctionResultStatus.SOLD.value,
            )
        )

        total_spent, player_count = result.one()

        total_spent = Decimal(str(total_spent or 0))
        player_count = int(player_count or 0)

        if player_count >= tournament.max_players_per_team:
            raise BidValidationError(
                "Your team has already reached the maximum "
                "number of players."
            )

        remaining_purse = tournament.purse_cr - total_spent

        if bid_cr > remaining_purse:
            raise BidValidationError(
                f"Your team has only "
                f"₹{remaining_purse:.2f} Cr remaining."
            )

        if player.is_overseas:
            overseas_result = await self.session.execute(
                select(func.count(AuctionResult.id))
                .join(
                    Player,
                    Player.id == AuctionResult.player_id,
                )
                .where(
                    AuctionResult.tournament_id
                    == tournament.id,
                    AuctionResult.winning_team_id
                    == team.id,
                    AuctionResult.result_status
                    == AuctionResultStatus.SOLD.value,
                    Player.is_overseas.is_(True),
                )
            )

            overseas_count = int(
                overseas_result.scalar() or 0
            )

            if (
                overseas_count
                >= tournament.max_overseas_players
            ):
                raise BidValidationError(
                    "Your team has reached the maximum "
                    "number of overseas players."
                )

    async def get_active_auction_player_with_details(
        self,
        tournament_id: int,
    ) -> AuctionPlayer | None:

        result = await self.session.execute(
            select(AuctionPlayer)
            .join(
                AuctionRun,
                AuctionRun.id == AuctionPlayer.auction_run_id,
            )
            .options(
                selectinload(AuctionPlayer.player),
                selectinload(AuctionPlayer.current_team),
            )
            .where(
                AuctionRun.tournament_id == tournament_id,
                AuctionRun.status
                == AuctionRunStatus.RUNNING.value,
                AuctionPlayer.status
                == AuctionPlayerStatus.ACTIVE.value,
            )
            .order_by(AuctionPlayer.started_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_running_auction(
    self,
    tournament_id: int,
    ) -> AuctionRun | None:

        result = await self.session.execute(
            select(AuctionRun)
            .where(
                AuctionRun.tournament_id == tournament_id,
                AuctionRun.status
                == AuctionRunStatus.RUNNING.value,
            )
            .order_by(AuctionRun.id.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()





