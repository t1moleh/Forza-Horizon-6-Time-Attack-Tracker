"""Baut freigestellte Fahrzeugbilder (web/cars/<slug>.png) aus labsgg-Renders.

Ablauf: labsgg-Autonamen <-> unsere car_names.csv matchen, FULL_CARS-Render von
Cloudinary laden (curl), per birefnet freistellen, als <slug>.png speichern.

    py build_car_images.py --dry-run     # nur Abdeckung zeigen
    py build_car_images.py               # herunterladen + freistellen
"""
import csv, difflib, html, os, re, subprocess, sys, time, unicodedata, urllib.parse

DRY = "--dry-run" in sys.argv
OUT = "web/cars"
BASE = "https://res.cloudinary.com/nba2klab/image/upload/f_auto,q_85,w_800/FH6/FULL_CARS/"


def norm(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def carslug(name):
    s = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"['’]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def year(name):
    m = re.match(r"\s*(\d{4})", name)
    return m.group(1) if m else None


def load_labs():
    h = html.unescape(open("labs_cars.html", encoding="utf-8", errors="replace").read())
    return list(dict.fromkeys(re.findall(r'fullCarName":\[0,"([^"]+)"', h)))


def load_ours():
    out = []
    for r in csv.reader(open("car_names.csv", encoding="utf-8")):
        if len(r) >= 2 and r[0].lstrip("-").isdigit() and r[1].strip():
            out.append((int(r[0]), r[1].strip()))
    return out


def build_matches():
    labs = load_labs()
    labs_norm = {norm(n): n for n in labs}
    keys = list(labs_norm)
    matches, misses = [], []
    for ordn, name in load_ours():
        n = norm(name)
        hit = labs_norm.get(n)
        if not hit:
            for cand in difflib.get_close_matches(n, keys, n=1, cutoff=0.80):
                ly, oy = year(labs_norm[cand]), year(name)
                if oy and ly and oy != ly:   # Jahr muss passen (gegen Falschtreffer)
                    continue
                hit = labs_norm[cand]
                break
        if hit:
            matches.append((ordn, name, carslug(name), hit))
        else:
            misses.append(name)
    return matches, misses


def cloud_urls(labs_name):
    """Mehrere moegliche Cloudinary-Dateinamen (Cloudinary ersetzt '/' durch '_'
    und laesst Apostrophe weg)."""
    raw = labs_name.replace(" ", "_")
    cands = []
    def add(s):
        if s not in cands:
            cands.append(s)
    add(raw)
    add(raw.replace("/", "_"))
    s = raw.replace("/", "_").replace("'", "").replace("’", "")
    add(s)
    add(s.replace(".", ""))
    add(s.replace(".", "_"))
    return [BASE + urllib.parse.quote(c + ".png", safe="") for c in cands]


def main():
    matches, misses = build_matches()
    print(f"Zugeordnet: {len(matches)}  |  ohne Treffer: {len(misses)}")
    if DRY:
        print("Beispiele zugeordnet:")
        for m in matches[:8]:
            print(f"  {m[1]}  ->  {m[3]}")
        return

    os.makedirs(OUT, exist_ok=True)
    from rembg import remove, new_session
    from PIL import Image
    sess = new_session("birefnet-general")
    ok = skip = fail = 0
    with open("car_images_manifest.csv", "w", newline="", encoding="utf-8") as mf:
        w = csv.writer(mf); w.writerow(["ordinal", "name", "slug", "labs_name", "status"])
        for i, (ordn, name, slug, labs_name) in enumerate(matches, 1):
            dst = os.path.join(OUT, slug + ".png")
            if os.path.exists(dst):
                skip += 1; w.writerow([ordn, name, slug, labs_name, "skip"]); continue
            tmp = os.path.join(OUT, "_tmp.bin")
            got = False
            for url in cloud_urls(labs_name):
                r = subprocess.run(["curl", "-s", "-f", "-m", "40", "-H",
                                    "Accept: image/png,*/*", "-o", tmp, url])
                if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    got = True; break
            if not got:
                fail += 1; w.writerow([ordn, name, slug, labs_name, "download_fail"]); continue
            try:
                im = Image.open(tmp).convert("RGBA")
                res = remove(im, session=sess)
                res.save(dst)
                ok += 1; w.writerow([ordn, name, slug, labs_name, "ok"])
            except Exception as e:
                fail += 1; w.writerow([ordn, name, slug, labs_name, f"cutout_fail:{e}"])
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            if i % 20 == 0:
                print(f"  {i}/{len(matches)}  ok={ok} skip={skip} fail={fail}", flush=True)
    print(f"FERTIG: ok={ok} skip={skip} fail={fail}  ->  {OUT}/")


if __name__ == "__main__":
    main()
