# -*- coding: utf-8 -*-
"""
Junkies-Pokal: Kickbase-IDs der Teilnehmer pruefen (nur lesen)
==============================================================

Liest junkies/pokal/teilnehmer_ids.json (Name aus meinSpielplan -> ID bzw.
Kandidaten) und fragt fuer jede ID die Challenge-Saisontabelle ab
(/v4/challenges/<ch>/table/<ID>). Kickbase liefert dort den Kickbase-Namen mit.
So sehen wir, ob die ID wirklich in der Challenge spielt und zum Namen passt.
Mehrdeutige Namen werden so automatisch aufgeloest.

Fehlende IDs kannst du vorher selbst in teilnehmer_ids.json eintragen
("id": "1234567") - dann prueft das Skript sie mit.

Aufruf (im Projektordner Junkies2.0, mit dem Account aus config/privat.txt):
    python scripts/junkies_pokal_ids.py

Ergebnis: teilnehmer_ids.json wird aktualisiert, offene Faelle stehen am Ende.
"""

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kickbase import Api, zugang  # noqa: E402

PFAD = os.path.join("junkies", "pokal", "teilnehmer_ids.json")
CHALLENGE = "910"


def norm(s):
    s = (s or "").lower().replace("ü", "u").replace("ä", "a").replace("ö", "o").replace("š", "s")
    return re.sub(r"[^a-z0-9]", "", s)


def aehnlich(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zugang", default="privat", help="Name der Zugangsdatei in config/ (Standard: privat)")
    args = p.parse_args()
    name = os.path.splitext(os.path.basename(args.zugang))[0]
    api = Api(*zugang(name))
    with open(PFAD, encoding="utf-8") as f:
        tn = json.load(f)

    cache = {}

    def kickbase_name(uid):
        if uid not in cache:
            d = api.get("/v4/challenges/%s/table/%s" % (CHALLENGE, uid))
            if isinstance(d, dict) and "_fehler" not in d and isinstance(d.get("u"), dict):
                cache[uid] = d["u"].get("n")
            else:
                cache[uid] = None
        return cache[uid]

    for name, e in sorted(tn.items(), key=lambda x: (x[1]["gruppe"], x[0])):
        ids = [e["id"]] if e.get("id") else list(e.get("kandidaten") or [])
        if not ids:
            continue
        treffer = []
        for uid in ids:
            kb = kickbase_name(uid)
            if kb is not None:
                treffer.append((aehnlich(name, kb), uid, kb))
        treffer.sort(reverse=True)
        if treffer and e.get("manuell"):
            q, uid, kb = treffer[0]
            e.update(id=uid, kickbase_name=kb, status="geprueft")
            print("  ok     %-22s -> %-9s (%s, vom Admin eingetragen)" % (name, uid, kb))
        elif treffer and treffer[0][0] >= 0.6:
            q, uid, kb = treffer[0]
            e.update(id=uid, kickbase_name=kb, status="geprueft")
            print("  ok     %-22s -> %-9s (%s)" % (name, uid, kb))
        elif treffer:
            e.update(status="pruefen", gefunden=[{"id": u, "kickbase_name": k} for _, u, k in treffer])
            print("  ?      %-22s -> %s" % (name, ", ".join("%s (%s)" % (u, k) for _, u, k in treffer)))
        else:
            e.update(status="nicht_in_challenge")
            print("  FEHLT  %-22s Kandidaten %s nicht in der Challenge" % (name, ", ".join(ids)))

    with open(PFAD, "w", encoding="utf-8") as f:
        json.dump(tn, f, ensure_ascii=False, indent=1)
    offen = sorted((e["gruppe"], n, e["status"]) for n, e in tn.items() if e["status"] != "geprueft")
    print("\nGeprueft: %d von %d" % (len(tn) - len(offen), len(tn)))
    if offen:
        print("Offen (bitte Kickbase-ID nachfragen und in %s eintragen):" % PFAD)
        for g, n, s in offen:
            print("  Gruppe %s  %-22s %s" % (g, n, s))


if __name__ == "__main__":
    main()
