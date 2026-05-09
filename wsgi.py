#!/usr/bin/env python3
"""
МУЛЬТИПЛЕЕРНЫЙ ДУРАК — до 4 игроков, комнаты, AI-режим
WSGI-приложение для PythonAnywhere
"""

import sys
import os
import json
import urllib.parse
import random
import uuid
from enum import Enum

# ─── Game Engine ───

class Suit(Enum):
    HEARTS = "♥️"
    DIAMONDS = "♦️"
    CLUBS = "♣️"
    SPADES = "♠️"

RANKS = ["6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
    def __str__(self):
        return f"{self.rank}{self.suit.value}"
    def __repr__(self):
        return self.__str__()
    def beats(self, other, trump):
        if self.suit == other.suit:
            return RANK_VALUES[self.rank] > RANK_VALUES[other.rank]
        return self.suit == trump and other.suit != trump
    def to_dict(self):
        return str(self)
    @classmethod
    def from_str(cls, s):
        rank = s[:-2] if len(s) > 2 else s[:-1]
        suit_str = s[-2:] if len(s) > 2 else s[-1:]
        for suit in Suit:
            if suit.value == suit_str:
                return cls(suit, rank)
        raise ValueError(f"Unknown suit: {suit_str}")

class DurakRoom:
    def __init__(self, room_id, max_players, with_ai=False):
        self.room_id = room_id
        self.max_players = max_players
        self.with_ai = with_ai
        self.players = []  # player indices 0..max_players-1
        self.ai_player_idx = max_players - 1 if with_ai else None
        self.started = False
        self.game_over = False
        self.winner_msg = None
        
        # Game state (like DurakGame)
        self.hands = {}      # player_idx -> [Card]
        self.deck = []
        self.trump = None
        self.table = []      # [(attack_card, defense_card_or_None)]
        self.discard = []
        self.phase = "WAITING"  # WAITING, ATTACK, DEFENSE, MORE, DONE
        self.attacker_idx = 0
        self.defender_idx = 1
        self.turn_order = []  # list of player indices in turn order

    def add_player(self):
        if self.started:
            return "Игра уже началась!"
        if len(self.players) >= self.max_players:
            return "Комната заполнена!"
        idx = len(self.players)
        self.players.append(idx)
        if len(self.players) == self.max_players:
            self._start_game()
        return f"Игрок {idx+1} подключился ({len(self.players)}/{self.max_players})"

    def _start_game(self):
        suits = list(Suit)
        self.deck = [Card(s, r) for s in suits for r in RANKS]
        random.shuffle(self.deck)
        self.trump = self.deck[-1].suit
        self.hands = {}
        for p in self.players:
            self.hands[p] = self.deck[:6]
            self.deck = self.deck[6:]
        self.phase = "ATTACK"
        self.attacker_idx = 0
        self.defender_idx = 1 % len(self.players)
        self.started = True
        self._sort_all()

    def _sort_all(self):
        def key(c):
            return (c.suit.value, RANK_VALUES[c.rank])
        for h in self.hands.values():
            h.sort(key=key)

    def _draw(self, player_idx):
        while len(self.hands[player_idx]) < 6 and self.deck:
            self.hands[player_idx].append(self.deck.pop())
        self._sort_all()

    def _next_player(self, idx):
        return (idx + 1) % len(self.players)

    def _next_round(self):
        # Check win
        for p in self.players:
            if not self.hands[p] and not self.deck:
                self.game_over = True
                if p == self.ai_player_idx:
                    self.winner_msg = f"🤬 Игрок {p+1} (OXI AI) выиграл! Вы все дураки!"
                else:
                    self.winner_msg = f"🎉 Игрок {p+1} выиграл! Остальные — дураки!"
                self.phase = "DONE"
                return
        
        # Defender becomes attacker, attack next player
        self.attacker_idx = self.defender_idx
        self.defender_idx = self._next_player(self.attacker_idx)
        self.phase = "ATTACK"

    def get_state(self, player_idx=None):
        state = {
            "room_id": self.room_id,
            "max_players": self.max_players,
            "with_ai": self.with_ai,
            "ai_player_idx": self.ai_player_idx,
            "players_joined": len(self.players),
            "started": self.started,
            "game_over": self.game_over,
            "winner_msg": self.winner_msg,
            "phase": self.phase,
            "trump": str(self.trump.value) if self.trump else None,
            "deck_count": len(self.deck),
            "table": [{"attack": str(a), "defense": str(d) if d else None} for a, d in self.table],
            "attacker_idx": self.attacker_idx if self.started else None,
            "defender_idx": self.defender_idx if self.started else None,
        }
        if player_idx is not None and self.started:
            state["your_hand"] = [str(c) for c in self.hands[player_idx]]
            state["your_idx"] = player_idx
            state["your_count"] = len(self.hands[player_idx])
            # Show other players' card counts
            state["other_players"] = {}
            for p in self.players:
                if p != player_idx:
                    state["other_players"][str(p)] = len(self.hands[p])
        return state

    def attack(self, player_idx, card_str):
        if self.phase != "ATTACK":
            return "❌ Сейчас не фаза атаки!"
        if player_idx != self.attacker_idx:
            return "❌ Не твоя очередь атаковать!"
        
        # Find card
        card, card_idx = self._find_card(player_idx, card_str)
        if card is None:
            return "❌ У тебя нет такой карты!"

        # If table not empty, can only throw matching ranks
        if self.table:
            valid_ranks = set()
            for a, d in self.table:
                valid_ranks.add(a.rank)
                if d:
                    valid_ranks.add(d.rank)
            if card.rank not in valid_ranks:
                return f"❌ Можно подкидывать только: {', '.join(sorted(valid_ranks))}"

        self.hands[player_idx].pop(card_idx)
        self.table.append((card, None))
        self.phase = "DEFENSE"
        self._sort_all()
        return f"✅ Игрок {player_idx+1} атаковал: {card}. Защищается игрок {self.defender_idx+1}..."

    def defend(self, player_idx, card_str, attack_idx=-1):
        if self.phase != "DEFENSE":
            return "❌ Сейчас не фаза защиты!"
        if player_idx != self.defender_idx:
            return "❌ Не твоя очередь защищаться!"

        # Find last undefended attack
        if attack_idx == -1:
            for i in range(len(self.table) - 1, -1, -1):
                if self.table[i][1] is None:
                    attack_idx = i
                    break
        
        if attack_idx < 0 or attack_idx >= len(self.table):
            return "❌ Неверная атака!"
        if self.table[attack_idx][1] is not None:
            return "❌ Эта атака уже отбита!"

        attack_card = self.table[attack_idx][0]
        card, card_idx = self._find_card(player_idx, card_str)
        if card is None:
            return "❌ У тебя нет такой карты!"
        if not card.beats(attack_card, self.trump):
            return f"❌ {card} не может побить {attack_card}!"

        self.hands[player_idx].pop(card_idx)
        self.table[attack_idx] = (attack_card, card)

        if all(d is not None for _, d in self.table):
            return "ALL_DEFENDED"
        
        self._sort_all()
        return f"✅ Игрок {player_idx+1} побил {attack_card} → {card}!"

    def take(self, player_idx):
        if self.phase != "DEFENSE":
            return "❌ Нечего забирать!"
        if player_idx != self.defender_idx:
            return "❌ Не твоя очередь!"

        for a, d in self.table:
            self.hands[player_idx].append(a)
            if d:
                self.hands[player_idx].append(d)
        self.table.clear()
        self._draw(self.defender_idx)
        self._draw(self.attacker_idx)
        self._next_after_take()
        self._sort_all()
        return f"📦 Игрок {player_idx+1} забрал карты."

    def done(self, player_idx):
        if self.phase not in ("DEFENSE", "MORE"):
            return "❌ Нечего говорить бито!"
        if player_idx != self.defender_idx:
            return "❌ Не твоя очередь!"

        if not all(d is not None for _, d in self.table):
            return "❌ Не все карты отбиты!"

        for a, d in self.table:
            self.discard.append(a)
            if d:
                self.discard.append(d)
        self.table.clear()
        self._draw(self.attacker_idx)
        self._draw(self.defender_idx)
        self._next_round()
        self._sort_all()
        return f"👌 Бито! Ход переходит к игроку {self.attacker_idx+1}."

    def more_attack(self, player_idx, card_str):
        """Any player except defender can throw more cards."""
        if self.phase != "MORE":
            return "❌ Сейчас нельзя подкидывать!"
        if player_idx == self.defender_idx:
            return "❌ Защищающийся не может подкидывать!"
        
        card, card_idx = self._find_card(player_idx, card_str)
        if card is None:
            return "❌ У тебя нет такой карты!"

        valid_ranks = set()
        for a, d in self.table:
            valid_ranks.add(a.rank)
            if d:
                valid_ranks.add(d.rank)
        if card.rank not in valid_ranks:
            return f"❌ Можно подкидывать только: {', '.join(sorted(valid_ranks))}"

        # Can't throw more cards than defender has
        if len(self.hands[self.defender_idx]) <= len([t for t in self.table if t[1] is None]):
            return "❌ У защищающегося не хватит карт!"

        self.hands[player_idx].pop(card_idx)
        self.table.append((card, None))
        self.phase = "DEFENSE"
        self._sort_all()
        return f"✅ Игрок {player_idx+1} подкинул: {card}"

    def pass_more(self, player_idx):
        if self.phase != "MORE":
            return "❌ Сейчас нечего пропускать!"
        if player_idx == self.defender_idx:
            return self.done(player_idx)
        return "ok"

    def _find_card(self, player_idx, card_str):
        for i, c in enumerate(self.hands[player_idx]):
            if str(c) == card_str:
                return c, i
        return None, -1

    def _next_after_take(self):
        # After take, defender keeps being defender
        # Attacker changes to next player
        self.phase = "ATTACK"
        self.attacker_idx = self._next_player(self.attacker_idx)
        if self.attacker_idx == self.defender_idx:
            self.attacker_idx = self._next_player(self.attacker_idx)

    # ─── AI Logic ───
    
    def ai_attack(self):
        """AI (me) makes an attack move."""
        ai = self.ai_player_idx
        if ai is None or self.phase != "ATTACK" or self.attacker_idx != ai:
            return None
        
        if not self.table:
            # First attack — smallest card
            if not self.hands[ai]:
                return None
            card = min(self.hands[ai], key=lambda c: RANK_VALUES[c.rank])
            return str(card), None
        else:
            # Throw more
            valid_ranks = set()
            for a, d in self.table:
                valid_ranks.add(a.rank)
                if d:
                    valid_ranks.add(d.rank)
            for card in sorted(self.hands[ai], key=lambda c: RANK_VALUES[c.rank]):
                if card.rank in valid_ranks:
                    return str(card), None
            return None, "no_more"  # signal: can't throw more

    def ai_defend(self):
        """AI defends."""
        ai = self.ai_player_idx
        if ai is None or self.phase != "DEFENSE" or self.defender_idx != ai:
            return None
        
        # Find undefended attack
        attack_card = None
        attack_idx = -1
        for i, (a, d) in enumerate(self.table):
            if d is None:
                attack_card = a
                attack_idx = i
                break
        
        if attack_card is None:
            return None
        
        # Find smallest card that beats it
        best = None
        for card in self.hands[ai]:
            if card.beats(attack_card, self.trump):
                if best is None or RANK_VALUES[card.rank] < RANK_VALUES[best.rank]:
                    best = card
        
        if best is None:
            return None, "take"  # can't defend
        
        return str(best), None

    def ai_more(self):
        """AI decides: throw more or pass?"""
        ai = self.ai_player_idx
        if ai is None or self.phase != "MORE":
            return None
        
        # Only attack if we're not the defender
        if ai == self.defender_idx:
            return None, "done"
        
        valid_ranks = set()
        for a, d in self.table:
            valid_ranks.add(a.rank)
            if d:
                valid_ranks.add(d.rank)
        
        for card in sorted(self.hands[ai], key=lambda c: RANK_VALUES[c.rank]):
            if card.rank in valid_ranks:
                return str(card), None
        
        return None, "pass"


# ─── Global State ───

rooms = {}  # room_id -> DurakRoom

# ─── WSGI Application ───

def send_json(data, start_response, status='200 OK'):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    headers = [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Access-Control-Allow-Origin', '*'),
    ]
    start_response(status, headers)
    return [body]

def send_html(html, start_response):
    body = html.encode('utf-8')
    headers = [('Content-Type', 'text/html; charset=utf-8')]
    start_response('200 OK', headers)
    return [body]

def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    qs = environ.get('QUERY_STRING', '')
    params = urllib.parse.parse_qs(qs)

    try:
        # ─── Frontend ───
        if path == '/':
            return send_html(FRONTEND, start_response)

        # ─── Create room ───
        if path == '/create':
            max_players = int(params.get('players', [2])[0])
            with_ai = params.get('ai', ['0'])[0] == '1'
            max_players = max(2, min(4, max_players))
            room_id = str(uuid.uuid4())[:8]
            rooms[room_id] = DurakRoom(room_id, max_players, with_ai)
            # If with AI, auto-join AI
            if with_ai:
                rooms[room_id].players.append(max_players - 1)  # AI is last
            return send_json({
                "room_id": room_id,
                "max_players": max_players,
                "with_ai": with_ai,
                "message": "Комната создана! Отправь ID друзьям."
            }, start_response)

        # ─── Join room ───
        if path == '/join':
            room_id = params.get('room', [''])[0]
            room = rooms.get(room_id)
            if not room:
                return send_json({"error": "Комната не найдена!"}, start_response, '404')
            player_nick = params.get('nick', ['Игрок'])[0]
            idx = len([p for p in room.players if p != room.ai_player_idx])
            if idx >= room.max_players - (1 if room.with_ai else 0):
                return send_json({"error": "Комната заполнена!"}, start_response)
            room.players.insert(idx, idx)  # insert before AI if AI present
            # Fix AI index
            if room.with_ai and room.ai_player_idx is not None:
                room.ai_player_idx = len(room.players) - 1
            
            if len(room.players) >= room.max_players:
                room._start_game()
            
            return send_json({
                "player_idx": idx,
                "nick": player_nick,
                "started": room.started,
                "message": f"Подключился! {len(room.players)}/{room.max_players}"
            }, start_response)

        # ─── Get state ───
        if path == '/state':
            room_id = params.get('room', [''])[0]
            player_idx = int(params.get('player', ['-1'])[0])
            room = rooms.get(room_id)
            if not room:
                return send_json({"error": "Комната не найдена!"}, start_response, '404')
            
            # AI auto-play if needed
            if room.with_ai and room.started and not room.game_over:
                _ai_tick(room)
            
            return send_json(room.get_state(player_idx), start_response)

        # ─── Player moves ───
        for action, handler in [
            ('/attack', _handle_attack),
            ('/defend', _handle_defend),
            ('/take', _handle_take),
            ('/done', _handle_done),
            ('/more', _handle_more),
        ]:
            if path == action:
                return handler(params, rooms, start_response)

        return send_json({"error": "not found"}, start_response, '404')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return send_json({"error": str(e)}, start_response, '500')

def _ai_tick(room):
    """Make AI do its moves."""
    ai = room.ai_player_idx
    if ai is None:
        return
    
    for _ in range(10):  # max 10 AI actions per tick
        if room.game_over or room.phase == "DONE":
            return
        
        if room.phase == "ATTACK" and room.attacker_idx == ai:
            result = room.ai_attack()
            if result is None:
                return
            card_str, signal = result
            if signal == "no_more":
                # AI can't throw more — beaten
                for a, d in room.table:
                    room.discard.append(a)
                    if d:
                        room.discard.append(d)
                room.table.clear()
                room._draw(room.attacker_idx)
                room._draw(room.defender_idx)
                room._next_round()
                continue
            if card_str:
                msg = room.attack(ai, card_str)
                continue
        
        elif room.phase == "DEFENSE" and room.defender_idx == ai:
            result = room.ai_defend()
            if result is None:
                return
            card_str, signal = result
            if signal == "take":
                room.take(ai)
                continue
            if card_str:
                msg = room.defend(ai, card_str)
                if msg == "ALL_DEFENDED":
                    room.phase = "MORE"
                continue
        
        elif room.phase == "MORE":
            result = room.ai_more()
            if result is None:
                return
            card_str, signal = result
            if signal == "done":
                room.done(ai)
                continue
            if signal == "pass":
                return
            if card_str:
                room.more_attack(ai, card_str)
                continue
        
        return


def _get_room(params, rooms):
    room_id = params.get('room', [''])[0]
    player_idx = int(params.get('player', ['-1'])[0])
    room = rooms.get(room_id)
    if not room:
        return None, None, (send_json({"error": "Комната не найдена!"}, None, '404'))
    return room, player_idx, None

def _handle_attack(params, rooms, start_response):
    room, player_idx, err = _get_room(params, rooms)
    if err: return err[2]
    card = params.get('card', [''])[0]
    msg = room.attack(player_idx, card)
    # After player attack, AI might need to respond
    if room.with_ai:
        _ai_tick(room)
    return send_json({"message": msg, **room.get_state(player_idx)}, start_response)

def _handle_defend(params, rooms, start_response):
    room, player_idx, err = _get_room(params, rooms)
    if err: return err[2]
    card = params.get('card', [''])[0]
    attack_idx = int(params.get('attack_idx', ['-1'])[0])
    msg = room.defend(player_idx, card, attack_idx)
    if msg == "ALL_DEFENDED":
        room.phase = "MORE"
        if room.with_ai:
            _ai_tick(room)
        return send_json({"message": "Все отбито! Можно подкинуть или бито.", "phase": "MORE", **room.get_state(player_idx)}, start_response)
    if room.with_ai:
        _ai_tick(room)
    return send_json({"message": msg, **room.get_state(player_idx)}, start_response)

def _handle_take(params, rooms, start_response):
    room, player_idx, err = _get_room(params, rooms)
    if err: return err[2]
    msg = room.take(player_idx)
    if room.with_ai:
        _ai_tick(room)
    return send_json({"message": msg, **room.get_state(player_idx)}, start_response)

def _handle_done(params, rooms, start_response):
    room, player_idx, err = _get_room(params, rooms)
    if err: return err[2]
    msg = room.done(player_idx)
    if room.with_ai:
        _ai_tick(room)
    return send_json({"message": msg, **room.get_state(player_idx)}, start_response)

def _handle_more(params, rooms, start_response):
    room, player_idx, err = _get_room(params, rooms)
    if err: return err[2]
    card = params.get('card', [''])[0]
    if card:
        msg = room.more_attack(player_idx, card)
    else:
        msg = room.pass_more(player_idx)
    if room.with_ai:
        _ai_tick(room)
    return send_json({"message": msg, **room.get_state(player_idx)}, start_response)


# ─── Frontend HTML ───

FRONTEND = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ДУРАК — Мультиплеер</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Courier New',monospace;background:#1a1a2e;color:#e0e0e0;max-width:600px;margin:0 auto;padding:20px}
h1{text-align:center;color:#e94560;font-size:22px;margin-bottom:10px}
h2{font-size:14px}
.panel{background:#16213e;border-radius:10px;padding:15px;margin:10px 0}
.cards{display:flex;flex-wrap:wrap;gap:8px}
.card{background:#fff;color:#000;padding:10px 14px;border-radius:8px;font-size:20px;cursor:pointer;transition:all .2s;border:2px solid transparent}
.card:hover{border-color:#e94560;transform:scale(1.05)}
.card.selected{border-color:#e94560;background:#ffe0e0}
.table-area{background:#0f3460;border-radius:10px;padding:15px;margin:10px 0}
.table-cards{display:flex;flex-wrap:wrap;gap:12px}
.pair{display:flex;align-items:center;gap:8px}
.pair .vs{color:#e94560;font-weight:bold}
.info{display:flex;justify-content:space-between;background:#0f3460;border-radius:10px;padding:10px 15px;margin:10px 0;font-size:14px}
.controls{display:flex;gap:10px;margin:15px 0;flex-wrap:wrap}
button{padding:10px 20px;border:none;border-radius:5px;cursor:pointer;font-size:14px;font-weight:bold;transition:.2s}
.btn-attack{background:#e94560;color:#fff}
.btn-defend{background:#0f3460;color:#e94560;border:2px solid #e94560}
.btn-take{background:#ffa500;color:#000}
.btn-done{background:#00cc66;color:#000}
.btn-new{background:#e94560;color:#fff;width:100%}
.btn-join{background:#0f3460;color:#e94560;border:2px solid #e94560}
button:disabled{opacity:.4;cursor:not-allowed}
.log{background:#000;border-radius:10px;padding:10px;margin:10px 0;max-height:150px;overflow-y:auto;font-size:13px;color:#00ff88}
input{padding:8px;border-radius:5px;border:1px solid #0f3460;background:#16213e;color:#e0e0e0;width:100%;margin:5px 0}
.highlight-box{border:2px solid #e94560!important}
</style>
</head>
<body>
<h1>🃏 ДУРАК — МУЛЬТИПЛЕЕР 🃏</h1>

<div id="lobby" class="panel">
<h2>🏠 ЛОББИ</h2>
<label><input type="checkbox" id="with-ai"> Играть против OXI (AI)</label><br>
<label>Игроков (включая AI): 
<select id="players-count"><option>2</option><option>3</option><option selected>4</option></select></label><br>
<button class="btn-new" onclick="createRoom()">🎮 Создать комнату</button>
<div style="margin-top:10px">
<input id="room-id-input" placeholder="Room ID...">
<button class="btn-join" onclick="joinRoom()">🚪 Подключиться</button>
</div>
</div>

<div id="game" style="display:none">
<div class="info">
<span>🃏 Козырь: <b id="trump">-</b></span>
<span>🎴 В колоде: <b id="deck">0</b></span>
<span>👥 Игроков: <b id="players-online">0</b></span>
</div>

<div class="panel" id="other-players"></div>

<div class="table-area">
<h2>🟫 СТОЛ</h2>
<div class="table-cards" id="table">-</div>
<div style="margin-top:5px;font-size:13px;color:#e94560" id="turn-info"></div>
</div>

<div class="panel">
<h2>🖐️ ТВОЯ РУКА</h2>
<div class="cards" id="hand"></div>
</div>

<div class="controls">
<button class="btn-attack" id="btn-attack">⚔️ Атаковать</button>
<button class="btn-defend" id="btn-defend">🛡️ Отбить</button>
<button class="btn-take" id="btn-take">📦 Забрать</button>
<button class="btn-done" id="btn-done">👌 Бито</button>
</div>

<div class="log" id="log"></div>
</div>

<script>
let ROOM = null;
let PLAYER = null;
let selectedCard = null;
let pollTimer = null;

async function api(path) {
    const r = await fetch(path);
    return await r.json();
}

async function createRoom() {
    const ai = document.getElementById('with-ai').checked ? '1' : '0';
    const players = document.getElementById('players-count').value;
    const d = await api('/create?players=' + players + '&ai=' + ai);
    if (d.error) { alert(d.error); return; }
    ROOM = d.room_id;
    PLAYER = 0;
    document.getElementById('room-id-input').value = ROOM;
    document.getElementById('lobby').style.display = 'none';
    document.getElementById('game').style.display = 'block';
    log('🎮 Комната создана! ID: ' + ROOM + ' (игроков: ' + players + ', AI: ' + (ai==='1'?'да':'нет') + ')');
    startPolling();
}

async function joinRoom() {
    const room = document.getElementById('room-id-input').value.trim();
    if (!room) { alert('Введи ID комнаты!'); return; }
    const d = await api('/state?room=' + room + '&player=-1');
    if (d.error) { alert(d.error); return; }
    
    // Join
    const j = await api('/join?room=' + room);
    if (j.error) { alert(j.error); return; }
    ROOM = room;
    PLAYER = j.player_idx;
    document.getElementById('lobby').style.display = 'none';
    document.getElementById('game').style.display = 'block';
    log('🚪 Подключился как игрок ' + (PLAYER+1));
    startPolling();
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refresh, 2000);
    refresh();
}

async function refresh() {
    if (!ROOM) return;
    const s = await api('/state?room=' + ROOM + '&player=' + PLAYER);
    if (s.error) return;
    
    document.getElementById('trump').textContent = s.trump || '-';
    document.getElementById('deck').textContent = s.deck_count;
    document.getElementById('players-online').textContent = s.players_joined + '/' + s.max_players;
    
    if (s.game_over) {
        log('🏁 ' + s.winner_msg);
        document.getElementById('hand').innerHTML = '';
        document.getElementById('table').innerHTML = '-';
        return;
    }
    
    if (!s.started) {
        document.getElementById('hand').innerHTML = 'Ожидание игроков...';
        document.getElementById('table').innerHTML = '-';
        document.getElementById('other-players').innerHTML = 'Ожидание... (' + s.players_joined + '/' + s.max_players + ')';
        return;
    }
    
    renderTable(s.table);
    renderHand(s);
    renderOtherPlayers(s);
    toggleButtons(s);
    updateTurnInfo(s);
}

function renderTable(table) {
    const el = document.getElementById('table');
    if (!table.length) { el.textContent = '-'; return; }
    el.innerHTML = table.map(t => 
        '<div class="pair"><span>' + t.attack + '</span><span class="vs">vs</span><span>' + (t.defense || '❓') + '</span></div>'
    ).join('');
}

function renderHand(s) {
    const el = document.getElementById('hand');
    if (!s.your_hand) { el.innerHTML = ''; return; }
    el.innerHTML = s.your_hand.map((c,i) => 
        '<div class="card' + (selectedCard === c ? ' selected' : '') + '" onclick="selectCard(\'' + c + '\')">' + c + '</div>'
    ).join('');
}

function renderOtherPlayers(s) {
    const el = document.getElementById('other-players');
    let html = '<h2>👥 ИГРОКИ</h2>';
    if (s.other_players) {
        for (const [pid, count] of Object.entries(s.other_players)) {
            const marker = parseInt(pid) === s.attacker_idx ? ' ⚔️' : (parseInt(pid) === s.defender_idx ? ' 🛡️' : '');
            const aiLabel = parseInt(pid) === s.ai_player_idx ? ' 🤖OXI' : '';
            html += '<div>Игрок ' + (parseInt(pid)+1) + aiLabel + ': ' + count + ' карт' + marker + '</div>';
        }
    }
    el.innerHTML = html;
}

function updateTurnInfo(s) {
    const el = document.getElementById('turn-info');
    el.textContent = s.phase === 'ATTACK' ? '⚔️ Атакует игрок ' + (s.attacker_idx+1) :
                     s.phase === 'DEFENSE' ? '🛡️ Защищается игрок ' + (s.defender_idx+1) :
                     s.phase === 'MORE' ? '🔄 Подкидывайте или бито' : '';
}

function selectCard(c) {
    selectedCard = selectedCard === c ? null : c;
    refresh();
}

function toggleButtons(s) {
    const atk = document.getElementById('btn-attack');
    const def = document.getElementById('btn-defend');
    const take = document.getElementById('btn-take');
    const done = document.getElementById('btn-done');
    [atk, def, take, done].forEach(b => b.disabled = true);
    
    if (s.game_over) return;
    
    const isMyTurn = s.attacker_idx === PLAYER || s.defender_idx === PLAYER;
    
    if (s.phase === 'ATTACK' && s.attacker_idx === PLAYER) atk.disabled = false;
    if (s.phase === 'DEFENSE' && s.defender_idx === PLAYER) def.disabled = false;
    if (s.phase === 'DEFENSE' && s.defender_idx === PLAYER) take.disabled = false;
    if ((s.phase === 'DEFENSE' || s.phase === 'MORE') && s.defender_idx === PLAYER) done.disabled = false;
}

async function doAction(url) {
    const d = await api(url);
    log('📝 ' + d.message);
    selectedCard = null;
    await refresh();
}

function log(msg) {
    document.getElementById('log').innerHTML = msg + '<br>' + document.getElementById('log').innerHTML;
}

document.getElementById('btn-attack').onclick = () => {
    if (!selectedCard) { log('Выбери карту!'); return; }
    doAction('/attack?room=' + ROOM + '&player=' + PLAYER + '&card=' + encodeURIComponent(selectedCard));
};

document.getElementById('btn-defend').onclick = () => {
    if (!selectedCard) { log('Выбери карту!'); return; }
    doAction('/defend?room=' + ROOM + '&player=' + PLAYER + '&card=' + encodeURIComponent(selectedCard));
};

document.getElementById('btn-take').onclick = () => doAction('/take?room=' + ROOM + '&player=' + PLAYER);
document.getElementById('btn-done').onclick = () => doAction('/done?room=' + ROOM + '&player=' + PLAYER);
</script>
</body>
</html>"""
