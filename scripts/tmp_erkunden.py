# Temporaer: welche Felder liefern Team Center und Challenge-Endpunkte? Nur lesen, nur Schluessel + Kurzprobe.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kickbase import Api, zugang

def kurz(d, n=600):
    s = json.dumps(d, ensure_ascii=False)
    return s[:n]

def zeigen(api, titel, pfad):
    d = api.get(pfad)
    if isinstance(d, dict):
        print("### %s  %s\nSchluessel: %s %s" % (titel, pfad, list(d.keys()), d.get("_fehler", "")))
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print("  %s[0] Schluessel: %s" % (k, list(v[0].keys())))
                print("  %s[0]: %s" % (k, kurz(v[0], 400)))
    else:
        print("### %s %s -> %s" % (titel, pfad, kurz(d, 200)))

p = Api(*zugang("privat"))
tn = json.load(open("junkies/pokal/teilnehmer_ids.json"))
pu = list(tn.values())[0]["id"]
for t, pf in [("Table user", "/v4/challenges/910/table/%s" % pu),
              ("Table user ST8", "/v4/challenges/910/table/%s?dayNumber=8" % pu),
              ("Lineup overview", "/v4/challenges/910/lineup/overview"),
              ("K", "/v4/challenges/910/lineup/selection?userId=%s" % pu),
              ("L", "/v4/challenges/910/users/%s/table?dayNumber=8" % pu)]:
    try:
        zeigen(p, t, pf)
    except Exception as e:
        print(t, "Fehler", e)
