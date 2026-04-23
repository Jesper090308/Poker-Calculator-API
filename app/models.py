from __future__ import annotations

import re
from enum import Enum

from app.runtime import bootstrap_local_packages

bootstrap_local_packages()

from pydantic import BaseModel, Field, field_validator, model_validator


CARD_PATTERN = re.compile(r"^(10|[2-9TJQKA])[CDHS]$", re.IGNORECASE)


def normalize_card(card: str) -> str:
    raw = card.strip()
    if not raw:
        raise ValueError("Card values cannot be blank.")
    raw = raw.upper().replace("10", "T")
    if not CARD_PATTERN.match(raw):
        raise ValueError(
            f"Invalid card '{card}'. Use ranks 2-9, T, J, Q, K, A and suits c, d, h, s."
        )
    return f"{raw[0]}{raw[1].lower()}"


class BackendMode(str, Enum):
    AUTO = "auto"
    HEURISTIC = "heuristic"
    OPEN_SPIEL = "open_spiel"


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class OpponentAction(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


class OpponentStyle(str, Enum):
    UNKNOWN = "unknown"
    TIGHT_PASSIVE = "tight_passive"
    TAG = "tag"
    LAG = "lag"
    MANIAC = "maniac"
    CALLING_STATION = "calling_station"


class OpponentProfile(BaseModel):
    style: OpponentStyle = OpponentStyle.UNKNOWN
    aggression: float = Field(0.5, ge=0.0, le=1.0)
    bluff_frequency: float = Field(0.35, ge=0.0, le=1.0)
    fold_to_raise: float = Field(0.42, ge=0.0, le=1.0)


class ObservedAction(BaseModel):
    street: Street
    actor: str = Field(min_length=1, max_length=40)
    action: OpponentAction
    amount: float = Field(0.0, ge=0.0)
    pot_size: float = Field(0.0, ge=0.0)

    @field_validator("actor", mode="before")
    @classmethod
    def _trim_actor(cls, value: object) -> str:
        if value is None:
            raise ValueError("Actor is required.")
        actor = str(value).strip()
        if not actor:
            raise ValueError("Actor is required.")
        return actor


class VillainState(BaseModel):
    seat: int = Field(ge=1, le=8)
    name: str | None = Field(default=None, max_length=40)
    stack: float = Field(ge=0.0)
    in_hand: bool = True
    is_aggressor: bool = False
    last_action: OpponentAction = OpponentAction.CHECK
    last_bet: float = Field(0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=200)
    profile: OpponentProfile = Field(default_factory=OpponentProfile)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def _sync_fold_state(self) -> "VillainState":
        if self.last_action == OpponentAction.FOLD:
            self.in_hand = False
        return self

    def display_name(self) -> str:
        return self.name or f"Villain {self.seat}"

    def actor_id(self) -> str:
        return self.display_name().lower().replace(" ", "_")


class GameSummary(BaseModel):
    game_id: str
    label: str
    created_at: str
    villain_count: int = Field(ge=1, le=8)
    hands_recorded: int = Field(ge=0)
    decisions_recorded: int = Field(ge=0)


class GameStateResponse(BaseModel):
    database_path: str
    current_game: GameSummary
    recent_games: list[GameSummary]


class NewGameRequest(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    villain_count: int = Field(1, ge=1, le=8)
    villain_names: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("villain_names", mode="before")
    @classmethod
    def _normalize_names(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Villain names must be provided as a list.")
        return [str(item).strip() for item in value if str(item).strip()]


class ResetGameRequest(BaseModel):
    game_id: str | None = Field(default=None, max_length=64)
    villain_count: int | None = Field(default=None, ge=1, le=8)
    villain_names: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("villain_names", mode="before")
    @classmethod
    def _normalize_names(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Villain names must be provided as a list.")
        return [str(item).strip() for item in value if str(item).strip()]


class VillainSnapshot(BaseModel):
    seat: int = Field(ge=1, le=8)
    name: str
    in_hand: bool
    stack: float = Field(ge=0.0)
    style: OpponentStyle
    aggression: float = Field(ge=0.0, le=1.0)
    bluff_frequency: float = Field(ge=0.0, le=1.0)
    fold_to_raise: float = Field(ge=0.0, le=1.0)
    hands_observed: int = Field(ge=0)
    average_bet_size: float = Field(ge=0.0)


class DecisionRequest(BaseModel):
    backend: BackendMode = BackendMode.AUTO
    game_id: str | None = Field(default=None, max_length=64)
    hero_cards: list[str] = Field(min_length=2, max_length=2)
    board_cards: list[str] = Field(default_factory=list, max_length=5)
    pot_size: float = Field(ge=0.0)
    to_call: float = Field(0.0, ge=0.0)
    hero_stack: float = Field(ge=0.0)
    big_blind: float = Field(1.0, gt=0.0)
    max_seconds: float = Field(8.0, ge=1.0, le=55.0)
    min_raise_to: float | None = Field(default=None, ge=0.0)
    notes: str | None = Field(default=None, max_length=400)
    action_history: list[ObservedAction] = Field(default_factory=list, max_length=48)
    active_villain_seat: int | None = Field(default=None, ge=1, le=8)
    villains: list[VillainState] = Field(default_factory=list, max_length=8)

    # Legacy single-villain compatibility.
    villain_stack: float | None = Field(default=None, ge=0.0)
    opponent_last_action: OpponentAction = OpponentAction.CHECK
    previous_bet: float = Field(0.0, ge=0.0)
    opponent_profile: OpponentProfile = Field(default_factory=OpponentProfile)

    @field_validator("hero_cards", "board_cards", mode="before")
    @classmethod
    def _normalize_card_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Cards must be provided as a list.")
        return [normalize_card(card) for card in value if str(card).strip()]

    @model_validator(mode="after")
    def _validate_consistency(self) -> "DecisionRequest":
        if len(self.board_cards) not in {0, 3, 4, 5}:
            raise ValueError("Board cards must contain 0, 3, 4, or 5 cards.")

        all_cards = self.hero_cards + self.board_cards
        if len(all_cards) != len(set(all_cards)):
            raise ValueError("Hero cards and board cards must be unique.")

        if not self.villains:
            if self.villain_stack is None:
                raise ValueError("Provide either villains or villain_stack.")
            self.villains = [
                VillainState(
                    seat=1,
                    name="Villain 1",
                    stack=self.villain_stack,
                    in_hand=True,
                    is_aggressor=True,
                    last_action=self.opponent_last_action,
                    last_bet=max(self.previous_bet, self.to_call),
                    profile=self.opponent_profile,
                )
            ]

        seen_seats: set[int] = set()
        for villain in self.villains:
            if villain.seat in seen_seats:
                raise ValueError("Villain seats must be unique.")
            seen_seats.add(villain.seat)

        active_villains = [villain for villain in self.villains if villain.in_hand]
        if not active_villains:
            raise ValueError("At least one villain must still be in the hand.")

        if self.active_villain_seat is not None and self.active_villain_seat not in {
            villain.seat for villain in active_villains
        }:
            raise ValueError("Active villain seat must reference a villain still in the hand.")

        aggressors = [villain for villain in active_villains if villain.is_aggressor]
        if self.active_villain_seat is None:
            if aggressors:
                self.active_villain_seat = aggressors[0].seat
            elif self.to_call > 0:
                self.active_villain_seat = max(
                    active_villains,
                    key=lambda villain: (villain.last_bet, villain.seat),
                ).seat
            else:
                self.active_villain_seat = active_villains[0].seat

        if self.min_raise_to is not None and self.min_raise_to < self.to_call:
            raise ValueError("Minimum raise must be at least the current call amount.")

        if self.to_call > self.effective_stack():
            raise ValueError("Call amount cannot exceed the effective stack.")

        return self

    def street(self) -> Street:
        board_count = len(self.board_cards)
        if board_count == 0:
            return Street.PREFLOP
        if board_count == 3:
            return Street.FLOP
        if board_count == 4:
            return Street.TURN
        return Street.RIVER

    def active_villains(self) -> list[VillainState]:
        return [villain for villain in self.villains if villain.in_hand]

    def active_villain(self) -> VillainState:
        active = {villain.seat: villain for villain in self.active_villains()}
        return active[self.active_villain_seat or self.active_villains()[0].seat]

    def effective_stack(self) -> float:
        active_villain = self.active_villain()
        return min(self.hero_stack, active_villain.stack)


class ActionScore(BaseModel):
    action: str
    amount: float = Field(ge=0.0)
    ev: float
    fold_equity: float = Field(ge=0.0, le=1.0)
    notes: str


class BackendStatus(BaseModel):
    requested: str
    selected: str
    openspiel_available: bool
    details: str


class DecisionResponse(BaseModel):
    game_id: str
    street: Street
    recommended_action: str
    recommended_amount: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    hero_equity: float = Field(ge=0.0, le=1.0)
    pot_odds: float = Field(ge=0.0, le=1.0)
    break_even_equity: float = Field(ge=0.0, le=1.0)
    spr: float = Field(ge=0.0)
    nut_advantage: float = Field(ge=-1.0, le=1.0)
    equity_bucket_hit: bool
    hand_summary: str
    board_summary: str
    opponent_summary: str
    session_summary: str
    reasoning: list[str]
    action_scores: list[ActionScore]
    villain_snapshots: list[VillainSnapshot]
    simulation_iterations: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    backend: BackendStatus
