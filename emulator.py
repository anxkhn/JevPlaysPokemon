"""FireRed ROM runner backed by mGBA and PokéBot's RAM/menu adapter."""
import argparse
import json
import sys
import os
import io
import time
import threading
import subprocess
import traceback
import wave
import queue
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor/pokebot-gen3"
sys.path.insert(0, str(VENDOR))


def load_env(path=ROOT / ".env"):
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name, value)

from modules.context import context
from modules.game import set_rom
from modules.libmgba import LibmgbaEmulator
from modules.profiles import Profile
from modules.roms import load_rom_data
from modules.save_import import get_state_data_from_png
from modules.memory import set_event_flag, get_game_state, GameState, get_game_state_symbol, read_symbol, write_symbol, get_save_block, write_to_save_block
from modules.debug_utilities import debug_create_pokemon, debug_write_party
from modules.pokemon import get_species_by_name, get_move_by_name, LearnedMove, get_nature_by_name, StatsValues, StatusCondition
from modules.items import get_item_by_name
from modules.pokemon_party import get_party
from modules.battle_state import battle_is_active, get_battle_state
from modules.battle_handler import handle_battle
import modules.battle_handler as battle_handler
from modules.menuing import scroll_to_party_menu_index, get_current_party_menu_index
from modules.battle_menuing import scroll_to_battle_action
from modules.battle_action_selection import battle_action_use_move
from modules.battle_state import get_battle_controller_callback, get_main_battle_callback
from modules.battle_strategies.default import DefaultBattleStrategy
from modules.battle_strategies import TurnAction
from modules.battle_strategies._util import BattleStrategyUtil
from modules.tasks import task_is_active
from modules.player import get_player_avatar
from modules.modes.util.higher_level_actions import fly_to, talk_to_npc
from modules.modes.util.walking import navigate_to
from modules.region_map import FlyDestinationFRLG
from modules.map_data import MapFRLG

DATA = ROOT / "emulator-data"
TRAINERS = {"lorelei": 410, "bruno": 411, "agatha": 412, "lance": 413, "champion": 440}
FRAME_HOOK = None


def select_living_party_member(personality):
    for _ in range(1200):
        if get_game_state() == GameState.PARTY_MENU:
            break
        yield
    else:
        raise RuntimeError("Party menu did not open.")
    for _ in range(30):
        yield
    index = next(i for i, p in enumerate(get_party()) if p.personality_value == personality)
    if get_party()[index].current_hp <= 0:
        raise RuntimeError("Refusing to select a fainted Pokémon.")
    yield from scroll_to_party_menu_index(index)
    selected = get_party()[get_current_party_menu_index()]
    if selected.personality_value != personality or selected.current_hp <= 0:
        raise RuntimeError("Party cursor does not match the chosen living Pokémon.")
    for _ in range(600):
        if get_game_state() != GameState.PARTY_MENU:
            return
        context.emulator.press_button("A")
        yield
    raise RuntimeError("Could not confirm selected Pokémon.")


def handle_action_selection(strategy):
    while battle_is_active() and get_main_battle_callback() in ("HandleTurnActionSelectionState", "sub_8012324"):
        callback = get_battle_controller_callback(0)
        if callback not in ("HandleInputChooseAction", "sub_802C098", "bx_battle_menu_t6_2"):
            if callback in ("HandleInputChooseMove", "HandleAction_ChooseMove"):
                context.emulator.press_button("B")
            yield
            continue
        battle = get_battle_state()
        action, index = strategy.decide_turn(battle)
        if action == TurnAction.UseMove:
            yield from battle_action_use_move(action, 0, index, battle)
        elif action == TurnAction.RotateLead:
            target = get_party()[index]
            if target.current_hp <= 0:
                raise RuntimeError("Refusing to switch to a fainted Pokémon.")
            personality = target.personality_value
            yield from scroll_to_battle_action(2)
            context.emulator.press_button("A")
            yield
            yield from select_living_party_member(personality)
        else:
            raise RuntimeError("Unsupported battle action.")


