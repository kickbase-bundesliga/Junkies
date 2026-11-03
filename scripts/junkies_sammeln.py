# -*- coding: utf-8 -*-
"""
Junkies: Daten sammeln (nur lesen)
==================================

Holt fuer alle Junkies-Ligen aus config/junkies.json die Spieltagswertungen und
speichert sie als kompakte JSON-Dateien in junkies/daten/. Fuer die Ligen mit
Abgabe-Regel (Liga A-C und 14er Draft) zusaetzlich:
  - Aufstellung mit Einzelpunkten je Manager und Spieltag (fuer die Top 3)
  - Transfers je Manager (fuer Haekchen / Verspaetung)
  - aktueller Kader je Manager
  - Marktwertverlauf der abzugebenden Spieler (fuer die Strafzahlung)

Ein Spieltag gilt als fertig, wenn alle Spiele beendet sind und die Kickbase-Abrechnung
(18 Uhr am Tag nach dem letzten Spiel) plus 1 Stunde vorbei ist. Danach wird er noch
48 h lang neu geholt (Nachkontrolle) und bleibt dann unveraendert liegen.

Aufruf (im Projektordner Junkies2.0):
    python scripts/junkies_sammeln.py            normal
    python scripts/junkies_sammeln.py --alles    alle Spieltage neu holen

Laeuft mit Python 3.7, nur Standardbibliothek.
"""

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kickbase import Api, zugang as zugangsdaten  # noqa: E402

CONFIG = os.path.join("config", "junkies.json")
DATEN = os.path.join("junkies", "daten")
NACHKONTROLLE_H = 48          # nach dem Abschluss noch so lange neu holen
# Kickbase rechnet am Tag nach dem letzten Spiel um 18 Uhr (Ortszeit) ab.
# Ein Spieltag gilt als fertig ab Abrechnung + 1 Stunde (normal Montag 19 Uhr).
ABRECHNUNG_UHR = 18
FERTIG_NACH_ABRECHNUNG_MIN = 60
ABGABE_FORMATE = ("quali", "draft")


# ---------------------------------------------------------------- Hilfen

def jetzt():
    return dt.datetime.now(dt.timezone.utc)


def zeit(text):
    """Kickbase-Zeit '2026-10-10T13:30:00Z' -> datetime (UTC)."""
    return dt.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)


def _letzter_sonntag(jahr, monat):
    t = dt.datetime(jahr, monat, 31 if monat in (3, 10) else 30, 1, tzinfo=dt.timezone.utc)
    return t - dt.timedelta(days=(t.weekday() + 1) % 7)


def berlin_offset(d):
    """Abstand deutsche Zeit zu UTC (Sommerzeit letzter So im Maerz bis letzter So im Oktober, 1 Uhr UTC)."""
    return dt.timedelta(hours=2 if _letzter_sonntag(d.year, 3) <= d < _letzter_sonntag(d.year, 10) else 1)


def fertig_ab(letzter_anstoss):
    """Abrechnung am Folgetag um ABRECHNUNG_UHR (Ortszeit) + FERTIG_NACH_ABRECHNUNG_MIN -> UTC."""
    lokal = letzter_anstoss + berlin_offset(letzter_anstoss)
    abrechnung = (lokal + dt.timedelta(days=1)).replace(hour=ABRECHNUNG_UHR, minute=0, second=0)
    abrechnung_utc = abrechnung - berlin_offset(abrechnung - dt.timedelta(hours=1))
    return abrechnung_utc + dt.timedelta(minutes=FERTIG_NACH_ABRECHNUNG_MIN)


def lesen(pfad, standard=None):
    if not os.path.exists(pfad):
        return standard
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def schreiben(pfad, daten):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    os.replace(tmp, pfad)


def fehler(d):
    return isinstance(d, dict) and "_fehler" in d


def zugang():
    return zugangsdaten("kwbl")


# ---------------------------------------------------------------- Spielplan

