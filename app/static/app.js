const body = document.body;
const form = document.getElementById("decision-form");
const resultShell = document.getElementById("result-shell");
const statusLine = document.getElementById("status-line");
const demoButton = document.getElementById("demo-button");
const newGameButton = document.getElementById("new-game-button");
const resetGameButton = document.getElementById("reset-game-button");
const syncVillainsButton = document.getElementById("sync-villains-button");
const villainsShell = document.getElementById("villains-shell");
const villainSummary = document.getElementById("villain-summary");
const gameIdInput = document.getElementById("game-id");
const gameLabelInput = document.getElementById("game-label");
const villainCountInput = document.getElementById("villain-count");
const gameSummaryLine = document.getElementById("game-summary-line");
const gameIdLine = document.getElementById("game-id-line");
const gameDecisionsLine = document.getElementById("game-decisions-line");
const gameObservationsLine = document.getElementById("game-observations-line");
const submitButton = document.getElementById("submit-button");

let villainState = [];

function money(value) {
  return Number(value).toFixed(2);
}

function percent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function humanize(value) {
  return String(value ?? "").replace(/_/g, " ");
}

function revealResults() {
  document.querySelector(".result-panel")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function rawDetails(data) {
  return `<details class="summary-card raw-card"><summary>Raw response</summary><pre>${JSON.stringify(
    data,
    null,
    2
  )}</pre></details>`;
}

function cardValues(prefix, count) {
  return Array.from({ length: count }, (_, index) =>
    document.getElementById(`${prefix}-${index + 1}`).value.trim()
  ).filter(Boolean);
}

function parseNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function bigBlind() {
  return Math.max(0.1, parseNumber(document.getElementById("big-blind").value, 1));
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(value, upper));
}

function defaultVillain(index) {
  return {
    seat: index + 1,
    name: `Villain ${index + 1}`,
    stack: 100,
    in_hand: index === 0,
    is_aggressor: index === 0,
    last_action: index === 0 ? "bet" : "check",
    last_bet: index === 0 ? 6 : 0,
    style: "unknown",
    aggression: 0.5,
    bluff_frequency: 0.35,
    fold_to_raise: 0.42,
  };
}

function normalizeVillainState(count) {
  const next = [];
  for (let index = 0; index < count; index += 1) {
    next.push(villainState[index] || defaultVillain(index));
  }
  villainState = next;
  if (!villainState.some((villain) => villain.in_hand)) {
    villainState[0].in_hand = true;
  }
  if (!villainState.some((villain) => villain.is_aggressor && villain.in_hand)) {
    const firstActive = villainState.find((villain) => villain.in_hand);
    if (firstActive) {
      firstActive.is_aggressor = true;
    }
  }
}

function setAggressor(seat) {
  villainState = villainState.map((villain) => ({
    ...villain,
    is_aggressor: villain.seat === seat && villain.in_hand,
  }));
  renderVillains();
}

