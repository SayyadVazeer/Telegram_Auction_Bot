"""Fix bid flow: same bidder check, button bids send message + edit live, /bid edits live."""

with open("app/bot/handlers/auction.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix _button_bid: add same bidder check + send bid message + edit live
old_button_bid = '''async def _button_bid(message: Message, user_id: int, amount: Decimal | None, increment: Decimal | None = None) -> str:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            return "No tournament is configured in this group."
        service = AuctionService(session)
        team = await service.get_team_by_owner(user_id, tournament.id)
        active = await service.get_active_auction_player(tournament.id)
        if not team or not active:
            return "You need to be a team owner and there must be an active player."
        player = active.player
        bid = amount
        if bid is None:
            bid = (Decimal(str(active.current_bid_cr)) if active.current_bid_cr is not None else Decimal(str(player.base_price_cr))) + increment
            if active.current_bid_cr is None:
                bid = max(Decimal(str(player.base_price_cr)), bid)
        try:
            await service.place_bid(active, team, tournament, bid, Decimal(str(tournament.minimum_bid_increment_cr)), user_id)
        except BidValidationError as exc:
            await session.rollback()
            return str(exc)
        await session.commit()

        # Update the live message with new bid info
        runtime = AuctionRuntime.get(active.auction_run_id)
        if runtime and runtime.live_message_id:
            try:
                text = _live_text(
                    player, team, bid, runtime.bid_timer_seconds,
                    bidder_username=team.owner_username,
                )
                markup = auction_keyboard(
                    Decimal(str(tournament.minimum_bid_increment_cr)),
                    is_admin=True,
                )
                # Try edit_message_caption first (for photo messages), then edit_message_text
                try:
                    await message.bot.edit_message_caption(
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        caption=text,
                        reply_markup=markup,
                    )
                except Exception:
                    await message.bot.edit_message_text(
                        text=text,
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        reply_markup=markup,
                    )
            except Exception:
                pass

    runtime = AuctionRuntime.get(active.auction_run_id)
    if runtime:
        await AuctionRuntime.restart_timer(runtime)
    return f"BID -- {team.name} ({team.short_code}) -- Rs.{bid:.2f} Cr -- @{team.owner_username or 'Owner'}"'''

new_button_bid = '''async def _button_bid(message: Message, user_id: int, amount: Decimal | None, increment: Decimal | None = None) -> str:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            return "\\u274c No tournament configured."
        service = AuctionService(session)
        team = await service.get_team_by_owner(user_id, tournament.id)
        active = await service.get_active_auction_player(tournament.id)
        if not team or not active:
            return "\\u274c You need to be a team owner with an active player."
        player = active.player

        # Same bidder check - can't bid on own highest bid
        if active.current_team_id and active.current_team_id == team.id:
            return "\\u26a0\\ufe0f You already have the highest bid!"

        bid = amount
        if bid is None:
            current = Decimal(str(active.current_bid_cr)) if active.current_bid_cr is not None else Decimal(str(player.base_price_cr))
            bid = current + increment
            if active.current_bid_cr is None:
                bid = max(Decimal(str(player.base_price_cr)), bid)
        try:
            await service.place_bid(active, team, tournament, bid, Decimal(str(tournament.minimum_bid_increment_cr)), user_id)
        except BidValidationError as exc:
            await session.rollback()
            return str(exc)
        await session.commit()

        # Update the live message with new bid info
        runtime = AuctionRuntime.get(active.auction_run_id)
        if runtime and runtime.live_message_id:
            try:
                text = _live_text(
                    player, team, bid, runtime.bid_timer_seconds,
                    bidder_username=team.owner_username,
                )
                markup = auction_keyboard(
                    Decimal(str(tournament.minimum_bid_increment_cr)),
                    is_admin=True,
                )
                try:
                    await message.bot.edit_message_caption(
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        caption=text,
                        reply_markup=markup,
                    )
                except Exception:
                    await message.bot.edit_message_text(
                        text=text,
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        reply_markup=markup,
                    )
            except Exception:
                pass

    runtime = AuctionRuntime.get(active.auction_run_id)
    if runtime:
        await AuctionRuntime.restart_timer(runtime)

    # Return bid announcement message
    owner_display = f"@{team.owner_username}" if team.owner_username else "Owner"
    return f"\\U0001f528 {team.name} ({team.short_code}) \\u2192 Rs.{bid:.2f} Cr\\nOwner: {owner_display}\\nPlayer: {player.name}"'''

content = content.replace(old_button_bid, new_button_bid)

with open("app/bot/handlers/auction.py", "w", encoding="utf-8") as f:
    f.write(content)

print("auction.py bid flow updated")


# Fix bidding.py: add same bidder check + edit live message
with open("app/bot/handlers/bidding.py", "r", encoding="utf-8") as f:
    bid_content = f.read()

# Add same bidder check in /bid handler
old_bid_check = '''        auction_player = (
            await service.get_active_auction_player(
                tournament.id
            )
        )

        if auction_player is None:
            await message.answer(
                "\\u274c There is currently no player accepting bids."
            )
            return'''

new_bid_check = '''        auction_player = (
            await service.get_active_auction_player(
                tournament.id
            )
        )

        if auction_player is None:
            await message.answer(
                "\\u274c There is currently no player accepting bids."
            )
            return

        # Same bidder check
        if auction_player.current_team_id:
            my_team = await service.get_team_by_owner(
                telegram_user_id=message.from_user.id,
                tournament_id=tournament.id,
            )
            if my_team and auction_player.current_team_id == my_team.id:
                await message.answer(
                    "\\u26a0\\ufe0f You already have the highest bid!"
                )
                return'''

bid_content = bid_content.replace(old_bid_check, new_bid_check)

# Add live message edit after /bid
old_bid_after = '''            await session.commit()
            runtime = AuctionRuntime.get(auction_player.auction_run_id)
            if runtime is not None:
                await AuctionRuntime.restart_timer(runtime)'''

new_bid_after = '''            await session.commit()

            # Edit live message
            runtime = AuctionRuntime.get(auction_player.auction_run_id)
            if runtime and runtime.live_message_id:
                try:
                    from app.bot.handlers.auction import _live_text, auction_keyboard as ak
                    text = _live_text(
                        auction_player.player, team, bid_cr, runtime.bid_timer_seconds,
                        bidder_username=team.owner_username,
                    )
                    markup = ak(
                        Decimal(str(tournament.minimum_bid_increment_cr)),
                        is_admin=True,
                    )
                    try:
                        await message.bot.edit_message_caption(
                            chat_id=message.chat.id,
                            message_id=runtime.live_message_id,
                            caption=text,
                            reply_markup=markup,
                        )
                    except Exception:
                        await message.bot.edit_message_text(
                            text=text,
                            chat_id=message.chat.id,
                            message_id=runtime.live_message_id,
                            reply_markup=markup,
                        )
                except Exception:
                    pass

            if runtime is not None:
                await AuctionRuntime.restart_timer(runtime)'''

bid_content = bid_content.replace(old_bid_after, new_bid_after)

with open("app/bot/handlers/bidding.py", "w", encoding="utf-8") as f:
    f.write(bid_content)

print("bidding.py updated")
