from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .hardware import (
    GpioZeroResetOutput,
    InputSource,
    Mcp23017InputSource,
    ResetOutput,
    WinnerInputPoller,
)
from .keypad import EvdevNumericKeypad, KeypadCommand, KeypadSource
from .match import MatchController
from .score_display import build_score_display
from .sheets import GoogleDriveSheetsSync, load_google_drive_config
from .storage import Database
from .subject_infer import infer_subjects_from_pdf
from .cloud import GoogleBridge, save_bridge_config, CONFIG_PATH
from .jobs import BackgroundJobs


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Science Bowl Buzzer Logger</title>
  <style>
    :root {
      --ink: #172026;
      --muted: #5d6975;
      --line: #ccd5dd;
      --panel: #f7f9fb;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b42318;
      --good: #1f7a4d;
      --blue: #2563eb;
      --bg: #eef3f7;
      font-family: Arial, Helvetica, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
    }
    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px;
    }
    header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      align-items: center;
      margin-bottom: 14px;
    }
    h1 {
      font-size: 24px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }
    .subtle { color: var(--muted); font-size: 13px; }
    .layout {
      display: grid;
      grid-template-columns: minmax(320px, 1fr) minmax(280px, 380px);
      gap: 14px;
    }
    section, .toolbar {
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    section + section { margin-top: 14px; }
    h2 {
      font-size: 15px;
      margin: 0 0 12px;
      letter-spacing: 0;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-height: 68px;
    }
    .metric .label {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .metric .value {
      font-size: 22px;
      font-weight: 700;
      white-space: nowrap;
    }
    .players {
      display: grid;
      grid-template-columns: repeat(4, minmax(78px, 1fr));
      gap: 8px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: white;
      color: var(--ink);
      min-height: 42px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { border-color: #8091a3; background: #f8fafc; }
    button:disabled {
      cursor: not-allowed;
      color: #718096;
      background: #edf1f4;
      border-color: var(--line);
    }
    button.primary { color: white; background: var(--accent); border-color: var(--accent); }
    button.good { color: white; background: var(--good); border-color: var(--good); }
    button.warn { color: white; background: var(--accent-2); border-color: var(--accent-2); }
    button.danger { color: white; background: var(--danger); border-color: var(--danger); }
    button.blue { color: white; background: var(--blue); border-color: var(--blue); }
    button.active { outline: 3px solid #fbbf24; }
    .actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(120px, 1fr));
      gap: 8px;
    }
    .score-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(120px, 1fr));
      gap: 8px;
    }
    .attempts {
      display: grid;
      gap: 8px;
    }
    .attempt {
      display: grid;
      grid-template-columns: minmax(90px, 1fr) 140px 74px;
      gap: 8px;
      align-items: center;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      font-size: 13px;
    }
    .pending {
      border-color: #f59e0b;
      background: #fff7ed;
    }
    .timer-bar {
      height: 16px;
      border-radius: 999px;
      background: #d9e2ea;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .timer-fill {
      height: 100%;
      width: 100%;
      background: linear-gradient(90deg, var(--good), #f59e0b, var(--danger));
      transition: width 0.2s linear;
    }
    input {
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      font-size: 14px;
    }
    .import-row {
      display: grid;
      grid-template-columns: 1fr 120px;
      gap: 8px;
    }
    .sync-actions {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .message {
      min-height: 22px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .reset-notice {
      margin-top: 10px;
      border-left: 4px solid var(--accent-2);
      background: #fff7ed;
      color: #7c2d12;
      padding: 10px 12px;
      font-size: 14px;
      font-weight: 700;
    }
    @media (max-width: 860px) {
      header, .layout, .status-grid { grid-template-columns: 1fr; }
      .players { grid-template-columns: repeat(2, minmax(78px, 1fr)); }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Science Bowl Buzzer Logger</h1>
      <div class="subtle" id="inputMode">Input mode: simulator</div>
      <div class="subtle" id="resetMode">Reset mode: manual</div>
    </div>
    <button class="blue" onclick="exportCsv()">Export CSV</button>
  </header>

  <div class="layout">
    <div>
      <section>
        <h2>Match Status</h2>
        <div class="status-grid">
          <div class="metric"><div class="label">Question</div><div class="value" id="question">1</div></div>
          <div class="metric"><div class="label">Pending</div><div class="value" id="pending">None</div></div>
          <div class="metric"><div class="label">Team A</div><div class="value" id="scoreA">0</div></div>
          <div class="metric"><div class="label">Team B</div><div class="value" id="scoreB">0</div></div>
        </div>
      </section>

      <section>
        <h2>Contestant Inputs</h2>
        <div class="players" id="players"></div>
      </section>

      <section>
        <h2>Current Toss-Up Attempts</h2>
        <div class="attempts" id="attempts"></div>
      </section>
    </div>

    <div>
      <section>
        <h2>Host Controls</h2>
        <div class="actions">
          <button class="good" onclick="action('correct')">Correct (C)</button>
          <button class="warn" onclick="action('wrong')">Incorrect (W)</button>
          <button onclick="action('timer')">5s Timer (T)</button>
          <button onclick="action('delete')">Delete (D)</button>
          <button id="undoButton" onclick="undoEntry()">Undo (U)</button>
          <button class="danger" onclick="newRound()">New Round (N)</button>
        </div>
        <div class="reset-notice" id="resetNotice" hidden>
          Press the physical EC500 reset button.
        </div>
      </section>

      <section>
        <h2>Timer</h2>
        <div class="metric">
          <div class="label">Remaining</div>
          <div class="value" id="timerText">5.0s</div>
        </div>
        <div class="timer-bar" aria-label="timer">
          <div class="timer-fill" id="timerFill"></div>
        </div>
      </section>

      <section>
        <h2>Score Display</h2>
        <div class="score-actions">
          <button onclick="score('A', 4, 'Toss-up')">A +4</button>
          <button onclick="score('B', 4, 'Toss-up')">B +4</button>
          <button onclick="score('A', 10, 'Bonus')">A +10</button>
          <button onclick="score('B', 10, 'Bonus')">B +10</button>
        </div>
      </section>

      <section>
        <h2>Question PDF Subjects</h2>
        <label for="gameSelect">Select a game to load, import or sync</label>
        <select id="gameSelect"></select>
        <button onclick="refreshGame()">Refresh game / Load selected</button>
        <div id="gameHistory" class="subtle"></div>
        <div class="import-row">
          <input id="pdfUrl" placeholder="Paste the direct PDF URL for this game">
          <button onclick="importSubjects()">Import</button>
        </div>
        <div class="message" id="message"></div>
      </section>

      <section>
        <h2>Google Drive</h2>
        <div class="sync-actions">
          <button class="blue" onclick="syncGoogleSheet()">Sync game + analysis</button>
          <button onclick="loadPlayerNames()">Load player names</button>
        </div>
        <div class="message" id="googleMessage"></div>
        <details><summary>Connect Google (one-time setup)</summary>
          <p>Deploy the supplied Google script, then enter its web app URL and private connection key.</p>
          <input id="bridgeUrl" placeholder="https://script.google.com/macros/s/.../exec" autocomplete="off">
          <input id="bridgeKey" type="password" placeholder="Connection key" autocomplete="new-password">
          <button onclick="connectGoogle()">Save and test connection</button>
        </details>
      </section>
    </div>
  </div>
</main>

<script>
let state = null;
let stateRequestNumber = 0;
let lastAppliedStateRequest = 0;

function playerButton(player) {
  const button = document.createElement('button');
  button.textContent = `P${player}`;
  button.onclick = () => buzz(player);
  button.id = `player-${player}`;
  return button;
}

function initPlayers() {
  const box = document.getElementById('players');
  for (let i = 1; i <= 16; i += 1) box.appendChild(playerButton(i));
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload || {})
  });
  let data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  if (data.job_id) {
    const jobId = data.job_id;
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, 700));
      const progress = await fetch(`/api/jobs?id=${encodeURIComponent(jobId)}`, {cache:'no-store',signal:AbortSignal.timeout(10000)});
      data = await progress.json();
      if (!progress.ok || data.status === 'error') throw new Error(data.error || 'Operation failed');
      if (data.status === 'done') return data.result;
    }
  }
  return data;
}