function renderVillains() {
  const count = clamp(parseNumber(villainCountInput.value, 1), 1, 8);
  villainCountInput.value = count;
  normalizeVillainState(count);

  villainsShell.innerHTML = villainState
    .map(
      (villain) => `
        <article class="villain-card ${villain.in_hand ? "active-seat" : ""}">
          <div class="villain-top">
            <div>
              <p class="seat-kicker">Seat ${villain.seat}</p>
              <input type="text" data-villain-field="name" data-seat="${villain.seat}" value="${villain.name}" />
            </div>
            <div class="toggle-row">
              <label class="toggle-pill">
                <input type="checkbox" data-villain-field="in_hand" data-seat="${villain.seat}" ${villain.in_hand ? "checked" : ""} />
                <span>In hand</span>
              </label>
              <label class="toggle-pill">
                <input type="radio" name="aggressor-seat" data-villain-field="is_aggressor" data-seat="${villain.seat}" ${villain.is_aggressor && villain.in_hand ? "checked" : ""} ${villain.in_hand ? "" : "disabled"} />
                <span>Acting villain</span>
              </label>
            </div>
          </div>

          <div class="villain-fields">
            <div class="field-group compact-group">
              <label>Stack</label>
              <div class="stepper">
                <button type="button" class="step-button villain-step" data-seat="${villain.seat}" data-field="stack" data-step="-5" data-unit="bb">-5bb</button>
                <input type="number" min="0" step="0.5" data-villain-field="stack" data-seat="${villain.seat}" value="${villain.stack}" />
                <button type="button" class="step-button villain-step" data-seat="${villain.seat}" data-field="stack" data-step="5" data-unit="bb">+5bb</button>
              </div>
            </div>

            <div class="field-group compact-group">
              <label>Last Action</label>
              <select data-villain-field="last_action" data-seat="${villain.seat}">
                ${["check", "call", "bet", "raise", "all_in", "fold"]
                  .map(
                    (action) =>
                      `<option value="${action}" ${villain.last_action === action ? "selected" : ""}>${action.replace("_", " ")}</option>`
                  )
                  .join("")}
              </select>
            </div>

            <div class="field-group compact-group">
              <label>Previous Bet</label>
              <div class="stepper">
                <button type="button" class="step-button villain-step" data-seat="${villain.seat}" data-field="last_bet" data-step="-1" data-unit="bb">-1bb</button>
                <input type="number" min="0" step="0.5" data-villain-field="last_bet" data-seat="${villain.seat}" value="${villain.last_bet}" />
                <button type="button" class="step-button villain-step" data-seat="${villain.seat}" data-field="last_bet" data-step="1" data-unit="bb">+1bb</button>
              </div>
            </div>
          </div>

          <details class="advanced-box">
            <summary>Advanced profile</summary>
            <div class="villain-fields">
              <div class="field-group compact-group">
                <label>Style</label>
                <select data-villain-field="style" data-seat="${villain.seat}">
                  ${[
                    "unknown",
                    "tight_passive",
                    "tag",
                    "lag",
                    "maniac",
                    "calling_station",
                  ]
                    .map(
                      (style) =>
                        `<option value="${style}" ${villain.style === style ? "selected" : ""}>${humanize(style)}</option>`
                    )
                    .join("")}
                </select>
              </div>
              <div class="field-group compact-group">
                <label>Aggression</label>
                <input type="number" min="0" max="1" step="0.01" data-villain-field="aggression" data-seat="${villain.seat}" value="${villain.aggression}" />
              </div>
              <div class="field-group compact-group">
                <label>Bluff Freq</label>
                <input type="number" min="0" max="1" step="0.01" data-villain-field="bluff_frequency" data-seat="${villain.seat}" value="${villain.bluff_frequency}" />
              </div>
              <div class="field-group compact-group">
                <label>Fold To Raise</label>
                <input type="number" min="0" max="1" step="0.01" data-villain-field="fold_to_raise" data-seat="${villain.seat}" value="${villain.fold_to_raise}" />
              </div>
            </div>
          </details>
        </article>
      `
    )
    .join("");

  const activeVillains = villainState.filter((villain) => villain.in_hand).length;
  villainSummary.textContent = `${activeVillains} active villain${activeVillains === 1 ? "" : "s"}`;
}

function readVillainsFromDom() {
  villainState = villainState.map((villain) => {
    const seat = villain.seat;
    const lookup = (field) =>
      document.querySelector(`[data-villain-field="${field}"][data-seat="${seat}"]`);

    const inHand = lookup("in_hand").checked;
    return {
      seat,
      name: lookup("name").value.trim() || `Villain ${seat}`,
      stack: parseNumber(lookup("stack").value, 0),
      in_hand: inHand,
      is_aggressor: inHand && lookup("is_aggressor").checked,
      last_action: lookup("last_action").value,
      last_bet: parseNumber(lookup("last_bet").value, 0),
      style: lookup("style").value,
      aggression: parseNumber(lookup("aggression").value, 0.5),
      bluff_frequency: parseNumber(lookup("bluff_frequency").value, 0.35),
      fold_to_raise: parseNumber(lookup("fold_to_raise").value, 0.42),
    };
  });

  if (!villainState.some((villain) => villain.in_hand)) {
    villainState[0].in_hand = true;
  }
  if (!villainState.some((villain) => villain.in_hand && villain.is_aggressor)) {
    const firstActive = villainState.find((villain) => villain.in_hand);
    if (firstActive) {
      firstActive.is_aggressor = true;
    }
  }
}

