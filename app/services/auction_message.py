from decimal import Decimal

from app.database.models.auction import AuctionPlayer
from app.database.models.player import Player
from app.database.models.team import Team


def format_live_auction(
    player: Player,
    auction_player: AuctionPlayer,
    team: Team | None,
) -> str:

    base_price = Decimal(str(player.base_price_cr))

    if auction_player.current_bid_cr is None:
        current_bid_text = "No bids yet"
        team_text = "—"
        owner_text = "—"
    else:
        current_bid = Decimal(
            str(auction_player.current_bid_cr)
        )

        current_bid_text = f"Rs.{current_bid:.2f} Cr"

        if team is not None:
            team_text = team.name

            if team.owner_username:
                owner_text = f"@{team.owner_username}"
            else:
                owner_text = "Telegram Owner"
        else:
            team_text = "—"
            owner_text = "—"

    return (
        "🔴 LIVE AUCTION\n\n"
        f"🙎{player.name}\n"
        f"💸Base Price: Rs.{base_price:.2f} Cr\n\n"
        f"💲Current Bid: {current_bid_text}\n"
        f"🫂Team: {team_text}\n"
        f"🤴Owner: {owner_text}"
    )
