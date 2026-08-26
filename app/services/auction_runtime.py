import asyncio
from collections.abc import Awaitable, Callable

from app.services.auction_service import (
    ActiveAuctionState,
    active_auctions,
)


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

        state.timer_task = asyncio.create_task(
            AuctionRuntime._timer_worker(
                state,
                on_expired,
            )
        )

    @staticmethod
    def cancel_timer(
        state: ActiveAuctionState,
    ) -> None:
        if state.timer_task is not None:
            state.timer_task.cancel()
            state.timer_task = None

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

            await on_expired()

        except asyncio.CancelledError:
            return
