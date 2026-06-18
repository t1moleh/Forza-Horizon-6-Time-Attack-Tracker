# Reddit post (v0.2.0) - copy-paste

**WICHTIG fuer mehr Reaktionen (Lehren aus v0.1.0):**
- Mach einen **Bild-/Galerie-Post** und lade 3 bis 5 Screenshots DIREKT bei Reddit
  hoch. Verlass dich NICHT auf den GitHub-Link fuer Bilder (dann sieht man sie nicht).
- Den Download-Link in den Text UND in den ersten Kommentar packen.
- Mit einer **konkreten Frage** enden (siehe unten) und in der ersten Stunde auf
  jeden Kommentar schnell antworten - das pusht die Sichtbarkeit am meisten.

---

**Title:** Free Time Attack lap tracker for FH6 with live telemetry + per-lap analysis (v0.2.0, open source)

---

Hey everyone! A while back I shared a small tool that auto-tracks your lap times
on the Open-World Time Attack circuits in Forza Horizon 6. Since then I have
added a lot, so here is v0.2.0.

Quick why: FH6 does not send the Time Attack lap time over "Data Out", so the
tool measures laps itself from your car position. No learning lap, and it keeps
working when you swap cars.

**New in v0.2.0**
- 🔧 Live telemetry: speed, RPM, gear, throttle/brake, tyre temps, power, torque
- 🏁 Per-lap analysis: click a lap to see speed / throttle / brake / tyre-slip
  graphs, where you lost the most time vs. your best lap, and tips to go faster
- ⚖️ Compare two cars or tunings side by side
- 🔊 Sound signals (double-beep at the finish, beep at the start, a chime on a
  personal best) - fully configurable
- 🎨 Dark and Light theme, cleaner UI, plus cut-out car images for ~320 cars
- 🗑️ Delete single laps, lap times grouped per car and tuning (class/PI)

**Core features**
- Accurate, automatic lap timing on Time Attack circuits (flying laps)
- Live dashboard in its own app window: current car, running timer, live delta
  vs. your best lap, session best, recent laps
- Pre-calibrated circuits: Legend Island, Hokubu, Soni, Sekibe
- Excel export, English and German UI

**How to use it**
1. Download the .exe (link below, no install needed)
2. In FH6: Settings, HUD, Data Out = ON, IP 127.0.0.1, Port 5300
3. Run the .exe, drive a Time Attack circuit, watch the times. That is it.

**Safe?** Yes, read-only. It only listens to the telemetry the game already
sends to your own PC, never touches game memory, sends nothing anywhere. Windows
may warn about an unknown publisher (normal for small tools); full source is on
GitHub.

This is still early development and I am actively building it, so I would really
love your input:
**Which circuits or cars should I add next, and what telemetry/feature would
actually help you go faster?** Drop it in the comments. 🙏

Download (free, open source): <GitHub release link>

Screenshots below 👇
