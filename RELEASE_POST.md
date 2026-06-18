# Reddit / ForzaMods release post (copy-paste)

**Title:** I made a free Time Attack lap tracker for FH6 (auto lap times, live telemetry, lap analysis)

---

Hey everyone! 👋

I made a small free tool that automatically tracks your lap times on the
Open-World Time Attack circuits in Forza Horizon 6, and shows everything on a
clean dashboard in your browser.

Quick background: FH6 doesn't actually send the Time Attack lap time over "Data
Out", so the tool just measures the laps itself from your car's position. It
knows where each circuit's start/finish line is and times every flying lap for
you. No learning lap, and it keeps working when you switch cars mid-session.

**What it does**
- ⏱️ Automatic, accurate lap timing on Time Attack circuits
- 🧠 Recognises the track instantly, no setup, and switches between circuits on its own
- 📊 Live dashboard: current car, running lap timer, live delta vs. your best lap (green/red), session best, recent laps
- 🔧 Live telemetry popup: tyre temps, power, torque, throttle and brake
- 🏁 Lap analysis: click any lap to get speed / throttle / brake / tyre-slip graphs, the spots where you lost the most time vs. your best lap, plus a few tips to go faster
- 🚗 Times sorted per car and tuning (class/PI), an overall best-times board per track, and you can delete single laps
- 📈 Excel export, and the UI is in English and German

**Tracks ready out of the box:** Legend Island, Hokubu, Soni and Sekibe Time
Attack. More are easy to add later.

**How to use it**
1. Grab the .exe from the link below (no Python or install needed)
2. In FH6 go to Settings, HUD, Data Out = ON, IP 127.0.0.1, Port 5300
3. Run the .exe. A small black console window opens and your browser opens the
   dashboard. Keep that console window open while you play (that's the tracker
   doing its thing). Close it when you're done.
4. Drive a Time Attack circuit and watch the times roll in. That's it.

**About the times:** the tool uses its own stopwatch (it measures from your
position), so a lap can differ from the in-game Time Attack timer by a few
milliseconds. The point is that it always measures the exact same way, so all
your times sit on the same basis. That makes it great for personal use:
comparing cars, tunings and sessions against each other is fully consistent. For
the cleanest times, drive your laps without pausing or using rewind.

**Is it safe / allowed?** Yep, it's read-only. It just listens to the telemetry
packets the game already sends to your own PC. It never touches game memory and
doesn't send your data anywhere. Heads up: Windows might warn about an "unknown
publisher" when you open it, which is normal for small tools like this. The full
source code is on GitHub if you want to check it or build it yourself.

**Optional car images:** the dashboard can show a cut-out picture of each car.
Grab the separate "cars" pack from the release and extract it next to the .exe
(about 320 of the most common cars are included; the rest show a placeholder and
you can drop in your own image). The images are community renders, so they ship
as an optional pack, not inside the tool.

**Important: this is an early version and I'm still working on it.** I'd really
love your feedback, bug reports and feature ideas, so please drop them in the
comments and I'll do my best to add them. 🙏

GitHub: <link>
Screenshots below 👇

Thanks for trying it, and have fun chasing those times! 🏎️💨
