"""Fix the auction timer flow: _finalize_player, _on_sold_warning, _on_timer_expired."""

with open("app/bot/handlers/auction.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the old _on_no_bids through _on_timer_expired and replace
# These functions start at _on_no_bids and end before @router.message(Command("start_auction"))
marker_start = 'async def _on_no_bids('
marker_end = '@router.message(Command("start_auction")'

idx_start = content.find(marker_start)
idx_end = content.find(marker_end)

if idx_start == -1 or idx_end == -1:
    print(f"ERROR: Could not find markers. start={idx_start}, end={idx_end}")
    import sys
    sys.exit(1)

print(f"Replacing lines at chars {idx_start}-{idx_end}")

new_functions = '''async def _finalize_player(bot, chat_id: int, auction_run_id: int) -> None:
    """Finalize current player as SOLD or UNSOLD and move to next."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.current_auction_player_id is None:
        return

    try:
        async with AsyncSessionLocal() as session:
            service = AuctionService(session)
            row = (
                await session.execute(
                    select(AuctionPlayer)
                    .options(selectinload(AuctionPlayer.auction_run))
                    .where(AuctionPlayer.id == state.current_auction_player_id)
                )
            ).scalar_one_or_none()

            if row is None or row.status != AuctionPlayerStatus.ACTIVE.value:
                return

            player = await session.get(Player, row.player_id)
            if row.current_team_id is None:
                await service.complete_player_unsold(row)
                result_text = f"UNSOLD -- {player.name}"
                team = None
            else:
                team = await session.get(Team, row.current_team_id)
                await service.complete_player_sold(
                    row, team, Decimal(str(row.current_bid_cr))
                )
                result_text = f"SOLD -- {player.name} to {team.name} for Rs.{row.current_bid_cr:.2f} Cr"
            await session.commit()

        # Send sold/unsold card
        if row.current_team_id is not None:
            from aiogram.types import BufferedInputFile

            card = await render_sold_card(
                bot, player, team, Decimal(str(row.current_bid_cr)),
                owner_username=team.owner_username,
            )
            await bot.send_photo(
                chat_id,
                BufferedInputFile(card, filename="sold.png"),
                caption=result_text,
            )
        else:
            card = await render_unsold_card(bot, player)
            await bot.send_photo(
                chat_id,
                BufferedInputFile(card, filename="unsold.png"),
                caption=result_text,
            )

        state.current_auction_player_id = None
        state.last_call_task = None
        await asyncio.sleep(5)

        # Check state again before sending next player
        if AuctionRuntime.get(auction_run_id) is state and not state.paused and not state.stopped:
            await _send_active_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Finalize player failed for auction_run_id=%s", auction_run_id)
        return


async def _on_sold_warning(bot, chat_id: int, auction_run_id: int) -> None:
    """15-second warning for player WITH bids: GOING ONCE at 10s, GOING TWICE at 5s, SOLD at 0s."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.current_auction_player_id is None:
        return

    try:
        state.last_call_task = asyncio.current_task()

        # 10 seconds left
        if AuctionRuntime.get(auction_run_id) is not state:
            return
        once_path = os.path.join("data", "once.gif")
        if os.path.exists(once_path):
            await bot.send_animation(chat_id, FSInputFile(once_path), caption="GOING ONCE -- Place your bid now!")
        else:
            await bot.send_message(chat_id, "GOING ONCE -- Place your bid now!")
        await asyncio.sleep(5)

        # 5 seconds left
        if AuctionRuntime.get(auction_run_id) is not state:
            return
        twice_path = os.path.join("data", "twice.gif")
        if os.path.exists(twice_path):
            await bot.send_animation(chat_id, FSInputFile(twice_path), caption="GOING TWICE -- Last chance!")
        else:
            await bot.send_message(chat_id, "GOING TWICE -- Last chance!")
        await asyncio.sleep(5)

        # 0 seconds -- finalize
        if AuctionRuntime.get(auction_run_id) is not state:
            return

        await _finalize_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Sold warning failed for auction_run_id=%s", auction_run_id)
        return


async def _on_timer_expired(bot, chat_id: int, auction_run_id: int) -> None:
    """Normal timer expired -- check if bids exist, then finalize or warn."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.paused or state.stopped:
        return

    # Check if anyone has bid
    has_bids = False
    if state.current_auction_player_id:
        async with AsyncSessionLocal() as session:
            row = await session.get(AuctionPlayer, state.current_auction_player_id)
            if row and row.current_team_id is not None:
                has_bids = True

    if has_bids:
        # Player has bids -- run GOING ONCE / GOING TWICE warning
        await _on_sold_warning(bot, chat_id, auction_run_id)
    else:
        # No bids at all -- mark UNSOLD immediately
        await _finalize_player(bot, chat_id, auction_run_id)


'''

content = content[:idx_start] + new_functions + content[idx_end:]

with open("app/bot/handlers/auction.py", "w", encoding="utf-8") as f:
    f.write(content)

print("auction.py timer flow rewritten")
