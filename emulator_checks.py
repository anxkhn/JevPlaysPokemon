import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def check(session_class, validate, only_custom=False):
    base = json.loads((ROOT / "emulator-config.json").read_text())
    base.update(agent="baseline", speed=0, audio=False, auto_advance=False)
    for trainer in (() if only_custom else ("lorelei", "bruno", "agatha", "lance", "champion")):
        config = {**base, "opponent": trainer}
        session = session_class()
        session.start(config)
        session.thread.join(timeout=120)
        if session.thread.is_alive():
            session.stop.set()
            session.thread.join(timeout=50)
        assert session.status["phase"] == "finished", session.status["message"]
        assert session.status["decisions"] > 0
        print(f"PASS actual ROM trainer {trainer}: {session.status['outcome']}")
    custom = {**base,
        "party": [{"species": "Mewtwo", "level": 75, "moves": ["Psychic", "Thunderbolt"], "nature": "Modest", "item": "Leftovers"}],
        "opponent_party": [{"species": "Magikarp", "level": 5, "moves": ["Splash"]}]}
    session = session_class()
    session.start(custom)
    session.thread.join(timeout=120)
    assert session.status["phase"] == "finished", session.status
    assert session.status["outcome"] == "Won"
    decision = json.loads((session.run_dir / "decisions.jsonl").read_text().splitlines()[0])
    state = decision["request"]["state"]
    assert state["you"]["species"] == "Mewtwo" and state["you"]["level"] == 75
    assert state["you"]["item"] == "Leftovers"
    assert state["opponent"]["species"] == "Magikarp" and state["opponent"]["level"] == 5
    assert [m["name"] for m in state["you"]["moves"]] == ["Psychic", "Thunderbolt"]
    for invalid in ({**base, "party": []}, {**base, "game": "emerald"}, {**base, "max_decisions": 0}):
        try:
            validate(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid configuration accepted")
    print("PASS custom player/enemy party RAM readback, outcome, and invalid configuration checks.")
    session = session_class()
    progression = {**base, "opponent": "lance", "auto_advance": True,
        "party": [{"species": "Mewtwo", "level": 100, "moves": ["Psychic", "Thunderbolt", "Ice Beam", "Flamethrower"]}]}
    session.start(progression)
    session.thread.join(timeout=120)
    assert [r["opponent"] for r in session.results] == ["lance", "champion"], session.results
    assert all(r["outcome"] == "Won" for r in session.results), session.results
    print("PASS automatic Lance -> Champion progression on real ROM wins. Test-only level-100 fixture.")
