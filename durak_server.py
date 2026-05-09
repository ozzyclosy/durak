#!/usr/bin/env python3
"""
ДУРАК — Текстовый движок. Игра против контейнерного джентельмена.
"""

import random
import json
import sys
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class Suit(Enum):
    HEARTS = "♥️"
    DIAMONDS = "♦️"
    CLUBS = "♣️"
    SPADES = "♠️"

RANKS = ["6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

@dataclass
class Card:
    suit: Suit
    rank: str

    def __str__(self):
        return f"{self.rank}{self.suit.value}"

    def __repr__(self):
        return self.__str__()

    def beats(self, other: "Card", trump: Suit) -> bool:
        """Может ли эта карта побить другую?"""
        if self.suit == other.suit:
            return RANK_VALUES[self.rank] > RANK_VALUES[other.rank]
        return self.suit == trump and other.suit != trump

    def to_dict(self):
        return {"suit": self.suit.name, "rank": self.rank}

    @classmethod
    def from_dict(cls, d):
        return cls(Suit[d["suit"]], d["rank"])


class DurakGame:
    def __init__(self):
        self.deck: list[Card] = []
        self.player_hand: list[Card] = []
        self.ai_hand: list[Card] = []
        self.trump: Optional[Suit] = None
        self.table: list[tuple[Card, Optional[Card]]] = []  # (attack, defense)
        self.phase = "NEW"  # NEW, ATTACK, DEFENSE, MORE, DONE
        self.discard: list[Card] = []
        self.attacker = "player"
        self.defender = "ai"

    def new_game(self):
        """Начать новую игру."""
        suits = list(Suit)
        self.deck = [Card(s, r) for s in suits for r in RANKS]
        random.shuffle(self.deck)

        self.trump = self.deck[-1].suit
        self.player_hand = self.deck[:6]
        self.ai_hand = self.deck[6:12]
        self.deck = self.deck[12:]
        self.table = []
        self.discard = []
        self.phase = "ATTACK"
        self.attacker = "player"
        self.defender = "ai"
        self._sort_hands()

    def _sort_hands(self):
        """Сортировка рук."""
        def sort_key(c: Card):
            return (c.suit.value, RANK_VALUES[c.rank])
        self.player_hand.sort(key=sort_key)
        self.ai_hand.sort(key=sort_key)

    def _draw_to(self, hand: list[Card], count: int = 6):
        """Добрать карты до count."""
        while len(hand) < count and self.deck:
            hand.append(self.deck.pop())
        self._sort_hands()

    def _fill_hands(self):
        """Добрать карты после раунда."""
        self._draw_to(self.player_hand)
        self._draw_to(self.ai_hand)

    def get_state(self) -> dict:
        """Получить состояние игры."""
        return {
            "phase": self.phase,
            "trump": str(self.trump.value) if self.trump else None,
            "player_hand": [str(c) for c in self.player_hand],
            "player_count": len(self.player_hand),
            "ai_count": len(self.ai_hand),
            "deck_count": len(self.deck),
            "table": [{"attack": str(a), "defense": str(d) if d else None} for a, d in self.table],
            "attacker": self.attacker,
            "defender": self.defender,
        }

    def player_attack(self, card_idx: int) -> str:
        """Игрок атакует картой по индексу."""
        if self.phase != "ATTACK" or self.attacker != "player":
            return "❌ Сейчас не твоя очередь атаковать!"

        if card_idx < 0 or card_idx >= len(self.player_hand):
            return "❌ Нет такой карты!"

        card = self.player_hand[card_idx]

        # Если на столе уже есть карты, можно подкидывать только ранги с них
        if self.table:
            valid_ranks = set()
            for a, d in self.table:
                valid_ranks.add(a.rank)
                if d:
                    valid_ranks.add(d.rank)
            if card.rank not in valid_ranks:
                return f"❌ Можно подкидывать только: {', '.join(sorted(valid_ranks))}"

        self.player_hand.pop(card_idx)
        self.table.append((card, None))
        self.phase = "DEFENSE"
        self._sort_hands()
        return f"✅ Ты атаковал картой {card}. Я защищаюсь..."

    def player_defend(self, card_idx: int, attack_idx: int = -1) -> str:
        """Игрок защищается картой по индексу."""
        if self.phase != "DEFENSE" or self.defender != "player":
            return "❌ Сейчас не твоя очередь защищаться!"

        if attack_idx == -1:
            # Найти последнюю незакрытую атаку
            for i in range(len(self.table) - 1, -1, -1):
                if self.table[i][1] is None:
                    attack_idx = i
                    break

        if attack_idx < 0 or attack_idx >= len(self.table):
            return "❌ Неверный индекс атаки!"

        attack_card, _ = self.table[attack_idx]
        if self.table[attack_idx][1] is not None:
            return "❌ Эта атака уже отбита!"

        if card_idx < 0 or card_idx >= len(self.player_hand):
            return "❌ Нет такой карты!"

        card = self.player_hand[card_idx]
        if not card.beats(attack_card, self.trump):
            return f"❌ {card} не может побить {attack_card}!"

        self.player_hand.pop(card_idx)
        self.table[attack_idx] = (attack_card, card)

        # Проверить, все ли атаки отбиты
        if all(d is not None for _, d in self.table):
            return "TAKE_OR_MORE"

        self._sort_hands()
        return f"✅ Ты побил {attack_card} картой {card}!"

    def player_take(self) -> str:
        """Игрок забирает карты со стола."""
        if self.phase != "TAKE" or self.defender != "player":
            return "❌ Нечего забирать!"

        for a, d in self.table:
            self.player_hand.append(a)
            if d:
                self.player_hand.append(d)
        self.table.clear()
        self._fill_hands()
        self._next_round()
        self._sort_hands()
        return f"📦 Ты забрал карты. Теперь у тебя {len(self.player_hand)} карт."

    def player_done(self) -> str:
        """Игрок говорит «бито»."""
        if self.phase not in ("DEFENSE", "MORE"):
            return "❌ Нечего говорить бито!"

        # Проверить, все ли атаки отбиты
        if not all(d is not None for _, d in self.table):
            return "❌ Не все карты отбиты!"

        # Сбросить стол
        for a, d in self.table:
            self.discard.append(a)
            if d:
                self.discard.append(d)
        self.table.clear()
        self._fill_hands()
        self._next_round()
        self._sort_hands()
        return f"👌 Бито! Сброшено карт: {len(self.discard)}"

    def player_more(self) -> str:
        """Игрок говорит «ещё» (после отбоя всех атак)."""
        if self.phase != "MORE":
            return "❌ Сейчас нельзя!"
        self.phase = "ATTACK"
        return "🔄 Можешь подкинуть ещё!"

    def _next_round(self):
        """Переход к следующему раунду."""
        # Проверить победу
        if not self.player_hand and not self.deck:
            self.phase = "PLAYER_WIN"
            return
        if not self.ai_hand and not self.deck:
            self.phase = "AI_WIN"
            return

        # Меняем атакующего и защитника
        if self.phase == "TAKE":
            # Тот кто взял — защищается снова (атакует другой с новой карты)
            pass
        self.attacker, self.defender = self.defender, self.attacker

        if self.attacker == "player":
            self.phase = "ATTACK"
        else:
            self.phase = "ATTACK"
            self._ai_attack()

    def check_end(self) -> Optional[str]:
        """Проверить конец игры."""
        if self.phase == "PLAYER_WIN":
            return "🎉 ТЫ ВЫИГРАЛ! Я — дурак! 🤡"
        if self.phase == "AI_WIN":
            return "🤬 ТЫ ДУРАК! Я выиграл, сука!"
        return None

    # --- AI LOGIC ---

    def _ai_attack(self) -> str:
        """AI атакует."""
        if not self.table:
            # Первая атака — кидаем самую маленькую карту
            if not self.ai_hand:
                return "AI_HAS_NO_CARDS"
            card = min(self.ai_hand, key=lambda c: RANK_VALUES[c.rank])
            self.ai_hand.remove(card)
            self.table.append((card, None))
            self.phase = "DEFENSE"
            self._sort_hands()
            return f"ai_attacked {card}"

        # Подкидываем карту того же ранга что на столе
        valid_ranks = set()
        for a, d in self.table:
            valid_ranks.add(a.rank)
            if d:
                valid_ranks.add(d.rank)

        for card in sorted(self.ai_hand, key=lambda c: RANK_VALUES[c.rank]):
            if card.rank in valid_ranks:
                self.ai_hand.remove(card)
                self.table.append((card, None))
                self._sort_hands()
                self.phase = "DEFENSE"
                return f"ai_attacked {card}"

        return "AI_NO_MORE"

    def _ai_defend(self) -> str:
        """AI защищается."""
        # Найти незакрытую атаку
        attack_card = None
        attack_idx = -1
        for i, (a, d) in enumerate(self.table):
            if d is None:
                attack_card = a
                attack_idx = i
                break

        if attack_card is None:
            return "AI_NOTHING_TO_DEFEND"

        # Ищем самую маленькую карту которая бьёт
        best = None
        best_idx = -1
        for i, card in enumerate(self.ai_hand):
            if card.beats(attack_card, self.trump):
                if best is None or RANK_VALUES[card.rank] < RANK_VALUES[best.rank]:
                    best = card
                    best_idx = i

        if best is None:
            # Не можем отбить — берём
            return "AI_TAKE"

        self.ai_hand.pop(best_idx)
        self.table[attack_idx] = (attack_card, best)

        # Проверить, всё ли отбито
        if all(d is not None for _, d in self.table):
            return "AI_ALL_DEFENDED"

        self._sort_hands()
        return f"ai_defended {attack_card} with {best}"

    def _ai_take(self):
        """AI забирает карты."""
        for a, d in self.table:
            self.ai_hand.append(a)
            if d:
                self.ai_hand.append(d)
        self.table.clear()
        self._fill_hands()
        self._sort_hands()

    def _ai_more_or_done(self):
        """AI решает: подкинуть ещё или бито."""
        if not self.ai_hand:
            return "AI_DONE"

        valid_ranks = set()
        for a, d in self.table:
            valid_ranks.add(a.rank)
            if d:
                valid_ranks.add(d.rank)

        has_more = any(c.rank in valid_ranks for c in self.ai_hand)
        if has_more and len(self.player_hand) > 0:
            return "AI_MORE"
        return "AI_DONE"

    def ai_turn(self) -> str:
        """Выполнить ход AI и вернуть описание."""
        while True:
            if self.phase in ("PLAYER_WIN", "AI_WIN"):
                return self.check_end() or "game_over"

            if self.attacker == "ai":
                if self.phase == "ATTACK":
                    result = self._ai_attack()
                    if result == "AI_HAS_NO_CARDS":
                        self.phase = "AI_WIN"
                        return self.check_end() or "ai_won"
                    if result == "AI_NO_MORE":
                        # Бита
                        self._ai_end_attack()
                        continue
                    return f"🤖 Я атакую: {self.table[-1][0]}"

                elif self.phase == "MORE":
                    decision = self._ai_more_or_done()
                    if decision == "AI_MORE":
                        result = self._ai_attack()
                        if result.startswith("ai_attacked"):
                            return f"🤖 Подкидываю: {result.split()[-1]}"
                    # AI_DONE
                    self._ai_end_attack()
                    continue

            elif self.defender == "ai":
                if self.phase == "DEFENSE":
                    result = self._ai_defend()
                    if result == "AI_TAKE":
                        self._ai_take()
                        self._fill_hands()
                        self._next_round()
                        self._sort_hands()
                        self.attacker = "player"
                        self.defender = "ai"
                        self.phase = "ATTACK"
                        return f"📦 Я беру! У меня {len(self.ai_hand)} карт. Твой ход!"
                    if result == "AI_ALL_DEFENDED":
                        self.phase = "MORE"
                        return "🛡️ Я всё отбил! Бито или подкинешь?"
                    if result.startswith("ai_defended"):
                        return f"🛡️ {result}"
                elif self.phase == "MORE":
                    decision = self._ai_more_or_done()
                    if decision == "AI_MORE":
                        result = self._ai_attack()
                        if result.startswith("ai_attacked"):
                            return f"🤖 Подкидываю: {result.split()[-1]}"
                    # AI_DONE
                    self._ai_end_attack()
                    continue

            break

        return self.check_end() or "ok"

    def _ai_end_attack(self):
        """AI завершает атаку (бито)."""
        for a, d in self.table:
            self.discard.append(a)
            if d:
                self.discard.append(d)
        self.table.clear()
        self._fill_hands()
        self.attacker = "player"
        self.defender = "ai"
        self.phase = "ATTACK"
        self._sort_hands()


# ─── HTTP SERVER ───

import http.server
import urllib.parse

game = DurakGame()

class DurakHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send_html()
            return

        if path == "/state":
            state = game.get_state()
            end = game.check_end()
            if end:
                state["game_over"] = end
            self._send_json(state)
            return

        if path == "/new":
            game.new_game()
            state = game.get_state()
            self._send_json({"message": "Новая игра!", **state})
            return

        if path == "/attack":
            idx = int(params.get("idx", [-1])[0])
            msg = game.player_attack(idx)

            if "✅" in msg or "🔄" in msg:
                ai_msg = game.ai_turn()
                self._send_json({"message": msg, "ai_turn": ai_msg, **game.get_state()})
            else:
                self._send_json({"message": msg, **game.get_state()})
            return

        if path == "/defend":
            idx = int(params.get("idx", [-1])[0])
            attack_idx = int(params.get("attack_idx", [-1])[0])
            msg = game.player_defend(idx, attack_idx)

            if msg == "TAKE_OR_MORE":
                self._send_json({"message": "Все отбито! /take или /done?", "phase": "MORE", **game.get_state()})
            elif "✅" in msg:
                # После защиты, проверим нужно ли AI
                if game.phase == "DEFENSE":
                    ai_msg = game.ai_turn()
                    self._send_json({"message": msg, "ai_turn": ai_msg, **game.get_state()})
                else:
                    self._send_json({"message": msg, **game.get_state()})
            else:
                self._send_json({"message": msg, **game.get_state()})
            return

        if path == "/take":
            msg = game.player_take()
            self._send_json({"message": msg, **game.get_state()})
            return

        if path == "/done":
            msg = game.player_done()
            self._send_json({"message": msg, **game.get_state()})
            return

        if path == "/more":
            msg = game.player_more()
            if msg.startswith("🔄"):
                game.phase = "ATTACK"
                self._send_json({"message": msg, **game.get_state()})
            else:
                self._send_json({"message": msg, **game.get_state()})
            return

        self._send_json({"error": "not found"}, 404)

    def _send_html(self):
        html = """
<!DOCTYPE html>
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
.controls { display: flex; gap: 10px; margin: 15px 0; }
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
<div class="cards" id="player-hand">-</div>
</div>

<div class="controls">
<button class="btn-attack" id="btn-attack" onclick="handleAttack()">👊 Атаковать</button>
<button class="btn-defend" id="btn-defend" onclick="handleDefend()">🛡️ Защититься</button>
<button class="btn-take" id="btn-take" onclick="handleTake()">📦 Беру</button>
<button class="btn-done" id="btn-done" onclick="handleDone()">✅ Бито</button>
</div>
<button class="btn-new" onclick="newGame()">🔄 Новая игра</button>

<div class="log" id="log">Добро пожаловать! Нажми «Новая игра» чтобы начать.</div>

<script>
let state = null;
let selectedCard = null;

async function api(path) {
const r = await fetch(path);
return await r.json();
}

async function refresh() {
state = await api('/state');
render();
}

function render() {
if (!state) return;
document.getElementById('trump').textContent = state.trump || '-';
document.getElementById('deck').textContent = state.deck_count;
document.getElementById('ai-count').textContent = state.ai_count;

// Table
const tableDiv = document.getElementById('table');
if (state.table.length === 0) {
tableDiv.innerHTML = '<span style="color:#666">Пусто</span>';
} else {
tableDiv.innerHTML = state.table.map(p =>
`<div class="pair"><span class="card">${p.attack}</span>${p.defense ? '<span class="vs">→</span><span class="card">' + p.defense + '</span>' : ''}</div>`
).join('');
}

// Player hand
const handDiv = document.getElementById('player-hand');
handDiv.innerHTML = (state.player_hand || []).map((c, i) => {
const sel = selectedCard === i ? ' selected' : '';
return `<span class="card${sel}" onclick="selectCard(${i})">${c}</span>`;
}).join('');

// Buttons
const phase = state.phase;
document.getElementById('btn-attack').disabled = !(phase === 'ATTACK' || phase === 'MORE');
document.getElementById('btn-defend').disabled = !(phase === 'DEFENSE');
document.getElementById('btn-take').disabled = !(phase === 'TAKE' || phase === 'DEFENSE');
document.getElementById('btn-done').disabled = !(phase === 'MORE' || phase === 'DEFENSE' || phase === 'DONE');
}

function selectCard(idx) {
if (selectedCard === idx) selectedCard = null;
else selectedCard = idx;
render();
}

async function handleAttack() {
if (selectedCard === null) { log("Выбери карту!"); return; }
const r = await api('/attack?idx=' + selectedCard);
selectedCard = null;
log(r.message);
if (r.ai_turn) log(r.ai_turn);
await refresh();
checkEnd(r);
}

async function handleDefend() {
if (selectedCard === null) { log("Выбери карту!"); return; }
const r = await api('/defend?idx=' + selectedCard);
selectedCard = null;
log(r.message);
if (r.ai_turn) log(r.ai_turn);
await refresh();
checkEnd(r);
}

async function handleTake() {
const r = await api('/take');
log(r.message);
await refresh();
checkEnd(r);
}

async function handleDone() {
const r = await api('/done');
log(r.message);
await refresh();
checkEnd(r);
}

async function newGame() {
const r = await api('/new');
state = r;
selectedCard = null;
log(r.message);
document.getElementById('log').innerHTML = '';
render();
}

function log(msg) {
const logDiv = document.getElementById('log');
logDiv.innerHTML += '<br>' + msg;
logDiv.scrollTop = logDiv.scrollHeight;
}

function checkEnd(r) {
if (r.game_over) {
log(r.game_over);
document.getElementById('btn-attack').disabled = true;
document.getElementById('btn-defend').disabled = true;
document.getElementById('btn-take').disabled = true;
document.getElementById('btn-done').disabled = true;
}
}

refresh();
</script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # тихо


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    game.new_game()
    print(f"🃏 СЕРВЕР ДУРАКА НА ПОРТУ {port}")
    print(f"   Открой http://172.21.0.5:{port}")
    httpd = http.server.HTTPServer(("0.0.0.0", port), DurakHandler)
    httpd.serve_forever()