def handle_fainted_replacement(strategy):
    battle = get_battle_state()
    chosen = strategy.choose_new_lead_after_faint(battle)
    if get_party()[chosen].current_hp <= 0:
        raise RuntimeError("Refusing a fainted Pokémon before opening replacement menu.")
    personality = get_party()[chosen].personality_value
    for _ in range(1200):
        if get_game_state() == GameState.PARTY_MENU:
            break
        if not battle_is_active():
            return
        context.emulator.press_button("A")
        yield
    else:
        raise RuntimeError("Replacement menu did not open.")
    for _ in range(30):
        yield
    # FireRed reorders its party on menu entry. Identify the selected Pokémon,
    # rather than applying the adapter's stale battle-slot mapping.
    index = next(i for i, p in enumerate(get_party()) if p.personality_value == personality)
    if get_party()[index].current_hp <= 0:
        raise RuntimeError("Refusing to select a fainted replacement.")
    yield from scroll_to_party_menu_index(index)
    selected = get_party()[get_current_party_menu_index()]
    if selected.personality_value != personality or selected.current_hp <= 0:
        raise RuntimeError("Replacement cursor does not match the chosen living Pokémon.")
    for _ in range(600):
        if get_game_state() != GameState.PARTY_MENU:
            strategy.pending_switch = personality
            return
        context.emulator.press_button("A")
        yield
    raise RuntimeError("Could not confirm replacement Pokémon.")


def initialise():
    load_env()
    battle_handler.handle_fainted_pokemon = handle_fainted_replacement
    battle_handler.handle_battle_action_selection = handle_action_selection
    DATA.mkdir(exist_ok=True)
    rom = load_rom_data(ROOT / "Pokemon - Fire Red Version (U) (V1.1).gba")
    context.profile = Profile(rom, DATA, datetime.now())
    set_rom(rom)
    context.testing = True
    context.emulator = LibmgbaEmulator(context.profile, lambda: None, is_test_run=True)
    context.emulator.set_audio_enabled(False)
    context.emulator.set_video_enabled(True)
    context.emulator.set_throttle(False)
    context.bot_mode = "Jev"


def tick():
    context.frame += 1
    context.emulator.run_single_frame()
    if FRAME_HOOK:
        FRAME_HOOK()


def drive(generator, limit=20000):
    for count, _ in enumerate(generator):
        tick()
        if count % 600 == 0 and FRAME_HOOK is None:
            avatar = get_player_avatar()
            print(count, get_game_state(), avatar.map_group_and_number, avatar.local_coordinates, flush=True)
        if count >= limit:
            context.emulator.get_screenshot().save(DATA / "stalled.png")
            raise RuntimeError("Emulator action exceeded frame limit")