function payloadVillains() {
  readVillainsFromDom();
  return villainState.map((villain) => ({
    seat: villain.seat,
    name: villain.name,
    stack: villain.stack,
    in_hand: villain.in_hand,
    is_aggressor: villain.is_aggressor,
    last_action: villain.last_action,
    last_bet: villain.last_bet,
    profile: {
      style: villain.style,
      aggression: villain.aggression,
      bluff_frequency: villain.bluff_frequency,
      fold_to_raise: villain.fold_to_raise,
    },
  }));
}

function applyStep(targetId, rawStep, unit = "raw") {
  const input = document.getElementById(targetId);
  if (!input) {
    return;
  }
  const stepBase = unit === "bb" ? bigBlind() : 1;
  const next = parseNumber(input.value, 0) + parseNumber(rawStep, 0) * stepBase;
  const min = input.min !== "" ? Number(input.min) : Number.NEGATIVE_INFINITY;
  const max = input.max !== "" ? Number(input.max) : Number.POSITIVE_INFINITY;
  input.value = clamp(next, min, max);
}

function applyVillainStep(seat, field, rawStep, unit = "raw") {
  readVillainsFromDom();
  villainState = villainState.map((villain) => {
    if (villain.seat !== seat) {
      return villain;
    }
    const stepBase = unit === "bb" ? bigBlind() : 1;
    return {
      ...villain,
      [field]: clamp(parseNumber(villain[field], 0) + parseNumber(rawStep, 0) * stepBase, 0, 9999),
    };
  });
  renderVillains();
}

async function fetchCurrentGame() {
  const response = await fetch("/api/game/current");
  return response.json();
}

function applyGameState(data) {
  gameIdInput.value = data.current_game.game_id;
  villainCountInput.value = data.current_game.villain_count;
  if (gameSummaryLine) {
    gameSummaryLine.textContent = `${data.current_game.label} with ${data.current_game.villain_count} villain seats.`;
  }
  if (gameIdLine) {
    gameIdLine.textContent = `Game ID: ${data.current_game.game_id}`;
  }
  if (gameDecisionsLine) {
    gameDecisionsLine.textContent = `Decisions: ${data.current_game.decisions_recorded}`;
  }
  if (gameObservationsLine) {
    gameObservationsLine.textContent = `Observations: ${data.current_game.hands_recorded}`;
  }
  if (!gameLabelInput.value.trim()) {
    gameLabelInput.value = data.current_game.label;
  }

  const names = data.recent_games[0]?.game_id === data.current_game.game_id ? [] : [];
  villainState = Array.from({ length: data.current_game.villain_count }, (_, index) => ({
    ...(villainState[index] || defaultVillain(index)),
    name: villainState[index]?.name || `Villain ${index + 1}`,
  }));

  if (names.length) {
    villainState = villainState.map((villain, index) => ({ ...villain, name: names[index] || villain.name }));
  }
  renderVillains();
}

async function createGame(resetCurrent = false) {
  readVillainsFromDom();
  const payload = {
    label: gameLabelInput.value.trim() || null,
    villain_count: clamp(parseNumber(villainCountInput.value, 1), 1, 8),
    villain_names: villainState.map((villain) => villain.name),
  };

  const endpoint = resetCurrent ? "/api/game/reset" : "/api/game/new";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(resetCurrent ? { villain_count: payload.villain_count, villain_names: payload.villain_names } : payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.message || "Could not update game.");
  }
  applyGameState(data);
  statusLine.textContent = resetCurrent ? "Current game reset." : "New game started.";
}

function loadDemo() {
  document.getElementById("hero-1").value = "Ah";
  document.getElementById("hero-2").value = "Kh";
  document.getElementById("board-1").value = "Qh";
  document.getElementById("board-2").value = "Jh";
  document.getElementById("board-3").value = "4c";
  document.getElementById("board-4").value = "";
  document.getElementById("board-5").value = "";
  document.getElementById("pot-size").value = "18";
  document.getElementById("to-call").value = "6";
  document.getElementById("hero-stack").value = "84";
  document.getElementById("big-blind").value = "2";
  document.getElementById("max-seconds").value = "8";
  document.getElementById("backend").value = "heuristic";
  gameLabelInput.value = "Demo Spot";
  villainCountInput.value = "2";
  villainState = [
    {
      seat: 1,
      name: "Seat 1",
      stack: 92,
      in_hand: true,
      is_aggressor: true,
      last_action: "bet",
      last_bet: 6,
      style: "tag",
      aggression: 0.62,
      bluff_frequency: 0.34,
      fold_to_raise: 0.46,
    },
    {
      seat: 2,
      name: "Seat 2",
      stack: 76,
      in_hand: true,
      is_aggressor: false,
      last_action: "call",
      last_bet: 6,
      style: "calling_station",
      aggression: 0.38,
      bluff_frequency: 0.22,
      fold_to_raise: 0.28,
    },
  ];
  document.getElementById("notes").value =
    "Seat 1 likes one-third-pot probes; Seat 2 peels wide and overcalls too much.";
  renderVillains();
}

