# WSGI application for Durak game
# Direct integration — no http.server needed

import sys
import os
import json
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))

from durak_server import DurakGame

# Reuse one game instance
game = DurakGame()

def send_json(data, start_response, status='200 OK'):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    headers = [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Access-Control-Allow-Origin', '*'),
    ]
    start_response(status, headers)
    return [body]

def send_html(html, start_response, status='200 OK'):
    body = html.encode('utf-8')
    headers = [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Access-Control-Allow-Origin', '*'),
    ]
    start_response(status, headers)
    return [body]

def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    qs = environ.get('QUERY_STRING', '')
    params = urllib.parse.parse_qs(qs)

    try:
        if path == '/':
            return serve_html(start_response)

        if path == '/state':
            state = game.get_state()
            end = game.check_end()
            if end:
                state['game_over'] = end
            return send_json(state, start_response)

        if path == '/new':
            game.new_game()
            state = game.get_state()
            return send_json({'message': 'Новая игра!', **state}, start_response)

        if path == '/attack':
            idx = int(params.get('idx', [-1])[0])
            msg = game.player_attack(idx)
            state = game.get_state()
            if '\u2705' in msg or '\U0001f504' in msg:
                ai_msg = game.ai_turn()
                return send_json({'message': msg, 'ai_turn': ai_msg, **state}, start_response)
            else:
                return send_json({'message': msg, **state}, start_response)

        if path == '/defend':
            idx = int(params.get('idx', [-1])[0])
            attack_idx = int(params.get('attack_idx', [-1])[0])
            msg = game.player_defend(idx, attack_idx)
            state = game.get_state()
            if msg == 'TAKE_OR_MORE':
                return send_json({'message': 'Все отбито! /take или /done?', 'phase': 'MORE', **state}, start_response)
            elif '\u2705' in msg:
                if game.phase == 'DEFENSE':
                    ai_msg = game.ai_turn()
                    return send_json({'message': msg, 'ai_turn': ai_msg, **state}, start_response)
                else:
                    return send_json({'message': msg, **state}, start_response)
            else:
                return send_json({'message': msg, **state}, start_response)

        if path == '/take':
            msg = game.player_take()
            return send_json({'message': msg, **game.get_state()}, start_response)

        if path == '/done':
            msg = game.player_done()
            return send_json({'message': msg, **game.get_state()}, start_response)

        if path == '/more':
            msg = game.player_more()
            if msg.startswith('\U0001f504'):
                game.phase = 'ATTACK'
                return send_json({'message': msg, **game.get_state()}, start_response)
            else:
                return send_json({'message': msg, **game.get_state()}, start_response)

        return send_json({'error': 'not found'}, start_response, '404 Not Found')

    except Exception as e:
        return send_json({'error': str(e)}, start_response, '500 Internal Server Error')


