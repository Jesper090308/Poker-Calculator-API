from __future__ import annotations

from app.runtime import bootstrap_local_packages, resource_root

bootstrap_local_packages()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.adapters.recognition import ScreenRecognitionAdapter
from app.engines.decision import HeuristicDecisionEngine
from app.engines.openspiel_adapter import detect_open_spiel, tuned_runtime_profile
from app.models import (
    DecisionRequest,
    DecisionResponse,
    GameStateResponse,
    NewGameRequest,
    ResetGameRequest,
)
from app.services.game_store import GameStore


ROOT = resource_root()
app = FastAPI(title="Pokerbot Workbench")
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))

game_store = GameStore()
recognition_adapter = ScreenRecognitionAdapter()
heuristic_engine = HeuristicDecisionEngine(game_store)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    availability = detect_open_spiel()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "openspiel_available": availability.available,
            "openspiel_details": availability.details,
            "runtime_profile": tuned_runtime_profile(),
            "game_state": game_store.get_state(),
            "recognition_status": recognition_adapter.status(),
        },
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    availability = detect_open_spiel()
    return {
        "status": "ok",
        "openspiel_available": availability.available,
        "openspiel_details": availability.details,
        "runtime_profile": tuned_runtime_profile(),
        "database": game_store.get_state(),
        "recognition": recognition_adapter.status().__dict__,
    }


@app.get("/api/game/current", response_model=GameStateResponse)
def current_game() -> GameStateResponse:
    return game_store.get_state()


@app.post("/api/game/new", response_model=GameStateResponse)
def new_game(request: NewGameRequest) -> GameStateResponse:
    return game_store.create_game(request)


@app.post("/api/game/reset", response_model=GameStateResponse)
def reset_game(request: ResetGameRequest) -> GameStateResponse:
    return game_store.reset_game(request)


@app.get("/api/recognition/status")
def recognition_status() -> dict[str, object]:
    return recognition_adapter.status().__dict__


@app.post("/api/decision", response_model=DecisionResponse)
def decision(request: DecisionRequest) -> DecisionResponse:
    availability = detect_open_spiel()
    return heuristic_engine.solve(request, availability)
