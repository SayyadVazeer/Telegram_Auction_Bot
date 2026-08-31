"""Match simulation database models.

Tables:
- Match: Match instance
- MatchInnings: Per-innings summary
- MatchDelivery: Ball-by-ball log
- MatchBattingScorecard: Individual batting stats per innings
- MatchBowlingScorecard: Individual bowling stats per innings
- TournamentStanding: Auto-calculated standings
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    team1_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    team2_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    venue_code: Mapped[str] = mapped_column(String(10), nullable=False)
    venue_name: Mapped[str] = mapped_column(String(150), nullable=False)

    toss_winner_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    toss_decision: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'bat' or 'bowl'

    result_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 'team1_won', 'team2_won', 'tie', 'no_result'
    result_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 'won by 5 wickets', 'won by 12 runs', etc.

    winner_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    potm_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    potm_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    # PENDING, TOSS, TEAM_SETUP, INNINGS1, INNINGS_BREAK, INNINGS2, COMPLETED

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Team setup data (JSON strings of selected playing 11, openers, etc.)
    team1_setup: Mapped[str | None] = mapped_column(Text, nullable=True)
    team2_setup: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tournament = relationship("Tournament")
    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
    toss_winner = relationship("Team", foreign_keys=[toss_winner_id])
    winner_team = relationship("Team", foreign_keys=[winner_team_id])
    potm_player = relationship("Player", foreign_keys=[potm_player_id])
    innings = relationship("MatchInnings", back_populates="match", cascade="all, delete-orphan")
    deliveries = relationship("MatchDelivery", back_populates="match", cascade="all, delete-orphan")


class MatchInnings(Base):
    __tablename__ = "match_innings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 or 2

    batting_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    bowling_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )

    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_wickets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_balls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    extras_wides: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_noballs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_byes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_legbyes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    # Relationships
    match = relationship("Match", back_populates="innings")
    batting_team = relationship("Team", foreign_keys=[batting_team_id])
    bowling_team = relationship("Team", foreign_keys=[bowling_team_id])


class MatchDelivery(Base):
    __tablename__ = "match_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)

    ball_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-100
    over_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-20 (5 balls each)
    ball_in_over: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5

    striker_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    non_striker_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    bowler_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    runs_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_wicket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dismissal_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dismissed_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    fielder_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )

    commentary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    match = relationship("Match", back_populates="deliveries")
    striker = relationship("Player", foreign_keys=[striker_id])
    non_striker = relationship("Player", foreign_keys=[non_striker_id])
    bowler = relationship("Player", foreign_keys=[bowler_id])
    dismissed_player = relationship("Player", foreign_keys=[dismissed_player_id])
    fielder = relationship("Player", foreign_keys=[fielder_id])


class MatchBattingScorecard(Base):
    __tablename__ = "match_batting_scorecard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    batting_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sixes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_not_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    dismissal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dismissed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    strike_rate: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)

    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    team = relationship("Team", foreign_keys=[team_id])
    dismissed_by = relationship("Player", foreign_keys=[dismissed_by_id])


class MatchBowlingScorecard(Base):
    __tablename__ = "match_bowling_scorecard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    balls_bowled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_conceded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wickets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wides: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    noballs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    economy: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    team = relationship("Team", foreign_keys=[team_id])


class TournamentStanding(Base):
    __tablename__ = "tournament_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )

    matches_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_result: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    runs_for: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balls_faced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_against: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balls_bowled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nrr: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0.000)

    # Relationships
    team = relationship("Team", foreign_keys=[team_id])
