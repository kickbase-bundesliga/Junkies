# -*- coding: utf-8 -*-
"""
Kickbase-API (v4) fuer die Junkies-Skripte - nur Standardbibliothek, Python 3.7.

Zugangsdaten:
  1. Umgebungsvariablen <NAME>_EMAIL und <NAME>_PASSWORT (online aus GitHub Secrets),
     z. B. KWBL_EMAIL / KWBL_PASSWORT oder PRIVAT_EMAIL / PRIVAT_PASSWORT
  2. sonst Datei config/<name>.txt (Zeile 1 E-Mail, Zeile 2 Passwort)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASIS = "https://api.kickbase.com"
PAUSE = 0.4  # Sekunden zwischen zwei Anfragen (API schonen)


def zugang(name):
    """(E-Mail, Passwort) fuer z. B. 'kwbl' oder 'privat'."""
    prefix = name.upper()
    email = os.environ.get(prefix + "_EMAIL", "").strip()
    passwort = os.environ.get(prefix + "_PASSWORT", "").strip()
    if email and passwort:
        return email, passwort
    pfad = os.path.join("config", name + ".txt")
    if not os.path.exists(pfad):
        sys.exit("Keine Zugangsdaten fuer '%s': Datei %s fehlt (Zeile 1 E-Mail, 2 Passwort) "
                 "bzw. Secrets %s_EMAIL / %s_PASSWORT." % (name, pfad, prefix, prefix))
    with open(pfad, encoding="utf-8-sig") as f:
        zeilen = [z.strip() for z in f.read().splitlines() if z.strip()]
    return zeilen[0], zeilen[1]


class Api:
    def __init__(self, email, passwort):
        self.token = None
        antwort = self._anfrage("POST", "/v4/user/login",
                                {"em": email, "pass": passwort, "loy": False, "rep": {}})
        self.token = antwort.get("tkn") if isinstance(antwort, dict) else None
        if not self.token:
            sys.exit("Login fehlgeschlagen (%s): %s" % (email, json.dumps(antwort, ensure_ascii=False)[:300]))
        self.login_antwort = antwort

    @classmethod
    def anmelden(cls, name):
        return cls(*zugang(name))

    def _anfrage(self, methode, pfad, body=None, versuche=3):
        daten = json.dumps(body).encode("utf-8") if body is not None else None
        for versuch in range(versuche):
            req = urllib.request.Request(BASIS + pfad, data=daten, method=methode)
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            if daten is not None:
                req.add_header("Content-Type", "application/json")
            if self.token:
                req.add_header("Authorization", "Bearer " + self.token)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    text = r.read().decode("utf-8")
                time.sleep(PAUSE)
                try:
                    return json.loads(text) if text else {}
                except ValueError:
                    return {"_fehler": "keine JSON-Antwort"}
            except urllib.error.HTTPError as e:
                time.sleep(PAUSE)
                if e.code in (429, 500, 502, 503, 504) and versuch < versuche - 1:
                    time.sleep(3 * (versuch + 1))
                    continue
                return {"_fehler": e.code}
            except Exception as e:  # Netzwerkproblem o. ae.
                if versuch < versuche - 1:
                    time.sleep(3)
                    continue
                return {"_fehler": str(e)}
        return {"_fehler": "unbekannt"}

    def get(self, pfad):
        return self._anfrage("GET", pfad)
