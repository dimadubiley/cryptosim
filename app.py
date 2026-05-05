from flask import Flask, render_template, jsonify, request
import random
import math
import threading
import json
import os
import base64
import time
from datetime import datetime

app = Flask(__name__)

# ─── Global in-memory state ───────────────────────────────────────────────────
_state = None
_lock = threading.Lock()
DATA_FILE = "save_data.json"

# ─── Exchange configs ─────────────────────────────────────────────────────────

EXCHANGES = {
    "exchange1": {
        "name": "NovaCrypt",
        "coin": "NVC",
        "personality": "stable",
        "description": "Low-volatility institutional market",
        "base_price": 100.0,
        "volatility": 0.008,
        "drift": 0.0001,
        "color": "#00d4aa",
        "region": "Europe",
    },
    "exchange2": {
        "name": "PulseX",
        "coin": "PLX",
        "personality": "volatile",
        "description": "High-frequency speculative exchange",
        "base_price": 50.0,
        "volatility": 0.035,
        "drift": 0.0003,
        "color": "#ff6b35",
        "region": "Iran",
    },
    "exchange3": {
        "name": "ChaosDAO",
        "coin": "CDX",
        "personality": "chaotic",
        "description": "Memecoin / chaos market with wild swings",
        "base_price": 10.0,
        "volatility": 0.07,
        "drift": -0.0002,
        "color": "#c77dff",
        "region": "Asia",
    },
}

EVENT_POOL = [
    {"name": "Whale Dump",            "magnitude": -0.18, "duration": 3, "probability": 0.003},
    {"name": "Whale Buy",             "magnitude":  0.20, "duration": 3, "probability": 0.003},
    {"name": "Exchange Hack",         "magnitude": -0.30, "duration": 5, "probability": 0.001},
    {"name": "Institutional Buy",     "magnitude":  0.25, "duration": 4, "probability": 0.002},
    {"name": "Regulatory Crackdown",  "magnitude": -0.22, "duration": 6, "probability": 0.002},
    {"name": "Partnership Announced", "magnitude":  0.15, "duration": 3, "probability": 0.004},
    {"name": "Flash Crash",           "magnitude": -0.40, "duration": 2, "probability": 0.001},
    {"name": "Hype Cycle",            "magnitude":  0.35, "duration": 5, "probability": 0.002},
    {"name": "Miner Capitulation",    "magnitude": -0.12, "duration": 4, "probability": 0.003},
    {"name": "Network Upgrade",       "magnitude":  0.18, "duration": 3, "probability": 0.003},
    {"name": "Iran Water Crisis",     "magnitude": -0.08, "duration": 5, "probability": 0.004},
    {"name": "Energy Cost Spike",     "magnitude": -0.06, "duration": 4, "probability": 0.005},
    {"name": "Flood Season",          "magnitude":  0.03, "duration": 3, "probability": 0.006},
    {"name": "Grid Blackout",         "magnitude": -0.10, "duration": 2, "probability": 0.004},
]

WEATHER_MODIFIERS = {
    "Europe": lambda t: 0.001 * math.sin(t / 200),
    "Iran":   lambda t: -0.002 * abs(math.sin(t / 150)) + 0.001 * random.gauss(0, 1),
    "Asia":   lambda t: 0.003 * math.cos(t / 100) * random.choice([-1, 1]),
}

# ─── Persistence ─────────────────────────────────────────────────────────────

def init_state():
    state = {
        "wallet": {"USD": 100.0},
        "holdings": {eid: 0.0 for eid in EXCHANGES},
        "trade_history": [],
        "total_invested": 0.0,
        "tick": 0,
        "markets": {},
        "profile": {
            "name": "Anonymous Trader",
            "avatar": None,  # base64 string or None
        },
    }
    for eid, ex in EXCHANGES.items():
        state["markets"][eid] = {
            "price": ex["base_price"],
            "history": [ex["base_price"]] * 60,
            "active_event": None,
            "event_ticks_left": 0,
            "daily_open": ex["base_price"],
            "tick_phase": random.uniform(0, 6.28),
        }
    return state


