from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AuctionRun(Base):
    __tablename__ = "auction_runs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    )

    set_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    bid_timer_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    tournament = relationship(
        "Tournament",
        back_populates="auction_runs",
    )

    auction_players = relationship(
        "AuctionPlayer",
        back_populates="auction_run",
        cascade="all, delete-orphan",
    )


class AuctionPlayer(Base):
    __tablename__ = "auction_players"

    
    __table_args__ = (
        UniqueConstraint(
            "auction_run_id",
            "player_id",
            name="uq_auction_run_player",
        ),
    )
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    auction_run_id: Mapped[int] = mapped_column(
        ForeignKey("auction_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
    )

    current_bid_cr: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    current_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    auction_run = relationship(
        "AuctionRun",
        back_populates="auction_players",
    )

    player = relationship(
        "Player",
    )

    current_team = relationship(
        "Team",
    )

    result = relationship(
        "AuctionResult",
        back_populates="auction_player",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AuctionResult(Base):
    __tablename__ = "auction_results"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    )

    auction_run_id: Mapped[int] = mapped_column(
        ForeignKey("auction_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    auction_player_id: Mapped[int] = mapped_column(
        ForeignKey("auction_players.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )

    result_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    winning_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )

    final_bid_cr: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    auction_player = relationship(
        "AuctionPlayer",
        back_populates="result",
    )

    player = relationship(
        "Player",
    )

    winning_team = relationship(
        "Team",
    )
