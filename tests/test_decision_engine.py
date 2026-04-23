from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.runtime import bootstrap_local_packages

bootstrap_local_packages()

from app.engines.decision import HeuristicDecisionEngine
from app.engines.openspiel_adapter import OpenSpielAvailability
from app.models import (
    DecisionRequest,
    NewGameRequest,
    OpponentAction,
    OpponentProfile,
    ResetGameRequest,
    VillainState,
)
from app.services.game_store import GameStore


class DecisionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(__file__).resolve().parents[1] / ".tmp-tests"
        self.temp_root.mkdir(exist_ok=True)
        self.db_path = self.temp_root / f"pokerbot-test-{uuid.uuid4().hex}.db"
        self.store = GameStore(self.db_path)
        self.game = self.store.create_game(
            NewGameRequest(label="Unit Test", villain_count=3, villain_names=["Seat 1", "Seat 2", "Seat 3"])
        )
        self.engine = HeuristicDecisionEngine(self.store)
        self.availability = OpenSpielAvailability(
            available=False,
            details="OpenSpiel disabled for tests.",
            suggested_setup="No setup required.",
        )

    def tearDown(self) -> None:
        try:
            if self.db_path.exists():
                self.db_path.unlink()
        except PermissionError:
            pass
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_multi_villain_decision_populates_session_fields(self) -> None:
        request = DecisionRequest(
            game_id=self.game.current_game.game_id,
            hero_cards=["Ah", "Kh"],
            board_cards=["Qh", "Jh", "4c"],
            pot_size=18,
            to_call=6,
            hero_stack=84,
            big_blind=2,
            max_seconds=2,
            villains=[
                VillainState(
                    seat=1,
                    name="Seat 1",
                    stack=92,
                    in_hand=True,
                    is_aggressor=True,
                    last_action=OpponentAction.BET,
                    last_bet=6,
                    profile=OpponentProfile(style="tag", aggression=0.62, bluff_frequency=0.34, fold_to_raise=0.46),
                ),
                VillainState(
                    seat=2,
                    name="Seat 2",
                    stack=76,
                    in_hand=True,
                    is_aggressor=False,
                    last_action=OpponentAction.CALL,
                    last_bet=6,
                ),
                VillainState(
                    seat=3,
                    name="Seat 3",
                    stack=110,
                    in_hand=False,
                    is_aggressor=False,
                    last_action=OpponentAction.FOLD,
                    last_bet=0,
                ),
            ],
        )

        response = self.engine.solve(request, self.availability)
        self.assertEqual(response.game_id, self.game.current_game.game_id)
        self.assertEqual(response.street.value, "flop")
        self.assertGreaterEqual(response.hero_equity, 0.0)
        self.assertGreater(response.simulation_iterations, 0)
        self.assertEqual(len(response.villain_snapshots), 3)
        self.assertIn("Unit Test", response.session_summary)

    def test_request_legacy_single_villain_still_validates(self) -> None:
        request = DecisionRequest(
            hero_cards=["Ah", "Ad"],
            board_cards=[],
            pot_size=3,
            to_call=1,
            hero_stack=100,
            villain_stack=100,
            big_blind=1,
            max_seconds=2,
        )

        self.assertEqual(len(request.villains), 1)
        self.assertEqual(request.active_villain().seat, 1)

    def test_reset_game_creates_fresh_game(self) -> None:
        reset = self.store.reset_game(ResetGameRequest(game_id=self.game.current_game.game_id))

        self.assertNotEqual(reset.current_game.game_id, self.game.current_game.game_id)
        self.assertEqual(reset.current_game.villain_count, self.game.current_game.villain_count)


if __name__ == "__main__":
    unittest.main()
