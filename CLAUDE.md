# BLOCKET BILBEVAKNING

**Complete Project Specification for Claude Code Migration**
Replacing n8n Workflow V5.9.4 — Deploying on Google Cloud

Autostore Sverige AB · autostoresverige.com · March 2026

---

## ARCHITECTURE DECISIONS (READ FIRST)

**These override any conflicting details in the spec below:**

- **Email**: Use **Resend** (`resend.com`) via the `resend` Python package. NOT Gmail, NOT SMTP. Env var: `RESEND_API_KEY`
- **Deduplication + Price History**: Use **SQLite** with a single local database file. NOT Google Sheets.
- **No Google services at all**: No Google Sheets, no Gmail, no Google OAuth. The n8n workflow broke because of Google OAuth token expiry — we are not repeating that mistake.
- **Grace Proxy fallback**: If `blocket-api.se` fails, fall back to Grace Proxy at `https://grace-gw.dvbrain.ai/fetch`. API key: env var `GRACE_GW_API_KEY`

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for AI brand/type classification |
| `RESEND_API_KEY` | Resend.com API key for sending emails |
| `GRACE_GW_API_KEY` | Grace Proxy API key for fallback scraping |
| `TRIGGER_API_KEY` | API key for Cloud Scheduler to authenticate trigger requests |
| `DATABASE_PATH` | SQLite database path (default: `data/blocket.db`) |
| `EMAIL_RECIPIENTS` | Comma-separated: `erik+blocket@autostoresverige.com,serge+autostore@lachapelle.se` |
| `EMAIL_FROM` | Sender address for Resend (e.g. `blocket@autostoresverige.com`) |

### Security Requirements (baked in from the start)

1. **SSRF protection on dealer URL check**: Only fetch URLs matching `*.blocket.se` domain. Block private IPs, localhost, metadata endpoints.
2. **No PII in logs**: Never log ad_id, car titles, seller names, or URLs. Log only counts and statuses (e.g. "processed 15 cars, 3 new").
3. **Endpoint auth**: The `/trigger` endpoint must require `X-API-Key` header matching `TRIGGER_API_KEY` env var.
4. **No Google Sheets**: All persistence is SQLite. Do not create a sheets.py or any Google API integration.

---

## 1. Project Overview

