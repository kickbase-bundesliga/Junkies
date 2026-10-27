# -*- coding: utf-8 -*-
"""
Junkies: Webseite bauen
=======================

Rechnet mit junkies_auswerten.py alles aus und schreibt eine einzelne Seite
junkies/webseite/index.html (Daten und Logo sind eingebettet, laeuft offline).

Aufruf (im Projektordner Junkies2.0):
    python scripts/junkies_webseite.py
Danach junkies/webseite/index.html im Browser oeffnen.
"""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from junkies_auswerten import auswerten  # noqa: E402

VORLAGE = os.path.join("scripts", "junkies_vorlage.html")
LOGO = os.path.join("junkies", "logo.png")
ZIEL = os.path.join("junkies", "webseite", "index.html")


def main():
    daten = auswerten()
    with open(VORLAGE, encoding="utf-8") as f:
        html = f.read()
    logo = ""
    if os.path.exists(LOGO):
        with open(LOGO, "rb") as f:
            logo = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    json_text = json.dumps(daten, ensure_ascii=False, separators=(",", ":"), default=str)
    json_text = json_text.replace("</", "<\\/")
    html = html.replace("__LOGO__", logo).replace("__DATEN__", json_text)
    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    with open(ZIEL, "w", encoding="utf-8") as f:
        f.write(html)
    print("Fertig: %s (Spieltag %s)" % (ZIEL, daten.get("spieltag")))


if __name__ == "__main__":
    main()
