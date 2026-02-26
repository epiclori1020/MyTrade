# Security — MyTrade

## Secrets Management
- Alle API Keys in **Environment Variables** (Railway für Backend, Vercel für Frontend)
- `.env` Datei NIEMALS committed (in .gitignore)
- `.env.example` als Template OHNE echte Werte

### Benötigte Secrets
```
# LLM
ANTHROPIC_API_KEY=

# Database
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=     # NUR Backend!

# Data Providers
FINNHUB_API_KEY=
ALPHA_VANTAGE_API_KEY=

# Broker
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER_MODE=true          # MUSS true sein in Stufe 1

# App
NEXTAUTH_SECRET=
NEXTAUTH_URL=
```

## Kritische Regeln

### Broker Keys
- **NIEMALS** im Frontend-Code
- **NIEMALS** in Git committed
- **NIEMALS** in Supabase-Tabellen gespeichert
- NUR im Backend über Environment Variables

### Supabase service_role
- Bypassed RLS komplett — auth.uid() funktioniert NICHT
- Backend nutzt entweder:
  - **Option A:** User-JWT weiterleiten (auth.uid() funktioniert)
  - **Option B:** service_role mit expliziter user_id Validierung im Code
- service_role Key darf NIEMALS im Frontend auftauchen

### CORS
- Strict Origin: nur Frontend-Domain erlaubt
- Keine Wildcards in Production

### API Rate Limiting
- 100 requests/min/user auf Backend-Endpoints
- Separate Limits für LLM-Calls (Budget-Cap)

### Authentication
- Supabase Auth mit JWT
- RLS auf allen Tabellen aktiv
- User sieht nur eigene Daten