async function buzz(player) {
  await postJson('/api/buzz', {player});
  await loadState();
}

async function action(name) {
  await postJson('/api/action', {action: name});
  await loadState();
  await loadHistory();
}

async function undoEntry() {
  if (!confirm('Are you sure you want to undo the latest entry in the loaded game? A completed question may reopen. Manual display points are unchanged.')) return;
  try {
    const result=await postJson('/api/action',{action:'undo'});
    await loadState();
    await loadHistory();
    document.getElementById('message').textContent=result.accepted ? 'Entry undone. Sync this game again to update Google.' : result.reason;
  } catch(error) {document.getElementById('message').textContent=error.message;}
}

async function refreshGame() {
  try {
    await postJson('/api/games/load',{round_id:selectedGame()});
    await loadState(); await loadGames(true);
    await loadHistory();
    document.getElementById('message').textContent='Selected game loaded. Controls now apply to this game.';
  } catch(error) {document.getElementById('message').textContent=error.message;}
}

async function loadHistory() {
  const response=await fetch('/api/games/history',{cache:'no-store'});
  if (!response.ok) throw new Error('Could not load game history');
  const game=await response.json(),box=document.getElementById('gameHistory');
  box.replaceChildren();
  const title=document.createElement('p');title.textContent=`Loaded game: ${game.name} — ${game.questions.length} recorded questions`;box.appendChild(title);
  for(const q of game.questions) {
    const row=document.createElement('p');
    const attempts=game.attempts.filter(a=>a.question_number===q.question_number);
    row.textContent=`Q${q.question_number} · ${q.subject || 'No subject'} · ${q.final_result || 'In progress'}: `+attempts.map(a=>`${a.player_name || 'No buzz'} — ${a.result}`).join('; ');
    box.appendChild(row);
  }
}