This system automatically monitors **Blocket.se** (Sweden's largest classifieds platform) to identify profitable vehicle purchase opportunities for Autostore Sverige AB. It runs every 60 minutes during operating hours and sends email notifications when new private-seller cars matching specific criteria are found.

The system specifically targets **private sellers only** (not dealers) because these offer better profit margins. It uses a multi-layered filtering approach: API-level parameters, structured data checks, AI-powered brand classification, page-level dealer URL scanning, and deduplication against previously seen ads.

### 1.1 Business Goals

- **Immediate acquisition alerts:** Email digest when new matching vehicles appear
- **Market research:** Price history tracking in SQLite for trend analysis
- **High-margin focus:** Pickups, vans, and skapbilar prioritized at top of notifications
- **Zero dealer noise:** Multiple detection layers ensure only genuine private seller ads reach the team

### 1.2 Recipients

Email notifications are sent to:
- `erik+blocket@autostoresverige.com`
- `serge+autostore@lachapelle.se`

---

## 2. System Architecture

### 2.1 Pipeline Flow (Exact Sequence)

> **CRITICAL:** The order matters. IDs must be written to the seen_ads table BEFORE the email is sent. This was a race condition bug in the n8n version that caused duplicate notifications.

```
Cloud Scheduler (60 min) -> POST /trigger with X-API-Key
  -> Check Time Window (6:00-00:00 Swedish time)
  -> Fetch Blocket API (pages 1-5, 500ms delay between pages)
  -> Extract & normalize car data
  -> Filter: Dealer Patterns (9 checks)
  -> Filter: AI Brand & Type (Claude API)
  -> Filter: Page-level dealer URL scan (blocket.se URLs only)
  -> Deduplicate within current run
  -> Read seen_ads from SQLite
  -> Filter: Remove already-seen cars + mileage check
  -> WRITE new IDs to seen_ads table   <- MUST complete first
  -> WRITE price data to price_history table   (can be parallel with email)
  -> Create email batches (max 20 cars per email)
  -> Format HTML email with priority sorting
  -> Throttle empty notifications (max every 4 hours)
  -> Send email via Resend
```

---

## 3. Data Sources & API Specifications

### 3.1 Primary: blocket-api.se (Third-Party Wrapper)

| Parameter | Value |
|-----------|-------|
| Endpoint | `GET https://blocket-api.se/v1/search/car` |
| Pagination | `page=1` through `page=5` (1-indexed) |
| Year filter | `year_from=2010` |
| Response format | JSON with `response.docs[]` array |
| Timeout | 30 seconds per request |
| Delay between pages | 500ms |

### 3.2 Fallback: Grace Proxy

If blocket-api.se fails (errors, empty results, unreachable), fall back to Grace Proxy:

```python
import httpx

async def fetch_via_grace(url: str, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://grace-gw.dvbrain.ai/fetch",
            json={"url": url},
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
        )
        return resp.json()
```

### 3.3 AI Classification: Anthropic Claude API

| Parameter | Value |
|-----------|-------|
| Endpoint | `POST https://api.anthropic.com/v1/messages` |
| Model | `claude-sonnet-4-20250514` |
| Max tokens | 1000 |
| Header | `anthropic-version: 2023-06-01` |
| Failure mode | **FAIL CLOSED** -- reject all cars if API fails |

---

## 4. Complete Filtering Pipeline

A car must pass ALL filter stages to be included in the email.

### 4.1 Stage 1: Dealer Pattern Detection (9 Checks)

A car is rejected if ANY single check matches.

1. `dealer_segment` not equal to `"Privat"` (case-insensitive) -> reject
2. `organisation_name` has any value -> reject
3. `seller_type` equals `"professional"`, `"dealer"`, or `"business"` -> reject
4. `org_id` present -> reject
5. Price > 0 but < 15,000 SEK -> reject (leasing)
6. Leasing keywords in title: `kr/man`, `kr/manad`, `/man`, `privatleasing` -> reject. BUT if preceded by `"ej"` or `"inte"`, do NOT reject.
7. Model year >= current year AND mileage < 500 -> reject (brand new)
8. `\bmoms\b` in title -> reject (VAT = dealer)
9. `X% ranta` or `superdeal` in title -> reject (financing)

### 4.2 Stage 2: AI Brand & Type Classification

Accepted passenger car brands (ALL models): Volvo, Audi, BMW, Volkswagen, Porsche

Accepted commercial vehicles (SPECIFIC models only):
- Ford: Ranger, Transit
- Nissan: Navara
- Toyota: Hilux
- Volkswagen: Transporter, Amarok, Caddy, Crafter

**FAIL CLOSED**: If Claude API fails, reject ALL cars.

### 4.3 Stage 3: Page-Level Dealer URL Detection

Fetch each car's Blocket ad page and scan for known dealer URLs.

**SSRF PROTECTION**: Only fetch URLs matching `*.blocket.se`. Reject any URL pointing to other domains, private IPs, or metadata endpoints.

Known dealer URLs to scan for in page HTML:
```
riddermarkbil.se, riddermark.se, bilia.se, bilia.com, hedinbil.se, hedin.se,
holmgrens.com, holmgrensbil.se, bavariabil.se, bavaria.se, upplands-motor.se,
upplandsmotor.se, bilmetro.se, kvd.se, kvd.com, wayke.se, kamux.se, kamux.com,
mollerbil.se, moller.se, dinbil.se, bilkompaniet.se, motorcentrum.se, bildeve.se,
bilvaruhuset.se, autoexperten.se, smistabil.se, smistabil.com
```

NOTE: `bytbil.com` is NOT in this list (appears on all Blocket pages).

Fetch with 15s timeout, 200ms delay between requests. Fail-open on errors.

### 4.4 Stage 4: Mileage Filter

| Vehicle Type | Mileage Limit |
|-------------|---------------|
| Passenger cars | Max 200,000 km |
| Commercial vehicles | No limit |
| Unknown/missing mileage | Include |

Mileage unit conversion: if raw value < 50,000 assume Swedish mil, multiply by 10 for km.

---

## 5. Data Extraction & Field Mapping

| Output Field | Source Fields (Priority Order) |
|-------------|-------------------------------|
| `ad_id` | `id`, `ad_id`, `list_id` |
| `car_title` | `heading`, `subject`, `title`, `name` |
| `thumbnail` | `thumbnail(.url)`, `image(.url)`, `images[0]` |
| `price` | `price.amount`, `price.value`, `price` |
| `year` | `model_year`, `year` |
| `mileage` | `mileage`, `milage` |
| `make` | `make`, `brand`, `heading.split(' ')[0]` |
| `fuel` | `fuel`, `fuel_type` |
| `gearbox` | `gearbox`, `transmission` |
| `location` | `location.municipality`, `location.city` |
| `url` | `share_url`, `url`, `canonical_url` |
| `dealer_segment` | `dealer_segment` |
| `organisation_name` | `organisation_name` |
| `seller_type` | `seller_type`, `owner_type` |
| `org_id` | `org_id` |

---

## 6. Deduplication & State Management

### 6.1 SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS seen_ads (
    ad_id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL  -- ISO datetime
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    car_title TEXT,
    make TEXT,
    year INTEGER,
    mileage_raw TEXT,
    mileage_km INTEGER,
    price_sek INTEGER,
    fuel TEXT,
    gearbox TEXT,
    location TEXT,
    ad_url TEXT
);

