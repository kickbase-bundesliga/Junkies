# -*- coding: utf-8 -*-
"""
Junkies: Auswertung (Tabellen, Abgabelisten, Knock Out, Playoffs)
=================================================================

Liest junkies/daten/ und config/junkies.json und erzeugt ein Datenpaket fuer die
Webseite (Funktion auswerten()). Wird von junkies_webseite.py benutzt.
Rechnet nur, ruft nichts von Kickbase ab.
"""

import datetime as dt
import json
import os

DATEN = os.path.join("junkies", "daten")
CONFIG = os.path.join("config", "junkies.json")
UTC = dt.timezone.utc


# ---------------------------------------------------------------- Zeit (Berlin)

def _letzter_sonntag(jahr, monat):
    d = dt.date(jahr, monat, 31)
    while d.weekday() != 6:
        d -= dt.timedelta(days=1)
    return d


def berlin_offset(t_utc):
    """Sommerzeit: letzter So im Maerz 01:00 UTC bis letzter So im Oktober 01:00 UTC."""
    j = t_utc.year
    beginn = dt.datetime.combine(_letzter_sonntag(j, 3), dt.time(1), UTC)
    ende = dt.datetime.combine(_letzter_sonntag(j, 10), dt.time(1), UTC)
    return dt.timedelta(hours=2 if beginn <= t_utc < ende else 1)


def nach_berlin(t_utc):
    return (t_utc + berlin_offset(t_utc)).replace(tzinfo=None)


def von_berlin(t_lokal):
    """Naive Berliner Zeit -> UTC."""
    roh = t_lokal.replace(tzinfo=UTC)
    return roh - berlin_offset(roh - dt.timedelta(hours=1))


def zeit(text):
    if not text:
        return None
    return dt.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


# ---------------------------------------------------------------- Laden

def lesen(pfad, standard=None):
    if not os.path.exists(pfad):
        return standard
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def spieltage_laden(lid):
    erg = {}
    ordner = os.path.join(DATEN, lid)
    if not os.path.isdir(ordner):
        return erg
    for name in os.listdir(ordner):
        if name.startswith("st_") and name.endswith(".json"):
            d = lesen(os.path.join(ordner, name))
            erg[int(d["spieltag"])] = d
    return erg


# ---------------------------------------------------------------- Tabellen

def sortiert(manager):
    """Gesamtpunkte absteigend, bei Gleichstand geringerer Teamwert vorn."""
    return sorted(manager, key=lambda m: (-(m["gesamt"] or 0), m["teamwert"] or 0, m["name"].lower()))


def tabelle(st_daten, ausschluss=(), korrektur=None, st=None):
    ms = []
    for m in st_daten["manager"]:
        if m["admin"] or m["name"].strip() in ausschluss:
            continue
        m = dict(m)
        m["name"] = m["name"].strip()
        if korrektur and m["name"] in korrektur and str(st) in korrektur[m["name"]]:
            m["gesamt"] = korrektur[m["name"]][str(st)]
            m["korrigiert"] = True
        ms.append(m)
    zeilen = []
    for i, m in enumerate(sortiert(ms), 1):
        zeilen.append({"platz": i, "id": m["id"], "name": m["name"], "punkte": m["punkte"],
                       "gesamt": m["gesamt"], "teamwert": m["teamwert"],
                       "korrigiert": m.get("korrigiert", False)})
    # Spieltagsplatz selbst berechnen
    for i, z in enumerate(sorted(zeilen, key=lambda z: (-(z["punkte"] or 0), z["teamwert"] or 0)), 1):
        z["st_platz"] = i
    return zeilen


# ---------------------------------------------------------------- Fristen, Strafen

def frist(st, plan, cfg):
    manuell = cfg.get("fristen_manuell", {}).get(str(st))
    if manuell:
        return von_berlin(dt.datetime.strptime(manuell, "%Y-%m-%dT%H:%M")), "manuell"
    info = plan.get(str(st)) or {}
    letzter = zeit(info.get("letzter"))
    if not letzter:
        return None, None
    lokal = nach_berlin(letzter)
    wt = lokal.weekday()  # Mo=0
    if wt in (1, 2, 3):   # Di-Do: englische Woche -> Freitag 20 Uhr
        tag = lokal.date() + dt.timedelta(days=4 - wt)
        return von_berlin(dt.datetime.combine(tag, dt.time(20))), "englische Woche"
    tage = (1 - wt) % 7 or 7  # naechster Dienstag
    tag = lokal.date() + dt.timedelta(days=tage)
    return von_berlin(dt.datetime.combine(tag, dt.time(22))), "Regelfall"