def prepare():
    fixture = VENDOR / "tests/states/firered/in_front_of_player_house_after_getting_starter.ss1"
    with fixture.open("rb") as file:
        state, save = get_state_data_from_png(file)
    context.emulator.load_save_game(save)
    context.emulator.load_save_state(state)
    tick()
    for badge in range(1, 9):
        set_event_flag(f"BADGE{badge:02}_GET", True)
    set_event_flag("WORLD_MAP_INDIGO_PLATEAU_EXTERIOR", True)
    debug_write_party([debug_create_pokemon(get_species_by_name("Charizard"), 60,
        moves=[LearnedMove.create(get_move_by_name("Fly"))])])
    tick()
    drive(fly_to(FlyDestinationFRLG.IndigoPlateau))
    drive(navigate_to(MapFRLG.INDIGO_PLATEAU_EXTERIOR, (11, 6)))
    for _ in range(180):
        tick()
    drive(navigate_to(MapFRLG.INDIGO_PLATEAU_POKEMON_CENTER_1F, (4, 1)))
    for _ in range(240):
        context.emulator.press_button("B")
        tick()
    drive(navigate_to(MapFRLG.POKEMON_LEAGUE_LORELEIS_ROOM, (6, 6)))
    for _ in range(60):
        tick()
    (DATA / "league.state").write_bytes(context.emulator.get_save_state())
    (DATA / "league.sav").write_bytes(context.emulator.read_save_data())
    context.emulator.get_screenshot().save(DATA / "league.png")
    print("Prepared League checkpoint", flush=True)


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object.")
    if not isinstance(config.get("auto_advance", False), bool):
        raise ValueError("auto_advance must be true or false.")
    if config.get("opponent_party") and config.get("auto_advance"):
        raise ValueError("Turn off automatic progression when using a custom opponent team.")
    if config.get("game") != "firered-v1.1":
        raise ValueError("This ROM adapter supports FireRed USA v1.1 only.")
    if config.get("opponent") not in TRAINERS:
        raise ValueError("Choose one of the five trainer presets.")
    if config.get("agent") not in ("jev", "baseline"):
        raise ValueError("Agent must be jev or baseline.")
    if config.get("battle_style") not in ("set", "shift"):
        raise ValueError("Battle style must be set or shift.")
    if config.get("speed") not in (1, 2, 4, 0):
        raise ValueError("Speed must be 1, 2, 4, or 0 for unthrottled testing.")
    if type(config.get("max_decisions")) is not int or not 1 <= config["max_decisions"] <= 500:
        raise ValueError("Decision limit must be between 1 and 500.")
    for name in ("party", "opponent_party"):
        party = config.get(name)
        if party is None and name == "opponent_party":
            continue
        if not isinstance(party, list) or not 1 <= len(party) <= 6:
            raise ValueError(f"{name} must contain 1 to 6 Pokémon.")
        alive = False
        for pokemon in party:
            species = get_species_by_name(pokemon["species"])
            if species.national_dex_number < 1 or species.national_dex_number > 386:
                raise ValueError("Choose a Generation 1-3 species.")
            if type(pokemon.get("level")) is not int or not 1 <= pokemon["level"] <= 100:
                raise ValueError("Levels must be integers from 1 to 100.")
            moves = pokemon.get("moves")
            if not isinstance(moves, list) or not 1 <= len(moves) <= 4 or len(set(moves)) != len(moves):
                raise ValueError("Each Pokémon needs 1 to 4 distinct moves.")
            for move in moves:
                get_move_by_name(move)
            get_nature_by_name(pokemon.get("nature", "Hardy"))
            if pokemon.get("item"):
                get_item_by_name(pokemon["item"])
            if pokemon.get("ability") and pokemon["ability"] not in [a.name for a in species.abilities]:
                raise ValueError(f"Invalid ability for {species.name}.")
            for stat_set, default, cap in (("ivs", 31, 31), ("evs", 0, 255)):
                stats = pokemon.get(stat_set, {})
                for stat in ("hp", "attack", "defence", "speed", "special_attack", "special_defence"):
                    value = stats.get(stat, default)
                    if type(value) is not int or not 0 <= value <= cap:
                        raise ValueError(f"Invalid {stat_set} {stat}.")
                if stat_set == "evs" and sum(stats.values()) > 510:
                    raise ValueError("Total EVs must be at most 510.")
            hp = pokemon.get("current_hp")
            if hp is not None and (type(hp) is not int or hp < 0):
                raise ValueError("current_hp must be a nonnegative integer.")
            StatusCondition[pokemon.get("status", "Healthy")]
            alive |= hp is None or hp > 0
        if not alive:
            raise ValueError(f"{name} needs at least one Pokémon with HP.")
    return config


def make_party(entries):
    result = []
    for entry in entries:
        species = get_species_by_name(entry["species"])
        result.append(debug_create_pokemon(species, entry["level"],
            moves=[LearnedMove.create(get_move_by_name(move)) for move in entry["moves"]],
            nature=get_nature_by_name(entry.get("nature", "Hardy")),
            held_item=get_item_by_name(entry["item"]) if entry.get("item") else None,
            has_second_ability=len(species.abilities) > 1 and entry.get("ability") == species.abilities[1].name,
            ivs=StatsValues(**{key: entry.get("ivs", {}).get(key, 31) for key in StatsValues.__dataclass_fields__}),
            evs=StatsValues(**{key: entry.get("evs", {}).get(key, 0) for key in StatsValues.__dataclass_fields__}),
            current_hp=entry.get("current_hp"), status_condition=StatusCondition[entry.get("status", "Healthy")]))
    return result


def describe(pokemon):
    in_battle = hasattr(pokemon, "status_permanent")
    result = {"species": pokemon.species.name, "level": pokemon.level,
        "hp": pokemon.current_hp, "max_hp": pokemon.total_hp,
        "types": [t.name for t in (pokemon.types if in_battle else pokemon.species.types)],
        "ability": pokemon.ability.name, "item": pokemon.held_item.name if pokemon.held_item else None,
        "status": (pokemon.status_permanent if in_battle else pokemon.status_condition).name,
        "stats": asdict(pokemon.stats),
        "moves": [{"name": m.move.name, "pp": m.pp, "type": m.move.type.name,
            "category": m.move.type.kind if m.move.base_power else "Status", "power": m.move.base_power,
            "accuracy": m.move.accuracy, "effect": m.move.effect} for m in pokemon.moves if m is not None]}
    if in_battle:
        result["boosts"] = asdict(pokemon.stats_modifiers)
        result["temporary_status"] = [s.name for s in pokemon.status_temporary]
    return result


