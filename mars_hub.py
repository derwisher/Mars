name: Mars CI

on:
  schedule:
    - cron: "0 * * * *"      # jede volle Stunde
    - cron: "0 12 * * *"     # täglich 12:00
    - cron: "0 17 * * *"     # täglich 17:00
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest

    env:
      ROTATION_SLOTS: "6"
      MAX_UNIVERSE: "200"

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      # ⬇️ Hier: mars_hub.py direkt ausführen und Ausgabe als alerts.json speichern
      - name: Generate alerts.json
        run: |
          python mars_hub.py > alerts.json

      - name: Publish alerts.json to docs (with robots.txt)
        run: |
          mkdir -p docs
          cp alerts.json docs/alerts.json
          echo "User-agent: *" > docs/robots.txt
          echo "Disallow: /" >> docs/robots.txt
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/alerts.json docs/robots.txt || true
          git commit -m "update alerts" || echo "no changes"
          git push
