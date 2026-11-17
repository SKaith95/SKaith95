"""Génère une carte SVG animée par jeu Roblox, avec les chiffres en direct.

Usage : python jeux.py <dossier_sortie> [--precedent <dossier>] [--sans-icone]
Ajoute un jeu en ajoutant son identifiant de place dans JEUX.

Les joueurs en ligne sont relus à chaque passage (toutes les 5 minutes).
Les visites, favoris, j'aime et l'icône ne sont rafraîchis qu'une fois par heure :
entre deux, on reprend les valeurs gardées dans etat-jeux.json du passage précédent.
"""
import base64
import html
import json
import os
import re
import sys
import time
import urllib.request

JEUX = [129135814237722]  # +1 Spider Evolution
RAFRAICHIR_STATS = 3600  # secondes entre deux mises à jour des stats lentes

OR, BG, TXT, MUTED, LINE, GREEN = "#FD843C", "#121214", "#FFFFFF", "#8A8B94", "#2C2D33", "#3DD68C"
SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=30).read()
    return data if raw else json.loads(data)


def infos(place, icone=True, ancien=None):
    """Lit le jeu sur Roblox. `ancien` (stats lentes de moins d'une heure) évite de les relire."""
    uid = get(f"https://apis.roblox.com/universes/v1/places/{place}/universe")["universeId"]
    g = get(f"https://games.roblox.com/v1/games?universeIds={uid}")["data"][0]
    accroche = next((l for l in g["description"].splitlines() if l.strip()), "")
    accroche = re.sub("[^\u0000-\uFFFF]|\uFE0F", "", accroche).strip()
    j = {"place": place, "nom": g["name"], "studio": g["creator"]["name"], "accroche": accroche, "joueurs": g["playing"]}
    if ancien:
        j.update({k: ancien[k] for k in ("visites", "favoris", "aime", "icone")})
        j["maj"] = ancien["maj"]
        return j
    v = get(f"https://games.roblox.com/v1/games/votes?universeIds={uid}")["data"][0]
    votes = v["upVotes"] + v["downVotes"]
    img = None
    if icone:
        url = get(f"https://thumbnails.roblox.com/v1/games/icons?universeIds={uid}&size=512x512&format=Png")["data"][0]["imageUrl"]
        img = "data:image/png;base64," + base64.b64encode(get(url, raw=True)).decode()
    j.update({"visites": g["visits"], "favoris": g["favoritedCount"],
              "aime": round(100 * v["upVotes"] / votes) if votes else None, "icone": img, "maj": time.time()})
    return j


