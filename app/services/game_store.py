from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models import (
    DecisionRequest,
    DecisionResponse,
    GameStateResponse,
    GameSummary,
    NewGameRequest,
    OpponentAction,
    OpponentProfile,
    OpponentStyle,
    ResetGameRequest,
    VillainSnapshot,
    VillainState,
)
from app.runtime import default_database_path


DEFAULT_VILLAIN_NAMES = tuple(f"Villain {seat}" for seat in range(1, 9))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DerivedVillainProfile:
    profile: OpponentProfile
    hands_observed: int
    average_bet_size: float


class GameStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self.ensure_active_game()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    archived_at TEXT,
                    villain_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS villains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    seat INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(game_id, seat)
                );

                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    villain_name TEXT NOT NULL,
                    seat INTEGER NOT NULL,
                    street TEXT NOT NULL,
                    action TEXT NOT NULL,
                    amount REAL NOT NULL,
                    pot_size REAL NOT NULL,
                    in_hand INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );
                """
            )

    def ensure_active_game(self, villain_count: int = 1, villain_names: list[str] | None = None) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'active_game_id'"
            ).fetchone()
            if row:
                return str(row["value"])

        current = self.create_game(
            NewGameRequest(villain_count=villain_count, villain_names=villain_names or [])
        )
        return current.current_game.game_id

    def _set_active_game(self, game_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES('active_game_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (game_id,),
            )

    def _villain_names(self, villain_count: int, explicit_names: list[str]) -> list[str]:
        names: list[str] = []
        for seat in range(1, villain_count + 1):
            provided = explicit_names[seat - 1] if seat - 1 < len(explicit_names) else ""
            names.append(provided or DEFAULT_VILLAIN_NAMES[seat - 1])
        return names

    def create_game(self, request: NewGameRequest) -> GameStateResponse:
        game_id = uuid.uuid4().hex[:12]
        created_at = utc_now()
        label = request.label or f"Game {created_at[:19].replace('T', ' ')}"
        villain_names = self._villain_names(request.villain_count, request.villain_names)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO games(game_id, label, created_at, archived_at, villain_count)
                VALUES(?, ?, ?, NULL, ?)
                """,
                (game_id, label, created_at, request.villain_count),
            )
            for seat, name in enumerate(villain_names, start=1):
                connection.execute(
                    "INSERT INTO villains(game_id, seat, name) VALUES(?, ?, ?)",
                    (game_id, seat, name),
                )

        self._set_active_game(game_id)
        return self.get_state(game_id)

    def reset_game(self, request: ResetGameRequest) -> GameStateResponse:
        target_game_id = request.game_id or self.ensure_active_game()
        prior = self.get_summary(target_game_id)
        villain_count = request.villain_count or prior.villain_count
        villain_names = request.villain_names or self.get_villain_names(target_game_id)

        with self._connect() as connection:
            connection.execute(
                "UPDATE games SET archived_at = ? WHERE game_id = ?",
                (utc_now(), target_game_id),
            )

        return self.create_game(
            NewGameRequest(
                label=f"{prior.label} reset",
                villain_count=villain_count,
                villain_names=villain_names,
            )
        )

    def get_villain_names(self, game_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM villains WHERE game_id = ? ORDER BY seat ASC",
                (game_id,),
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_recent_games(self, limit: int = 6) -> list[GameSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    games.game_id,
                    games.label,
                    games.created_at,
                    games.villain_count,
                    (
                        SELECT COUNT(*)
                        FROM observations
                        WHERE observations.game_id = games.game_id
                    ) AS hands_recorded,
                    (
                        SELECT COUNT(*)
                        FROM decisions
                        WHERE decisions.game_id = games.game_id
                    ) AS decisions_recorded
                FROM games
                ORDER BY games.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [GameSummary.model_validate(dict(row)) for row in rows]

    def get_summary(self, game_id: str) -> GameSummary:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    games.game_id,
                    games.label,
                    games.created_at,
                    games.villain_count,
                    (
                        SELECT COUNT(*)
                        FROM observations
                        WHERE observations.game_id = games.game_id
                    ) AS hands_recorded,
                    (
                        SELECT COUNT(*)
                        FROM decisions
                        WHERE decisions.game_id = games.game_id
                    ) AS decisions_recorded
                FROM games
                WHERE games.game_id = ?
                """,
                (game_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown game id: {game_id}")
        return GameSummary.model_validate(dict(row))

    def get_state(self, game_id: str | None = None) -> GameStateResponse:
        current_game_id = game_id or self.ensure_active_game()
        return GameStateResponse(
            database_path=str(self.db_path),
            current_game=self.get_summary(current_game_id),
            recent_games=self.list_recent_games(),
        )

    def upsert_villains(self, game_id: str, villains: list[VillainState]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE games SET villain_count = ? WHERE game_id = ?",
                (max(1, len(villains)), game_id),
            )
            for villain in villains:
                connection.execute(
                    """
                    INSERT INTO villains(game_id, seat, name)
                    VALUES(?, ?, ?)
                    ON CONFLICT(game_id, seat) DO UPDATE SET name = excluded.name
                    """,
                    (game_id, villain.seat, villain.display_name()),
                )

    def record_request(self, game_id: str, request: DecisionRequest) -> None:
        self.upsert_villains(game_id, request.villains)
        timestamp = utc_now()

        with self._connect() as connection:
            for villain in request.villains:
                connection.execute(
                    """
                    INSERT INTO observations(
                        game_id,
                        villain_name,
                        seat,
                        street,
                        action,
                        amount,
                        pot_size,
                        in_hand,
                        created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        game_id,
                        villain.display_name(),
                        villain.seat,
                        request.street().value,
                        villain.last_action.value,
                        villain.last_bet,
                        request.pot_size,
                        1 if villain.in_hand else 0,
                        timestamp,
                    ),
                )

            for action in request.action_history:
                connection.execute(
                    """
                    INSERT INTO observations(
                        game_id,
                        villain_name,
                        seat,
                        street,
                        action,
                        amount,
                        pot_size,
                        in_hand,
                        created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        game_id,
                        action.actor,
                        0,
                        action.street.value,
                        action.action.value,
                        action.amount,
                        action.pot_size,
                        1,
                        timestamp,
                    ),
                )

    def record_decision(
        self,
        game_id: str,
        request: DecisionRequest,
        response: DecisionResponse,
    ) -> None:
        payload_request = json.dumps(request.model_dump(mode="json"), sort_keys=True)
        payload_response = json.dumps(response.model_dump(mode="json"), sort_keys=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO decisions(game_id, created_at, request_json, response_json)
                VALUES(?, ?, ?, ?)
                """,
                (game_id, utc_now(), payload_request, payload_response),
            )

    def derive_profile(self, game_id: str, villain: VillainState) -> DerivedVillainProfile:
        with self._connect() as connection:
            current_rows = connection.execute(
                """
                SELECT action, amount, pot_size
                FROM observations
                WHERE game_id = ? AND seat = ?
                """,
                (game_id, villain.seat),
            ).fetchall()

            lifetime_rows = []
            if villain.name:
                lifetime_rows = connection.execute(
                    """
                    SELECT action, amount, pot_size
                    FROM observations
                    WHERE villain_name = ? AND game_id <> ?
                    ORDER BY created_at DESC
                    LIMIT 40
                    """,
                    (villain.display_name(), game_id),
                ).fetchall()

        rows = [*current_rows, *lifetime_rows]
        sample_size = len(rows)
        if sample_size == 0:
            return DerivedVillainProfile(
                profile=villain.profile,
                hands_observed=0,
                average_bet_size=0.0,
            )

        aggressive = 0
        passive = 0
        folds = 0
        bet_ratios: list[float] = []
        small_bets = 0
        large_bets = 0

        for row in rows:
            action = OpponentAction(str(row["action"]))
            amount = float(row["amount"])
            pot_size = max(float(row["pot_size"]), 1.0)

            if action in {OpponentAction.BET, OpponentAction.RAISE, OpponentAction.ALL_IN}:
                aggressive += 1
                ratio = amount / pot_size
                bet_ratios.append(ratio)
                if ratio <= 0.45:
                    small_bets += 1
                if ratio >= 0.9:
                    large_bets += 1
            elif action in {OpponentAction.CHECK, OpponentAction.CALL}:
                passive += 1
            elif action == OpponentAction.FOLD:
                folds += 1

        action_count = max(sample_size, 1)
        aggression_rate = aggressive / action_count
        passive_rate = passive / action_count
        fold_rate = folds / action_count
        average_bet_size = sum(bet_ratios) / len(bet_ratios) if bet_ratios else 0.0
        small_bet_rate = small_bets / max(len(bet_ratios), 1)
        large_bet_rate = large_bets / max(len(bet_ratios), 1)

        sample_weight = min(0.78, sample_size / 18.0)
        aggression = self._blend(
            villain.profile.aggression,
            0.18 + aggression_rate * 0.82,
            sample_weight,
        )
        bluff_frequency = self._blend(
            villain.profile.bluff_frequency,
            self._clamp(0.18 + small_bet_rate * 0.34 + aggression_rate * 0.14 - large_bet_rate * 0.16, 0.05, 0.88),
            sample_weight,
        )
        fold_to_raise = self._blend(
            villain.profile.fold_to_raise,
            self._clamp(0.18 + fold_rate * 0.55 - passive_rate * 0.08, 0.05, 0.9),
            sample_weight,
        )

        style = villain.profile.style
        if sample_size >= 5:
            if aggression >= 0.74 and average_bet_size >= 0.55:
                style = OpponentStyle.MANIAC
            elif aggression >= 0.61 and passive_rate <= 0.26:
                style = OpponentStyle.LAG
            elif passive_rate >= 0.45 and fold_rate <= 0.15:
                style = OpponentStyle.CALLING_STATION
            elif aggression >= 0.52 and fold_rate >= 0.16:
                style = OpponentStyle.TAG
            elif aggression <= 0.42 and passive_rate >= 0.35:
                style = OpponentStyle.TIGHT_PASSIVE
            else:
                style = OpponentStyle.UNKNOWN

        return DerivedVillainProfile(
            profile=OpponentProfile(
                style=style,
                aggression=self._clamp(aggression, 0.0, 1.0),
                bluff_frequency=self._clamp(bluff_frequency, 0.0, 1.0),
                fold_to_raise=self._clamp(fold_to_raise, 0.0, 1.0),
            ),
            hands_observed=sample_size,
            average_bet_size=round(average_bet_size, 3),
        )

    def villain_snapshot(self, game_id: str, villain: VillainState) -> VillainSnapshot:
        derived = self.derive_profile(game_id, villain)
        return VillainSnapshot(
            seat=villain.seat,
            name=villain.display_name(),
            in_hand=villain.in_hand,
            stack=villain.stack,
            style=derived.profile.style,
            aggression=round(derived.profile.aggression, 3),
            bluff_frequency=round(derived.profile.bluff_frequency, 3),
            fold_to_raise=round(derived.profile.fold_to_raise, 3),
            hands_observed=derived.hands_observed,
            average_bet_size=derived.average_bet_size,
        )

    def session_summary(self, game_id: str) -> str:
        summary = self.get_summary(game_id)
        return (
            f"{summary.label}: {summary.decisions_recorded} decisions recorded with "
            f"{summary.hands_recorded} villain observations across {summary.villain_count} seats."
        )

    @staticmethod
    def _blend(base: float, updated: float, weight: float) -> float:
        return base * (1.0 - weight) + updated * weight

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(value, upper))
