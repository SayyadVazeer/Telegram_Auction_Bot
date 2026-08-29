import asyncio

import pytest

from app.services.auction_runtime import AuctionRuntime


@pytest.mark.asyncio
async def test_restart_timer_cancels_last_call_and_runs_new_timer() -> None:
    state = AuctionRuntime.create(999_001, -1001, 0)
    last_call = asyncio.create_task(asyncio.sleep(60))
    state.last_call_task = last_call
    expired = asyncio.Event()

    async def on_expired() -> None:
        expired.set()

    state.on_timer_expired = on_expired
    await AuctionRuntime.restart_timer(state)
    await asyncio.wait_for(expired.wait(), timeout=1)
    assert last_call.cancelled() or last_call.cancelling()
    AuctionRuntime.remove(state.auction_run_id)


@pytest.mark.asyncio
async def test_remove_cancels_runtime_tasks() -> None:
    state = AuctionRuntime.create(999_002, -1002, 30)
    state.timer_task = asyncio.create_task(asyncio.sleep(60))
    AuctionRuntime.remove(state.auction_run_id)
    assert state.timer_task.cancelled() or state.timer_task.cancelling()
