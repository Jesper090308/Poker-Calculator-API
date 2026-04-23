from __future__ import annotations

import math
import random
import sys
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from itertools import combinations

from app.runtime import bootstrap_local_packages

bootstrap_local_packages()

from treys import Card, Evaluator

from app.engines.openspiel_adapter import OpenSpielAvailability
from app.models import (
    ActionScore,
    BackendStatus,
    DecisionRequest,
    DecisionResponse,
    OpponentAction,
    OpponentProfile,
    OpponentStyle,
    Street,
    VillainSnapshot,
    VillainState,
)
from app.services.game_store import GameStore


RANKS = "23456789TJQKA"
SUITS = "cdhs"
ALL_CARDS = tuple(f"{rank}{suit}" for rank in RANKS for suit in SUITS)
RANK_TO_VALUE = {rank: index + 2 for index, rank in enumerate(RANKS)}
TREYS_INT_BY_CARD = {card: Card.new(card) for card in ALL_CARDS}
EVALUATOR = Evaluator()

STYLE_RANGE_WIDTH = {
    OpponentStyle.UNKNOWN: 0.52,
    OpponentStyle.TIGHT_PASSIVE: 0.34,
    OpponentStyle.TAG: 0.45,
    OpponentStyle.LAG: 0.66,
    OpponentStyle.MANIAC: 0.82,
    OpponentStyle.CALLING_STATION: 0.61,
}

STYLE_LABEL = {
    OpponentStyle.UNKNOWN: "unknown",
    OpponentStyle.TIGHT_PASSIVE: "tight-passive",
    OpponentStyle.TAG: "tight-aggressive",
    OpponentStyle.LAG: "loose-aggressive",
    OpponentStyle.MANIAC: "maniac",
    OpponentStyle.CALLING_STATION: "calling station",
}

HAND_CLASS_STRENGTH = {
    "Straight Flush": 1.00,
    "Four of a Kind": 0.99,
    "Full House": 0.96,
    "Flush": 0.91,
    "Straight": 0.86,
    "Three of a Kind": 0.76,
    "Two Pair": 0.64,
    "Pair": 0.47,
    "High Card": 0.18,
}

STRAIGHT_WINDOWS = [
    {14, 2, 3, 4, 5},
    {2, 3, 4, 5, 6},
    {3, 4, 5, 6, 7},
    {4, 5, 6, 7, 8},
    {5, 6, 7, 8, 9},
    {6, 7, 8, 9, 10},
    {7, 8, 9, 10, 11},
    {8, 9, 10, 11, 12},
    {9, 10, 11, 12, 13},
    {10, 11, 12, 13, 14},
]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def card_value(card: str) -> int:
    return RANK_TO_VALUE[card[0]]


def card_suit(card: str) -> str:
    return card[1]


def describe_starting_hand(cards: list[str]) -> str:
    first, second = cards
    values = sorted([card_value(first), card_value(second)], reverse=True)
    suited = card_suit(first) == card_suit(second)
    if values[0] == values[1]:
        pair_rank = first[0]
        return f"pocket {pair_rank}{pair_rank}"
    gap = abs(values[0] - values[1])
    if values[0] >= 10 and values[1] >= 10:
        return "broadway combo" + (" (suited)" if suited else "")
    if suited and gap <= 2:
        return "suited connector-style hand"
    if suited:
        return "suited high-card hand"
    if gap <= 2:
        return "connected offsuit hand"
    return "offsuit high-card hand"


def board_texture(board_cards: list[str]) -> str:
    if not board_cards:
        return "Preflop spot with no community cards yet."

    values = [card_value(card) for card in board_cards]
    suits = Counter(card_suit(card) for card in board_cards)
    ranks = Counter(card[0] for card in board_cards)
    descriptors: list[str] = []

    if max(ranks.values()) >= 2:
        descriptors.append("paired")
    if max(suits.values()) >= 4:
        descriptors.append("four-flush")
    elif max(suits.values()) == 3:
        descriptors.append("three-to-a-flush")
    elif max(suits.values()) == 2:
        descriptors.append("two-tone")

    rank_span = max(values) - min(values)
    if rank_span <= 4:
        descriptors.append("connected")
    elif rank_span <= 6:
        descriptors.append("semi-connected")

    broadway_count = sum(value >= 10 for value in values)
    if broadway_count >= 2:
        descriptors.append("broadway-heavy")

    if not descriptors:
        descriptors.append("dry")

    return f"{len(board_cards)}-card board: " + ", ".join(descriptors) + "."


def board_texture_key(board_cards: list[str]) -> str:
    if not board_cards:
        return "preflop"
    values = sorted(card_value(card) for card in board_cards)
    suits = Counter(card_suit(card) for card in board_cards)
    ranks = Counter(card[0] for card in board_cards)
    suit_peak = max(suits.values())
    pair_flag = "p" if max(ranks.values()) >= 2 else "u"
    span = max(values) - min(values)
    connectivity = "c" if span <= 4 else "s" if span <= 6 else "d"
    broadway = "b" if sum(value >= 10 for value in values) >= 2 else "n"
    return f"{len(board_cards)}-{pair_flag}-{suit_peak}-{connectivity}-{broadway}"


def evaluate_current_hand(hero_cards: list[str], board_cards: list[str]) -> str:
    if not board_cards:
        return f"Hero holds {describe_starting_hand(hero_cards)}."

    board_ints = [TREYS_INT_BY_CARD[card] for card in board_cards]
    hand_ints = [TREYS_INT_BY_CARD[card] for card in hero_cards]
    score = EVALUATOR.evaluate(board_ints, hand_ints)
    class_name = EVALUATOR.class_to_string(EVALUATOR.get_rank_class(score))
    draw_score_value, draw_label = draw_profile(hero_cards, board_cards)
    suffix = f" plus {draw_label}" if draw_score_value > 0 else ""
    return f"Current made hand: {class_name.lower()}{suffix}."


