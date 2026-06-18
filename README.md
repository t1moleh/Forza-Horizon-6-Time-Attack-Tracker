# FH6 Time Attack Lap Tracker

A lightweight tool that **automatically records your lap times on the Open‑World
Time Attack circuits in Forza Horizon 6** and shows them on a clean local
dashboard — with live telemetry and per‑lap analysis.

Forza Horizon 6 does **not** send the Time Attack lap time over "Data Out", so
this tool measures laps itself from your position (a GPS stopwatch): it knows
each circuit's start/finish line and times every flying lap automatically — no
learning lap, works across car changes.

> **Read‑only.** The tool only *receives* the telemetry packets the game already
> broadcasts. It never writes to the game or interferes with it (anti‑cheat‑safe).

> **Status: in active development** — feedback and feature wishes very welcome!

## Download & run

1. Download `FH6 Lap Tracker.exe` from the latest [release](#).
2. In Forza Horizon 6: **Settings → HUD → Data Out = ON**, IP `127.0.0.1`,
   Port `5300`.
3. Double‑click the `.exe`. The dashboard opens in **its own app window** (a
   small console window also stays open in the background while it runs).
4. Drive a Time Attack circuit, times appear automatically. Close the window to
   stop.

No Python needed. On first start the tool creates `circuits.csv`,
`car_names.csv`, `lap_times.csv` next to the `.exe`.

## Features

- **Automatic lap timing** on Time Attack circuits — flying laps, precise line
  crossing with time interpolation.
- **Instant circuit recognition** — known tracks are picked up by position; no
  learning lap, survives garage/car changes, auto‑switches between circuits.
- **Live dashboard** (local, dark UI): current car, running lap timer, **live
  delta** vs. your best lap (green/red), session best, recent laps, cars used.
- **Telemetry pop‑up**: tyre temperatures, power, torque, throttle/brake (live).
- **Per‑lap analysis**: click a lap to see speed/throttle/brake/tyre‑slip charts,
  the sections where you lost the most time vs. your best lap, and concrete
  **improvement tips**.
- **Per car & tuning**: lap lists grouped by model + class + PI (different tunes
  show separately), an overall best‑times ranking per track, and **delete**
  individual laps.
- **Excel export** of all times (optional).
- **German & English** UI.

## Included circuits

Comes pre‑calibrated for: **Legend Island, Hokubu, Soni, Sekibe** (Time Attack).
More can be added easily — record a lap, and the start/finish line is calibrated
from your driven line.

## Car images (optional)

The dashboard can show a cut‑out image of each car. These are optional: download
the `cars.zip` pack from the release and extract it so that a `cars/` folder sits
**next to the .exe**. Around 320 of the most common cars are covered; missing
ones simply show a placeholder, and you can drop your own image onto a car in the
UI to add it. The images are community renders (source: labs.gg); they are not
bundled with the tool.

## A note on the times

The tool uses its own stopwatch (measured from your position), so a lap can
differ from the in‑game Time Attack timer by a few milliseconds. What matters is
that it always measures the same way, so every time you record sits on the same
basis. That makes it ideal for personal use: comparing cars, tunings and
sessions is fully consistent.

**Pause and rewind:** for valid times, drive your laps without pausing or using
rewind. If you pause (the game leaves the active session), the current lap is
discarded and timing simply re-arms when you next cross the start/finish line, so
no wrong time is recorded. Rewind, however, is not compensated yet: the stopwatch
keeps running, so a lap that includes a rewind gets an inflated, unreliable time.
Detecting and invalidating such laps automatically is planned for a later update.

## Privacy & fair play

The tool binds a local UDP socket and reads the "Data Out" packets the game
sends to `127.0.0.1`. It does not read or modify game memory and sends nothing
anywhere. Your data stays on your PC.

## Roadmap

- More cut‑out car images (currently ~320 of the most common cars)
- More circuits / community‑contributed start/finish lines
- Side‑by‑side compare of two cars/tunings
- Whatever you suggest 🙂

## Build from source (developers)

```bash
py -m pip install -e ".[dev]"
py -m pytest                       # tests
py -m fh6tracker.tracker           # run live + dashboard
py -m fh6tracker.recorder          # record a calibration trace
py -m PyInstaller --onefile --noconfirm --clean --name "FH6 Lap Tracker" \
  --collect-all webview \
  --add-data "web;web" --add-data "car_names.csv;." --add-data "circuits.csv;." \
  fh6_tracker_app.py               # build the .exe (Windows)
```

## Feedback & bugs

Found a bug or have an idea? Open an issue using the **Bug report** or
**Feature request** template under the repo's Issues tab. Feedback is very welcome!

## Disclaimer

Not affiliated with Microsoft, Turn 10 or Playground Games. "Forza Horizon" is a
trademark of Microsoft. Car names are from community data. License: MIT.