def court(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M".replace(".", ",").replace(",0 ", " ")
    if n >= 10_000:
        return f"{n // 1000} K"
    if n >= 1000:
        return f"{n / 1000:.1f} K".replace(".", ",").replace(",0 ", " ")
    return str(n)


STYLE = """
.up{opacity:0;animation:up .8s cubic-bezier(.16,1,.3,1) forwards}
.d1{animation-delay:.1s}.d2{animation-delay:.25s}.d3{animation-delay:.4s}.d4{animation-delay:.55s}.d5{animation-delay:.7s}
.float{animation:float 5s ease-in-out infinite}
.live{animation:live 1.6s ease-in-out infinite}
.btn{animation:btn 2.6s 1.2s ease-in-out infinite}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes float{50%{transform:translateY(-6px)}}
@keyframes live{50%{opacity:.25}}
@keyframes btn{0%,100%{opacity:1}50%{opacity:.82}}
"""


def icone(j, x, y, s):
    if j["icone"]:
        img = f'<image x="{x}" y="{y}" width="{s}" height="{s}" href="{j["icone"]}" clip-path="url(#ic)"/>'
    else:
        img = f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="#2A2B31" clip-path="url(#ic)"/>'
    return (f'<defs><clipPath id="ic"><rect x="{x}" y="{y}" width="{s}" height="{s}" rx="{s * .18:.0f}"/></clipPath></defs>'
            f'<g class="float">{img}<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="{s * .18:.0f}" fill="none" stroke="#ffffff" stroke-opacity=".08" stroke-width="2"/></g>')


def stat(x, y, label, valeur, cls, taille=30, live=False):
    point = f'<circle class="live" cx="{x + 5}" cy="{y - 4}" r="4.5" fill="{GREEN}"/>' if live else ""
    lx = x + 16 if live else x
    return (f'<g class="up {cls}">{point}<text x="{lx}" y="{y}" font-family="{MONO}" font-size="12" font-weight="700" fill="{MUTED}" letter-spacing="1.5">{label}</text>'
            f'<text x="{x}" y="{y + taille + 6}" font-family="{SANS}" font-size="{taille}" font-weight="800" fill="{TXT}">{valeur}</text></g>')


def bouton(x, y, w, h, taille):
    return (f'<g class="up d5"><g class="btn"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{OR}"/>'
            f'<path d="M{x + 26} {y + h / 2 - 8}v16l13-8z" fill="#111"/>'
            f'<text x="{x + 50}" y="{y + h / 2 + taille * .36:.0f}" font-family="{SANS}" font-size="{taille}" font-weight="800" fill="#111">Jouer sur Roblox</text></g></g>')


def wrap(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><style>{STYLE}</style>'
            f'<defs><clipPath id="k"><rect width="{w}" height="{h}" rx="18"/></clipPath></defs>'
            f'<g clip-path="url(#k)"><rect width="{w}" height="{h}" fill="{BG}"/><rect width="{w}" height="6" fill="{OR}"/>{body}</g></svg>')


def carte(j):
    e = html.escape
    aime = f'{j["aime"]} %' if j["aime"] is not None else "—"
    body = [
        icone(j, 44, 44, 232),
        f'<text class="up" x="316" y="78" font-family="{MONO}" font-size="13" font-weight="700" fill="{OR}" letter-spacing="2">JEU ROBLOX · {e(j["studio"].upper())}</text>',
        f'<text class="up d1" x="314" y="138" font-family="{SANS}" font-size="52" font-weight="900" fill="{TXT}" letter-spacing="-1">{e(j["nom"])}</text>',
        f'<text class="up d1" x="316" y="174" font-family="{SANS}" font-size="20" fill="#A9A9B2">{e(j["accroche"])}</text>',
        stat(316, 232, "EN JEU", court(j["joueurs"]), "d2", live=True),
        stat(486, 232, "VISITES", court(j["visites"]), "d3"),
        stat(656, 232, "FAVORIS", court(j["favoris"]), "d4"),
        stat(826, 232, "J'AIME", aime, "d4"),
        bouton(956, 222, 208, 52, 18),
    ]
    return wrap(1200, 320, "".join(body))


def carte_mobile(j):
    e = html.escape
    aime = f'{j["aime"]} %' if j["aime"] is not None else "—"
    nom = e(j["nom"])
    taille_nom = 34 if len(j["nom"]) <= 20 else 28
    body = [
        icone(j, 24, 32, 120),
        f'<text class="up" x="160" y="58" font-family="{MONO}" font-size="11" font-weight="700" fill="{OR}" letter-spacing="1.5">JEU ROBLOX</text>',
        f'<text class="up" x="160" y="78" font-family="{MONO}" font-size="11" font-weight="700" fill="{MUTED}" letter-spacing="1">{e(j["studio"].upper())}</text>',
        f'<text class="up d1" x="22" y="196" font-family="{SANS}" font-size="{taille_nom}" font-weight="900" fill="{TXT}" letter-spacing="-1">{nom}</text>',
        f'<text class="up d1" x="24" y="226" font-family="{SANS}" font-size="15" fill="#A9A9B2">{e(j["accroche"])}</text>',
        stat(24, 274, "EN JEU", court(j["joueurs"]), "d2", 26, live=True),
        stat(210, 274, "VISITES", court(j["visites"]), "d3", 26),
        stat(24, 350, "FAVORIS", court(j["favoris"]), "d4", 26),
        stat(210, 350, "J'AIME", aime, "d4", 26),
        bouton(24, 412, 352, 52, 18),
    ]
    return wrap(400, 492, "".join(body))


TITRE = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 70" width="1200" height="70">'
         f'<text x="0" y="44" font-family="{MONO}" font-size="20" font-weight="700" fill="{OR}" letter-spacing="4">MES JEUX</text>'
         f'<rect x="150" y="37" width="1050" height="2" fill="{OR}" fill-opacity=".35"/></svg>')

TITRE_MOBILE = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 50" width="400" height="50">'
                f'<text x="0" y="32" font-family="{MONO}" font-size="17" font-weight="700" fill="{OR}" letter-spacing="3">MES JEUX</text>'
                f'<rect x="124" y="26" width="276" height="2" fill="{OR}" fill-opacity=".35"/></svg>')

def charger_etat(dossier):
    try:
        return json.load(open(os.path.join(dossier, "etat-jeux.json"), encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


if __name__ == "__main__":
    out = sys.argv[1]
    avec_icone = "--sans-icone" not in sys.argv
    precedent = sys.argv[sys.argv.index("--precedent") + 1] if "--precedent" in sys.argv else None
    etat = charger_etat(precedent) if precedent else {}
    nouvel_etat = {}
    open(f"{out}/titre-jeux.svg", "w", encoding="utf-8").write(TITRE)
    open(f"{out}/titre-jeux-mobile.svg", "w", encoding="utf-8").write(TITRE_MOBILE)
    for place in JEUX:
        ancien = etat.get(str(place))
        frais = ancien and time.time() - ancien.get("maj", 0) < RAFRAICHIR_STATS and (ancien.get("icone") or not avec_icone)
        j = infos(place, avec_icone, ancien if frais else None)
        nouvel_etat[str(place)] = {k: j[k] for k in ("maj", "visites", "favoris", "aime", "icone")}
        open(f"{out}/jeu-{place}.svg", "w", encoding="utf-8").write(carte(j))
        open(f"{out}/jeu-{place}-mobile.svg", "w", encoding="utf-8").write(carte_mobile(j))
        print(j["nom"], "joueurs", j["joueurs"], "| stats lentes", "gardées" if frais else "rafraîchies", j["visites"], j["favoris"], j["aime"])
    json.dump(nouvel_etat, open(f"{out}/etat-jeux.json", "w", encoding="utf-8"))
