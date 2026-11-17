"""Génère des cartes SVG animées des contributions GitHub (style orange du profil).

Usage : python contributions.py <utilisateur> <dossier_sortie> [--precedent <dossier>] [--html <fichier_local>]
Lit le calendrier public https://github.com/users/<utilisateur>/contributions.
Les cartes ne sont régénérées qu'une fois par heure : entre deux, on recopie
celles du passage précédent (dossier --precedent).
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.request

RAFRAICHIR = 3600  # secondes entre deux régénérations
FICHIERS = ("contributions.svg", "contributions-mobile.svg")

OR, OR2, INK, BG, CELL0, TXT, MUTED = "#FD843C", "#FD5D57", "#111111", "#121214", "#1E1F24", "#FFFFFF", "#8A8B94"
LEVELS = [CELL0, "#5C2C12", "#94461C", "#CC6128", OR]
SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fetch(user, local=None):
    if local:
        return open(local, encoding="utf-8").read()
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions", headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")


def parse(page):
    tips = {}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        n = re.match(r"([\d,]+) contribution", m.group(2))
        tips[m.group(1)] = int(n.group(1).replace(",", "")) if n else 0
    days = []
    for m in re.finditer(r"<td[^>]*>", page):
        tag = m.group(0)
        d, lv, i = (re.search(rf'{k}="([^"]+)"', tag) for k in ("data-date", "data-level", "id"))
        if d and lv and i:
            days.append((dt.date.fromisoformat(d.group(1)), int(lv.group(1)), tips.get(i.group(1), 0)))
    days.sort()
    return days


def stats(days):
    total = sum(c for _, _, c in days)
    best = max((c for _, _, c in days), default=0)
    active = sum(1 for _, _, c in days if c)
    streak = run = 0
    for _, _, c in days:
        run = run + 1 if c else 0
        streak = max(streak, run)
    return total, best, active, streak


def weeks_of(days):
    weeks, cur = [], []
    for d, lv, c in days:
        if cur and d.weekday() == 6:  # dimanche = nouvelle colonne
            weeks.append(cur)
            cur = []
        cur.append((d, lv, c))
    if cur:
        weeks.append(cur)
    return weeks


def fmt(n):
    return f"{n:,}".replace(",", " ")


def grid(weeks, x0, y0, size, gap, best_day, delay_step):
    out, css = [], []
    for wi, week in enumerate(weeks):
        x = x0 + wi * (size + gap)
        for d, lv, c in week:
            row = (d.weekday() + 1) % 7
            y = y0 + row * (size + gap)
            cls = "c best" if (d, c) == best_day and c else "c"
            out.append(f'<rect class="{cls}" style="animation-delay:{wi * delay_step:.2f}s" x="{x}" y="{y}" width="{size}" height="{size}" rx="{size * .22:.1f}" fill="{LEVELS[lv]}"/>')
    starts, last = [], None
    for wi, week in enumerate(weeks):
        m = week[0][0].month
        if m != last:
            starts.append((wi, m))
            last = m
    # un mois n'a son étiquette que s'il dure au moins 3 colonnes (évite les chevauchements)
    keep = [(wi, m) for k, (wi, m) in enumerate(starts)
            if (starts[k + 1][0] if k + 1 < len(starts) else len(weeks)) - wi >= 3]
    labels = [f'<text x="{x0 + wi * (size + gap)}" y="{y0 - 12}" font-family="{MONO}" font-size="{max(11, size * .7):.0f}" fill="{MUTED}">{MOIS[m - 1]}</text>' for wi, m in keep]
    return "".join(labels) + "".join(out)


STYLE = """
.c{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.2,.8,.2,1) forwards}
.best{animation:pop .5s cubic-bezier(.2,.8,.2,1) forwards,glow 2.4s 2s ease-in-out infinite}
.up{opacity:0;animation:up .8s cubic-bezier(.16,1,.3,1) forwards}
.d1{animation-delay:.1s}.d2{animation-delay:.25s}.d3{animation-delay:.4s}.d4{animation-delay:.55s}
.sweep{animation:sweep 7s 2.5s ease-in-out infinite}
@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:scale(1)}}
@keyframes glow{50%{fill:#FFD2B0}}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes sweep{0%{transform:translateX(-200px)}70%,100%{transform:translateX(1400px)}}
"""


def stat(x, y, label, value, cls, big=30):
    return (f'<g class="up {cls}"><text x="{x}" y="{y}" font-family="{MONO}" font-size="12" font-weight="700" fill="{MUTED}" letter-spacing="1.5">{label}</text>'
            f'<text x="{x}" y="{y + big + 8}" font-family="{SANS}" font-size="{big}" font-weight="800" fill="{TXT}">{value}</text></g>')


def card_desktop(days):
    total, best, active, streak = stats(days)
    best_day = next(((d, c) for d, _, c in days if c == best), None)
    weeks = weeks_of(days)
    W, H = 1200, 400
    size, gap = 17, 4
    gw = len(weeks) * (size + gap) - gap
    x0 = (W - gw) // 2
    body = [
        f'<text class="up" x="48" y="62" font-family="{MONO}" font-size="13" font-weight="700" fill="{OR}" letter-spacing="2">CONTRIBUTIONS · 12 DERNIERS MOIS</text>',
        f'<text class="up d1" x="46" y="140" font-family="{SANS}" font-size="78" font-weight="900" fill="{TXT}" letter-spacing="-2">{fmt(total)}</text>',
        stat(560, 82, "MEILLEURE SÉRIE", f"{streak} jours", "d2"),
        stat(780, 82, "RECORD", f"{fmt(best)} / jour", "d3"),
        stat(990, 82, "JOURS ACTIFS", f"{active}", "d4"),
        grid(weeks, x0, 214, size, gap, best_day, 0.025),
    ]
    return wrap(W, H, "".join(body), sweep_h=(200, 370))


def card_mobile(days):
    weeks = weeks_of(days)[-17:]
    sub = [x for w in weeks for x in w]
    total, best, active, streak = stats(days)
    best_day = next(((d, c) for d, _, c in sub if c == max(c for _, _, c in sub)), None)
    W, H = 400, 430
    size, gap = 18, 4
    gw = len(weeks) * (size + gap) - gap
    x0 = (W - gw) // 2
    body = [
        f'<text class="up" x="24" y="50" font-family="{MONO}" font-size="11" font-weight="700" fill="{OR}" letter-spacing="1.5">CONTRIBUTIONS · 12 DERNIERS MOIS</text>',
        f'<text class="up d1" x="22" y="118" font-family="{SANS}" font-size="64" font-weight="900" fill="{TXT}" letter-spacing="-2">{fmt(total)}</text>',
        stat(24, 160, "SÉRIE", f"{streak} j", "d2", 24),
        stat(150, 160, "RECORD", f"{fmt(best)}", "d3", 24),
        stat(284, 160, "ACTIFS", f"{active} j", "d4", 24),
        grid(weeks, x0, 252, size, gap, best_day, 0.05),
    ]
    return wrap(W, H, "".join(body), sweep_h=(236, 410))


def wrap(W, H, body, sweep_h):
    y1, y2 = sweep_h
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<defs><clipPath id="k"><rect width="{W}" height="{H}" rx="18"/></clipPath>'
            f'<linearGradient id="sw" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
            f'<style>{STYLE}</style><g clip-path="url(#k)"><rect width="{W}" height="{H}" fill="{BG}"/><rect width="{W}" height="6" fill="{OR}"/>'
            f'{body}<rect class="sweep" x="0" y="{y1}" width="160" height="{y2 - y1}" fill="url(#sw)"/></g></svg>')


def recopier_si_recent(precedent, out):
    try:
        maj = json.load(open(os.path.join(precedent, "etat-contributions.json")))["maj"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if time.time() - maj >= RAFRAICHIR or not all(os.path.exists(os.path.join(precedent, f)) for f in FICHIERS):
        return False
    for f in FICHIERS + ("etat-contributions.json",):
        shutil.copy(os.path.join(precedent, f), os.path.join(out, f))
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    opt = lambda nom: args[args.index(nom) + 1] if nom in args else None
    user, out = args[0], args[1]
    precedent, local = opt("--precedent"), opt("--html")
    if precedent and recopier_si_recent(precedent, out):
        print("contributions : gardées (moins d'une heure)")
        sys.exit(0)
    days = parse(fetch(user, local))
    if len(days) < 300:
        sys.exit(f"Calendrier introuvable ou incomplet ({len(days)} jours)")
    open(f"{out}/contributions.svg", "w", encoding="utf-8").write(card_desktop(days))
    open(f"{out}/contributions-mobile.svg", "w", encoding="utf-8").write(card_mobile(days))
    json.dump({"maj": time.time()}, open(f"{out}/etat-contributions.json", "w"))
    print("contributions : régénérées", stats(days))