class JevStrategy(DefaultBattleStrategy):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.last_signature = None
        self.last_action = None
        self.history = []
        self.pending_switch = None

    def which_move_should_be_replaced(self, pokemon, move):
        return 4

    def should_allow_evolution(self, pokemon, party_index):
        return False

    def choose(self, battle, forced=False):
        session = self.session
        if session.status["decisions"] >= session.config["max_decisions"]:
            raise RuntimeError("Decision limit reached. Battle stopped.")
        active = battle.own_side.active_battler
        if not forced and self.pending_switch is not None:
            if active.personality_value != self.pending_switch:
                raise RuntimeError("The emulator sent out a different Pokémon than Jev selected.")
            session.status.setdefault("switches_verified", 0)
            session.status["switches_verified"] += 1
            self.pending_switch = None
        signature = (battle.current_turn, active.species.name, active.current_hp, forced,
            tuple(m.pp for m in active.moves if m), battle.opponent.active_battler.species.name,
            battle.opponent.active_battler.current_hp)
        if signature == self.last_signature:
            session.metrics["reused_decisions"] += 1
            return self.last_action
        choices = {}
        actions = {}
        labels = {}
        move_context = []
        if not forced:
            for index, move in enumerate(active.moves):
                if move and active.can_use_move(move.move) and not (active.taunt_turns_remaining and move.move.base_power == 0):
                    key = f"move_{index + 1}"
                    choices[key] = json.dumps(describe(active)["moves"][index])
                    actions[key] = TurnAction.use_move(index)
                    labels[key] = move.move.name
                    estimate = BattleStrategyUtil(battle).calculate_move_damage_range(move.move, active, battle.opponent.active_battler)
                    move_context.append({"move": move.move.name, "estimated_damage": [estimate.min, estimate.max],
                        "note": "Approximate mechanics calculation, not a model score or guaranteed outcome."})
        if forced or BattleStrategyUtil(battle).can_switch():
            for index, pokemon in enumerate(get_party()):
                if pokemon.current_hp > 0 and not pokemon.is_egg and (forced or index != active.party_index):
                    key = f"switch_{index + 1}"
                    choices[key] = "Switch to " + json.dumps(describe(pokemon))
                    actions[key] = TurnAction.rotate_lead(index)
                    labels[key] = f"Switch to {pokemon.species.name}"
        if not actions:
            # With no usable moves, selecting Fight lets the ROM use Struggle.
            choices["struggle"] = "No usable moves remain. Fight using Struggle."
            actions["struggle"] = TurnAction.use_move(0)
            labels["struggle"] = "Struggle"
        state = {"game": "Pokemon FireRed USA v1.1, actual GBA ROM", "turn": battle.current_turn,
            "information": "Privileged RAM state, exact opponent active HP and moves. No images sent to Jev.",
            "forced_switch": forced, "weather": battle.weather.name,
            "you": describe(active), "opponent": describe(battle.opponent.active_battler),
            "party": [describe(p) for p in get_party()], "move_matchups": move_context,
            "recent_actions": self.history[-6:]}
        session.status.update(phase="thinking", message="Jev is choosing an action", battle=state)
        started = time.monotonic()
        request = {"model": "jev-1.13.0", "state": state, "questions": {"action": {
            "type": "choice", "instructions": "Choose the best legal action to win this Gen 3 Pokemon battle. Consider type immunity, abilities, damage, HP, speed, PP and status. Prefer reliable knockouts and avoid unnecessary repeated switches. Physical/special categories follow move type. Choose only one provided option.",
            "criteria": choices}}}
        if session.config["agent"] == "baseline":
            if forced:
                action = next(iter(actions))
            else:
                move_index = BattleStrategyUtil(battle).get_strongest_move_against(active, battle.opponent.active_battler)
                key = f"move_{move_index + 1}" if move_index is not None else ""
                action = key if key in actions else next(iter(actions))
            response = None
        else:
            import requests
            response = None
            for attempt in range(3):
                session.check_stop()
                reply = requests.post("https://api.typesafe.ai/v1/systemone", json=request,
                    headers={"Authorization": f"Bearer {session.key}"}, timeout=45)
                if reply.status_code in (429, 500, 502, 503, 504, 529) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                if reply.status_code != 200:
                    raise RuntimeError(f"TypeSafe HTTP {reply.status_code}. Battle stopped without fallback.")
                response = reply.json()
                break
            answer = response.get("answers", {}).get("action", {})
            action = answer.get("choice")
            if answer.get("type") != "choice" or action not in actions:
                raise RuntimeError("Jev returned an invalid action.")
            probabilities = answer.get("probabilities", {})
            confidence = answer.get("confidence")
            if (not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1
                or set(probabilities) != set(actions)
                or any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
                or abs(sum(probabilities.values()) - 1) > 0.02):
                    raise RuntimeError("Jev returned invalid probabilities or confidence.")
            session.metrics["api_calls"] += 1
            session.metrics["input_tokens"] += response.get("usage", {}).get("input_tokens", 0)
            session.metrics["output_tokens"] += response.get("usage", {}).get("output_tokens", 0)
            session.metrics["estimated_cost_usd"] = session.metrics["input_tokens"] * 0.042 / 1000000
        session.check_stop()
        session.status["decisions"] += 1
        record = {"decision": session.status["decisions"], "frame": context.frame,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "video_time": session.frames / 59.7275, "labels": labels,
            "request": request, "response": response, "action": action}
        with (session.run_dir / "decisions.jsonl").open("a") as file:
            file.write(json.dumps(record) + "\n")
        session.status.update(phase="playing", message=f"{active.species.name} chose {labels[action]}", last_decision=record)
        session.metrics["last_latency_ms"] = record["latency_ms"]
        session.metrics["latency_ms"] += record["latency_ms"]
        session.status["events"] = (session.status.get("events", []) + [{"message": session.status["message"],
            "decision": record["decision"], "turn": battle.current_turn}])[-20:]
        print(f"Decision {session.status['decisions']}: {active.species.name} -> {action}", flush=True)
        self.last_signature = signature
        self.last_action = actions[action]
        self.history.append({"turn": battle.current_turn, "pokemon": active.species.name, "action": labels[action]})
        if not forced and action.startswith("switch_"):
            self.pending_switch = get_party()[actions[action][1]].personality_value
        return actions[action]

    def decide_turn(self, battle_state):
        return self.choose(battle_state)

    def choose_new_lead_after_faint(self, battle_state):
        return self.choose(battle_state, forced=True)[1]


