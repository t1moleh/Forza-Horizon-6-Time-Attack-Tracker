"""Tests fuer die Rivals-Rundenerkennung (spielinterner Lap-Timer)."""
from fh6tracker.rivals import RivalsLap, RivalsTracker, is_rivals


def _lt(race_on=1, lap=0, last=0.0, best=0.0, cur=0.0):
    return {"race_on": race_on, "lap_number": lap, "last_lap": last,
            "best_lap": best, "current_lap": cur}


def test_is_rivals_detection():
    assert is_rivals(_lt(race_on=1, lap=2, last=90.0)) is True
    assert is_rivals(_lt(race_on=0, lap=2, last=90.0)) is False   # nicht in Welt
    assert is_rivals(_lt(race_on=1, lap=0, last=0.0)) is False    # Time Attack: alles 0
    assert is_rivals(None) is False


def test_emits_lap_on_lapnumber_increment():
    rt = RivalsTracker()
    assert rt.update(_lt(race_on=0)) is None                      # Menue
    assert rt.update(_lt(lap=1, cur=5.0)) is None                 # Runde 1 laeuft
    assert rt.update(_lt(lap=1, cur=80.0)) is None                # noch Runde 1
    ev = rt.update(_lt(lap=2, last=121.627, best=121.627))        # Runde 1 fertig
    assert ev == RivalsLap(lap_time=121.627, lap_number=1)
    ev2 = rt.update(_lt(lap=3, last=114.102, best=114.102))       # Runde 2 fertig
    assert ev2 == RivalsLap(lap_time=114.102, lap_number=2)


def test_no_double_emit_same_lapnumber():
    rt = RivalsTracker()
    rt.update(_lt(lap=1))
    assert rt.update(_lt(lap=2, last=90.0)) is not None
    assert rt.update(_lt(lap=2, last=90.0)) is None               # gleiche Runde -> kein 2. Event


def test_lap_kept_when_results_menu_pops_up():
    # FH6 Rivals: nach Runde 1 oeffnet ein Ergebnis-Menue (race_on=0) genau wenn
    # LastLapTime auf Runde 1 gesetzt wird. Beim Weiterfahren muss Runde 1 noch
    # gewertet werden (frueher ging sie verloren).
    rt = RivalsTracker()
    rt.update(_lt(lap=1, cur=5.0, last=0.0))      # Runde 1 laeuft
    rt.update(_lt(lap=1, cur=80.0, last=0.0))     # noch Runde 1
    assert rt.update(_lt(race_on=0, lap=1, last=92.5)) is None   # Menue: nicht verarbeiten, nicht vergessen
    ev = rt.update(_lt(lap=2, cur=3.0, last=92.5))               # Weiterfahren -> Runde 1 nachtragen
    assert ev == RivalsLap(92.5, 1)


def test_run_restart_resets():
    rt = RivalsTracker()
    rt.update(_lt(lap=3, last=90.0))
    rt.update(_lt(race_on=0))                                     # Run verlassen
    assert rt.update(_lt(lap=1, last=0.0)) is None                # neuer Run, Runde 1 laeuft
    assert rt.update(_lt(lap=2, last=95.0)) == RivalsLap(95.0, 1)