def preflop_combo_strength(combo: tuple[str, str]) -> float:
    first, second = combo
    values = sorted([card_value(first), card_value(second)], reverse=True)
    suited = card_suit(first) == card_suit(second)
    pair = values[0] == values[1]
    gap = abs(values[0] - values[1])

    strength = 0.18 + ((values[0] - 2) + (values[1] - 2)) / 24 * 0.52
    if pair:
        strength += 0.22 + (values[0] - 2) / 12 * 0.18
    if suited:
        strength += 0.06
    if gap == 1:
        strength += 0.07
    elif gap == 2:
        strength += 0.04
    elif gap == 3:
        strength += 0.02
    if values[0] >= 10 and values[1] >= 10:
        strength += 0.05
    if 14 in values and suited:
        strength += 0.03

    return clamp(strength, 0.0, 1.0)


def draw_profile(cards: list[str], board_cards: list[str]) -> tuple[float, str]:
    if len(board_cards) >= 5 or not board_cards:
        return 0.0, "no live draws"

    combined = cards + board_cards
    suits = Counter(card_suit(card) for card in combined)
    values = {card_value(card) for card in combined}
    if 14 in values:
        values.add(1)

    flush_draw = max(suits.values()) >= 4
    backdoor_flush = len(board_cards) == 3 and max(suits.values()) == 3
    straight_hits = max(len(window & values) for window in STRAIGHT_WINDOWS)

    if flush_draw and straight_hits >= 4:
        return 0.55, "a combo draw"
    if flush_draw:
        return 0.34, "a flush draw"
    if straight_hits >= 4:
        return 0.28, "a straight draw"
    if backdoor_flush:
        return 0.10, "backdoor flush potential"
    return 0.0, "no live draws"


def current_made_strength(combo: tuple[str, str], board_cards: list[str]) -> float:
    if not board_cards:
        return preflop_combo_strength(combo)

    board_ints = [TREYS_INT_BY_CARD[card] for card in board_cards]
    hand_ints = [TREYS_INT_BY_CARD[card] for card in combo]
    score = EVALUATOR.evaluate(board_ints, hand_ints)
    class_name = EVALUATOR.class_to_string(EVALUATOR.get_rank_class(score))
    base = HAND_CLASS_STRENGTH.get(class_name, 0.18)
    normalized = 1.0 - (score / 7462.0)
    return clamp(base * 0.65 + normalized * 0.35, 0.0, 1.0)


def hand_bucket_signature(cards: list[str]) -> str:
    values = sorted([card_value(cards[0]), card_value(cards[1])], reverse=True)
    suited = card_suit(cards[0]) == card_suit(cards[1])
    if values[0] == values[1]:
        return f"pair-{values[0]}"
    gap = abs(values[0] - values[1])
    broadway = values[0] >= 10 and values[1] >= 10
    if broadway and suited:
        return "suited-broadway"
    if broadway:
        return "offsuit-broadway"
    if suited and gap <= 2:
        return "suited-connector"
    if gap <= 2:
        return "connected"
    return "mixed"


def blocker_bonus(hero_cards: list[str], board_cards: list[str]) -> float:
    if not board_cards:
        return 0.0
    suits = Counter(card_suit(card) for card in board_cards)
    dominant_suit, dominant_count = suits.most_common(1)[0]
    bonus = 0.0
    if dominant_count >= 2 and any(
        card_suit(card) == dominant_suit and card_value(card) >= 13 for card in hero_cards
    ):
        bonus += 0.06
    values = {card_value(card) for card in hero_cards + board_cards}
    if 14 in values:
        values.add(1)
    if max(len(window & values) for window in STRAIGHT_WINDOWS) >= 4:
        bonus += 0.04
    return bonus


def merge_profiles(base: OpponentProfile, updated: OpponentProfile, observations: int) -> OpponentProfile:
    weight = min(0.76, observations / 16.0)
    return OpponentProfile(
        style=updated.style if observations >= 4 else base.style,
        aggression=clamp(base.aggression * (1.0 - weight) + updated.aggression * weight, 0.0, 1.0),
        bluff_frequency=clamp(
            base.bluff_frequency * (1.0 - weight) + updated.bluff_frequency * weight,
            0.0,
            1.0,
        ),
        fold_to_raise=clamp(
            base.fold_to_raise * (1.0 - weight) + updated.fold_to_raise * weight,
            0.0,
            1.0,
        ),
    )


class LruCache:
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self._data: OrderedDict[object, object] = OrderedDict()

    def get(self, key: object) -> object | None:
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def put(self, key: object, value: object) -> None:
        if key in self._data:
            self._data.pop(key)
        self._data[key] = value
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)


@dataclass(frozen=True)
class CandidateAction:
    label: str
    amount: float
    aggressive: bool


@dataclass(frozen=True)
class ResolvedVillain:
    seat: int
    name: str
    stack: float
    in_hand: bool
    is_aggressor: bool
    last_action: OpponentAction
    last_bet: float
    profile: OpponentProfile
    hands_observed: int
    average_bet_size: float

    def actor_keys(self) -> set[str]:
        normalized = self.name.lower().replace(" ", "_")
        return {
            self.name.lower(),
            normalized,
            f"villain_{self.seat}",
            f"seat_{self.seat}",
        }


@dataclass(frozen=True)
class PreparedRequest:
    request: DecisionRequest
    game_id: str
    street: Street
    villains: tuple[ResolvedVillain, ...]
    active_villains: tuple[ResolvedVillain, ...]
    active_villain: ResolvedVillain
    effective_stack: float
    spr: float
    session_summary: str
    villain_snapshots: tuple[VillainSnapshot, ...]


@dataclass(frozen=True)
class RangeAnalysis:
    villain: ResolvedVillain
    combos: tuple[tuple[str, str], ...]
    weights: tuple[float, ...]
    cumulative: tuple[float, ...]
    total_weight: float
    summary: str
    nut_share: float
    draw_share: float


@dataclass(frozen=True)
class EquityResult:
    equity: float
    iterations: int
    range_summary: str
    nut_advantage: float
    bucket_hit: bool


def action_history_for_villain(prepared: PreparedRequest, villain: ResolvedVillain) -> list[object]:
    history: list[object] = []
    for action in prepared.request.action_history:
        actor = action.actor.strip().lower().replace(" ", "_")
        if actor in villain.actor_keys():
            history.append(action)
    return history