function renderResult(data) {
  const safeScores = Array.isArray(data.action_scores) ? data.action_scores : [];
  const safeReasoning = Array.isArray(data.reasoning) ? data.reasoning : [];
  const safeVillains = Array.isArray(data.villain_snapshots) ? data.villain_snapshots : [];

  const scoreRows = safeScores
    .map(
      (score, index) => `
        <div class="score-row ${index === 0 ? "best" : ""}">
          <div>
            <strong>${score.action}</strong>
            <div class="meta">Size: ${money(score.amount)} | Fold equity: ${percent(score.fold_equity)}</div>
            <div class="meta">${score.notes}</div>
          </div>
          <div>
            <div class="meta">EV</div>
            <strong>${money(score.ev)}</strong>
          </div>
          <div>
            <div class="meta">Rank</div>
            <strong>#${index + 1}</strong>
          </div>
        </div>
      `
    )
    .join("");

  const reasoning = safeReasoning.map((line) => `<li>${line}</li>`).join("");
  const villains = safeVillains
    .map(
      (villain) => `
        <div class="villain-read">
          <strong>${villain.name}</strong>
          <span>${humanize(villain.style)}</span>
          <span>Agg ${percent(villain.aggression)}</span>
          <span>Bluff ${percent(villain.bluff_frequency)}</span>
          <span>Fold vs raise ${percent(villain.fold_to_raise)}</span>
          <span>Samples ${villain.hands_observed}</span>
        </div>
      `
    )
    .join("");

  resultShell.classList.remove("empty");
  resultShell.innerHTML = `
    <div class="badge-row">
      <div class="badge">
        <span class="label">Recommended Action</span>
        <span class="value">${data.recommended_action}</span>
      </div>
      <div class="badge">
        <span class="label">Suggested Size</span>
        <span class="value">${money(data.recommended_amount)}</span>
      </div>
    </div>

    <div class="metric-grid">
      <div class="metric">
        <span class="small-copy">Equity</span>
        <strong>${percent(data.hero_equity)}</strong>
      </div>
      <div class="metric">
        <span class="small-copy">SPR</span>
        <strong>${Number(data.spr).toFixed(2)}</strong>
      </div>
      <div class="metric">
        <span class="small-copy">Nut Advantage</span>
        <strong>${percent(data.nut_advantage)}</strong>
      </div>
      <div class="metric">
        <span class="small-copy">Confidence</span>
        <strong>${percent(data.confidence)}</strong>
      </div>
      <div class="metric">
        <span class="small-copy">Compute Time</span>
        <strong>${data.elapsed_ms.toFixed(1)} ms</strong>
      </div>
      <div class="metric">
        <span class="small-copy">Cache</span>
        <strong>${data.equity_bucket_hit ? "Bucket hit" : "Fresh solve"}</strong>
      </div>
    </div>

    <div class="summary-card">
      <p><strong>Game:</strong> ${data.game_id} | <strong>Street:</strong> ${data.street}</p>
    </div>
    <div class="summary-card">
      <p><strong>Hand:</strong> ${data.hand_summary}</p>
    </div>
    <div class="summary-card">
      <p><strong>Board:</strong> ${data.board_summary}</p>
    </div>
    <div class="summary-card">
      <p><strong>Opponents:</strong> ${data.opponent_summary}</p>
    </div>
    <div class="summary-card">
      <p><strong>Session:</strong> ${data.session_summary}</p>
    </div>
    <div class="summary-card">
      <p><strong>Backend:</strong> ${data.backend.details}</p>
    </div>
    <div class="summary-card">
      <p><strong>Iterations:</strong> ${data.simulation_iterations} | <strong>Pot odds:</strong> ${percent(data.pot_odds)} | <strong>Break-even:</strong> ${percent(data.break_even_equity)}</p>
    </div>

    <div class="summary-card">
      <strong>Why this line</strong>
      <ul class="reason-list">${reasoning}</ul>
    </div>

    <div class="summary-card">
      <strong>Villain reads</strong>
      <div class="villain-read-grid">${villains}</div>
    </div>

    <div class="score-table">
      ${scoreRows}
    </div>

    ${rawDetails(data)}
  `;

  statusLine.textContent = `Used ${data.backend.selected} backend with ${data.simulation_iterations} simulations.`;
  gameIdInput.value = data.game_id;
  revealResults();
}