async function score(team, points, reason) {
  await postJson('/api/action', {action: 'score', team, points, reason});
  await loadState();
}

async function newRound() {
  await postJson('/api/action', {action: 'new_round'});
  await loadState();
  await loadGames(true);
  await loadHistory();
}

function selectedGame() { return Number(document.getElementById('gameSelect').value) || state.round.id; }
async function loadGames(selectActive=false) {
  const response = await fetch('/api/games', {cache:'no-store'});
  const data = await response.json();
  const box = document.getElementById('gameSelect');
  const previous = selectActive ? '' : box.value;
  box.replaceChildren(...data.games.map(g=> {
    const option = document.createElement('option'); option.value=g.id;
    option.textContent=`${g.name}${g.active ? ' (current)' : ''}`;
    option.selected=previous ? String(g.id)===previous : Boolean(g.active);
    return option;
  }));
}
async function connectGoogle() {
  const message=document.getElementById('googleMessage'); message.textContent='Testing Google connection...';
  try {
    await postJson('/api/google/connect',{url:document.getElementById('bridgeUrl').value,token:document.getElementById('bridgeKey').value});
    document.getElementById('bridgeKey').value=''; message.textContent='Google connected. Load player names before your next game.';
  } catch(error) {message.textContent=error.message;}
}
async function loadPlayerNames() {
  const message=document.getElementById('googleMessage'); message.textContent='Loading player names...';
  try { const result=await postJson('/api/players/import',{});message.textContent=`Loaded ${result.named} player names. Saved for offline use.`;await loadState(); }
  catch(error) {message.textContent=error.message;}
}
function playerLabel(port, name) {
  const display=name || state?.players?.[String(port)]?.name;
  return display && display !== `P${port}` ? `${display} (P${port})` : `P${port}`;
}
function escapeHtml(value) {const span=document.createElement('span');span.textContent=String(value);return span.innerHTML;}

