from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Team(Base):
    __tablename__ = "teams"

    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "short_code",
            name="uq_team_tournament_short_code",
        ),
        UniqueConstraint(
            "tournament_id",
            "name",
            name="uq_team_tournament_name",
        ),
        UniqueConstraint(
        "tournament_id",
        "owner_telegram_id",
        name="uq_team_tournament_owner",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    short_code: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    owner_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    owner_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    logo_file_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    co_owner_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    co_owner_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Purse settled through player trades. Positive = team paid extra cash
    # out to another team; negative = team received cash. Effective spend is
    # sum(player bids) + purse_adjustment_cr.
    purse_adjustment_cr: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