function safeRenderResult(data) {
  try {
    renderResult(data);
  } catch (error) {
    resultShell.classList.remove("empty");
    resultShell.innerHTML = `
      <div class="error-box">
        Rendering failed in the browser, so the raw decision response is shown instead.<br />
        ${error.message}
      </div>
      ${rawDetails(data)}
    `;
    statusLine.textContent = "Decision returned, but the rich renderer hit a browser-side issue.";
    revealResults();
  }
}

function renderError(message) {
  resultShell.classList.remove("empty");
  resultShell.innerHTML = `<div class="error-box">${message}</div>`;
  statusLine.textContent = "Input needs attention.";
  revealResults();
}

async function submitDecision(event) {
  event.preventDefault();
  statusLine.textContent = "Running simulation...";
  submitButton.disabled = true;
  submitButton.textContent = "Running...";
  resultShell.classList.add("empty");
  resultShell.innerHTML = `<p class="empty-copy">Crunching the spot...</p>`;
  revealResults();

  const villains = payloadVillains();
  const aggressor = villains.find((villain) => villain.is_aggressor && villain.in_hand) || villains.find((villain) => villain.in_hand);
  const payload = {
    game_id: gameIdInput.value || null,
    backend: document.getElementById("backend").value,
    hero_cards: cardValues("hero", 2),
    board_cards: cardValues("board", 5),
    pot_size: parseNumber(document.getElementById("pot-size").value, 0),
    to_call: parseNumber(document.getElementById("to-call").value, 0),
    hero_stack: parseNumber(document.getElementById("hero-stack").value, 0),
    big_blind: parseNumber(document.getElementById("big-blind").value, 1),
    max_seconds: parseNumber(document.getElementById("max-seconds").value, 8),
    active_villain_seat: aggressor ? aggressor.seat : 1,
    villains,
    notes: document.getElementById("notes").value.trim() || null,
  };

  try {
    const response = await fetch("/api/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || data.message || "Unknown error.";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    safeRenderResult(data);
  } catch (error) {
    renderError(error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Run Decision";
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".step-button");
  if (!button) {
    return;
  }
  if (button.classList.contains("villain-step")) {
    applyVillainStep(
      Number(button.dataset.seat),
      button.dataset.field,
      button.dataset.step,
      button.dataset.unit || "raw"
    );
    return;
  }
  applyStep(button.dataset.target, button.dataset.step, button.dataset.unit || "raw");
});

villainsShell.addEventListener("change", (event) => {
  const target = event.target;
  const seat = Number(target.dataset.seat);
  if (!seat) {
    return;
  }
  if (target.dataset.villainField === "is_aggressor") {
    setAggressor(seat);
    return;
  }
  readVillainsFromDom();
  renderVillains();
});

demoButton.addEventListener("click", loadDemo);
syncVillainsButton.addEventListener("click", () => {
  readVillainsFromDom();
  renderVillains();
});
newGameButton.addEventListener("click", async () => {
  try {
    await createGame(false);
  } catch (error) {
    renderError(error.message);
  }
});
resetGameButton.addEventListener("click", async () => {
  try {
    await createGame(true);
  } catch (error) {
    renderError(error.message);
  }
});
form.addEventListener("submit", submitDecision);

(async () => {
  villainState = Array.from(
    { length: clamp(parseNumber(body.dataset.currentVillainCount, 1), 1, 8) },
    (_, index) => defaultVillain(index)
  );
  renderVillains();

  try {
    const state = await fetchCurrentGame();
    applyGameState(state);
  } catch (error) {
    statusLine.textContent = "Loaded with local defaults.";
  }
})();
