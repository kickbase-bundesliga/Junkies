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
        print("### %s  %s\nSchluessel: %s" % (titel, pfad, list(d.keys())))
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print("  %s[0] Schluessel: %s" % (k, list(v[0].keys())))
                print("  %s[0]: %s" % (k, kurz(v[0], 400)))
    else:
        print("### %s %s -> %s" % (titel, pfad, kurz(d, 200)))

a = Api(*zugang("kwbl"))
st = json.load(open("junkies/daten/6883396/st_08.json"))
uid = [m["id"] for m in st["manager"] if not m["admin"]][0]
zeigen(a, "Teamcenter KO", "/v4/leagues/6883396/users/%s/teamcenter?dayNumber=8" % uid)
zeigen(a, "Spieler", "/v4/leagues/6883396/players/%s" % st["manager"][0]["aufstellung_ids"][0])

p = Api(*zugang("privat"))
tn = json.load(open("junkies/pokal/teilnehmer_ids.json"))
pu = list(tn.values())[0]["id"]
for t, pf in [("Table user", "/v4/challenges/910/table/%s" % pu),
              ("Table user ST8", "/v4/challenges/910/table/%s?dayNumber=8" % pu),
              ("Lineup overview", "/v4/challenges/910/lineup/overview"),
              ("Lineup user", "/v4/challenges/910/users/%s/lineup?dayNumber=8" % pu),
              ("Lineup user2", "/v4/challenges/910/lineup/%s?dayNumber=8" % pu),
              ("Teamcenter user", "/v4/challenges/910/users/%s/teamcenter?dayNumber=8" % pu),
              ("Performance", "/v4/challenges/910/performance?userId=%s" % pu),
              ("Ranking ST8", "/v4/challenges/910/ranking?dayNumber=8"),
              ("Table ST8", "/v4/challenges/910/table?dayNumber=8")]:
    try:
        zeigen(p, t, pf)
    except Exception as e:
        print(t, "Fehler", e)