def load_state():
    global _state
    if _state is not None:
        return _state

    # Try loading from file
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                saved = json.loads(content)
                # Merge saved data into fresh state (in case structure changed)
                state = init_state()
                state["wallet"] = saved.get("wallet", state["wallet"])
                state["holdings"] = saved.get("holdings", state["holdings"])
                state["trade_history"] = saved.get("trade_history", [])
                state["total_invested"] = saved.get("total_invested", 0.0)
                state["tick"] = saved.get("tick", 0)
                state["profile"] = saved.get("profile", state["profile"])
                # Restore market prices from saved (keep history fresh)
                for eid in EXCHANGES:
                    if eid in saved.get("markets", {}):
                        saved_market = saved["markets"][eid]
                        state["markets"][eid]["price"] = saved_market.get("price", EXCHANGES[eid]["base_price"])
                        state["markets"][eid]["daily_open"] = saved_market.get("daily_open", EXCHANGES[eid]["base_price"])
                        state["markets"][eid]["history"] = saved_market.get("history", state["markets"][eid]["history"])
                _state = state
                return _state
        except Exception:
            pass

    _state = init_state()
    return _state


def save_state(state):
    global _state
    _state = state


def persist_to_disk(state):
    """Write state to disk safely. Called by background thread and on trades."""
    try:
        data = json.dumps(state, ensure_ascii=False)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        # Windows-safe replace
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        os.rename(tmp, DATA_FILE)
    except Exception:
        pass  # Never crash the server over a save failure


# ─── Background autosave thread ──────────────────────────────────────────────

def autosave_loop():
    while True:
        time.sleep(30)  # save every 30 seconds
        with _lock:
            if _state is not None:
                persist_to_disk(_state)

_autosave_thread = threading.Thread(target=autosave_loop, daemon=True)
_autosave_thread.start()


# ─── Market simulation ────────────────────────────────────────────────────────

def simulate_tick(state):
    state["tick"] += 1
    t = state["tick"]

    for eid, ex in EXCHANGES.items():
        market = state["markets"][eid]
        price = market["price"]
        phase = market["tick_phase"]

        vol = ex["volatility"]
        drift = ex["drift"]
        rand_component = random.gauss(0, vol)

        if ex["personality"] == "stable":
            reversion = (ex["base_price"] - price) * 0.002
            delta = drift + rand_component * 0.6 + reversion

        elif ex["personality"] == "volatile":
            momentum = (price - market["history"][-1]) * 0.3 if len(market["history"]) > 1 else 0
            delta = drift + rand_component + momentum * 0.2

        else:  # chaotic
            sine = 0.01 * math.sin(t / 30 + phase) + 0.005 * math.cos(t / 13 + phase * 1.7)
            delta = drift + rand_component * 1.2 + sine

        weather = WEATHER_MODIFIERS[ex["region"]](t)
        delta += weather

        if market["event_ticks_left"] > 0:
            ev = market["active_event"]
            event_push = ev["magnitude"] * 0.15 * (1 + random.gauss(0, 0.3))
            delta += event_push
            market["event_ticks_left"] -= 1
            if market["event_ticks_left"] == 0:
                market["active_event"] = None
        else:
            for ev in EVENT_POOL:
                if random.random() < ev["probability"]:
                    market["active_event"] = ev
                    market["event_ticks_left"] = ev["duration"]
                    break

        new_price = max(0.01, price * (1 + delta))

        if ex["personality"] == "chaotic" and random.random() < 0.005:
            new_price *= random.uniform(0.7, 1.5)

        market["price"] = round(new_price, 6)

        market["history"].append(market["price"])
        if len(market["history"]) > 120:
            market["history"] = market["history"][-120:]

        if t % 300 == 0:
            market["daily_open"] = market["price"]

    return state


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html", exchanges=EXCHANGES)


@app.route("/exchange/<eid>")
def exchange(eid):
    if eid not in EXCHANGES:
        return "Not found", 404
    return render_template("exchange.html", eid=eid, ex=EXCHANGES[eid], exchanges=EXCHANGES)


@app.route("/profile")
def profile():
    return render_template("profile.html", exchanges=EXCHANGES)