# ─── HTML Frontend (embedded) ───

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Дурак vs Контейнерный Бро</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Courier New', monospace; background: #1a1a2e; color: #e0e0e0; max-width: 600px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; color: #e94560; font-size: 22px; margin-bottom: 20px; }
.card-area { background: #16213e; border-radius: 10px; padding: 15px; margin: 10px 0; }
.card-area h2 { color: #0f3460; background: #e94560; display: inline-block; padding: 4px 12px; border-radius: 5px; font-size: 14px; margin-bottom: 10px; }
.cards { display: flex; flex-wrap: wrap; gap: 8px; }
.card { background: #fff; color: #000; padding: 10px 14px; border-radius: 8px; font-size: 20px; cursor: pointer; transition: all 0.2s; border: 2px solid transparent; }
.card:hover { border-color: #e94560; transform: scale(1.05); }
.card.selected { border-color: #e94560; background: #ffe0e0; }
.table-area { background: #0f3460; border-radius: 10px; padding: 15px; margin: 10px 0; }
.table-area h2 { color: #e94560; font-size: 14px; margin-bottom: 10px; }
.table-cards { display: flex; flex-wrap: wrap; gap: 12px; }
.pair { display: flex; align-items: center; gap: 8px; }
.pair .vs { color: #e94560; font-weight: bold; }
.info { display: flex; justify-content: space-between; background: #0f3460; border-radius: 10px; padding: 10px 15px; margin: 10px 0; font-size: 14px; }
.controls { display: flex; gap: 10px; margin: 15px 0; flex-wrap: wrap; }
button { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold; transition: all 0.2s; }
.btn-attack { background: #e94560; color: #fff; }
.btn-defend { background: #0f3460; color: #e94560; border: 2px solid #e94560; }
.btn-take { background: #ffa500; color: #000; }
.btn-done { background: #00cc66; color: #000; }
.btn-new { background: #e94560; color: #fff; width: 100%; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.log { background: #000; border-radius: 10px; padding: 10px; margin: 10px 0; max-height: 150px; overflow-y: auto; font-size: 13px; color: #00ff88; }
</style>
</head>
<body>
<h1>🃏 ДУРАК 🃏<br><small>Ты vs Контейнерный Бро</small></h1>

<div class="info">
<span>🃏 Козырь: <b id="trump">-</b></span>
<span>🎴 В колоде: <b id="deck">0</b></span>
<span>🤖 ИИ карт: <b id="ai-count">0</b></span>
</div>

<div class="table-area">
<h2>🟫 СТОЛ</h2>
<div class="table-cards" id="table">-</div>
</div>

<div class="card-area">
<h2>🖐️ ТВОЯ РУКА</h2>
<div class="cards" id="hand"></div>
</div>

<div class="controls">
<button class="btn-attack" id="btn-attack" disabled>⚔️ Атаковать</button>
<button class="btn-defend" id="btn-defend" disabled>🛡️ Отбить</button>
<button class="btn-take" id="btn-take" disabled>📦 Забрать</button>
<button class="btn-done" id="btn-done" disabled>👌 Бито</button>
<button class="btn-new" id="btn-new">🔄 Новая игра</button>
</div>

<div class="log" id="log">Добро пожаловать! Нажми «Новая игра» 🃏</div>

<script>
let selectedCard = null;
let attackIdx = null;
let phase = null;

async function api(path) {
    const r = await fetch(path);
    return await r.json();
}

async function refresh() {
    const s = await api('/state');
    if (s.game_over) {
        document.getElementById('log').innerHTML = '🎮 ' + s.game_over + '<br>Нажми «Новая игра»';
        document.getElementById('hand').innerHTML = '';
        document.getElementById('table').innerHTML = '-';
        toggleButtons('GAMEOVER');
        return;
    }
    phase = s.phase;
    document.getElementById('trump').textContent = s.trump || '-';
    document.getElementById('deck').textContent = s.deck_count;
    document.getElementById('ai-count').textContent = s.ai_count;
    renderTable(s.table);
    renderHand(s);
    toggleButtons(s);
}

function renderTable(table) {
    const el = document.getElementById('table');
    if (!table.length) { el.textContent = '-'; return; }
    el.innerHTML = table.map((t,i) => 
        '<div class="pair">' +
        '<span>' + t.attack + '</span>' +
        '<span class="vs">vs</span>' +
        '<span>' + (t.defense || '❓') + '</span>' +
        (phase === 'DEFENSE' && !t.defense ? ' <button onclick="setAttack('+i+')" style="font-size:10px">🔽</button>' : '') +
        '</div>'
    ).join('');
}

function renderHand(s) {
    const el = document.getElementById('hand');
    if (!s.player_hand) { el.innerHTML = 'Нет карт!'; return; }
    el.innerHTML = s.player_hand.map((c,i) => 
        '<div class="card' + (selectedCard === i ? ' selected' : '') + '" onclick="selectCard('+i+')">' + c + '</div>'
    ).join('');
}

function selectCard(i) {
    if (selectedCard === i) selectedCard = null;
    else selectedCard = i;
    refresh();
}

function setAttack(i) { attackIdx = i; refresh(); }

function toggleButtons(s) {
    const atk = document.getElementById('btn-attack');
    const def = document.getElementById('btn-defend');
    const take = document.getElementById('btn-take');
    const done = document.getElementById('btn-done');
    [atk, def, take, done].forEach(b => b.disabled = true);
    
    if (s.game_over) return;
    
    if (s.phase === 'ATTACK' && s.attacker === 'player') atk.disabled = false;
    if (s.phase === 'DEFENSE' && s.defender === 'player') def.disabled = false;
    if (s.phase === 'DEFENSE' || s.phase === 'MORE') done.disabled = false;
    
    // Take: defender can take if there are unblocked attacks
    if (s.phase === 'DEFENSE' && s.defender === 'player') {
        const hasUnblocked = s.table.some(t => !t.defense);
        if (hasUnblocked) take.disabled = false;
    }
}

async function doAction(path) {
    const s = await api(path);
    document.getElementById('log').innerHTML = '📝 ' + s.message + (s.ai_turn ? '<br>🤖 ' + s.ai_turn : '');
    selectedCard = null;
    attackIdx = null;
    await refresh();
}

document.getElementById('btn-new').onclick = async () => {
    await api('/new');
    selectedCard = null;
    attackIdx = null;
    document.getElementById('log').textContent = 'Новая игра! Твой ход ⚔️';
    await refresh();
};

document.getElementById('btn-attack').onclick = () => {
    if (selectedCard === null) { document.getElementById('log').textContent = 'Выбери карту!'; return; }
    doAction('/attack?idx=' + selectedCard);
};

document.getElementById('btn-defend').onclick = () => {
    if (selectedCard === null) { document.getElementById('log').textContent = 'Выбери карту!'; return; }
    let url = '/defend?idx=' + selectedCard;
    if (attackIdx !== null) url += '&attack_idx=' + attackIdx;
    doAction(url);
};

document.getElementById('btn-take').onclick = () => doAction('/take');
document.getElementById('btn-done').onclick = () => doAction('/done');

refresh();
</script>
</body>
</html>"""

def serve_html(start_response):
    return send_html(HTML, start_response)
