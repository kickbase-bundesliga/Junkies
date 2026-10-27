# Kickbase Junkies

Tabellen, Abgabelisten, Knock Out, Playoffs und Pokal der Junkies-Community.

## Online (GitHub)
- Workflow **Junkies** (Reiter "Actions") laeuft taeglich frueh morgens: holt neue Daten, speichert sie im Repository und veroeffentlicht die Webseite.
- Manuell: Actions -> Junkies -> Run workflow. Haken "Nur Webseite neu bauen" = ohne Kickbase-Abruf.
- Aenderungen an `config/`, `scripts/` oder `junkies/pokal/` (auch direkt auf github.com) bauen die Webseite automatisch neu.
- Secrets (Settings -> Secrets and variables -> Actions): `KWBL_EMAIL`, `KWBL_PASSWORT` (Admin-Account der Ligen), `PRIVAT_EMAIL`, `PRIVAT_PASSWORT` (Account in der Junkies-Challenge, fuer den Pokal).

## Lokal
- Vor jeder Arbeit in GitHub Desktop **Fetch/Pull**, danach **Commit + Push**. Die Daten holt online die Automatik - lokal nur noch Config/Skripte aendern.
- Zugangsdaten fuer lokale Tests: `config/kwbl.txt` und `config/privat.txt` (Zeile 1 E-Mail, Zeile 2 Passwort). Werden nie hochgeladen.
- `start.bat` = Daten sammeln + Webseite bauen (nur fuer Tests; danach nicht die Daten committen, sondern verwerfen).

## Einstellungen (`config/junkies.json`)
- `ko.ausgeschieden`: Rauswuerfe der Knock Out Liga eintragen (Manager, nach_st, grund rauswurf/freiwillig).
- `korrekturen_gesamt`: Gesamtpunkte manuell setzen, wenn Kickbase sie verloren hat.
- `fristen_manuell`, `zusatzstrafen`: Sonderfaelle bei den Abgaben.
- `pokal.inaktiv`: zusaetzlich ausgeschlossene Pokalteilnehmer (3 Nullrunden erkennt die Seite selbst).
- Pokal-Teilnehmer und IDs: `junkies/pokal/teilnehmer_ids.json`.