@app.route("/api/tick")
def api_tick():
    with _lock:
        state = load_state()
        state = simulate_tick(state)
        save_state(state)

    result = {}
    for eid, market in state["markets"].items():
        history = market["history"]
        avg = sum(history[-300:]) / len(history[-300:])
        prev = history[-2] if len(history) >= 2 else market["price"]
        change = (market["price"] - prev) / prev if prev else 0
        result[eid] = {
            "price": market["price"],
            "history": history[-80:],
            "avg": round(avg, 6),
            "change": round(change, 6),
            "daily_open": market["daily_open"],
            "event": market["active_event"]["name"] if market["active_event"] else None,
            "event_ticks": market["event_ticks_left"],
        }
    return jsonify({"markets": result, "tick": state["tick"]})


@app.route("/api/state")
def api_state():
    with _lock:
        state = load_state()

    wallet = state["wallet"]["USD"]
    holdings = state["holdings"]

    portfolio_value = wallet
    for eid, qty in holdings.items():
        price = state["markets"][eid]["price"]
        portfolio_value += qty * price

    return jsonify({
        "wallet": round(wallet, 4),
        "holdings": {k: round(v, 8) for k, v in holdings.items()},
        "portfolio_value": round(portfolio_value, 4),
        "trade_history": state["trade_history"][-50:],
        "total_invested": state.get("total_invested", 0),
        "profile": state.get("profile", {"name": "Anonymous Trader", "avatar": None}),
    })


@app.route("/api/trade", methods=["POST"])
def api_trade():
    data = request.json
    eid = data.get("exchange")
    action = data.get("action")
    amount_usd = float(data.get("amount", 0))

    if eid not in EXCHANGES or action not in ("buy", "sell") or amount_usd <= 0:
        return jsonify({"ok": False, "msg": "Invalid trade parameters"})

    with _lock:
        state = load_state()
        market = state["markets"][eid]
        price = market["price"]
        wallet = state["wallet"]["USD"]
        holdings = state["holdings"]

        if action == "buy":
            fee = amount_usd * 0.001
            total_cost = amount_usd + fee
            if total_cost > wallet:
                return jsonify({"ok": False, "msg": "Insufficient USD balance"})
            qty = amount_usd / price
            state["wallet"]["USD"] -= total_cost
            holdings[eid] = holdings.get(eid, 0) + qty
            state["total_invested"] = state.get("total_invested", 0) + amount_usd

        else:  # sell
            sell_qty = amount_usd / price
            if sell_qty > holdings.get(eid, 0):
                sell_qty = holdings.get(eid, 0)
            if sell_qty <= 0:
                return jsonify({"ok": False, "msg": "No holdings to sell"})
            proceeds = sell_qty * price
            fee = proceeds * 0.001
            state["wallet"]["USD"] += proceeds - fee
            holdings[eid] = holdings.get(eid, 0) - sell_qty
            amount_usd = proceeds
            qty = sell_qty

        trade = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "exchange": EXCHANGES[eid]["name"],
            "coin": EXCHANGES[eid]["coin"],
            "action": action,
            "amount_usd": round(amount_usd, 4),
            "price": round(price, 6),
            "qty": round(qty, 8),
        }
        state["trade_history"].append(trade)
        save_state(state)
        persist_to_disk(state)  # save immediately on every trade

    return jsonify({
        "ok": True,
        "trade": trade,
        "wallet": round(state["wallet"]["USD"], 4)
    })


@app.route("/api/profile", methods=["POST"])
def api_profile():
    data = request.json
    name = data.get("name", "").strip()
    avatar = data.get("avatar")  # base64 data URL or None

    if not name:
        return jsonify({"ok": False, "msg": "Name cannot be empty"})
    if len(name) > 32:
        return jsonify({"ok": False, "msg": "Name too long (max 32 chars)"})

    with _lock:
        state = load_state()
        state["profile"]["name"] = name
        if avatar is not None:
            # Accept data URLs like "data:image/png;base64,..."
            state["profile"]["avatar"] = avatar
        save_state(state)
        persist_to_disk(state)

    return jsonify({"ok": True, "profile": state["profile"]})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    global _state
    with _lock:
        # Keep profile when resetting game
        old_profile = _state.get("profile", {"name": "Anonymous Trader", "avatar": None}) if _state else {"name": "Anonymous Trader", "avatar": None}
        _state = init_state()
        _state["profile"] = old_profile
        persist_to_disk(_state)
    return jsonify({"ok": True})


if __name__ == "__main__":
    load_state()  # load from disk on startup
    app.run(debug=True, port=5000)