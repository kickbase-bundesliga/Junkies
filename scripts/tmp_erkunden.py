# Temporaer: Challenge-Aufstellung anderer Manager finden. Nur lesen.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kickbase import Api, zugang
def kurz(d, n=500): return json.dumps(d, ensure_ascii=False)[:n]
p = Api(*zugang("privat"))
tn = json.load(open("junkies/pokal/teilnehmer_ids.json"))
pu = list(tn.values())[0]["id"]
d = p.get("/v4/challenges/910/table/%s?dayNumber=8" % pu)
for k, v in d.items():
    if k != "mds": print("table/uid", k, "=", kurz(v, 300))
for t, pf in [("livepitch", "/v4/challenges/910/lineup/livepitch?userId=%s&dayNumber=8" % pu),
              ("livepitch2", "/v4/challenges/910/users/%s/livepitch?dayNumber=8" % pu),
              ("topteams", "/v4/challenges/910/topteams?dayNumber=8"),
              ("teamcenter", "/v4/challenges/910/teamcenter?userId=%s&dayNumber=8" % pu),
              ("teamcenter2", "/v4/challenges/910/users/%s/teamcenter?dayNumber=8" % pu),
              ("table/uid/lp", "/v4/challenges/910/table/%s/lineup?dayNumber=8" % pu),
              ("profile", "/v4/challenges/910/profile/%s" % pu)]:
    d = p.get(pf)
    print("###", t, pf, "->", list(d.keys()) if isinstance(d, dict) else type(d), d.get("_fehler", "") if isinstance(d, dict) else "")
    if isinstance(d, dict):
        for k, v in d.items():
            print("   ", k, "=", kurz(v, 250))
