# Reporte diario SECOP II — Región Caribe

Daily email of the top 5 public construction tenders in Atlántico, Bolívar,
Magdalena, Sucre, Córdoba and Cesar, matched against CYV Constructora's
profile. Runs free on GitHub Actions at 8:00 AM Colombia time.

## How it works

```
GitHub Actions cron (13:00 UTC)
  → datos.gov.co Socrata API   deterministic filter: date, value, department
  → Python keyword filter      civil works only, excludes interventoría etc.
  → Claude API                 ranks top 5, writes Spanish rationale
  → Resend                     HTML email
  → commits state/seen.json    so tomorrow only surfaces new processes
```

The model **never retrieves data**. It receives numbered candidates and
returns only index numbers plus commentary. Every process ID, value, deadline
and link in the email is read back from the original API response, so a
hallucinated tender number is structurally impossible.

## Setup

### 1. Verify the schema first

Field names on datos.gov.co change occasionally. Before anything else:

```bash
pip install -r requirements.txt
python main.py --inspect
```

This prints the live column names and checks every entry in
`src/config.py → FIELDS` against them. Fix anything marked `MISSING`, then
re-run until it says all fields match.

### 2. Verify the modality and contract-type spelling

The pipeline only keeps **Licitación Pública** processes whose contract type
is **Obra** (construction), which is what filters out consultorías,
interventorías, and supply contracts that happen to mention a construction
keyword. SECOP's exact spelling/punctuation for these values can vary, so
confirm it against live data:

```bash
python main.py --list-modalities
```

This samples the last 90 days for your six departments and prints every
distinct value seen for `modalidad_de_contratacion` and `tipo_de_contrato`,
flagging which ones currently match `REQUIRE_MODALITY` /
`REQUIRE_CONTRACT_TYPE` in `src/config.py`. If "Licitación Pública" or "Obra"
isn't flagged, adjust those two lists to match what's actually printed.

### 3. Preview locally

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --dry-run
open preview.html
```

No email is sent and state is not updated. Iterate on the keyword lists and
`COMPANY_PROFILE` in `src/config.py` until the output looks right.

### 4. Set up email delivery (Gmail, no domain needed)

The report sends through your own Gmail account using an **App Password** —
a 16-character code Google generates that lets a script log in without your
real password. This needs no domain, no DNS, and sends to anyone.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Turn on **2-Step Verification** if it isn't already on (required for App Passwords)
3. Search for **"App passwords"** in the account settings search bar
4. Create one, name it something like `secop-report`, and copy the 16-character code it gives you — Google only shows it once

That code is `GMAIL_APP_PASSWORD` below. Your normal Gmail address is `GMAIL_ADDRESS`.

### 5. Configure GitHub

In your repo → Settings → Secrets and variables → Actions:

**Secrets** (encrypted — anyone with repo access can't read these back):
- `ANTHROPIC_API_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `SOCRATA_APP_TOKEN` — optional, raises the API rate limit

**Variables** (plain text — fine for non-secret settings):
- `REPORT_TO` — Claudia's email
- `REPORT_CC` — your own email, so you see every report too

### 6. Test the schedule

Actions tab → "Reporte diario SECOP" → Run workflow. This triggers a real run
immediately so you don't have to wait until tomorrow morning.

## Tuning

Everything adjustable is in `src/config.py`:

| Setting | What it does |
|---|---|
| `TARGET_DEPARTMENTS` | Geographic scope. Accent-insensitive — write them unaccented. |
| `MIN_BASE_PRICE_COP` | Value floor. Currently 5,000M COP. |
| `LOOKBACK_DAYS` | How far back to look. Currently 30. |
| `RELEVANT_KEYWORDS` | What counts as civil works. |
| `EXCLUDE_KEYWORDS` | What to reject outright. |
| `COMPANY_PROFILE` | What the ranking model reads. Update as you learn more. |

## Cost

GitHub Actions: free. SECOP API: free. Gmail SMTP: free.
Claude API: roughly $0.01–0.03 per run, so well under $1/month.