async function importSubjects() {
  const message = document.getElementById('message');
  message.textContent = 'Importing subjects...';
  try {
    const data = await postJson('/api/subjects/import_url', {url: document.getElementById('pdfUrl').value,round_id:selectedGame()});
    message.textContent = `Found ${data.found} toss-up subjects; updated ${data.updated} questions. ${data.missing.length ? 'Unmatched recorded questions: '+data.missing.join(', ') : 'Ready to sync the game.'}`;
    if (!data.missing.length && data.google_connected) await syncGoogleSheet();
  } catch (error) {
    message.textContent = error.message;
  }
  await loadState();
}

async function syncGoogleSheet() {
  const message = document.getElementById('googleMessage');
  message.textContent = 'Syncing game and refreshing player statistics...';
  try {
    const data = await postJson('/api/google/sync', {round_id:selectedGame()});
    message.textContent = `Synced ${data.attempts} records. Data center includes ${data.games} games. `;
    const link=document.createElement('a'); link.textContent='Open game sheet';
    if (data.url.startsWith('https://docs.google.com/spreadsheets/')) {link.href=data.url;link.target='_blank';link.rel='noreferrer';message.appendChild(link);}
  } catch (error) {
    message.textContent = error.message;
  }
}

function exportCsv() {
  window.location.href = '/api/export';
}

function renderAttempts() {
  const box = document.getElementById('attempts');
  box.innerHTML = '';
  if (state.pending) {
    const item = document.createElement('div');
    item.className = 'attempt pending';
    const timing = state.pending.interrupt ? 'Interrupt' : 'Timed';
    item.innerHTML = `<strong>${escapeHtml(playerLabel(state.pending.player_id,state.pending.player_name))}</strong><span>Pending ${timing}</span><span>${(state.pending.elapsed_ms / 1000).toFixed(2)}s</span>`;
    box.appendChild(item);
  }
  for (const attempt of state.attempts) {
    const item = document.createElement('div');
    item.className = 'attempt';
    const player = attempt.player_id ? escapeHtml(playerLabel(attempt.player_id,attempt.player_name || `P${attempt.player_id}`)) : '-';
    const time = attempt.elapsed_ms == null ? '' : `${(attempt.elapsed_ms / 1000).toFixed(2)}s`;
    const timing = attempt.interrupt == null ? '' : (attempt.interrupt ? 'Interrupt' : 'Timed');
    item.innerHTML = `<strong>${player}</strong><span>${attempt.result}${timing ? ` / ${timing}` : ''}</span><span>${time}</span>`;
    box.appendChild(item);
  }
  if (!state.pending && state.attempts.length === 0) {
    box.innerHTML = '<div class="subtle">No attempts on this toss-up yet.</div>';
  }
}

function renderState() {
  const inputMode = state.hardware ? state.hardware.input_mode : 'simulator';
  const resetAvailable = Boolean(state.reset && state.reset.available);
  const activePlayers = state.hardware ? state.hardware.active_players : [];
  const manualHardwareReset = inputMode === 'mcp23017' && !resetAvailable;
  document.getElementById('inputMode').textContent = `Input mode: ${inputMode}`;
  document.getElementById('resetMode').textContent = `Reset mode: ${manualHardwareReset ? 'physical EC500 button' : (resetAvailable ? 'website' : 'not connected')}`;
  const resetNotice = document.getElementById('resetNotice');
  resetNotice.hidden = !(manualHardwareReset && !state.pending && activePlayers.length > 0);
  document.getElementById('question').textContent = state.question.question_number;
  document.getElementById('pending').textContent = state.pending ? playerLabel(state.pending.player_id,state.pending.player_name) : 'None';
  document.getElementById('scoreA').textContent = state.scores.A;
  document.getElementById('scoreB').textContent = state.scores.B;
  const remaining = state.timer.remaining_ms / 1000;
  document.getElementById('timerText').textContent = `${remaining.toFixed(1)}s`;
  const pct = Math.max(0, Math.min(100, state.timer.remaining_ms / state.timer.duration_ms * 100));
  document.getElementById('timerFill').style.width = `${pct}%`;
  for (let i = 1; i <= 16; i += 1) {
    const player = document.getElementById(`player-${i}`);
    player.textContent = playerLabel(i);
    player.classList.toggle('active', state.pending && state.pending.player_id === i);
    player.disabled = state.hardware && state.hardware.input_mode === 'mcp23017';
  }
  renderAttempts();
}