def mw_am(werte, tag):
    if not werte:
        return None
    if tag.isoformat() in werte:
        return werte[tag.isoformat()]
    frueher = sorted(k for k in werte if k <= tag.isoformat())
    return werte[frueher[-1]] if frueher else None


def strafe(preis, mw_frist, frist_utc, verkauf_utc, pro_tag):
    """MW-Gewinn ab Frist (nie negativ) + Gebuehr je weiteren angefangenen Tag."""
    spaet = verkauf_utc - frist_utc
    tage = int(-(-spaet.total_seconds() // 86400))  # aufrunden
    gebuehr = max(0, tage - 1) * pro_tag
    diff = max(0, (preis or 0) - mw_frist) if mw_frist is not None and preis is not None else None
    return {"mw_frist": mw_frist, "mw_diff": diff, "tage": tage, "gebuehr": gebuehr,
            "summe": (diff or 0) + gebuehr}


# ---------------------------------------------------------------- Abgabelisten

def verkauf_suchen(transfers_mgr, pid, ab):
    kand = [t for t in transfers_mgr if t["art"] == 2 and t["spieler_id"] == pid and zeit(t["zeit"]) >= ab]
    return min(kand, key=lambda t: t["zeit"]) if kand else None


def kaeufer_suchen(alle_transfers, verkaeufer, pid, t_verkauf):
    for uid, liste in alle_transfers.items():
        if uid == verkaeufer:
            continue
        for t in liste:
            if t["art"] == 1 and t["spieler_id"] == pid and abs((zeit(t["zeit"]) - t_verkauf).total_seconds()) < 180:
                return uid
    return None


def verkauf_info(pid, uid, ctx):
    """Wurde der Spieler nach Spieltagsbeginn verkauft? An wen?"""
    v = verkauf_suchen(ctx["transfers"].get(uid, []), pid, ctx["ab"])
    if not v:
        return None
    tv = zeit(v["zeit"])
    kaeufer = kaeufer_suchen(ctx["transfers"], uid, pid, tv)
    return {"zeit": tv, "preis": v["preis"], "an": ctx["namen"].get(kaeufer, kaeufer) if kaeufer else None}


def aufgestellt_danach(pid, uid, ctx, verkauf):
    """Stand der Spieler am naechsten Spieltag noch in der Elf (und war da noch nicht verkauft)?"""
    n = ctx["naechste"]
    if not n:
        return None
    auf = (n.get("aufstellungen") or {}).get(uid) or {}
    if pid not in [x["id"] for x in auf.get("elf", [])]:
        return None
    if verkauf and ctx["naechster_anstoss"] and verkauf["zeit"] < ctx["naechster_anstoss"]:
        return None
    return n["spieltag"]


def manager_abgabe(z, kandidaten, ctx, ersatzregel):
    """Regel: mindestens EINER der Top 3 muss verkauft werden.
    Liga A-C: Verkauf an einen anderen Manager zaehlt nicht, dann rueckt der naechste (Top 4) nach."""
    def grenze(rang):
        """Anzahl Kandidaten: alle mit mindestens so vielen Punkten wie der Spieler auf Rang <rang>."""
        if len(kandidaten) < rang:
            return len(kandidaten)
        p = kandidaten[rang - 1]["punkte"]
        return sum(1 for k in kandidaten if k["punkte"] >= p)

    rang, liste = 3, []
    pool_n = grenze(rang)
    for i, s in enumerate(kandidaten):
        if i >= pool_n:
            break
        v = verkauf_info(s["id"], z["id"], ctx)
        e = {"id": s["id"], "name": s["name"], "punkte": s["punkte"], "ersatz": False,
             "gleichstand": i >= 3 and s["punkte"] == kandidaten[2]["punkte"],
             "verkauft": iso(v["zeit"]) if v else None, "preis": v["preis"] if v else None,
             "an_manager": v["an"] if v else None, "status": None, "strafe": None, "_v": v}
        e["ersatz"] = i >= 3 and not e["gleichstand"]
        if v and v["an"] and ersatzregel:
            e["status"] = "an_manager"
            rang += 1
            pool_n = grenze(rang)
        liste.append(e)
    gueltig = [e for e in liste if e["_v"] and e["status"] != "an_manager"]
    erster = min(gueltig, key=lambda e: e["_v"]["zeit"]) if gueltig else None
    f = ctx["frist"]
    strafe_m = None
    if erster:
        if f and erster["_v"]["zeit"] > f:
            status = "zu_spaet"
            mw = mw_am(ctx["mw"].get(erster["id"]), nach_berlin(f).date())
            strafe_m = strafe(erster["preis"], mw, f, erster["_v"]["zeit"], ctx["pro_tag"])
            erster["strafe"] = strafe_m
            erster["status"] = "zu_spaet"
        else:
            status = "erfuellt"
            erster["status"] = "ok"
    else:
        status = "ueberfaellig" if f and ctx["jetzt"] > f else "offen"
        if status == "ueberfaellig":
            strafe_m = strafe(None, None, f, ctx["jetzt"], ctx["pro_tag"])
    for e in liste:
        if e["status"]:
            pass
        elif e["_v"]:
            e["status"] = "auch_verkauft"
        else:
            e["status"] = "bleibt" if erster else ("ueberfaellig" if status == "ueberfaellig" else "offen")
        if e["status"] == "ueberfaellig" and f:
            werte = ctx["mw"].get(e["id"]) or {}
            mw_f = mw_am(werte, nach_berlin(f).date())
            if werte and mw_f is not None:
                e["mw_seit_frist"] = werte[max(werte)] - mw_f
        if status in ("zu_spaet", "ueberfaellig") and e["status"] in ("zu_spaet", "ueberfaellig"):
            nach = aufgestellt_danach(e["id"], z["id"], ctx, e["_v"])
            if nach:
                e["aufgestellt_nach_frist"] = nach
        del e["_v"]
    return {"name": z["name"], "punkte": z["punkte"], "spieler": liste, "status": status,
            "erledigt": status in ("erfuellt", "zu_spaet"),
            "strafe": (strafe_m or {}).get("summe", 0), "strafe_info": strafe_m}


def abgabeliste(liga, st, sts, plan, cfg, jetzt, fmt):
    d = sts.get(st)
    if not d or not d.get("fertig") or not d.get("aufstellungen"):
        return None
    ordner = os.path.join(DATEN, liga["id"])
    transfers = lesen(os.path.join(ordner, "transfers.json"), {})
    mw = lesen(os.path.join(ordner, "marktwerte.json"), {})
    grenze = cfg["abgabe"]["grenze_punkte"]
    f, f_art = frist(st, plan, cfg)
    ab = zeit((plan.get(str(st)) or {}).get("erster")) or zeit(d["abgerufen"])
    tab = tabelle(d)
    namen = {m["id"]: m["name"].strip() for m in d["manager"]}
    ctx = {"transfers": transfers, "mw": mw, "frist": f, "ab": ab, "jetzt": jetzt, "namen": namen,
           "pro_tag": cfg["abgabe"]["strafe_pro_tag"], "naechste": sts.get(st + 1),
           "naechster_anstoss": zeit((plan.get(str(st + 1)) or {}).get("erster"))}
    ersatzregel = fmt == "quali"

    def top(uid, n):
        auf = d["aufstellungen"].get(uid) or {}
        return sorted(auf.get("elf", []), key=lambda s: -(s["punkte"] or 0))[:n]

    erg = {"spieltag": st, "frist": iso(f), "frist_art": f_art, "sieger": None, "manager": []}

    sieger_id = None
    if fmt == "draft" and tab:
        sieger = sorted(tab, key=lambda z: (-(z["punkte"] or 0), z["teamwert"] or 0))[0]
        letzter = tab[-1]
        sieger_id = sieger["id"]
        spieler = []
        for s in top(sieger["id"], 3):
            kauf = [t for t in transfers.get(letzter["id"], [])
                    if t["art"] == 1 and t["spieler_id"] == s["id"] and zeit(t["zeit"]) >= ab]
            spieler.append({"id": s["id"], "name": s["name"], "punkte": s["punkte"],
                            "an_letzten": iso(zeit(min(kauf, key=lambda t: t["zeit"])["zeit"])) if kauf else None,
                            "preis": kauf[0]["preis"] if kauf else None})
        erg["sieger"] = {"name": sieger["name"], "punkte": sieger["punkte"],
                         "letzter": letzter["name"], "spieler": spieler,
                         "erledigt": any(s["an_letzten"] for s in spieler)}

    for z in tab:
        if z["id"] == sieger_id or (z["punkte"] or 0) < grenze:
            continue
        erg["manager"].append(manager_abgabe(z, top(z["id"], 11), ctx, ersatzregel))
    erg["manager"].sort(key=lambda m: -m["punkte"])
    return erg


# ---------------------------------------------------------------- Knock Out

def knockout(liga, sts, cfg):
    ko = cfg["ko"]
    korr = cfg.get("korrekturen_gesamt", {}).get(liga["id"], {})
    raus = {e["manager"].strip(): e for e in ko.get("ausgeschieden", [])}
    tabellen, vorschlaege = {}, []
    for st in sorted(sts):
        ausgeschlossen = {n for n, e in raus.items() if e["nach_st"] < st}
        tabellen[st] = tabelle(sts[st], ausgeschlossen, korr, st)
    fertig = [st for st in sorted(sts) if sts[st].get("fertig")]
    akt = fertig[-1] if fertig else 0
    # Vorschlag: Letzter nach jedem Rauswurf-Spieltag, der noch nicht eingetragen ist
    erledigte = {e["nach_st"] for e in raus.values()}
    freiwillig = sum(1 for e in raus.values() if e.get("grund") == "freiwillig")
    for st in ko["rauswurf_nach"]:
        if st in fertig and st not in erledigte and tabellen.get(st):
            vorschlaege.append({"nach_st": st, "manager": tabellen[st][-1]["name"]})
    naechster = next((s for s in ko["rauswurf_nach"] if s > akt or (s == akt and s not in erledigte)), None)
    aktiv = [z for z in tabellen.get(akt, []) if z["name"] not in raus or raus[z["name"]]["nach_st"] >= akt]
    # Ausgeschiedene mit Punkten zum Zeitpunkt des Ausscheidens
    liste = []
    for n, e in sorted(raus.items(), key=lambda x: -x[1]["nach_st"]):
        zeile = next((z for z in tabellen.get(e["nach_st"], []) if z["name"] == n), None)
        liste.append({"name": n, "nach_st": e["nach_st"], "grund": e.get("grund", "rauswurf"),
                      "gesamt": zeile["gesamt"] if zeile else None})
    aktive_n = len([z for z in tabellen.get(akt, []) if z["name"] not in raus])
    return {"tabellen": tabellen, "akt": akt, "naechster_rauswurf": naechster,
            "gefaehrdet": (sorted([z for z in tabellen.get(akt, []) if z["name"] not in raus],
                                  key=lambda z: (-(z["gesamt"] or 0), z["teamwert"] or 0)) or [{}])[-1].get("name"),
            "aktive": aktive_n, "ausgeschieden": liste, "vorschlaege": vorschlaege,
            "rauswurf_nach": ko["rauswurf_nach"], "freiwillig": freiwillig}


# ---------------------------------------------------------------- Playoffs

BAUM = [(1, 16), (8, 9), (4, 13), (5, 12), (2, 15), (7, 10), (3, 14), (6, 11)]


def serie(a, b, spieltage, sts):
    """a, b: Manager-Dicts mit id. Liefert Spiele bis zur Entscheidung."""
    noetig = len(spieltage) // 2 + 1
    sa = sb = 0
    spiele = []
    for st in spieltage:
        if sa >= noetig or sb >= noetig:
            break
        d = sts.get(st)
        if not d or not d.get("fertig"):
            spiele.append({"st": st, "offen": True})
            continue
        ma = next((m for m in d["manager"] if m["id"] == a["id"]), None)
        mb = next((m for m in d["manager"] if m["id"] == b["id"]), None)
        if not ma or not mb:
            spiele.append({"st": st, "offen": True})
            continue
        pa, pb = ma["punkte"], mb["punkte"]
        a_gewinnt = pa > pb or (pa == pb and (ma["teamwert"] or 0) < (mb["teamwert"] or 0))
        if a_gewinnt:
            sa += 1
        else:
            sb += 1
        spiele.append({"st": st, "a": pa, "b": pb, "sieger": "a" if a_gewinnt else "b"})
    sieger = a if sa >= noetig else b if sb >= noetig else None
    verlierer = (b if sieger is a else a) if sieger else None
    return {"a": a, "b": b, "stand": [sa, sb], "spiele": spiele, "sieger": sieger, "verlierer": verlierer}


def playoff(liga, sts, cfg):
    po = cfg["playoff"]
    hr = po["hauptrunde_bis"]
    fertig = [st for st in sorted(sts) if sts[st].get("fertig")]
    akt = fertig[-1] if fertig else 0
    tabellen = {st: tabelle(sts[st]) for st in sorted(sts) if st <= hr}
    basis = min(akt, hr)
    setz = tabellen.get(basis, [])
    seeds = {z["platz"]: {"id": z["id"], "name": z["name"], "seed": z["platz"]} for z in setz}
    runden = []
    paare = [(seeds.get(a), seeds.get(b)) for a, b in BAUM]
    verlierer_hf = []
    for r in po["runden"]:
        serien = []
        for a, b in paare:
            if a and b and akt >= hr:
                serien.append(serie(a, b, r["st"], sts))
            else:
                serien.append({"a": a, "b": b, "stand": [0, 0], "spiele": [], "sieger": None, "vorschau": True})
        runden.append({"name": r["name"], "st": r["st"], "serien": serien})
        if r["name"] == "Halbfinale":
            verlierer_hf = [s.get("verlierer") for s in serien]
        if r["name"] == "Finale":
            break
        sieger = [s.get("sieger") for s in serien]
        paare = [(sieger[i], sieger[i + 1]) for i in range(0, len(sieger), 2)]
    if len(verlierer_hf) == 2 and all(verlierer_hf):
        platz3 = serie(verlierer_hf[0], verlierer_hf[1], po["runden"][-1]["st"], sts)
    else:
        platz3 = {"a": None, "b": None, "stand": [0, 0], "spiele": [], "sieger": None, "vorschau": True}
    return {"tabellen": tabellen, "akt": akt, "hauptrunde_bis": hr, "runden": runden, "platz3": platz3,
            "setzliste_vorlaeufig": akt < hr}


# ---------------------------------------------------------------- Quali A-C

def quali_uebersicht(ligen_daten, st):
    liga1, liga2, raus = [], [], []
    for l in ligen_daten:
        tab = l["tabellen"].get(st, [])
        for z in tab:
            e = {"name": z["name"], "liga": l["kurz"], "platz": z["platz"], "gesamt": z["gesamt"],
                 "teamwert": z["teamwert"]}
            (liga1 if z["platz"] <= 5 else liga2 if z["platz"] <= 10 else raus).append(e)
    key = lambda e: (-(e["gesamt"] or 0), e["teamwert"] or 0)  # noqa: E731
    return {"liga1": sorted(liga1, key=key), "liga2": sorted(liga2, key=key), "raus": sorted(raus, key=key)}


# ---------------------------------------------------------------- Pokal

def pokal(cfg, plan):
    pk = cfg.get("pokal")
    gp = lesen(os.path.join("junkies", "pokal", "gruppenphase.json"))
    if not pk or not gp:
        return None
    tn = lesen(os.path.join("junkies", "pokal", "teilnehmer_ids.json"), {})
    pd = lesen(os.path.join(DATEN, "pokal", "punkte.json"), {"manager": {}})
    inaktiv = set(pk.get("inaktiv", []))
    fertig = sorted(int(st) for st, i in plan.items() if i.get("fertig"))
    akt = max([st for st in fertig if st <= pk.get("gruppenphase_bis", 18)] or [0])

    # Automatischer Ausschluss: 3x 0 Punkte (nicht aufgestellt) -> alle Spiele mit 0 gewertet
    nullrunden = int(pk.get("ausschluss_nach_nullrunden", 3))
    ausgeschlossen = {}
    for name, m in pd["manager"].items():
        nullen = [st for st in range(1, akt + 1) if not m["punkte"].get(str(st))]
        if len(nullen) >= nullrunden:
            ausgeschlossen[name] = nullen[nullrunden - 1]
    for name in pk.get("inaktiv", []):
        ausgeschlossen.setdefault(name, None)
    inaktiv = set(ausgeschlossen)

    def punkte(name, st):
        if name in inaktiv:
            return 0
        m = pd["manager"].get(name)
        if not m:
            return None
        # kein Eintrag fuer einen gewerteten Spieltag = nicht aufgestellt = 0 Punkte
        return m["punkte"].get(str(st), 0)

    gruppen = {}
    for g, namen in gp["gruppen"].items():
        tab = {n: {"name": n, "sp": 0, "s": 0, "u": 0, "n": 0, "plus": 0, "minus": 0, "pkt": 0,
                   "id_fehlt": not (n in pd["manager"] or n in inaktiv),
                   "inaktiv": n in inaktiv, "ausgeschlossen_st": ausgeschlossen.get(n)} for n in namen}
        spieltage = {}
        for s in gp["spiele"][g]:
            st = s["st"]
            pa = punkte(s["heim"], st) if st <= akt else None
            pb = punkte(s["gast"], st) if st <= akt else None
            ergebnis = {"heim": s["heim"], "gast": s["gast"], "a": pa, "b": pb}
            if st <= akt and pa is not None and pb is not None:
                for n, x, y in ((s["heim"], pa, pb), (s["gast"], pb, pa)):
                    t = tab[n]
                    t["sp"] += 1
                    t["plus"] += x
                    t["minus"] += y
                    if x > y:
                        t["s"] += 1
                        t["pkt"] += 2
                    elif x == y:
                        t["u"] += 1
                        t["pkt"] += 1
                    else:
                        t["n"] += 1
            elif st <= akt:
                ergebnis["offen"] = True
            spieltage.setdefault(st, []).append(ergebnis)
        for st, liste in spieltage.items():
            dabei = {p for e in liste for p in (e["heim"], e["gast"])}
            frei = [n for n in namen if n not in dabei]
            spieltage[st] = {"spiele": liste, "frei": frei[0] if frei else None}
        zeilen = sorted(tab.values(), key=lambda t: (-t["pkt"], -t["plus"], t["name"].lower()))
        for i, z in enumerate(zeilen, 1):
            z["platz"] = i
        gruppen[g] = {"tabelle": zeilen, "spieltage": spieltage}
    fehlende = sorted(n for n in tn if n not in pd["manager"] and n not in inaktiv)
    return {"gruppen": gruppen, "akt": akt, "gruppenphase_bis": pk.get("gruppenphase_bis", 18),
            "runden": pk.get("runden", []), "ids_fehlen": fehlende,
            "ausgeschlossen": [{"name": n, "st": st} for n, st in sorted(ausgeschlossen.items())],
            "stand_punkte": pd.get("abgerufen")}


# ---------------------------------------------------------------- Gesamt

def auswerten(jetzt=None):
    jetzt = jetzt or dt.datetime.now(UTC)
    cfg = lesen(CONFIG)
    plan = lesen(os.path.join(DATEN, "spielplan.json"), {})
    erg = {"saison": cfg.get("saison"), "stand": iso(jetzt), "formate": {}}
    quali = []
    akt_gesamt = 0
    for liga in cfg["ligen"]:
        sts = spieltage_laden(liga["id"])
        fertig = [st for st in sorted(sts) if sts[st].get("fertig")]
        akt = fertig[-1] if fertig else 0
        akt_gesamt = max(akt_gesamt, akt)
        fmt = liga["format"]
        namen = liga["namen"]
        if fmt == "quali":
            name = namen["hinrunde"] if akt <= cfg["hinrunde_bis"] else (namen.get("rueckrunde") or namen["hinrunde"])
            quali.append({"id": liga["id"], "name": name, "kurz": name.replace("Junkies ", ""), "akt": akt,
                          "tabellen": {st: tabelle(sts[st]) for st in sorted(sts)},
                          "abgaben": {st: abgabeliste(liga, st, sts, plan, cfg, jetzt, fmt) for st in fertig}})
        elif fmt == "draft":
            erg["formate"]["draft"] = {"id": liga["id"], "name": namen["saison"], "akt": akt,
                                       "tabellen": {st: tabelle(sts[st]) for st in sorted(sts)},
                                       "abgaben": {st: abgabeliste(liga, st, sts, plan, cfg, jetzt, fmt)
                                                   for st in fertig}}
        elif fmt == "ko":
            erg["formate"]["ko"] = dict(knockout(liga, sts, cfg), id=liga["id"], name=namen["saison"])
        elif fmt == "playoff":
            erg["formate"]["playoff"] = dict(playoff(liga, sts, cfg), id=liga["id"], name=namen["saison"])
    if quali:
        akt_q = max(l["akt"] for l in quali)
        erg["formate"]["quali"] = {"ligen": quali, "akt": akt_q, "hinrunde_bis": cfg["hinrunde_bis"],
                                   "uebersicht": {st: quali_uebersicht(quali, st) for st in range(1, akt_q + 1)}}
    p = pokal(cfg, plan)
    if p:
        erg["formate"]["pokal"] = p
    erg["spieltag"] = akt_gesamt
    erg["fristen"] = {st: iso(frist(st, plan, cfg)[0]) for st in range(1, akt_gesamt + 2)}
    return erg


if __name__ == "__main__":
    import sys
    e = auswerten()
    json.dump(e, sys.stdout, ensure_ascii=False, indent=1, default=str)