def spielplan(api, wettbewerb):
    """{spieltag: {"fertig": bool, "erster": iso, "letzter": iso}}"""
    d = api.get("/v4/competitions/%d/matchdays" % wettbewerb)
    jetzt = dt.datetime.now(dt.timezone.utc)
    plan = {}
    for tag in d.get("it", []) if isinstance(d, dict) else []:
        spiele = tag.get("it", [])
        if not spiele:
            continue
        zeiten = sorted(s["dt"] for s in spiele if s.get("dt"))
        ab = fertig_ab(zeit(zeiten[-1])) if zeiten else None
        plan[int(tag["day"])] = {
            # alle Spiele beendet UND Kickbase-Abrechnung (+1 h) vorbei
            "fertig": all(s.get("st") == 2 for s in spiele) and ab is not None and jetzt >= ab,
            "erster": zeiten[0] if zeiten else None,
            "letzter": zeiten[-1] if zeiten else None,
            "fertig_ab": ab.strftime("%Y-%m-%dT%H:%M:%SZ") if ab else None,
        }
    return plan


def muss_holen(gespeichert, info, alles):
    if alles or not gespeichert:
        return True
    if not gespeichert.get("fertig"):
        return True
    if info.get("fertig") and "aufstellungen" not in gespeichert:
        return True                      # Aufstellungen nachholen (seit 11/2026 fuer alle Formate)
    if not info or not info.get("letzter"):
        return False
    basis = zeit(info["fertig_ab"]) if info.get("fertig_ab") else zeit(info["letzter"])
    grenze = basis + dt.timedelta(hours=NACHKONTROLLE_H)
    return zeit(gespeichert["abgerufen"]) < grenze


# ---------------------------------------------------------------- Abruf

def wertung(api, lid, st, admin_ids):
    d = api.get("/v4/leagues/%s/ranking?dayNumber=%d" % (lid, st))
    if fehler(d):
        raise RuntimeError("Wertung %s ST %d: %s" % (lid, st, d))
    manager = []
    for m in d.get("us", []):
        uid = str(m.get("i"))
        manager.append({
            "id": uid,
            "name": m.get("n"),
            "admin": bool(m.get("adm")) or uid in admin_ids,
            "punkte": m.get("mdp", 0),
            "gesamt": m.get("sp", 0),
            "platz": m.get("spl"),
            "st_platz": m.get("mdpl"),
            "teamwert": m.get("tv"),
            "aufstellung_ids": [str(x) for x in (m.get("lp") or []) if x is not None],
        })
    return manager


def aufstellung(api, lid, uid, st):
    d = api.get("/v4/leagues/%s/users/%s/teamcenter?dayNumber=%d" % (lid, uid, st))
    if fehler(d):
        return None

    def spieler(liste):
        return [{"id": str(s.get("i")), "name": s.get("n"), "verein": str(s.get("tid")),
                 "punkte": s.get("p", 0) or 0} for s in liste or []]
    return {"elf": spieler(d.get("lp")), "bank": spieler(d.get("nlp"))}


def transfers(api, lid, uid):
    alle, start = [], 0
    while True:
        d = api.get("/v4/leagues/%s/managers/%s/transfer?start=%d" % (lid, uid, start))
        it = d.get("it", []) if isinstance(d, dict) else []
        alle += [{"spieler_id": str(t.get("pi")), "spieler": t.get("pn"), "art": t.get("tty"),
                  "preis": t.get("trp"), "zeit": t.get("dt")} for t in it]
        if len(it) < 25 or start > 500:
            return alle
        start += len(it)


def kader(api, lid, uid):
    d = api.get("/v4/leagues/%s/managers/%s/squad" % (lid, uid))
    return [{"id": str(s.get("pi")), "name": s.get("pn"), "marktwert": s.get("mv")}
            for s in (d.get("it", []) if isinstance(d, dict) else [])]


def marktwerte(api, lid, pid):
    d = api.get("/v4/leagues/%s/players/%s/marketvalue/92" % (lid, pid))
    werte = {}
    for e in d.get("it", []) if isinstance(d, dict) else []:
        tag = dt.date(1970, 1, 1) + dt.timedelta(days=int(e["dt"]))
        werte[tag.isoformat()] = e.get("mv")
    return werte