class Session:
    def __init__(self):
        self.status = {"phase": "ready", "message": "Configure your party, then start a battle.", "decisions": 0}
        self.jpeg = (DATA / "league.png").read_bytes() if (DATA / "league.png").exists() else b""
        self.thread = None
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.lock = threading.Lock()

    def check_stop(self):
        if self.stop.is_set():
            raise InterruptedError("Battle stopped by player.")

    def start(self, config):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("A battle is already running. Stop it before starting another.")
            self.config = validate_config(config)
            load_env()
            key = (os.environ.get("TYPESAFE_API_KEY") or "").strip()
            if config["agent"] == "jev" and not key:
                raise ValueError("Set TYPESAFE_API_KEY in .env or in the environment.")
            self.key = key if config["agent"] == "jev" else None
            self.stop.clear()
            self.paused.clear()
            self.thread = threading.Thread(target=self.run_series, daemon=True)
            self.thread.start()

    def run_series(self):
        trainers = list(TRAINERS)
        first = trainers.index(self.config["opponent"])
        queue = trainers[first:] if self.config.get("auto_advance") else [self.config["opponent"]]
        self.results = []
        self.series_dir = DATA / "recordings" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-0")
        for index, trainer in enumerate(queue):
            if self.stop.is_set():
                self.status.update(phase="stopped", message="League run stopped.")
                break
            self.config = {**self.config, "opponent": trainer}
            self.run()
            result = {"opponent": trainer, "outcome": self.status.get("outcome"), "run": self.run_dir.name,
                "decisions": self.status["decisions"]}
            self.results.append(result)
            self.status["series"] = self.results.copy()
            if self.status["phase"] != "finished" or self.status.get("outcome") != "Won":
                break
            if index + 1 < len(queue):
                next_trainer = queue[index + 1]
                self.status.update(phase="between", next_opponent=next_trainer,
                    message=f"{trainer.title()} defeated. Next: {next_trainer.title()}. Your configured party is restored for the next match.")
                for _ in range(50):
                    if self.stop.wait(0.1):
                        break
                    while self.paused.is_set() and not self.stop.is_set():
                        time.sleep(0.1)
        (DATA / "last-series.json").write_text(json.dumps(self.results, indent=2))
        if self.config.get("auto_advance") and self.results:
            self.finish_series()

    def finish_series(self):
        self.series_dir.mkdir(parents=True, exist_ok=True)
        clips = []
        records = []
        offset = 0.0
        for result in self.results:
            directory = DATA / "recordings" / result["run"]
            video = directory / "replay.mp4"
            if not video.exists():
                continue
            clips.append(f"file '{video.as_posix()}'")
            if (directory / "decisions.jsonl").exists():
                for line in (directory / "decisions.jsonl").read_text().splitlines():
                    record = json.loads(line)
                    record["video_time"] += offset
                    record["trainer"] = result["opponent"]
                    record["decision"] = len(records) + 1
                    records.append(record)
            duration = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], text=True)
            offset += float(duration)
        if not clips:
            return
        playlist = self.series_dir / "clips.txt"
        playlist.write_text("\n".join(clips))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(playlist),
            "-c", "copy", "-movflags", "+faststart", str(self.series_dir / "replay.mp4")], check=True)
        (self.series_dir / "decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
        summary = {"phase": self.status["phase"], "outcome": self.status.get("outcome"), "opponent": "league",
            "agent": self.config["agent"], "decisions": len(records), "series": self.results,
            "recording_note": "Consecutive matches, no retries. Party restored between matches. API waiting time omitted from game-frame recording."}
        (self.series_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        self.status["series_recording"] = self.series_dir.name

    def frame(self):
        self.check_stop()
        while self.paused.is_set():
            self.check_stop()
            time.sleep(0.05)
        self.frames += 1
        audio_queue = context.emulator.get_last_audio_data()
        while True:
            try:
                audio = audio_queue.get_nowait()
                if self.audio_file:
                    self.audio_file.writeframesraw(audio)
            except queue.Empty:
                break
        if self.frames % 2 == 0:
            image = context.emulator.get_screenshot()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=90)
            self.jpeg = buffer.getvalue()
            self.video.stdin.write(image.tobytes())
        self.status["frames"] = self.frames

    def run(self):
        global FRAME_HOOK
        self.run_dir = DATA / "recordings" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.run_dir.mkdir(parents=True)
        self.status = {"phase": "starting", "message": "Loading your party into FireRed", "decisions": 0,
            "run": self.run_dir.name, "opponent": self.config["opponent"], "agent": self.config["agent"],
            "series": getattr(self, "results", []).copy()}
        self.metrics = {"api_calls": 0, "input_tokens": 0, "output_tokens": 0, "last_latency_ms": 0,
            "estimated_cost_usd": 0, "reused_decisions": 0, "latency_ms": 0}
        self.status["metrics"] = self.metrics
        self.frames = 0
        self.video = None
        self.audio_file = None
        try:
            context.emulator.load_save_game((DATA / "league.sav").read_bytes())
            context.emulator.load_save_state((DATA / "league.state").read_bytes())
            context.emulator.reset_held_buttons()
            tick()
            debug_write_party(make_party(self.config["party"]))
            options = bytearray(get_save_block(2, offset=0x14, size=2))
            options[0] = (options[0] & 0xF8) | 2
            options[1] = (options[1] & 0xF9) | (2 if self.config["battle_style"] == "set" else 0) | (0 if self.config["animations"] else 4)
            write_to_save_block(options, 2, offset=0x14)
            context.bot_mode = "Jev"
            context.emulator.set_audio_enabled(self.config["audio"])
            context.emulator.set_throttle(self.config["speed"] != 0)
            context.emulator.set_speed_factor(self.config["speed"] or 1)
            if self.config["audio"] and self.config["speed"]:
                self.audio_file = wave.open(str(self.run_dir / "audio.wav"), "wb")
                self.audio_file.setnchannels(2)
                self.audio_file.setsampwidth(2)
                self.audio_file.setframerate(round(context.emulator.get_sample_rate() / self.config["speed"]))
            (self.run_dir / "config.json").write_text(json.dumps(self.config, indent=2))
            (self.run_dir / "start.state").write_bytes(context.emulator.get_save_state())
            self.video = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "240x160", "-framerate", "29.86375",
                "-i", "pipe:0", "-vf", "scale=720:480:flags=neighbor", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(self.run_dir / "replay.mp4")], stdin=subprocess.PIPE)
            FRAME_HOOK = self.frame
            drive(talk_to_npc(1), 3000)
            trainer_set = False
            enemy_set = self.config.get("opponent_party") is None
            for _ in range(3000):
                if task_is_active("Task_BattleStart") and not trainer_set:
                    write_symbol("gTrainerBattleOpponent_A", TRAINERS[self.config["opponent"]].to_bytes(2, "little"))
                    trainer_set = True
                if (not enemy_set and get_game_state_symbol() == "CB2_HANDLESTARTBATTLE"
                    and read_symbol("gMain", offset=0x439, size=1)[0] & 2
                    and read_symbol("gBattleCommunication", size=1)[0] in (0, 1)):
                    party = make_party(self.config["opponent_party"])
                    write_symbol("gEnemyParty", b"".join(p.data for p in party).ljust(600, b"\0"))
                    write_symbol("gEnemyPartyCount", bytes([len(party)]))
                    enemy_set = True
                if get_game_state() == GameState.BATTLE:
                    break
                context.emulator.press_button("A")
                tick()
            else:
                raise RuntimeError("The trainer battle did not start.")
            if not trainer_set or not enemy_set:
                raise RuntimeError("Battle setup was not applied.")
            strategy = JevStrategy(self)
            generator = handle_battle(strategy)
            for _ in range(150000):
                try:
                    next(generator)
                except StopIteration as complete:
                    outcome = complete.value.outcome.name
                    break
                tick()
            else:
                raise RuntimeError("Emulator frame limit reached.")
            for _ in range(120):
                context.emulator.press_button("B")
                tick()
            self.status.update(phase="finished", message=f"Battle finished: {outcome}", outcome=outcome)
        except InterruptedError as error:
            self.status.update(phase="stopped", message=str(error))
        except Exception as error:
            traceback.print_exc()
            self.status.update(phase="error", message=str(error))
        finally:
            FRAME_HOOK = None
            context.emulator.set_audio_enabled(False)
            context.emulator.set_throttle(False)
            context.emulator.reset_held_buttons()
            if self.video:
                self.video.stdin.close()
                code = self.video.wait(timeout=30)
                if code:
                    self.status.update(phase="error", message=f"Video recording failed with code {code}")
            if self.audio_file:
                self.audio_file.close()
                muxed = self.run_dir / "with-audio.mp4"
                mux = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(self.run_dir / "replay.mp4"), "-i", str(self.run_dir / "audio.wav"),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(muxed)])
                if mux.returncode == 0:
                    muxed.replace(self.run_dir / "replay.mp4")
                else:
                    self.status.update(phase="error", message="Could not add game audio to recording.")
            self.status["agent"] = self.config["agent"]
            context.emulator.get_screenshot().save(self.run_dir / "final.png")
            (self.run_dir / "final.state").write_bytes(context.emulator.get_save_state())
            (self.run_dir / "summary.json").write_text(json.dumps(self.status, indent=2))
            print(json.dumps({k: v for k, v in self.status.items() if k not in ("battle", "last_decision")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true", help="Run one configured match and exit")
    parser.add_argument("--config", default=str(ROOT / "emulator-config.json"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--speed", type=int, choices=(0, 1, 2, 4))
    parser.add_argument("--agent", choices=("jev", "baseline"))
    parser.add_argument("--opponent", choices=tuple(TRAINERS))
    parser.add_argument("--check", action="store_true", help="Check custom teams and all trainer presets without API calls")
    parser.add_argument("--check-custom", action="store_true")
    args = parser.parse_args()
    initialise()
    if args.check or args.check_custom:
        from emulator_checks import check
        check(Session, validate_config, only_custom=args.check_custom)
    elif args.prepare:
        prepare()
    else:
        if not (DATA / "league.state").exists():
            prepare()
        session = Session()
        if args.run:
            config = json.loads(Path(args.config).read_text())
            if args.speed is not None:
                config["speed"] = args.speed
                config["audio"] = args.speed != 0
            if args.agent:
                config["agent"] = args.agent
            if args.opponent:
                config["opponent"] = args.opponent
                config["auto_advance"] = False
            session.start(config)
            session.thread.join()
            if session.status["phase"] != "finished":
                sys.exit(1)
        else:
            from emulator_web import serve
            serve(session, args.port)