def combo_weight(combo: tuple[str, str], prepared: PreparedRequest, villain: ResolvedVillain) -> float:
    request = prepared.request
    pressure = max(request.to_call, villain.last_bet) / max(request.pot_size, request.big_blind)
    profile = villain.profile
    width = STYLE_RANGE_WIDTH[profile.style]
    history = action_history_for_villain(prepared, villain)

    if not request.board_cards:
        strength = preflop_combo_strength(combo)
        if villain.last_action == OpponentAction.CHECK:
            weight = 0.28 + width * 0.24 + strength * 0.36
        elif villain.last_action == OpponentAction.CALL:
            weight = 0.12 + width * 0.20 + strength * 0.40
        elif villain.last_action == OpponentAction.BET:
            weight = 0.04 + strength * (0.82 + pressure * 0.10)
            weight += (1.0 - strength) * profile.bluff_frequency * (0.12 + profile.aggression * 0.06)
        elif villain.last_action == OpponentAction.RAISE:
            weight = 0.02 + strength * (0.94 + pressure * 0.14)
            weight += (1.0 - strength) * profile.bluff_frequency * (0.06 + profile.aggression * 0.08)
        else:
            weight = 0.01 + strength * (1.03 + pressure * 0.16)
            weight += (1.0 - strength) * profile.bluff_frequency * 0.03

        sizing_ratio = villain.last_bet / max(request.pot_size, request.big_blind)
        if sizing_ratio <= 0.45:
            weight += (1.0 - strength) * profile.bluff_frequency * 0.08
        elif sizing_ratio >= 0.90:
            weight += strength * 0.10

        multiplier = action_history_multiplier(history, strength, 0.0, 0.0)
        return clamp(weight * multiplier * (0.24 + width), 0.001, 2.2)

    made = current_made_strength(combo, request.board_cards)
    draw_score_value, _ = draw_profile(list(combo), request.board_cards)
    air = max(0.0, 1.0 - max(made, draw_score_value * 0.85))

    if villain.last_action == OpponentAction.CHECK:
        weight = 0.18 + width * 0.16 + made * 0.24 + draw_score_value * 0.18
        weight += air * (0.04 + profile.bluff_frequency * 0.08)
    elif villain.last_action == OpponentAction.CALL:
        weight = 0.10 + made * 0.28 + draw_score_value * 0.22 + air * 0.03
    elif villain.last_action == OpponentAction.BET:
        weight = 0.03 + made * (0.84 + pressure * 0.18)
        weight += draw_score_value * (0.26 + profile.aggression * 0.16)
        weight += air * (0.03 + profile.bluff_frequency * 0.10)
    elif villain.last_action == OpponentAction.RAISE:
        weight = 0.01 + made * (0.96 + pressure * 0.24)
        weight += draw_score_value * (0.20 + profile.aggression * 0.18)
        weight += air * (0.02 + profile.bluff_frequency * 0.06)
    else:
        weight = 0.005 + made * (1.04 + pressure * 0.26)
        weight += draw_score_value * (0.11 + profile.aggression * 0.08)
        weight += air * 0.02

    sizing_ratio = villain.last_bet / max(request.pot_size, request.big_blind)
    if sizing_ratio <= 0.45:
        weight += air * profile.bluff_frequency * 0.14 + draw_score_value * 0.08
    elif sizing_ratio >= 0.90:
        weight += made * 0.16 - air * 0.09
    else:
        weight += made * 0.06 + draw_score_value * 0.05

    if profile.style == OpponentStyle.CALLING_STATION:
        weight += made * 0.08
    if profile.style == OpponentStyle.TIGHT_PASSIVE:
        weight += made * 0.06 - air * 0.04
    if profile.style == OpponentStyle.TAG:
        weight += made * 0.04 + draw_score_value * 0.03 - air * 0.04

    multiplier = action_history_multiplier(history, made, draw_score_value, air)
    return clamp(weight * multiplier * (0.28 + width), 0.001, 2.4)


def action_history_multiplier(
    history: list[object],
    strength: float,
    draw_score_value: float,
    air: float,
) -> float:
    multiplier = 1.0
    for index, action in enumerate(history[-8:]):
        decay = 1.0 - min(0.55, index * 0.08)
        sizing_ratio = action.amount / max(action.pot_size, 1.0)
        if action.action in {OpponentAction.BET, OpponentAction.RAISE, OpponentAction.ALL_IN}:
            if sizing_ratio <= 0.45:
                multiplier += (air * 0.22 + draw_score_value * 0.12) * decay
                multiplier -= strength * 0.04 * decay
            elif sizing_ratio >= 0.90:
                multiplier += strength * 0.26 * decay
                multiplier -= air * 0.18 * decay
            else:
                multiplier += (strength * 0.14 + draw_score_value * 0.10) * decay
        elif action.action == OpponentAction.CALL:
            multiplier += (strength * 0.08 + draw_score_value * 0.12 - air * 0.04) * decay
        elif action.action == OpponentAction.CHECK:
            multiplier += (air * 0.06 + draw_score_value * 0.04 - strength * 0.02) * decay
    return clamp(multiplier, 0.35, 1.95)


def range_bucket(combo: tuple[str, str], board_cards: list[str]) -> str:
    if not board_cards:
        values = sorted([card_value(combo[0]), card_value(combo[1])], reverse=True)
        suited = card_suit(combo[0]) == card_suit(combo[1])
        if values[0] == values[1] and values[0] >= 11:
            return "big pairs"
        if values[0] >= 10 and values[1] >= 10:
            return "broadway hands"
        if suited and abs(values[0] - values[1]) <= 2:
            return "suited connectors"
        return "mixed offsuit hands"

    made = current_made_strength(combo, board_cards)
    draw_score_value, _ = draw_profile(list(combo), board_cards)
    if made >= 0.80:
        return "strong made hands"
    if draw_score_value >= 0.30:
        return "draw-heavy hands"
    if made >= 0.48:
        return "showdown hands"
    return "air and floats"


def summarize_range(analysis: RangeAnalysis, board_cards: list[str]) -> str:
    weighted_buckets: Counter[str] = Counter()
    for combo, weight in zip(analysis.combos, analysis.weights):
        weighted_buckets[range_bucket(combo, board_cards)] += weight

    top_buckets = [bucket for bucket, _ in weighted_buckets.most_common(2)]
    style_text = STYLE_LABEL[analysis.villain.profile.style]
    if not top_buckets:
        return f"{analysis.villain.name}: {style_text} profile with a balanced range estimate."

    shape = "mixed"
    if analysis.villain.last_action in {OpponentAction.RAISE, OpponentAction.ALL_IN}:
        shape = "polarized"
    elif analysis.villain.last_action in {OpponentAction.BET, OpponentAction.CALL}:
        shape = "pressure-capped"

    buckets_text = " and ".join(top_buckets)
    return f"{analysis.villain.name}: {style_text} {shape} range leaning toward {buckets_text}."