async function loadState() {
  const requestNumber = ++stateRequestNumber;
  const response = await fetch(`/api/state?_=${Date.now()}`, {cache: 'no-store',signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error(`State request failed: ${response.status}`);
  const nextState = await response.json();
  if (requestNumber < lastAppliedStateRequest) return;
  lastAppliedStateRequest = requestNumber;
  state = nextState;
  renderState();
}

async function pollState() {
  try {
    await loadState();
  } catch (error) {
    console.error('Live state update failed; retrying.', error);
  } finally {
    window.setTimeout(pollState, 200);
  }
}

document.addEventListener('keydown', (event) => {
  if (['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName) || event.target.isContentEditable) return;
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  if (event.repeat) return;
  if (key === 'c') action('correct');
  if (key === 'w') action('wrong');
  if (key === 'd') action('delete');
  if (key === 't') action('timer');
  if (key === 'u') undoEntry();
  if (key === 'n') newRound();
  if (key === '1') action('correct');
  if (key === '2') action('wrong');
  if (key === '3') action('timer');
  if (key === '0' && state && state.reset.available) action('reset');
  if (key === 'decimal' || key === '.') action('delete');
  if (key === '4') score('A', 4, 'Toss-up');
  if (key === '5') score('B', 4, 'Toss-up');
  if (key === '7') score('A', 10, 'Bonus');
  if (key === '8') score('B', 10, 'Bonus');
});

initPlayers();
loadGames().catch(console.error);
pollState();
window.addEventListener('focus', () => loadState().catch(() => {}));
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) loadState().catch(() => {});
});
</script>
</body>
</html>
"""


def dispatch_action(
    controller: MatchController,
    action: str,
    *,
    team: str | None = None,
    points: int | None = None,
    reason: str = "Manual",
    round_name: str | None = None,
) -> dict:
    if action == "correct":
        return controller.correct()
    if action == "wrong":
        return controller.wrong()
    if action == "delete":
        return controller.delete()
    if action == "undo":
        return controller.undo()
    if action == "timer":
        return controller.start_timer()
    if action == "time_up":
        return controller.time_up()
    if action == "score":
        if team is None or points is None:
            raise ValueError("score action requires team and points")
        return controller.add_score(team, points, reason)
    if action == "new_round":
        return controller.new_round(round_name)
    if action == "reset":
        return controller.reset_buzzers()
    raise ValueError(f"unknown action: {action}")


class HardwareRuntime:
    def __init__(
        self,
        controller: MatchController,
        input_source: InputSource | None = None,
        keypad_source: KeypadSource | None = None,
    ) -> None:
        self.controller = controller
        self.input_source = input_source
        self.keypad_source = keypad_source
        self.winner_poller = (
            WinnerInputPoller(input_source, controller.buzz) if input_source else None
        )
        self.keypad_error: str | None = None

    @staticmethod
    def _dispatch_keypad(controller: MatchController, command: KeypadCommand) -> None:
        dispatch_action(
            controller,
            command.action,
            team=command.team,
            points=command.points,
            reason=command.reason or "Keypad",
        )

    def poll(self) -> None:
        if self.winner_poller is not None:
            self.winner_poller.poll()

        if self.keypad_source is None:
            return
        try:
            for command in self.keypad_source.read_commands():
                self._dispatch_keypad(self.controller, command)
            self.keypad_error = None
        except Exception as exc:
            self.keypad_error = f"Keypad read failed: {exc}"

    def snapshot(self) -> dict:
        return {
            "input_mode": "mcp23017" if self.winner_poller else "simulator",
            "active_players": (
                self.winner_poller.active_players if self.winner_poller else []
            ),
            "input_error": (
                self.winner_poller.last_error if self.winner_poller else None
            ),
            "keypad_enabled": self.keypad_source is not None,
            "keypad_error": self.keypad_error,
        }

    def close(self) -> None:
        for resource in (self.input_source, self.keypad_source):
            close = getattr(resource, "close", None)
            if callable(close):
                close()


class BuzzerHTTPServer(HTTPServer):
    def __init__(self, server_address, handler_class, runtime: HardwareRuntime) -> None:
        self.runtime = runtime
        self.jobs = BackgroundJobs()
        super().__init__(server_address, handler_class)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(1)
        return connection, address

    def service_actions(self) -> None:
        self.runtime.poll()
        self.runtime.controller._expire_timer_if_needed()
        self.jobs.poll()

    def server_close(self) -> None:
        try:
            self.jobs.close()
            self.runtime.close()
            reset_close = getattr(self.runtime.controller.reset_output, "close", None)
            if callable(reset_close):
                reset_close()
            display_close = getattr(self.runtime.controller.score_display, "close", None)
            if callable(display_close):
                display_close()
            self.runtime.controller.db.close()
        finally:
            super().server_close()


class BuzzerRequestHandler(BaseHTTPRequestHandler):
    controller: MatchController
    google_config_path: str | None = None

    def _json_response(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, body: str, content_type: str = "text/html") -> None:
        data = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1024 * 1024:
            raise ValueError("Request too large")
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/api/games':
            self._json_response({'games':self.controller.db.rounds_list()})
            return
        if parsed.path == '/api/games/history':
            self._json_response(self.controller.db.game_payload())
            return
        if parsed.path == '/api/jobs':
            try:
                self._json_response(self.server.jobs.get(parse_qs(parsed.query).get('id',[''])[0]))
            except ValueError as exc:
                self._json_response({'error':str(exc)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/":
            self._text_response(HTML)
            return
        if parsed.path == "/api/state":
            state = self.controller.snapshot()
            if isinstance(self.server, BuzzerHTTPServer):
                state["hardware"] = self.server.runtime.snapshot()
            self._json_response(state)
            return
        if parsed.path == "/api/export":
            query = parse_qs(parsed.query)
            default_name = "exports/current_round.csv"
            output_path = Path(query.get("path", [default_name])[0])
            csv_path = self.controller.db.export_csv(output_path)
            data = csv_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", f'attachment; filename="{csv_path.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/buzz":
                if (
                    isinstance(self.server, BuzzerHTTPServer)
                    and self.server.runtime.winner_poller is not None
                ):
                    raise RuntimeError(
                        "Manual player buttons are disabled in MCP23017 hardware mode"
                    )
                result = self.controller.buzz(int(payload["player"]))
                self._json_response(result)
                return
            if parsed.path == "/api/action":
                action = payload.get("action")
                result = dispatch_action(
                    self.controller,
                    str(action),
                    team=str(payload["team"]) if "team" in payload else None,
                    points=int(payload["points"]) if "points" in payload else None,
                    reason=str(payload.get("reason", "Manual")),
                    round_name=payload.get("name"),
                )
                self._json_response(result)
                return
            if parsed.path == '/api/games/load':
                self._json_response(self.controller.load_round(int(payload['round_id'])))
                return
            if parsed.path == "/api/subjects/import_url":
                url = str(payload['url']).strip()
                if not url.startswith(('https://','http://')):
                    raise ValueError('Paste a direct HTTP or HTTPS PDF URL')
                round_id = int(payload.get('round_id') or self.controller.db.active_round()['id'])
                def finish(subjects):
                    updated=self.controller.db.set_subjects(subjects,round_id,url)
                    return {'found':len(subjects),'updated':updated,'missing':self.controller.db.game_payload(round_id)['missing_subjects'],'google_connected':CONFIG_PATH.exists()}
                self._json_response(self.server.jobs.start(lambda:infer_subjects_from_pdf(url),finish))
                return
            if parsed.path == '/api/google/connect':
                save_bridge_config(str(payload.get('url','')),str(payload.get('token','')))
                self._json_response(self.server.jobs.start(lambda:GoogleBridge().call('status')))
                return
            if parsed.path == '/api/players/import':
                if self.controller.pending:
                    raise ValueError('Mark or delete the pending buzz before loading player names')
                def finish_roster(result):
                    if self.controller.pending:
                        raise ValueError('A buzz is pending. Finish it, then load names again.')
                    self.controller.db.set_roster(result['players'])
                    return {'named':sum(bool(p['name']) for p in self.controller.db.roster().values())}
                self._json_response(self.server.jobs.start(lambda:GoogleBridge().call('roster'),finish_roster))
                return
            if parsed.path == "/api/google/sync":
                game = self.controller.db.game_payload(int(payload.get('round_id') or self.controller.db.active_round()['id']))
                if self.controller.pending and game['round_id']==self.controller.db.active_round()['id']:
                    raise ValueError('Mark or delete the pending buzz before syncing')
                if not game['questions']:
                    raise ValueError('No recorded questions to sync')
                if game['missing_subjects']:
                    raise ValueError('Import the question PDF first. Missing subjects: '+', '.join(map(str,game['missing_subjects'])))
                self._json_response(self.server.jobs.start(lambda:GoogleBridge().call('sync',game=game)))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def build_server(
    host: str,
    port: int,
    db_path: str,
    google_config_path: str | None = None,
    max7219_display: bool = False,
    input_source: InputSource | None = None,
    keypad_source: KeypadSource | None = None,
    reset_output: ResetOutput | None = None,
) -> BuzzerHTTPServer:
    db = Database(db_path)
    controller = MatchController(
        db,
        reset_output=reset_output,
        score_display=build_score_display(max7219_display),
    )
    runtime = HardwareRuntime(controller, input_source, keypad_source)
    BuzzerRequestHandler.controller = controller
    BuzzerRequestHandler.google_config_path = google_config_path
    return BuzzerHTTPServer((host, port), BuzzerRequestHandler, runtime)


def auto_int(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Science Bowl buzzer logger")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="data/buzzer.db")
    parser.add_argument("--google-config", default=None)
    parser.add_argument(
        "--max7219-display",
        action="store_true",
        help="Mirror Team A/B scores to two daisy-chained MAX7219 modules on SPI0",
    )
    parser.add_argument(
        "--mcp23017",
        action="store_true",
        help="Read 16 active-low winner inputs from an MCP23017",
    )
    parser.add_argument("--mcp-address", type=auto_int, default=0x20)
    parser.add_argument("--mcp-bus", type=int, default=1)
    parser.add_argument(
        "--mcp-active-high",
        action="store_true",
        help="Treat a high MCP23017 input as active instead of the default active-low",
    )
    parser.add_argument(
        "--keypad-device",
        default=None,
        help="USB keypad event path, or 'auto' to select the only numeric keypad",
    )
    parser.add_argument(
        "--reset-gpio",
        type=int,
        default=None,
        help="BCM GPIO driving the isolated PhotoMOS reset input; disabled by default",
    )
    parser.add_argument("--reset-pulse-ms", type=int, default=150)
    args = parser.parse_args()

    input_source = None
    if args.mcp23017:
        input_source = Mcp23017InputSource(
            address=args.mcp_address,
            bus_number=args.mcp_bus,
            active_low=not args.mcp_active_high,
        )
    keypad_source = (
        EvdevNumericKeypad(args.keypad_device) if args.keypad_device else None
    )
    reset_output = None
    if args.reset_gpio is not None:
        if args.reset_pulse_ms <= 0:
            parser.error("--reset-pulse-ms must be positive")
        reset_output = GpioZeroResetOutput(
            gpio_pin=args.reset_gpio,
            pulse_seconds=args.reset_pulse_ms / 1000,
        )

    server = build_server(
        args.host,
        args.port,
        args.db,
        args.google_config,
        args.max7219_display,
        input_source,
        keypad_source,
        reset_output,
    )
    print(f"Listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.01)
    except KeyboardInterrupt:
        print("\nStopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
