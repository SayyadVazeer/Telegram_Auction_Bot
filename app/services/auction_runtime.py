import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class ActiveAuctionState:
    auction_run_id: int
    chat_id: int
    bid_timer_seconds: int

    # Telegram message containing the latest BID notification
    bid_message_id: int | None = None
    live_message_id: int | None = None
    current_auction_player_id: int | None = None
    on_timer_expired: Callable[[], Awaitable[None]] | None = None

    # Timer tasks
    timer_task: asyncio.Task | None = None
    last_call_task: asyncio.Task | None = None

    # State flags
    paused: bool = False
    stopped: bool = False


active_auctions: dict[int, ActiveAuctionState] = {}


class AuctionRuntime:
    @staticmethod
    def get(
        auction_run_id: int,
    ) -> ActiveAuctionState | None:
        return active_auctions.get(auction_run_id)

    @staticmethod
    def create(
        auction_run_id: int,
        chat_id: int,
        bid_timer_seconds: int,
    ) -> ActiveAuctionState:
        state = ActiveAuctionState(
            auction_run_id=auction_run_id,
            chat_id=chat_id,
            bid_timer_seconds=bid_timer_seconds,
        )

        active_auctions[auction_run_id] = state

        return state

    @staticmethod
    def remove(
        auction_run_id: int,
    ) -> None:
        state = active_auctions.pop(
            auction_run_id,
            None,
        )

        if state is None:
            return

        if state.timer_task:
            state.timer_task.cancel()

        if state.last_call_task:
            state.last_call_task.cancel()

    @staticmethod
    async def start_timer(
        state: ActiveAuctionState,
        on_expired: Callable[
            [],
            Awaitable[None],
        ],
    ) -> None:
        AuctionRuntime.cancel_timer(state)

        state.on_timer_expired = on_expired
        state.timer_task = asyncio.create_task(
            AuctionRuntime._timer_worker(
                state,
                on_expired,
            )
        )

    @staticmethod
    async def restart_timer(state: ActiveAuctionState) -> None:
        if state.paused or state.stopped:
            return
        AuctionRuntime.cancel_last_call(state)
        if state.on_timer_expired is not None:
            await AuctionRuntime.start_timer(state, state.on_timer_expired)

    @staticmethod
    def cancel_timer(
        state: ActiveAuctionState,
    ) -> None:
        if state.timer_task is not None:
            state.timer_task.cancel()
            state.timer_task = None

    @staticmethod
    def cancel_last_call(state: ActiveAuctionState) -> None:
        if state.last_call_task is not None:
            state.last_call_task.cancel()
            state.last_call_task = None

    @staticmethod
    async def _timer_worker(
        state: ActiveAuctionState,
        on_expired: Callable[
            [],
            Awaitable[None],
        ],
    ) -> None:
        try:
            await asyncio.sleep(
                state.bid_timer_seconds
            )
            state.timer_task = None
            if not state.paused and not state.stopped:
                await on_expired()

        except asyncio.CancelledError:
            return