def candidate_actions(prepared: PreparedRequest) -> list[CandidateAction]:
    request = prepared.request
    effective_stack = prepared.effective_stack
    pot = request.pot_size
    to_call = request.to_call
    villains_left = len(prepared.active_villains)
    spr = prepared.spr
    candidates: list[CandidateAction] = []

    if to_call > 0:
        candidates.append(CandidateAction("fold", 0.0, False))
        candidates.append(CandidateAction("call", round(to_call, 2), False))

        minimum = request.min_raise_to or to_call + max(request.big_blind * 2, prepared.active_villain.last_bet)
        small_factor = 0.45 if spr >= 6 else 0.55 if spr >= 3 else 0.70
        pressure_factor = 1.0 + max(0, villains_left - 1) * 0.12
        small = clamp(max(minimum, to_call + pot * small_factor * pressure_factor), to_call, effective_stack)
        pot_raise = clamp(
            max(small, to_call + pot * (0.90 if spr >= 4 else 1.15)),
            to_call,
            effective_stack,
        )
        jam = round(effective_stack, 2)

        for label, amount in (
            ("raise small", small),
            ("raise pot", pot_raise),
            ("jam", jam),
        ):
            if amount > to_call:
                candidates.append(CandidateAction(label, round(amount, 2), True))
    else:
        candidates.append(CandidateAction("check", 0.0, False))
        probe_factor = 0.28 if len(prepared.active_villains) > 1 else 0.33
        value_factor = 0.58 if spr >= 7 else 0.74
        probe = clamp(max(request.big_blind * 2, pot * probe_factor), 0.0, effective_stack)
        value = clamp(max(probe, pot * value_factor), 0.0, effective_stack)
        jam = round(effective_stack, 2)

        for label, amount in (
            ("bet 33%", probe),
            ("bet 75%", value),
            ("jam", jam),
        ):
            if amount > 0:
                candidates.append(CandidateAction(label, round(amount, 2), True))

    deduped: dict[tuple[str, float], CandidateAction] = {}
    for candidate in candidates:
        key = (candidate.label, round(candidate.amount, 2))
        deduped[key] = candidate
    return list(deduped.values())


def estimate_fold_equity(
    prepared: PreparedRequest,
    action: CandidateAction,
    equity: float,
    nut_advantage: float,
) -> float:
    if not action.aggressive:
        return 0.0

    request = prepared.request
    villains_left = len(prepared.active_villains)
    primary = prepared.active_villain
    added_pressure = max(0.0, action.amount - request.to_call) / max(request.pot_size, request.big_blind)
    base = primary.profile.fold_to_raise

    style_adjustment = {
        OpponentStyle.UNKNOWN: 0.0,
        OpponentStyle.TIGHT_PASSIVE: 0.12,
        OpponentStyle.TAG: 0.04,
        OpponentStyle.LAG: -0.06,
        OpponentStyle.MANIAC: -0.10,
        OpponentStyle.CALLING_STATION: -0.18,
    }[primary.profile.style]

    sizing_tell_bonus = 0.0
    if primary.last_bet > 0:
        ratio = primary.last_bet / max(request.pot_size, request.big_blind)
        if ratio <= 0.45:
            sizing_tell_bonus += 0.08
        elif ratio >= 0.90:
            sizing_tell_bonus -= 0.06

    fold_equity = base + style_adjustment + sizing_tell_bonus + min(1.25, added_pressure) * 0.12
    fold_equity -= primary.profile.aggression * 0.08
    fold_equity -= primary.profile.bluff_frequency * 0.04
    fold_equity += clamp(nut_advantage, -0.2, 0.2) * 0.18
    fold_equity += max(0.0, equity - 0.58) * 0.08
    fold_equity /= 1.0 + max(0, villains_left - 1) * 0.55

    if action.amount >= prepared.effective_stack * 0.85:
        fold_equity -= 0.08

    return clamp(fold_equity, 0.02, 0.88)


def equity_realization(
    prepared: PreparedRequest,
    action: CandidateAction,
    equity: float,
    nut_advantage: float,
) -> float:
    realization = 0.86 if action.aggressive else 0.82
    if action.label == "check":
        realization += 0.06
    if prepared.spr <= 3.0 and equity >= 0.54:
        realization += 0.06
    if prepared.spr >= 7.0 and action.aggressive and equity < 0.52:
        realization -= 0.06
    realization += clamp(nut_advantage, -0.18, 0.18) * 0.22
    realization -= max(0, len(prepared.active_villains) - 1) * 0.04
    return clamp(realization, 0.62, 1.04)


def plan_bonus(
    prepared: PreparedRequest,
    action: CandidateAction,
    equity: float,
    nut_advantage: float,
) -> tuple[float, str]:
    pot = max(prepared.request.pot_size, prepared.request.big_blind)

    if action.aggressive and prepared.spr <= 2.5 and equity >= 0.54:
        return pot * 0.12, "Low SPR makes later-street commitment straightforward."
    if action.aggressive and prepared.spr >= 7.0 and equity < 0.50 and nut_advantage < 0:
        return -pot * 0.10, "High SPR makes future barrels awkward without a nut edge."
    if action.label in {"check", "call"} and prepared.spr >= 6.0 and 0.36 <= equity <= 0.57:
        return pot * 0.05, "Keeping the pot under control preserves flexibility for turn and river."
    if action.aggressive and nut_advantage > 0.12:
        return pot * 0.06, "Nut advantage supports a cleaner multi-street value plan."
    return 0.0, "No strong multi-street planning edge either way."