# ---------------------------------------------------------------- Ablauf

def liga_sammeln(api, liga, plan, admin_ids, alles):
    lid, fmt = liga["id"], liga["format"]
    ordner = os.path.join(DATEN, lid)
    akt = api.get("/v4/leagues/%s/ranking" % lid)
    letzter_st = int(akt.get("day", 0)) if isinstance(akt, dict) else 0
    print("\n%s (%s, Format %s) - aktueller Spieltag %d" % (akt.get("ti", lid), lid, fmt, letzter_st))

    geholt = []
    for st in range(1, letzter_st + 1):
        pfad = os.path.join(ordner, "st_%02d.json" % st)
        alt = lesen(pfad)
        info = plan.get(st, {})
        if not muss_holen(alt, info, alles):
            continue
        manager = wertung(api, lid, st, admin_ids)
        eintrag = {"liga": lid, "spieltag": st, "fertig": bool(info.get("fertig")),
                   "abgerufen": jetzt().strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "letzter_anstoss": info.get("letzter"), "manager": manager}
        if info.get("fertig"):
            # Aufstellungen aller Manager (Profile, Elfen des Spieltags; bei Liga A-C/Draft auch Top 3)
            eintrag["aufstellungen"] = {}
            for m in manager:
                if not m["admin"]:
                    eintrag["aufstellungen"][m["id"]] = aufstellung(api, lid, m["id"], st)
        schreiben(pfad, eintrag)
        geholt.append(st)
    print("  Spieltage geholt: %s" % (", ".join(map(str, geholt)) or "keine (alles aktuell)"))
    spieler_stammdaten(api, lid, ordner)

    if fmt not in ABGABE_FORMATE:
        return

    # Transfers und Kader (immer aktuell)
    stand = lesen(os.path.join(ordner, "st_%02d.json" % letzter_st)) or {}
    aktive = [m for m in stand.get("manager", []) if not m["admin"]]
    alle_transfers = lesen(os.path.join(ordner, "transfers.json"), {})
    kaeder = {}
    for m in aktive:
        neu = transfers(api, lid, m["id"])
        bekannt = {(t["spieler_id"], t["zeit"], t["art"]) for t in alle_transfers.get(m["id"], [])}
        alle_transfers.setdefault(m["id"], []).extend(
            t for t in neu if (t["spieler_id"], t["zeit"], t["art"]) not in bekannt)
        kaeder[m["id"]] = kader(api, lid, m["id"])
    schreiben(os.path.join(ordner, "transfers.json"), alle_transfers)
    schreiben(os.path.join(ordner, "kader.json"),
              {"abgerufen": jetzt().strftime("%Y-%m-%dT%H:%M:%SZ"), "kader": kaeder})
    print("  Transfers und Kader von %d Managern aktualisiert" % len(aktive))

    # Marktwerte der Top-4-Spieler der letzten 3 fertigen Spieltage (Strafberechnung)
    mw = lesen(os.path.join(ordner, "marktwerte.json"), {})
    spieler = set()
    for st in range(max(1, letzter_st - 2), letzter_st + 1):
        d = lesen(os.path.join(ordner, "st_%02d.json" % st)) or {}
        for uid, auf in (d.get("aufstellungen") or {}).items():
            if not auf:
                continue
            top = sorted(auf["elf"], key=lambda s: -s["punkte"])[:4]
            spieler.update(s["id"] for s in top)
    for pid in sorted(spieler):
        mw.setdefault(pid, {}).update(marktwerte(api, lid, pid))
    schreiben(os.path.join(ordner, "marktwerte.json"), mw)
    print("  Marktwertverlauf fuer %d Spieler aktualisiert" % len(spieler))


