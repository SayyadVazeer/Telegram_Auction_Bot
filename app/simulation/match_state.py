"""Live match state tracker for The Hundred format.

Tracks:
- Innings (1st and 2nd)
- Score (runs/wickets/balls)
- Current over (1-20) and ball in over (1-5)
- Strike rotation (The Hundred rules)
- Bowling: who bowls each set (2 overs), bowling end changes
- Partnership tracking
- Per-player batting/bowling stats
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.simulation.probability import BallOutcome


BALLS_PER_OVER = 5        # The Hundred: 5 balls per over
OVERS_PER_INNINGS = 20     # 20 overs
BALLS_PER_INNINGS = 100    # 5 × 20
MAX_PER_BOWLER = 20        # 20 balls (4 overs equivalent)
POWERPLAY_BALLS = 25       # first 25 balls (overs 1-5)
DEATH_OVER_START = 17      # overs 17-20 are death (balls 81-100)
MAX_BOWLERS = 6            # max 6 bowlers per innings


@dataclass
class BatterStats:
    """Individual batter's stats in current innings."""
    player_id: str
    name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    is_not_out: bool = False
    dismissal_type: str = ""
    dismissed_by: str = ""
    dismissed_detail: str = ""

    @property
    def strike_rate(self) -> float:
        if self.balls == 0:
            return 0.0
        return round(self.runs / self.balls * 100, 2)


@dataclass
class BowlerStats:
    """Individual bowler's stats in current innings."""
    player_id: str
    name: str
    balls_bowled: int = 0
    runs_conceded: int = 0
    wickets: int = 0
    wides: int = 0
    noballs: int = 0

    @property
    def overs_display(self) -> str:
        full_overs = self.balls_bowled // BALLS_PER_OVER
        remaining = self.balls_bowled % BALLS_PER_OVER
        return f"{full_overs}-{remaining}" if remaining else f"{full_overs}.0"

    @property
    def economy(self) -> float:
        if self.balls_bowled == 0:
            return 0.0
        return round(self.runs_conceded / self.balls_bowled * BALLS_PER_OVER, 2)

    @property
    def figures(self) -> str:
        return f"{self.overs_display}-{self.runs_conceded}-{self.wickets}"

    @property
    def balls_remaining(self) -> int:
        return MAX_PER_BOWLER - self.balls_bowled


@dataclass
class Partnership:
    """Current partnership between two batters."""
    runs: int = 0
    balls: int = 0
    batter1_id: str = ""
    batter2_id: str = ""

    def add_run(self, runs: int):
        self.runs += runs
        self.balls += 1

    def reset(self, batter1_id: str, batter2_id: str):
        self.runs = 0
        self.balls = 0
        self.batter1_id = batter1_id
        self.batter2_id = batter2_id


@dataclass
class InningsState:
    """Complete state for one innings."""
    innings_number: int  # 1 or 2
    batting_team_id: int
    bowling_team_id: int

    total_runs: int = 0
    total_wickets: int = 0
    total_balls: int = 0

    # Current over tracking
    current_over: int = 1       # 1-20
    ball_in_over: int = 0       # 0-4 (0-indexed, resets each over)

    # Active batters
    striker_id: str = ""
    striker_name: str = ""
    non_striker_id: str = ""
    non_striker_name: str = ""

    # Current bowler
    current_bowler_id: str = ""
    current_bowler_name: str = ""
    balls_in_current_over: int = 0  # how many balls bowled in this over

    # Extras
    wides: int = 0
    noballs: int = 0
    byes: int = 0
    legbyes: int = 0

    # Partnership
    partnership: Partnership = field(default_factory=Partnership)

    # Per-player stats
    batting_stats: dict[str, BatterStats] = field(default_factory=dict)
    bowling_stats: dict[str, BowlerStats] = field(default_factory=dict)

    # Batting order tracking
    batting_order: list[str] = field(default_factory=list)  # player_ids in order
    next_batting_index: int = 0  # who comes in next

    # Bowling tracking
    bowlers_used: set[str] = field(default_factory=set)
    bowler_end: str = "A"  # alternates A/B after every set (2 overs)

    # State flags
    is_complete: bool = False
    all_out: bool = False
    target_reached: bool = False

    # Required runs (2nd innings)
    target: Optional[int] = None
    runs_needed: Optional[int] = None

    # Free hit tracking
    is_free_hit: bool = False

    @property
    def balls_remaining(self) -> int:
        return BALLS_PER_INNINGS - self.total_balls

    @property
    def run_rate(self) -> float:
        if self.total_balls == 0:
            return 0.0
        return round(self.total_runs / self.total_balls * BALLS_PER_OVER, 2)

    @property
    def required_run_rate(self) -> float:
        if self.runs_needed is None or self.balls_remaining == 0:
            return 0.0
        return round(self.runs_needed / self.balls_remaining * BALLS_PER_OVER, 2)

    @property
    def overs_display(self) -> str:
        full = self.total_balls // BALLS_PER_OVER
        remaining = self.total_balls % BALLS_PER_OVER
        if remaining:
            return f"{full}.{remaining}"
        return f"{full}.0"

    @property
    def phase(self) -> str:
        if self.total_balls < POWERPLAY_BALLS:
            return "powerplay"
        elif self.total_balls >= (BALLS_PER_INNINGS - (OVERS_PER_INNINGS - DEATH_OVER_START + 1) * BALLS_PER_OVER):
            return "death"
        return "middle"

    @property
    def is_set_over(self) -> bool:
        """True if we just completed a set (even-numbered over)."""
        return self.total_balls > 0 and self.total_balls % (BALLS_PER_OVER * 2) == 0

    @property
    def total_extras(self) -> int:
        return self.wides + self.noballs + self.byes + self.legbyes