def score_action(
    prepared: PreparedRequest,
    action: CandidateAction,
    equity: float,
    nut_advantage: float,
) -> ActionScore:
    request = prepared.request
    pot = request.pot_size
    to_call = request.to_call
    effective_stack = max(1.0, prepared.effective_stack)

    if action.label == "fold":
        return ActionScore(
            action=action.label,
            amount=0.0,
            ev=0.0,
            fold_equity=0.0,
            notes="Stops the loss immediately when the price and future SPR both look bad.",
        )

    realization = equity_realization(prepared, action, equity, nut_advantage)
    plan_ev, plan_note = plan_bonus(prepared, action, equity, nut_advantage)

    if action.label in {"check", "call"}:
        amount = action.amount
        final_pot = pot + amount
        ev = realization * equity * final_pot - amount
        if len(prepared.active_villains) > 1 and action.label == "call":
            ev -= pot * 0.04 * (len(prepared.active_villains) - 1)
        note = "Profits if raw equity and realization beat the current price."
        if action.label == "check":
            note = "Keeps the pot manageable and realizes equity for free."
        return ActionScore(
            action=action.label,
            amount=amount,
            ev=round(ev + plan_ev, 3),
            fold_equity=0.0,
            notes=f"{note} {plan_note}",
        )

    fold_equity = estimate_fold_equity(prepared, action, equity, nut_advantage)
    expected_callers = 1.0 + max(0, len(prepared.active_villains) - 1) * 0.30
    called_pot = pot + action.amount + max(0.0, action.amount - to_call) * expected_callers
    called_ev = realization * equity * called_pot - action.amount
    ev = fold_equity * pot + (1.0 - fold_equity) * called_ev + plan_ev
    ev += clamp(nut_advantage, -0.2, 0.2) * pot * 0.10

    stack_commitment = action.amount / effective_stack
    if prepared.spr >= 5.5 and stack_commitment >= 0.65 and equity < 0.56:
        ev -= pot * 0.14
    elif prepared.spr <= 2.5 and equity >= 0.58 and stack_commitment >= 0.55:
        ev += pot * 0.06

    if equity >= 0.62:
        note = "Strong value line that also denies equity."
    elif fold_equity >= 0.42:
        note = "Leans on fold equity more than showdown strength."
    else:
        note = "Semi-bluff style pressure line."

    return ActionScore(
        action=action.label,
        amount=action.amount,
        ev=round(ev, 3),
        fold_equity=round(fold_equity, 3),
        notes=f"{note} {plan_note}",
    )


def build_reasoning(
    prepared: PreparedRequest,
    hero_equity: float,
    best_action: ActionScore,
    range_summary: str,
    nut_advantage: float,
    bucket_hit: bool,
) -> list[str]:
    request = prepared.request
    break_even = request.to_call / (request.pot_size + request.to_call) if request.to_call else 0.0
    reasons = [
        f"Estimated equity is {hero_equity:.1%}; break-even on a call is {break_even:.1%}.",
        board_texture(request.board_cards),
        range_summary,
        f"SPR is {prepared.spr:.2f}, so the stack geometry {'favors commitment' if prepared.spr <= 3 else 'keeps more streets in play'}.",
        f"Nut advantage is {nut_advantage:+.1%}, which {'supports aggression' if nut_advantage > 0 else 'argues for restraint'} on this texture.",
    ]

    if best_action.action in {"call", "check"}:
        reasons.append("The passive line wins on equity realization and avoids building an awkward future tree.")
    elif best_action.fold_equity >= 0.40:
        reasons.append("The aggressive line works because the sizing should still fold out a meaningful slice of weaker holdings.")
    else:
        reasons.append("The aggressive line is mostly a value or protection raise rather than a pure bluff.")

    if bucket_hit:
        reasons.append("An equity bucket cache entry was reused, then refined with the current exact spot data.")
    if request.notes:
        reasons.append(f"Table note considered: {request.notes.strip()}.")
    reasons.append(prepared.session_summary)
    return reasons


