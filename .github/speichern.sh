#!/usr/bin/env bash
# Neue Daten committen und pushen (mit Wiederholung, falls parallel etwas gespeichert wurde).
# Aufruf: bash .github/speichern.sh "Commit-Nachricht"
set -u
git config user.name  "junkies-automatik"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A junkies/daten
if git diff --cached --quiet; then
  echo "Keine neuen Daten."
  exit 0
fi
git commit -q -m "$1"
for i in 1 2 3 4 5; do
  if git pull --rebase --autostash -q && git push -q; then
    echo "Gespeichert."
    exit 0
  fi
  sleep $((i * 5))
done
echo "::error::Speichern (push) fehlgeschlagen"
exit 1