CREATE TABLE IF NOT EXISTS run_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### 6.2 Race Condition Fix (CRITICAL)

Write new IDs to seen_ads FIRST, wait for completion, THEN send email. Non-negotiable.

### 6.3 Empty notification throttle

Store `last_empty_email` timestamp in `run_state` table.

---

## 7. Email Notification System (Resend)

### 7.1 Sending via Resend

```python
import resend

resend.api_key = os.environ["RESEND_API_KEY"]

resend.Emails.send({
    "from": os.environ.get("EMAIL_FROM", "blocket@autostoresverige.com"),
    "to": recipients,
    "subject": subject,
    "html": html_body,
})
```

### 7.2 Priority Sorting

Priority vehicles sorted first. Detected by word-boundary regex on title:

Swedish: `skapbil`, `skap`, `pickup`, `pick-up`, `flak`, `lastbil`, `transport`
English: `van`, `panel`, `cargo`, `pickup`, `truck`
Models: `transporter`, `caddy`, `crafter`, `amarok`, `transit`, `ranger`, `custom`, `sprinter`, `vito`, `citan`, `ducato`, `talento`, `fiorino`, `doblo`, `boxer`, `partner`, `expert`, `rifter`, `berlingo`, `jumper`, `jumpy`, `dispatch`, `vivaro`, `movano`, `combo`, `trafic`, `master`, `kangoo`, `hiace`, `proace`, `hilux`, `nv200`, `nv300`, `navara`, `primastar`, `l200`, `outlander`, `daily`, `multivan`, `caravelle`, `california`

### 7.3 Email Subject Line

- With cars: `Nya Privatannonser -- {count} bilar`
- With batching: `Nya Privatannonser -- {count} bilar (Del {n}/{total})`
- No cars: `Bilsokning -- Inga nya bilar`

### 7.4 Batching

Max 20 cars per email, 2-second delay between sends.

### 7.5 Empty Notification Throttling

At most every 4 hours. Always send immediately when cars are found.

### 7.6 Mileage Display

- Raw < 1,000: `"{value} mil ({value*10} km)"`
- Raw >= 1,000: `"{value} km"`

### 7.7 HTML Email Template

Purple gradient header, quick overview section, individual car cards with thumbnails. Priority vehicles get orange badges. See the full CSS in the original spec.

Style guide:
- Gradient: `linear-gradient(135deg, #667EEA 0%, #764BA2 100%)`
- Priority badge: `#F5A623` (orange)
- Card style: White, border-radius 10px, box-shadow
- Footer: "Autostore Sverige AB -- Automatisk bilsokning"

---

## 8. Scheduling & Operational Rules

- Run every 60 minutes via Cloud Scheduler
- **ONLY** during 06:00-00:00 Swedish time (`Europe/Stockholm`)
- Always use explicit timezone, never rely on server time (UTC on Cloud Run)

### Rate Limiting

- 500ms delay between Blocket API page fetches
- 200ms delay between ad page fetches
- 30s timeout on API calls
- 15s timeout on ad page fetches

---

## 9. Known Bugs (DO NOT re-introduce)

| Bug | Fix |
|-----|-----|
| AI failure = all cars pass | FAIL CLOSED: reject all on API error |
| Mileage threshold too low (1,000) | Raised to 50,000 |
| "Ej leasing" rejected | Check for negation before leasing keywords |
| Server timezone = UTC | Explicitly use Europe/Stockholm |
| Race condition: parallel write/send | Sequential: write IDs first, then email |
| bytbil.com false positive | Removed from dealer URL list |
| Image objects not unpacked | Handle both string and object for thumbnail |

---

## 10. Deployment

### Dockerfile

Python slim base, install requirements, run with uvicorn.

### Cloud Run

- Region: `europe-north1`
- Memory: 512Mi
- Max instances: 1 (SQLite)
- Timeout: 300s

### Cloud Scheduler

- Schedule: `0 6-23 * * *` (every hour 6-23) + `0 0 * * *` (midnight)
- Target: POST to Cloud Run `/trigger` URL
- Headers: `X-API-Key: {TRIGGER_API_KEY}`

### Deploy script

Include `deploy.sh` with:
- `gcloud run deploy` with all env vars
- `gcloud scheduler jobs create http` for the cron
- Set `--max-instances=1` for SQLite safety