class HeuristicDecisionEngine:
    """Session-aware no-limit heuristic engine with cached multi-villain equity estimation."""

    def __init__(self, store: GameStore | None = None) -> None:
        self.store = store
        self.exact_equity_cache = LruCache(256)
        self.bucket_equity_cache = LruCache(512)

    def solve(
        self,
        request: DecisionRequest,
        availability: OpenSpielAvailability,
    ) -> DecisionResponse:
        started = time.perf_counter()
        prepared = self._prepare_request(request)

        if request.backend.value in {"open_spiel", "auto"} and availability.available:
            if len(prepared.active_villains) == 1:
                try:
                    from app.engines.openspiel_adapter import OpenSpielDecisionEngine

                    os_engine = OpenSpielDecisionEngine()
                    os_result = os_engine.solve(request)
                    if os_result:
                        elapsed_ms = (time.perf_counter() - started) * 1000.0
                        response = DecisionResponse(
                            game_id=prepared.game_id,
                            street=prepared.street,
                            recommended_action=os_result["action"],
                            recommended_amount=os_result.get("amount", 0),
                            confidence=os_result.get("confidence", 0.5),
                            hero_equity=0.0,
                            pot_odds=0.0,
                            break_even_equity=0.0,
                            spr=round(prepared.spr, 3),
                            nut_advantage=0.0,
                            equity_bucket_hit=False,
                            hand_summary=evaluate_current_hand(request.hero_cards, request.board_cards),
                            board_summary=board_texture(request.board_cards),
                            opponent_summary="OpenSpiel CFR solver used.",
                            session_summary=prepared.session_summary,
                            reasoning=["Decision made via OpenSpiel MCCFR solver."],
                            action_scores=[],
                            villain_snapshots=list(prepared.villain_snapshots),
                            simulation_iterations=os_result.get("iterations", 0),
                            elapsed_ms=round(elapsed_ms, 1),
                            backend=BackendStatus(
                                requested=request.backend.value,
                                selected="open_spiel",
                                openspiel_available=True,
                                details="Used OpenSpiel CFR solver.",
                            ),
                        )
                        self._record(prepared.game_id, request, response)
                        return response
                except Exception as exc:
                    print(
                        f"[Decision] OpenSpiel exception: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    "[Decision] OpenSpiel requested but multi-villain spots still use the heuristic engine.",
                    file=sys.stderr,
                )

        equity_result = self._estimate_equity(prepared)
        pot_odds = (
            request.to_call / (request.pot_size + request.to_call)
            if request.to_call > 0
            else 0.0
        )
        scores = [
            score_action(prepared, action, equity_result.equity, equity_result.nut_advantage)
            for action in candidate_actions(prepared)
        ]
        scores.sort(key=lambda item: item.ev, reverse=True)
        best_action = scores[0]
        second_best = scores[1] if len(scores) > 1 else scores[0]

        confidence = clamp(
            0.48
            + min(0.22, max(0.0, best_action.ev - second_best.ev) / max(request.pot_size, 1.0))
            + min(0.12, equity_result.iterations / 25000.0 * 0.12)
            + min(0.08, abs(equity_result.nut_advantage) * 0.16),
            0.36,
            0.93,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if request.backend.value == "open_spiel" and not availability.available:
            backend_prefix = "OpenSpiel was requested, but the app fell back to the local heuristic engine. "
        elif request.backend.value == "open_spiel":
            backend_prefix = "OpenSpiel is limited to heads-up spots, so this hand used the heuristic engine. "
        elif request.backend.value == "auto":
            backend_prefix = "Auto mode selected the local heuristic engine. "
        else:
            backend_prefix = "Using the local heuristic engine. "

        backend_details = backend_prefix + availability.details + " " + availability.suggested_setup
        response = DecisionResponse(
            game_id=prepared.game_id,
            street=prepared.street,
            recommended_action=best_action.action,
            recommended_amount=round(best_action.amount, 2),
            confidence=round(confidence, 3),
            hero_equity=round(equity_result.equity, 3),
            pot_odds=round(pot_odds, 3),
            break_even_equity=round(pot_odds, 3),
            spr=round(prepared.spr, 3),
            nut_advantage=round(equity_result.nut_advantage, 3),
            equity_bucket_hit=equity_result.bucket_hit,
            hand_summary=evaluate_current_hand(request.hero_cards, request.board_cards),
            board_summary=board_texture(request.board_cards),
            opponent_summary=equity_result.range_summary,
            session_summary=prepared.session_summary,
            reasoning=build_reasoning(
                prepared,
                equity_result.equity,
                best_action,
                equity_result.range_summary,
                equity_result.nut_advantage,
                equity_result.bucket_hit,
            ),
            action_scores=scores,
            villain_snapshots=list(prepared.villain_snapshots),
            simulation_iterations=equity_result.iterations,
            elapsed_ms=round(elapsed_ms, 1),
            backend=BackendStatus(
                requested=request.backend.value,
                selected="heuristic",
                openspiel_available=availability.available,
                details=backend_details,
            ),
        )
        self._record(prepared.game_id, request, response)
        return response

    def _record(self, game_id: str, request: DecisionRequest, response: DecisionResponse) -> None:
        if not self.store:
            return
        self.store.record_request(game_id, request)
        self.store.record_decision(game_id, request, response)

    def _prepare_request(self, request: DecisionRequest) -> PreparedRequest:
        game_id = request.game_id or (
            self.store.ensure_active_game(len(request.villains), [villain.display_name() for villain in request.villains])
            if self.store
            else "ad_hoc"
        )

        resolved_villains: list[ResolvedVillain] = []
        snapshots: list[VillainSnapshot] = []
        for villain in request.villains:
            if self.store:
                derived = self.store.derive_profile(game_id, villain)
                profile = merge_profiles(villain.profile, derived.profile, derived.hands_observed)
                snapshots.append(self.store.villain_snapshot(game_id, villain))
                hands_observed = derived.hands_observed
                average_bet_size = derived.average_bet_size
            else:
                profile = villain.profile
                snapshots.append(
                    VillainSnapshot(
                        seat=villain.seat,
                        name=villain.display_name(),
                        in_hand=villain.in_hand,
                        stack=villain.stack,
                        style=profile.style,
                        aggression=profile.aggression,
                        bluff_frequency=profile.bluff_frequency,
                        fold_to_raise=profile.fold_to_raise,
                        hands_observed=0,
                        average_bet_size=0.0,
                    )
                )
                hands_observed = 0
                average_bet_size = 0.0

            resolved_villains.append(
                ResolvedVillain(
                    seat=villain.seat,
                    name=villain.display_name(),
                    stack=villain.stack,
                    in_hand=villain.in_hand,
                    is_aggressor=villain.is_aggressor,
                    last_action=villain.last_action,
                    last_bet=villain.last_bet,
                    profile=profile,
                    hands_observed=hands_observed,
                    average_bet_size=average_bet_size,
                )
            )

        active_villains = tuple(villain for villain in resolved_villains if villain.in_hand)
        active_villain = next(
            villain for villain in active_villains if villain.seat == request.active_villain_seat
        )
        effective_stack = min(request.hero_stack, active_villain.stack)
        spr = effective_stack / max(request.pot_size, request.big_blind)
        session_summary = self.store.session_summary(game_id) if self.store else "Session tracking disabled."

        return PreparedRequest(
            request=request,
            game_id=game_id,
            street=request.street(),
            villains=tuple(resolved_villains),
            active_villains=active_villains,
            active_villain=active_villain,
            effective_stack=effective_stack,
            spr=spr,
            session_summary=session_summary,
            villain_snapshots=tuple(snapshots),
        )

    def _estimate_equity(self, prepared: PreparedRequest) -> EquityResult:
        exact_key = self._exact_cache_key(prepared)
        cached_exact = self.exact_equity_cache.get(exact_key)
        if isinstance(cached_exact, EquityResult):
            return EquityResult(
                equity=cached_exact.equity,
                iterations=cached_exact.iterations,
                range_summary=cached_exact.range_summary,
                nut_advantage=cached_exact.nut_advantage,
                bucket_hit=True,
            )

        bucket_key = self._bucket_cache_key(prepared)
        cached_bucket = self.bucket_equity_cache.get(bucket_key)
        bucket_hit = isinstance(cached_bucket, EquityResult)

        range_analyses = self._build_range_analyses(prepared)
        hero_cards = prepared.request.hero_cards
        board_cards = prepared.request.board_cards
        hero_combo = (hero_cards[0], hero_cards[1])
        hero_made = current_made_strength(hero_combo, board_cards)
        hero_draw, _ = draw_profile(hero_cards, board_cards)
        hero_nut_score = clamp(max(hero_made, hero_draw * 0.92) + blocker_bonus(hero_cards, board_cards), 0.0, 1.0)
        villain_nut_share = (
            sum(analysis.nut_share for analysis in range_analyses) / max(len(range_analyses), 1)
        )
        nut_advantage = clamp(hero_nut_score - villain_nut_share, -1.0, 1.0)
        range_summary = " ".join(analysis.summary for analysis in range_analyses)

        if bucket_hit:
            base_equity = cached_bucket.equity
            nut_advantage = clamp((nut_advantage + cached_bucket.nut_advantage) / 2.0, -1.0, 1.0)
        else:
            base_equity = 0.50

        equity, iterations = self._simulate_equity(prepared, range_analyses, base_equity)
        result = EquityResult(
            equity=equity,
            iterations=iterations,
            range_summary=range_summary,
            nut_advantage=nut_advantage,
            bucket_hit=bucket_hit,
        )
        self.exact_equity_cache.put(exact_key, result)
        self.bucket_equity_cache.put(bucket_key, result)
        return result

    def _build_range_analyses(self, prepared: PreparedRequest) -> list[RangeAnalysis]:
        excluded = set(prepared.request.hero_cards + prepared.request.board_cards)
        combos = tuple(combo for combo in combinations(ALL_CARDS, 2) if not excluded.intersection(combo))
        analyses: list[RangeAnalysis] = []

        for villain in prepared.active_villains:
            weights = [combo_weight(combo, prepared, villain) for combo in combos]
            running_total = 0.0
            cumulative: list[float] = []
            nut_mass = 0.0
            draw_mass = 0.0
            total_weight = 0.0

            for combo, weight in zip(combos, weights):
                running_total += weight
                cumulative.append(running_total)
                total_weight += weight
                made = current_made_strength(combo, prepared.request.board_cards)
                draw_score_value, _ = draw_profile(list(combo), prepared.request.board_cards)
                if made >= 0.88 or draw_score_value >= 0.48:
                    nut_mass += weight
                if draw_score_value >= 0.28:
                    draw_mass += weight

            analysis = RangeAnalysis(
                villain=villain,
                combos=combos,
                weights=tuple(weights),
                cumulative=tuple(cumulative),
                total_weight=running_total,
                summary="",
                nut_share=nut_mass / total_weight if total_weight else 0.0,
                draw_share=draw_mass / total_weight if total_weight else 0.0,
            )
            summary = summarize_range(analysis, prepared.request.board_cards)
            analyses.append(
                RangeAnalysis(
                    villain=villain,
                    combos=analysis.combos,
                    weights=analysis.weights,
                    cumulative=analysis.cumulative,
                    total_weight=analysis.total_weight,
                    summary=summary,
                    nut_share=analysis.nut_share,
                    draw_share=analysis.draw_share,
                )
            )

        return analyses

    def _simulate_equity(
        self,
        prepared: PreparedRequest,
        range_analyses: list[RangeAnalysis],
        base_equity: float,
    ) -> tuple[float, int]:
        rng = random.Random()
        request = prepared.request
        board_cards_needed = 5 - len(request.board_cards)
        board_base = [TREYS_INT_BY_CARD[card] for card in request.board_cards]
        hero_ints = [TREYS_INT_BY_CARD[card] for card in request.hero_cards]
        blocked = set(request.hero_cards + request.board_cards)

        time_budget = request.max_seconds * 0.70
        max_iterations = max(1000, min(24000, int(request.max_seconds * 3200 / max(len(range_analyses), 1))))
        min_iterations = 400 if board_cards_needed <= 1 else 700
        start = time.perf_counter()
        wins = base_equity * 120.0
        iterations = 120
        sum_squares = (base_equity**2) * 120.0

        while iterations < max_iterations and (time.perf_counter() - start) < time_budget:
            sampled_combos = self._sample_villain_combos(range_analyses, blocked, rng)
            if sampled_combos is None:
                break

            remaining_cards = [card for card in ALL_CARDS if card not in blocked and card not in sampled_combos[1]]
            score = self._street_aware_showdown(
                prepared,
                board_base,
                hero_ints,
                sampled_combos[0],
                remaining_cards,
                board_cards_needed,
                rng,
            )
            wins += score
            sum_squares += score * score
            iterations += 1

            if iterations >= min_iterations:
                mean = wins / iterations
                variance = max(0.0001, sum_squares / iterations - mean * mean)
                stderr = math.sqrt(variance / iterations)
                if mean >= 0.85 and stderr <= 0.022:
                    break
                if mean <= 0.15 and stderr <= 0.022:
                    break

        return clamp(wins / max(iterations, 1), 0.0, 1.0), iterations

    def _sample_villain_combos(
        self,
        range_analyses: list[RangeAnalysis],
        blocked: set[str],
        rng: random.Random,
    ) -> tuple[list[list[int]], set[str]] | None:
        used_cards: set[str] = set()
        villain_ints_list: list[list[int]] = []

        for analysis in range_analyses:
            combo = self._sample_combo_from_range(analysis, blocked | used_cards, rng)
            if combo is None:
                return None
            used_cards.update(combo)
            villain_ints_list.append([TREYS_INT_BY_CARD[combo[0]], TREYS_INT_BY_CARD[combo[1]]])

        return villain_ints_list, used_cards

    def _sample_combo_from_range(
        self,
        analysis: RangeAnalysis,
        blocked: set[str],
        rng: random.Random,
    ) -> tuple[str, str] | None:
        for _ in range(20):
            if analysis.total_weight <= 0:
                break
            pick = rng.random() * analysis.total_weight
            index = self._bisect_left(analysis.cumulative, pick)
            combo = analysis.combos[index]
            if combo[0] not in blocked and combo[1] not in blocked:
                return combo

        valid: list[tuple[tuple[str, str], float]] = []
        total = 0.0
        for combo, weight in zip(analysis.combos, analysis.weights):
            if combo[0] in blocked or combo[1] in blocked:
                continue
            valid.append((combo, weight))
            total += weight

        if not valid or total <= 0:
            return None

        pick = rng.random() * total
        running = 0.0
        for combo, weight in valid:
            running += weight
            if running >= pick:
                return combo
        return valid[-1][0]

    def _street_aware_showdown(
        self,
        prepared: PreparedRequest,
        board_base: list[int],
        hero_ints: list[int],
        villain_ints_list: list[list[int]],
        remaining_cards: list[str],
        board_cards_needed: int,
        rng: random.Random,
    ) -> float:
        if board_cards_needed == 0:
            return self._showdown_value(board_base, hero_ints, villain_ints_list)

        if board_cards_needed == 1:
            total = 0.0
            for river_card in remaining_cards:
                full_board = board_base + [TREYS_INT_BY_CARD[river_card]]
                total += self._showdown_value(full_board, hero_ints, villain_ints_list)
            return total / max(len(remaining_cards), 1)

        if board_cards_needed == 2 and prepared.street == Street.FLOP and prepared.request.max_seconds >= 4:
            turn_card = self._draw_weighted_next_card(
                prepared.request.hero_cards,
                prepared.request.board_cards,
                remaining_cards,
                rng,
            )
            turn_remaining = [card for card in remaining_cards if card != turn_card]
            total = 0.0
            for river_card in turn_remaining:
                full_board = board_base + [TREYS_INT_BY_CARD[turn_card], TREYS_INT_BY_CARD[river_card]]
                total += self._showdown_value(full_board, hero_ints, villain_ints_list)
            return total / max(len(turn_remaining), 1)

        sampled_runout = self._sample_street_runout(prepared.request.hero_cards, prepared.request.board_cards, remaining_cards, board_cards_needed, rng)
        full_board = board_base + [TREYS_INT_BY_CARD[card] for card in sampled_runout]
        return self._showdown_value(full_board, hero_ints, villain_ints_list)

    def _sample_street_runout(
        self,
        hero_cards: list[str],
        board_cards: list[str],
        remaining_cards: list[str],
        cards_needed: int,
        rng: random.Random,
    ) -> list[str]:
        available = list(remaining_cards)
        board = list(board_cards)
        runout: list[str] = []

        for _ in range(cards_needed):
            next_card = self._draw_weighted_next_card(hero_cards, board, available, rng)
            runout.append(next_card)
            board.append(next_card)
            available.remove(next_card)

        return runout

    def _draw_weighted_next_card(
        self,
        hero_cards: list[str],
        board_cards: list[str],
        available_cards: list[str],
        rng: random.Random,
    ) -> str:
        suits = Counter(card_suit(card) for card in board_cards)
        dominant_suit = suits.most_common(1)[0][0] if suits else None
        hero_suits = Counter(card_suit(card) for card in hero_cards)
        values = {card_value(card) for card in hero_cards + board_cards}
        if 14 in values:
            values.add(1)

        weighted_cards: list[tuple[str, float]] = []
        total_weight = 0.0
        for card in available_cards:
            weight = 1.0
            if dominant_suit and suits[dominant_suit] >= 2 and card_suit(card) == dominant_suit:
                weight *= 0.94 if hero_suits[dominant_suit] else 1.05
            trial_values = set(values)
            trial_values.add(card_value(card))
            if card_value(card) == 14:
                trial_values.add(1)
            straight_hits = max(len(window & trial_values) for window in STRAIGHT_WINDOWS)
            if straight_hits >= 4:
                weight *= 0.97 if any(card_value(hero) == card_value(card) for hero in hero_cards) else 1.03
            weighted_cards.append((card, weight))
            total_weight += weight

        pick = rng.random() * total_weight
        running = 0.0
        for card, weight in weighted_cards:
            running += weight
            if running >= pick:
                return card
        return weighted_cards[-1][0]

    @staticmethod
    def _showdown_value(
        full_board: list[int],
        hero_ints: list[int],
        villain_ints_list: list[list[int]],
    ) -> float:
        hero_score = EVALUATOR.evaluate(full_board, hero_ints)
        best_villain = min(EVALUATOR.evaluate(full_board, villain_ints) for villain_ints in villain_ints_list)
        if hero_score < best_villain:
            return 1.0
        if hero_score > best_villain:
            return 0.0
        ties = sum(
            1
            for villain_ints in villain_ints_list
            if EVALUATOR.evaluate(full_board, villain_ints) == hero_score
        )
        return 1.0 / (ties + 1)

    @staticmethod
    def _bisect_left(values: tuple[float, ...], target: float) -> int:
        lower = 0
        upper = len(values)
        while lower < upper:
            middle = (lower + upper) // 2
            if values[middle] < target:
                lower = middle + 1
            else:
                upper = middle
        return min(lower, len(values) - 1)

    def _exact_cache_key(self, prepared: PreparedRequest) -> tuple[object, ...]:
        villain_key = tuple(
            (
                villain.seat,
                round(villain.stack, 2),
                villain.last_action.value,
                round(villain.last_bet, 2),
                villain.profile.style.value,
                round(villain.profile.aggression, 2),
                round(villain.profile.bluff_frequency, 2),
                round(villain.profile.fold_to_raise, 2),
                villain.in_hand,
            )
            for villain in prepared.active_villains
        )
        history_key = tuple(
            (
                action.street.value,
                action.actor.lower(),
                action.action.value,
                round(action.amount, 2),
                round(action.pot_size, 2),
            )
            for action in prepared.request.action_history[-12:]
        )
        return (
            tuple(prepared.request.hero_cards),
            tuple(prepared.request.board_cards),
            round(prepared.request.pot_size, 2),
            round(prepared.request.to_call, 2),
            round(prepared.request.hero_stack, 2),
            round(prepared.request.big_blind, 2),
            prepared.street.value,
            villain_key,
            history_key,
        )

    def _bucket_cache_key(self, prepared: PreparedRequest) -> tuple[object, ...]:
        villain_key = tuple(
            sorted(
                (
                    villain.profile.style.value,
                    villain.last_action.value,
                    "s" if villain.last_bet / max(prepared.request.pot_size, prepared.request.big_blind) <= 0.45 else "l" if villain.last_bet / max(prepared.request.pot_size, prepared.request.big_blind) >= 0.90 else "m",
                )
                for villain in prepared.active_villains
            )
        )
        return (
            hand_bucket_signature(prepared.request.hero_cards),
            board_texture_key(prepared.request.board_cards),
            len(prepared.active_villains),
            villain_key,
            "low" if prepared.spr <= 3 else "mid" if prepared.spr <= 7 else "high",
            round(prepared.request.to_call / max(prepared.request.pot_size, prepared.request.big_blind), 1),
        )
