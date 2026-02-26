# Repo-Audit Bericht — MyTrade

**Datum:** 26. Februar 2026
**Auditor:** Claude (Cowork-Session)
**Ziel:** Sicherstellen, dass das Repo nach Best Practices strukturiert ist, bevor Claude Code damit arbeitet.

---

## Gesamtbewertung

Das Repo ist **sehr gut aufgebaut** — die CLAUDE.md, die docs-Struktur, die Agents/Skills-Konfiguration und die Security-Hooks zeigen, dass hier sorgfältig geplant wurde.

| Kategorie | Status | Details |
|-----------|--------|---------|
| CLAUDE.md | Gut | Kompakt, nutzt @imports, klare Regeln |
| Docs-Struktur | Gut | Nummeriert, thematisch sortiert, 03_architecture jetzt vorhanden |
| Agents & Skills | Gut | Saubere Aufteilung, richtige Modell-Zuweisung |
| Security | Sehr gut | PostToolUse-Hooks (inkl. ALPHA_VANTAGE), .env-Deny, RLS-Fokus |
| Namensgebung | Erledigt | Alle Referenzen auf "MyTrade" aktualisiert |
| Fehlende Dateien | Erledigt | docs/03_architecture/ mit Platzhaltern erstellt |

---

## Durchgeführte Fixes

### Fix 3: `docs/03_architecture/` erstellt
- `system-overview.md` — Platzhalter mit geplantem Inhalt und Referenzen
- `database-schema.md` — Platzhalter mit geplanten Tabellen und Grundregeln
- CLAUDE.md @imports funktionieren jetzt

### Fix 4: "Arwin Alpha" → "MyTrade" (18 Dateien)
Alle Referenzen in folgenden Dateien aktualisiert:
- `CLAUDE.md`, `.env.example`, `Claude-Code-Master-Prompt-v3-FINAL.md`
- `.claude/skills/frontend-design/SKILL.md` (3 Stellen)
- Alle 14 Docs-Dateien (00-09)
- Verifiziert: `grep -rn "Arwin Alpha"` findet keine Treffer mehr

### Fix 5: Security-Hook verbessert
- `ALPHA_VANTAGE_API_KEY` zum PostToolUse-Hook hinzugefügt
- Alle 6 sensiblen Keys werden jetzt nach jedem Write/Edit im Frontend geprüft

### Fix 6: Master-Prompt kopiert
- `Claude-Code-Master-Prompt-v3-FINAL.md` → `docs/00_build-brief/master-prompt.md`
- Original im Root bleibt vorerst (Lösch-Berechtigung nicht verfügbar)

---

## Noch offen (für Claude Code)

Diese Aufgaben konnten wegen fehlender Lösch-Berechtigung nicht in Cowork erledigt werden:

1. **`{docs` Verzeichnis löschen** — Leeres Überbleibsel einer fehlgeschlagenen Brace-Expansion. Enthält null Dateien, nur leere Ordner mit kaputten Namen. Befehl: `rm -rf "{docs"`

2. **4x `.DS_Store` entfernen** — macOS-Metadaten in Root, .claude/, .claude/skills/, docs/. Befehle:
   ```
   git rm --cached .DS_Store .claude/.DS_Store .claude/skills/.DS_Store docs/.DS_Store
   ```

3. **`Claude-Code-Master-Prompt-v3-FINAL.md` aus Root löschen** — Wurde nach `docs/00_build-brief/master-prompt.md` kopiert. Original kann entfernt werden.

---

## Gute Practices (beibehalten)

### CLAUDE.md
- 60 Zeilen, kompakt und strukturiert — genau im empfohlenen Bereich (< 100 Zeilen)
- Nutzt @imports statt alles inline zu schreiben
- Enthält Commands, Critical Rules, Tech Stack — alles was Claude Code braucht
- Compaction Instructions vorhanden (wichtig für lange Sessions)

### .claude/settings.json
- PostToolUse-Hook prüft nach jedem Write/Edit ob API-Keys im Frontend gelandet sind
- Permission-Deny für .env-Dateien und secrets/ — vorbildlich

### Agents (5 Stück)
- Sinnvolle Aufteilung nach Domäne (Backend, Frontend, DB, Security, Tests)
- Richtige Modell-Zuweisung: Opus für Security + Backend (kritisch), Sonnet für Frontend + Tests (kosteneffizient)
- Security-Reviewer hat nur Read-Tools (Grep/Glob) — kein Write-Zugriff

### Skills (4 Stück)
- `frontend-design`: Umfangreiches Design-System, verhindert "AI-Slop"
- `db-migrate`, `new-agno-agent`, `security-check`: Alle mit `disable-model-invocation: true`

### Docs-Struktur (00-09)
```
docs/
├── 00_build-brief/     ← Ziel, MVP-Scope, Master-Prompt
├── 01_vision/          ← Langfrist-Zielbild
├── 02_policy/          ← IPS, Settings, Asset Universe, Steuern
├── 03_architecture/    ← System-Übersicht, DB-Schema (Platzhalter)
├── 04_verification/    ← Claim-Schema, Tier-System
├── 05_risk/            ← Execution Contract, Kill-Switch, Policy Engine
├── 06_data/            ← Datenprovider
├── 07_compliance/      ← Decision Support Regeln
├── 08_eval/            ← Metriken
└── 09_broker/          ← Broker-Router, Security
```

### .gitignore & .mcp.json
- Umfassend und korrekt konfiguriert

---

## Fazit

Das Repo ist jetzt zu **~95% ready für Claude Code**. Die verbleibenden 5% sind drei Lösch-Aufgaben (kaputtes `{docs`-Verzeichnis, `.DS_Store`-Dateien, Original Master-Prompt im Root), die Claude Code als erstes erledigen kann.