def spieler_stammdaten(api, lid, ordner):
    """Position und Verein aller aufgestellten Spieler (einmalig je Spieler) -> junkies/daten/spieler.json."""
    pfad = os.path.join(DATEN, "spieler.json")
    sp = lesen(pfad, {})
    fehlend = set()
    for fn in os.listdir(ordner):
        if not fn.startswith("st_"):
            continue
        for auf in ((lesen(os.path.join(ordner, fn)) or {}).get("aufstellungen") or {}).values():
            for s in (auf or {}).get("elf", []):
                if s["id"] not in sp:
                    fehlend.add(s["id"])
    for pid in sorted(fehlend):
        d = api.get("/v4/leagues/%s/players/%s" % (lid, pid))
        if fehler(d) or not isinstance(d, dict):
            continue
        sp[pid] = {"n": d.get("ln") or pid, "nr": d.get("shn"), "pos": d.get("pos"), "tn": d.get("tn") or ""}
    if fehlend:
        schreiben(pfad, sp)
        print("  Stammdaten fuer %d Spieler geholt" % len(fehlend))


def pokal_sammeln(cfg):
    """Spieltagspunkte aller Pokalteilnehmer aus der Challenge (eigener Account noetig)."""
    pk = cfg.get("pokal") or {}
    name = pk.get("zugang", "privat")
    if not os.environ.get(name.upper() + "_EMAIL") and not os.path.exists(os.path.join("config", name + ".txt")):
        print("\nPokal: Zugangsdaten '%s' fehlen - uebersprungen" % name)
        return
    tn = lesen(os.path.join("junkies", "pokal", "teilnehmer_ids.json"), {})
    api = Api(*zugangsdaten(name))
    ch = pk.get("challenge_id", "910")
    pfad = os.path.join(DATEN, "pokal", "punkte.json")
    alt = lesen(pfad, {})
    neu, fehler_n = {}, []
    for name, e in tn.items():
        uid = e.get("id")
        if not uid or e.get("status") != "geprueft":
            continue
        d = api.get("/v4/challenges/%s/table/%s" % (ch, uid))
        if fehler(d) or not isinstance(d.get("mds"), list):
            fehler_n.append(name)
            if name in alt:
                neu[name] = alt[name]
            continue
        punkte = {str(m["day"]): m.get("p", 0) for m in d["mds"] if m.get("t") == 2}
        # fp = in der Challenge am haeufigsten eingesetzte Spieler (Tagesaufstellungen gibt die API nicht her)
        fav = [[str(f.get("i")), f.get("n"), f.get("usc", 0), str(f.get("tid") or "")] for f in (d.get("fp") or [])]
        neu[name] = {"id": uid, "kickbase_name": (d.get("u") or {}).get("n"), "punkte": punkte, "favoriten": fav}
    schreiben(pfad, {"abgerufen": jetzt().strftime("%Y-%m-%dT%H:%M:%SZ"), "manager": neu})
    print("\nPokal: Punkte von %d Teilnehmern geholt%s" % (
        len(neu), (", Fehler bei: " + ", ".join(fehler_n)) if fehler_n else ""))


def main():
    p = argparse.ArgumentParser(description="Junkies-Daten sammeln (nur lesen)")
    p.add_argument("--alles", action="store_true", help="alle Spieltage neu holen")
    p.add_argument("--liga", help="nur diese Liga-ID")
    args = p.parse_args()

    cfg = lesen(CONFIG)
    if not cfg:
        sys.exit("config/junkies.json fehlt")
    admin_ids = set(cfg.get("admin_ids", []))
    email, pw = zugang()
    print("Login ...")
    api = Api(email, pw)
    plan = spielplan(api, cfg.get("wettbewerb", 1))
    schreiben(os.path.join(DATEN, "spielplan.json"), plan)

    for liga in cfg["ligen"]:
        if args.liga and liga["id"] != args.liga:
            continue
        try:
            liga_sammeln(api, liga, plan, admin_ids, args.alles)
        except RuntimeError as e:
            print("  FEHLER: %s" % e)
    if not args.liga:
        pokal_sammeln(cfg)
    print("\nFertig. Daten liegen in %s" % DATEN)


if __name__ == "__main__":
    main()