class MatchState:
    """Complete match state tracker."""

    def __init__(
        self,
        match_id: int,
        team1_id: int,
        team2_id: int,
        team1_name: str,
        team2_name: str,
        venue_code: str,
    ):
        self.match_id = match_id
        self.team1_id = team1_id
        self.team2_id = team2_id
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.venue_code = venue_code

        self.innings1: Optional[InningsState] = None
        self.innings2: Optional[InningsState] = None
        self.current_innings: Optional[InningsState] = None

        self.toss_winner_id: Optional[int] = None
        self.toss_decision: str = ""  # 'bat' or 'bowl'

    def start_innings(
        self,
        innings_number: int,
        batting_team_id: int,
        bowling_team_id: int,
        batting_team_name: str,
        bowling_team_name: str,
        opening_batter1_id: str,
        opening_batter1_name: str,
        opening_batter2_id: str,
        opening_batter2_name: str,
        first_bowler_id: str,
        first_bowler_name: str,
        batting_order: list[str],
        target: Optional[int] = None,
    ) -> InningsState:
        """Initialize a new innings."""
        innings = InningsState(
            innings_number=innings_number,
            batting_team_id=batting_team_id,
            bowling_team_id=bowling_team_id,
        )

        innings.striker_id = opening_batter1_id
        innings.striker_name = opening_batter1_name
        innings.non_striker_id = opening_batter2_id
        innings.non_striker_name = opening_batter2_name

        innings.current_bowler_id = first_bowler_id
        innings.current_bowler_name = first_bowler_name

        innings.batting_order = batting_order
        innings.next_batting_index = 2  # first two are opening

        # Initialize batter stats
        innings.batting_stats[opening_batter1_id] = BatterStats(
            player_id=opening_batter1_id, name=opening_batter1_name
        )
        innings.batting_stats[opening_batter2_id] = BatterStats(
            player_id=opening_batter2_id, name=opening_batter2_name
        )

        # Initialize bowler stats
        innings.bowling_stats[first_bowler_id] = BowlerStats(
            player_id=first_bowler_id, name=first_bowler_name
        )
        innings.bowlers_used.add(first_bowler_id)

        # Partnership
        innings.partnership.reset(opening_batter1_id, opening_batter2_id)

        if target is not None:
            innings.target = target
            innings.runs_needed = target

        if innings_number == 1:
            self.innings1 = innings
        else:
            self.innings2 = innings

        self.current_innings = innings
        return innings

    def process_ball(self, outcome: BallOutcome) -> dict:
        """Process a ball outcome and update state. Returns a summary dict."""
        inn = self.current_innings
        if inn is None or inn.is_complete:
            return {"error": "No active innings"}

        summary = {
            "ball_number": inn.total_balls + 1,
            "over_number": inn.current_over,
            "ball_in_over": inn.ball_in_over + 1,
            "striker_id": inn.striker_id,
            "striker_name": inn.striker_name,
            "non_striker_id": inn.non_striker_id,
            "non_striker_name": inn.non_striker_name,
            "bowler_id": inn.current_bowler_id,
            "bowler_name": inn.current_bowler_name,
            "outcome": outcome,
            "is_free_hit": inn.is_free_hit,
        }

        # Reset free hit after this ball (unless it's a no-ball)
        if outcome.outcome != "noball":
            inn.is_free_hit = False

        # Process extras
        if outcome.outcome == "wide":
            inn.wides += 1
            inn.total_runs += 1
            inn.bowling_stats.setdefault(
                inn.current_bowler_id, BowlerStats(inn.current_bowler_id, inn.current_bowler_name)
            ).wides += 1
            inn.bowling_stats[inn.current_bowler_id].runs_conceded += 1
            if inn.runs_needed is not None:
                inn.runs_needed = max(0, inn.runs_needed - 1)
            # Wide doesn't count as a ball — don't advance ball counter
            # BUT in The Hundred, wides do count the extra ball in some rules
            # We'll count wides as a ball to keep it simple
            inn.total_balls += 1
            inn.ball_in_over += 1
            inn.balls_in_current_over += 1
            inn.partnership.add_run(1)
            summary["runs_after"] = inn.total_runs
            summary["wickets_after"] = inn.total_wickets
            summary["balls_after"] = inn.total_balls
            self._check_over_completion()
            return summary

        if outcome.outcome == "noball":
            inn.noballs += 1
            inn.total_runs += 1
            inn.bowling_stats.setdefault(
                inn.current_bowler_id, BowlerStats(inn.current_bowler_id, inn.current_bowler_name)
            ).noballs += 1
            inn.bowling_stats[inn.current_bowler_id].runs_conceded += 1
            if inn.runs_needed is not None:
                inn.runs_needed = max(0, inn.runs_needed - 1)
            # No-ball doesn't count as a legal delivery, but we count it as a ball
            inn.total_balls += 1
            inn.ball_in_over += 1
            inn.balls_in_current_over += 1
            inn.is_free_hit = True  # next ball is free hit
            inn.partnership.add_run(1)
            summary["runs_after"] = inn.total_runs
            summary["wickets_after"] = inn.total_wickets
            summary["balls_after"] = inn.total_balls
            summary["is_free_hit"] = True
            self._check_over_completion()
            return summary

        if outcome.outcome in ("bye", "legbye"):
            runs = outcome.extras
            inn.total_runs += runs
            if outcome.outcome == "bye":
                inn.byes += runs
            else:
                inn.legbyes += runs
            inn.total_balls += 1
            inn.ball_in_over += 1
            inn.balls_in_current_over += 1
            inn.bowler_stats.setdefault(
                inn.current_bowler_id, BowlerStats(inn.current_bowler_id, inn.current_bowler_name)
            )
            inn.partnership.add_run(runs)
            # Rotate strike on odd runs
            if runs % 2 == 1:
                inn.striker_id, inn.non_striker_id = inn.non_striker_id, inn.striker_id
                inn.striker_name, inn.non_striker_name = inn.non_striker_name, inn.striker_name
            if inn.runs_needed is not None:
                inn.runs_needed = max(0, inn.runs_needed - runs)
            summary["runs_after"] = inn.total_runs
            summary["wickets_after"] = inn.total_wickets
            summary["balls_after"] = inn.total_balls
            self._check_over_completion()
            return summary

        # Regular delivery (dot/single/double/triple/four/six/wicket)
        runs = outcome.runs_scored

        # Update batting stats
        bat_stat = inn.batting_stats[inn.striker_id]
        bat_stat.balls += 1
        bat_stat.runs += runs
        if runs == 4:
            bat_stat.fours += 1
        elif runs == 6:
            bat_stat.sixes += 1

        # Update bowling stats
        bowl_stat = inn.bowling_stats.setdefault(
            inn.current_bowler_id, BowlerStats(inn.current_bowler_id, inn.current_bowler_name)
        )
        bowl_stat.runs_conceded += runs
        bowl_stat.balls_bowled += 1

        # Update totals
        inn.total_runs += runs
        inn.total_balls += 1
        inn.ball_in_over += 1
        inn.balls_in_current_over += 1

        # Partnership
        inn.partnership.add_run(runs)

        # Target tracking
        if inn.runs_needed is not None:
            inn.runs_needed = max(0, inn.runs_needed - runs)

        # Wicket
        if outcome.is_wicket:
            bat_stat.dismissal_type = outcome.dismissal_type
            bat_stat.dismissed_detail = outcome.dismissal_detail
            bat_stat.dismissed_by = inn.current_bowler_name

            inn.total_wickets += 1
            bowl_stat.wickets += 1

            # Check if all out (10 wickets)
            if inn.total_wickets >= 10:
                inn.all_out = True
                inn.is_complete = True
                bat_stat.is_not_out = False
            else:
                # New batter comes in
                bat_stat.is_not_out = False
                self._send_in_next_batter(inn)

        # Strike rotation on regular runs (The Hundred rules)
        if not outcome.is_wicket:
            if runs % 2 == 1:
                # Odd runs: rotate strike
                inn.striker_id, inn.non_striker_id = inn.non_striker_id, inn.striker_id
                inn.striker_name, inn.non_striker_name = inn.non_striker_name, inn.striker_name
            # Even runs (0, 2, 4, 6): striker stays on strike

        summary["runs_after"] = inn.total_runs
        summary["wickets_after"] = inn.total_wickets
        summary["balls_after"] = inn.total_balls

        # Check if innings is complete
        if inn.total_balls >= BALLS_PER_INNINGS:
            inn.is_complete = True
        if inn.target is not None and inn.total_runs >= inn.target:
            inn.target_reached = True
            inn.is_complete = True

        self._check_over_completion()
        return summary

    def _check_over_completion(self):
        """Check if current over is complete and handle over change."""
        inn = self.current_innings
        if inn is None:
            return

        if inn.balls_in_current_over >= BALLS_PER_OVER:
            # Over complete
            inn.current_over += 1
            inn.ball_in_over = 0
            inn.balls_in_current_over = 0

            # Strike rotation at end of over (The Hundred rules)
            # From odd to even over: odd runs = non-striker for next, even = striker
            # From even to odd over: odd runs = striker for next, even = non-striker
            # We handle this by always rotating at over end
            # The actual rule depends on last ball runs, but we simplify:
            inn.striker_id, inn.non_striker_id = inn.non_striker_id, inn.striker_id
            inn.striker_name, inn.non_striker_name = inn.non_striker_name, inn.striker_name

            # Bowling end changes every set (2 overs)
            if inn.current_over % 2 == 0:
                inn.bowler_end = "B" if inn.bowler_end == "A" else "A"

    def set_next_bowler(self, bowler_id: str, bowler_name: str) -> bool:
        """Set the next bowler for the upcoming over. Returns True if valid."""
        inn = self.current_innings
        if inn is None:
            return False

        bowl_stat = inn.bowling_stats.get(bowler_id)
        if bowl_stat and bowl_stat.balls_bowled >= MAX_PER_BOWLER:
            return False  # already bowled max

        inn.current_bowler_id = bowler_id
        inn.current_bowler_name = bowler_name
        inn.bowlers_used.add(bowler_id)
        return True

    def set_next_batter(self, batter_id: str, batter_name: str) -> bool:
        """Set the next batter after a wicket. Returns True if valid."""
        inn = self.current_innings
        if inn is None:
            return False

        # Initialize batter stats
        inn.batting_stats[batter_id] = BatterStats(
            player_id=batter_id, name=batter_name
        )

        # Set as striker (new batter always faces)
        inn.striker_id = batter_id
        inn.striker_name = batter_name
        inn.next_batting_index += 1

        # Reset partnership
        inn.partnership.reset(batter_id, inn.non_striker_id)
        return True

    def _send_in_next_batter(self, inn: InningsState):
        """Auto-send in next batter from batting order (fallback)."""
        if inn.next_batting_index < len(inn.batting_order):
            next_id = inn.batting_order[inn.next_batting_index]
            if next_id not in inn.batting_stats:
                inn.batting_stats[next_id] = BatterStats(
                    player_id=next_id, name=f"Player {next_id}"
                )
                inn.striker_id = next_id
                inn.striker_name = f"Player {next_id}"
                inn.partnership.reset(next_id, inn.non_striker_id)
                inn.next_batting_index += 1

    def get_live_summary(self) -> dict:
        """Get current match state as a dictionary."""
        inn = self.current_innings
        if inn is None:
            return {}

        return {
            "score": f"{inn.total_runs}/{inn.total_wickets}",
            "overs": inn.overs_display,
            "run_rate": inn.run_rate,
            "required_run_rate": inn.required_run_rate,
            "runs_needed": inn.runs_needed,
            "balls_remaining": inn.balls_remaining,
            "phase": inn.phase,
            "striker": {
                "id": inn.striker_id,
                "name": inn.striker_name,
                "runs": inn.batting_stats.get(inn.striker_id, BatterStats("", "")).runs,
                "balls": inn.batting_stats.get(inn.striker_id, BatterStats("", "")).balls,
                "sr": inn.batting_stats.get(inn.striker_id, BatterStats("", "")).strike_rate,
            },
            "non_striker": {
                "id": inn.non_striker_id,
                "name": inn.non_striker_name,
                "runs": inn.batting_stats.get(inn.non_striker_id, BatterStats("", "")).runs,
                "balls": inn.batting_stats.get(inn.non_striker_id, BatterStats("", "")).balls,
                "sr": inn.batting_stats.get(inn.non_striker_id, BatterStats("", "")).strike_rate,
            },
            "current_bowler": {
                "id": inn.current_bowler_id,
                "name": inn.current_bowler_name,
                "figures": inn.bowling_stats.get(
                    inn.current_bowler_id, BowlerStats("", "")
                ).figures,
            },
            "partnership": {
                "runs": inn.partnership.runs,
                "balls": inn.partnership.balls,
            },
            "extras": {
                "wides": inn.wides,
                "noballs": inn.noballs,
                "byes": inn.byes,
                "legbyes": inn.legbyes,
                "total": inn.total_extras,
            },
            "is_complete": inn.is_complete,
            "target": inn.target,
            "innings_number": inn.innings_number,
        }
