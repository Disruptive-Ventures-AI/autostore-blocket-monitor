# BLOCKET BILBEVAKNING

**Complete Project Specification for Claude Code Migration**
Replacing n8n Workflow V5.9.4 — Deploying on Google Cloud

Autostore Sverige AB · autostoresverige.com · March 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Data Sources & API Specifications](#3-data-sources--api-specifications)
4. [Complete Filtering Pipeline](#4-complete-filtering-pipeline)
5. [Data Extraction & Field Mapping](#5-data-extraction--field-mapping)
6. [Deduplication & State Management](#6-deduplication--state-management)
7. [Email Notification System](#7-email-notification-system)
8. [Data Persistence (Google Sheets)](#8-data-persistence-google-sheets)
9. [Scheduling & Operational Rules](#9-scheduling--operational-rules)
10. [Known Bugs & Fixes (Critical History)](#10-known-bugs--fixes-critical-history)
11. [Grace Gateway (Proxy Fallback)](#11-grace-gateway-proxy-fallback)
12. [Style Guide Reference](#12-style-guide-reference)
13. [Deployment Target: Google Cloud](#13-deployment-target-google-cloud)
14. [Environment Variables & Secrets](#14-environment-variables--secrets)
15. [Testing Checklist](#15-testing-checklist)

---

## 1. Project Overview

This system automatically monitors **Blocket.se** (Sweden's largest classifieds platform) to identify profitable vehicle purchase opportunities for Autostore Sverige AB. It runs every 60 minutes during operating hours and sends email notifications when new private-seller cars matching specific criteria are found.

The system specifically targets **private sellers only** (not dealers) because these offer better profit margins. It uses a multi-layered filtering approach: API-level parameters, structured data checks, AI-powered brand classification, page-level dealer URL scanning, and deduplication against previously seen ads.

### 1.1 Business Goals

- **Immediate acquisition alerts:** Email digest when new matching vehicles appear
- **Market research:** Price history tracking in Google Sheets for trend analysis
- **High-margin focus:** Pickups, vans, and skåpbilar prioritized at top of notifications
- **Zero dealer noise:** Multiple detection layers ensure only genuine private seller ads reach the team

### 1.2 Recipients

Email notifications are sent to:
- `erik+blocket@autostoresverige.com`
- `serge+autostore@lachapelle.se`

---

## 2. System Architecture

### 2.1 Previous Architecture (n8n — Being Replaced)

The system was built as an n8n workflow (V5.9.4) running on n8n cloud at `disruptiveventures.app.n8n.cloud`. The n8n OAuth2 tokens for Google Sheets and Gmail have expired, causing the workflow to break with:

```
NodeApiError: The provided authorization grant (e.g., authorization code, resource owner credentials)
or refresh token is invalid, expired, revoked, does not match the redirection URI used in the
authorization request, or was issued to another client.
```

### 2.2 New Architecture (Claude Code + Google Cloud)

The replacement should be a standalone application (Python or Node.js) deployed on Google Cloud, running on a cron schedule:

1. Cron trigger (Cloud Scheduler or equivalent) every 60 minutes
2. Application fetches cars from Blocket API (with Grace GW fallback)
3. Filtering pipeline processes cars through all filter stages
4. Deduplication against Google Sheets (Seen_IDs)
5. Write new IDs to Google Sheets **BEFORE** sending email (race condition fix)
6. Log price data to Google Sheets (Price_History)
7. Send HTML email digest via Gmail API or SMTP

### 2.3 Pipeline Flow (Exact Sequence)

> **CRITICAL:** The order matters. IDs must be written to the Seen_IDs sheet BEFORE the email is sent. This was a race condition bug in earlier versions that caused duplicate notifications across hourly batches.

```
Schedule (60 min)
  → Check Time Window (6:00–00:00 Swedish time)
  → Fetch Blocket API (pages 1–5, 500ms delay between pages)
  → Extract & normalize car data
  → Filter: Dealer Patterns (9 checks)
  → Filter: AI Brand & Type (Claude API)
  → Filter: Page-level dealer URL scan
  → Deduplicate within current run
  → Read Seen_IDs from Google Sheets
  → Filter: Remove already-seen cars + mileage check
  → WRITE new IDs to Seen_IDs sheet   ← MUST complete first
  → WRITE price data to Price_History   (can be parallel with email)
  → Create email batches (max 20 cars per email)
  → Format HTML email with priority sorting
  → Throttle empty notifications (max every 4 hours)
  → Send email via Gmail
```

---

## 3. Data Sources & API Specifications

### 3.1 Primary: blocket-api.se (Third-Party Wrapper)

This is a third-party REST wrapper around Blocket's internal API, hosted at blocket-api.se. Source code: `github.com/dunderrrrrr/blocket_api`

| Parameter | Value |
|-----------|-------|
| Endpoint | `GET https://blocket-api.se/v1/search/car` |
| Pagination | `page=1` through `page=5` (1-indexed) |
| Year filter | `year_from=2010` |
| Other params | `price_from`, `price_to`, `milage_from`, `milage_to`, `locations`, `models`, `sort` |
| Response format | JSON with `response.docs[]` array |
| Timeout | 30 seconds per request |
| Delay between pages | 500ms |

#### Response Structure (per car in `docs[]`)

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique ad identifier |
| `heading` | string | Ad title |
| `price` | object | `price.amount` = numeric value |
| `model_year` / `year` | number | Year of manufacture |
| `mileage` / `milage` | varies | Sometimes mil, sometimes km |
| `make` / `brand` | string | Manufacturer name |
| `fuel` / `fuel_type` | string | Fuel type |
| `gearbox` / `transmission` | string | Transmission type |
| `location` | object | `location.municipality` or `location.city` |
| `thumbnail` / `image` | string/obj | Image URL (may be nested `.url`) |
| `dealer_segment` | string | `"Privat"` or `"Företag"` — **PRIMARY dealer check** |
| `organisation_name` | string | Only dealers have this |
| `seller_type` / `owner_type` | string | `professional` / `dealer` / `business` |
| `org_id` | string | Organisation ID (only registered businesses) |
| `share_url` / `url` | string | Direct link to ad |

### 3.2 Fallback: Grace Gateway (Proxy)

If the blocket-api.se wrapper fails or is unavailable, the system should fall back to **Grace GW** — a proxy service that can fetch Blocket pages directly. The Grace GW endpoint is at `dvbrain.ai/mcp/sse` (MCP server). This should be used as a secondary data source when the primary API returns errors or empty results.

### 3.3 AI Classification: Anthropic Claude API

| Parameter | Value |
|-----------|-------|
| Endpoint | `POST https://api.anthropic.com/v1/messages` |
| Model | `claude-sonnet-4-20250514` |
| Max tokens | 1000 |
| Header | `anthropic-version: 2023-06-01` |
| Failure mode | **FAIL CLOSED** — reject all cars if API fails |

---

## 4. Complete Filtering Pipeline

A car must pass **ALL** filter stages to be included in the email notification. Each stage is described in exact detail below.

### 4.1 Stage 1: Dealer Pattern Detection (9 Checks)

**Runs first on structured API data. A car is rejected if ANY single check matches.**

#### Check 1: `dealer_segment` (PRIMARY — Most Reliable)

Field: `dealer_segment` from API response. If present and NOT equal to `"Privat"` (case-insensitive), reject. This is the single most reliable indicator. `"Företag"` means business/dealer.

#### Check 2: `organisation_name`

If the field `organisation_name` has any value (non-empty), the ad is from a registered business. Reject.

#### Check 3: `seller_type` from API

If `seller_type` equals `"professional"`, `"dealer"`, or `"business"` (case-insensitive), reject.

#### Check 4: `org_id` present

If the ad has any `org_id` value, it belongs to a registered organisation. Reject.

#### Check 5: Leasing price detection

If the numeric price is > 0 but < 15,000 SEK, it is almost certainly a monthly leasing cost, not a purchase price. Reject.

#### Check 6: Leasing keywords in title

Scan the ad title (case-insensitive) for: `kr/mån`, `kr/månad`, `/mån`, `privatleasing`.

> **IMPORTANT:** If the keyword is preceded by `"ej"` or `"inte"` (negation), do **NOT** reject. This was a bug fix — ads saying "ej leasing" were incorrectly rejected in earlier versions.

#### Check 7: Brand-new vehicle detection

If model year >= current year AND mileage < 500 (in whatever unit), it is likely a brand-new dealer car. Reject.

#### Check 8: MOMS in title

If the title contains the word `"moms"` as a whole word (word boundary match `\bmoms\b`), reject. This indicates VAT-deductible business vehicles typically from dealers.

#### Check 9: Financing patterns

If the title matches patterns like `X% ränta` or contains `"superdeal"`, reject. These are dealer marketing terms.

### 4.2 Stage 2: AI Brand & Type Classification

Cars that pass dealer pattern detection are sent in batch to the Claude API for brand/model classification. The AI receives a numbered list of car titles with year and price, and responds with structured decisions.

#### Accepted Passenger Car Brands (ALL models)

- Volvo
- Audi
- BMW
- Volkswagen
- Porsche

#### Accepted Commercial Vehicles (SPECIFIC models only)

| Brand | Accepted Models |
|-------|----------------|
| Ford | Ranger, Transit |
| Nissan | Navara |
| Toyota | Hilux |
| Volkswagen | Transporter, Amarok, Caddy, Crafter |

#### AI Prompt Format

The prompt sends vehicles as: `NUMBER. "TITLE" (YEAR, PRICE)` and asks for response format: `NUMBER|BRAND|TYPE|DECISION` where DECISION is `ACCEPT` or `REJECT`.

> **CRITICAL FAILURE MODE:** If the Claude API call fails for any reason (timeout, rate limit, error), the system must **FAIL CLOSED** — reject ALL cars in the batch. Earlier versions had a bug where API failures let all cars through unfiltered.

### 4.3 Stage 3: Page-Level Dealer URL Detection

For each car that passes the first two stages, the system fetches the actual Blocket ad page and scans the HTML for known dealer website URLs. This catches dealers who pass structured data checks.

#### Known Dealer URLs to Scan For

```
riddermarkbil.se, riddermark.se, bilia.se, bilia.com, hedinbil.se, hedin.se,
holmgrens.com, holmgrensbil.se, bavariabil.se, bavaria.se, upplands-motor.se,
upplandsmotor.se, bilmetro.se, kvd.se, kvd.com, wayke.se, kamux.se, kamux.com,
mollerbil.se, moller.se, dinbil.se, bilkompaniet.se, motorcentrum.se, bildeve.se,
bilvaruhuset.se, autoexperten.se, smistabil.se, smistabil.com
```

> **NOTE:** `bytbil.com` was **removed** from this list because it appears on ALL Blocket car pages (as a Blocket partner), not just dealer pages.

**Implementation details:** HTTP GET with 15s timeout, 200ms delay between requests. If page fetch fails or returns < 500 chars, fail-open (allow the car through). Uses `User-Agent: Mozilla/5.0` header.

### 4.4 Stage 4: Mileage Filter

Applied after deduplication, during the "new cars only" filtering:

| Vehicle Type | Mileage Limit |
|-------------|---------------|
| Passenger cars (PASSENGER) | Max 200,000 km |
| Commercial vehicles (COMMERCIAL) | No limit (these remain valuable at high mileage) |
| Unknown/missing mileage | Include (don't filter out) |

#### Mileage Unit Conversion (Critical Bug Fix)

The Blocket API returns mileage inconsistently — sometimes in Swedish "mil" (1 mil = 10 km), sometimes in km. The conversion logic is:

- If numeric value < 50,000: assume Swedish mil, multiply by 10 to get km
- If numeric value >= 50,000: assume already in km

> **Previous bug:** Threshold was 1,000 which meant 25,000 mil (= 250,000 km) was treated as 25,000 km and incorrectly passed. The threshold was raised to 50,000 in V5.1.

---

## 5. Data Extraction & Field Mapping

Each car from the API goes through normalization to extract consistent fields:

| Output Field | Source Fields (Priority Order) | Notes |
|-------------|-------------------------------|-------|
| `ad_id` | `id`, `ad_id`, `list_id` | Falls back to timestamp+random |
| `car_title` | `heading`, `subject`, `title`, `name` | Original ad title |
| `thumbnail` | `thumbnail(.url)`, `image(.url)`, `images[0]` | Handle both string and object |
| `price` | `price.amount`, `price.value`, `price` | Format as "X kr" with sv-SE locale |
| `year` | `model_year`, `year` | Numeric year |
| `mileage` | `mileage`, `milage` | Raw value (converted later) |
| `make` | `make`, `brand`, `heading.split(' ')[0]` | First word fallback |
| `fuel` | `fuel`, `fuel_type` | |
| `gearbox` | `gearbox`, `transmission` | |
| `location` | `location.municipality`, `location.city` | Handle object vs string |
| `url` | `share_url`, `url`, `canonical_url` | Fallback: `blocket.se/mobility/item/{id}` |
| `dealer_segment` | `dealer_segment` | `"Privat"` or `"Företag"` |
| `organisation_name` | `organisation_name` | Only dealers have this |
| `seller_type` | `seller_type`, `owner_type` | |
| `org_id` | `org_id` | Business registration ID |

---

## 6. Deduplication & State Management

### 6.1 Within-Run Deduplication

Since we fetch pages 1–5 from the API, the same car can appear on multiple pages. Before any further processing, deduplicate by `ad_id` using a Map (first occurrence wins).

### 6.2 Cross-Run Deduplication (Google Sheets)

After all filtering, compare remaining car `ad_id`s against the `Seen_IDs` sheet in Google Sheets. Only cars NOT already in the sheet proceed.

### 6.3 Race Condition Fix (CRITICAL)

In the n8n workflow, there was a race condition where email sending and ID writing happened in parallel. This caused the same cars to appear in multiple consecutive hourly emails (11 cars appeared in all 3 emails in one observed case).

> **THE FIX:** Write new IDs to the Seen_IDs sheet **FIRST**, wait for confirmation, **THEN** create and send the email. This is non-negotiable — the ID write must complete before email dispatch begins.

### 6.4 Merge Strategy

When merging scraped cars with Seen_IDs data, use a simple append (not a cross-product join). The previous n8n version used "All Possible Combinations" merge which broke when the Seen_IDs sheet was empty. The code distinguishes scraped cars (have `_isScrapedCar` flag) from sheet rows (have `ad_id` but no flag).

---

## 7. Email Notification System

### 7.1 Priority Sorting

Before generating the email, cars are sorted so that high-margin vehicles appear first. A car is classified as "priority" if its title contains any of these keywords (whole-word match using `\b` word boundary regex, case-insensitive):

**Swedish terms:** `skåpbil`, `skåp`, `pickup`, `pick-up`, `flak`, `lastbil`, `transport`

**English terms:** `van`, `panel`, `cargo`, `pickup`, `truck`

**Model names:** `transporter`, `caddy`, `crafter`, `amarok`, `transit`, `ranger`, `custom`, `sprinter`, `vito`, `citan`, `ducato`, `talento`, `fiorino`, `doblò`, `doblo`, `boxer`, `partner`, `expert`, `rifter`, `berlingo`, `jumper`, `jumpy`, `dispatch`, `vivaro`, `movano`, `combo`, `trafic`, `master`, `kangoo`, `hiace`, `proace`, `hilux`, `nv200`, `nv300`, `navara`, `primastar`, `l200`, `outlander`, `daily`, `multivan`, `caravelle`, `california`

> **IMPORTANT:** Use word boundary regex (`\b`) to avoid false positives like "Advanced" matching "van".

### 7.2 Email Format

The email is HTML with:

1. **Header** with gradient background (`#667eea → #764ba2`), total car count, and priority vehicle count
2. **Quick overview section:** Clickable list of all cars with name, year, price, and location. Priority vehicles have orange left border and "🚛 PRIO" badge
3. **Divider** between priority and non-priority vehicles in the overview
4. **Individual car cards** with: thumbnail image, title, price (large), info badges (year, mileage, fuel, gearbox, location), and "Se annons på Blocket →" button
5. **Footer** with "Autostore Sverige AB — Automatisk bilsökning" and timestamp

### 7.3 Email Subject Line

Dynamic subject based on results:

- With cars: `🚗 Nya Privatannonser — {count} bilar`
- With cars + batching: `🚗 Nya Privatannonser — {count} bilar (Del {n}/{total})`
- No cars: `🚗 Bilsökning — Inga nya bilar`

### 7.4 Batching

If more than 20 cars are found, split into batches of 20 with a 2-second delay between sends.

### 7.5 Empty Notification Throttling

When no new cars are found:

- Send "no new cars" notification at most every 4 hours
- Track last empty email timestamp in persistent state
- When cars ARE found: always send immediately regardless of throttle

### 7.6 Mileage Display in Email

- If raw value < 1,000: Show as `"{value} mil ({value×10} km)"`
- If raw value >= 1,000: Show as `"{value} km"`

### 7.7 Full HTML Email Template

The complete HTML/CSS structure from the n8n workflow:

```html
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
      margin: 0; padding: 20px; background-color: #f5f5f5;
    }
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white; padding: 20px; border-radius: 10px;
      margin-bottom: 20px; text-align: center;
    }
    .header h1 { margin: 0 0 10px 0; font-size: 24px; }
    .header p { margin: 5px 0; font-size: 16px; }
    .summary {
      background: white; padding: 20px; border-radius: 10px;
      margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .summary h2 {
      color: #667eea; margin: 0 0 15px 0; font-size: 18px;
      border-bottom: 2px solid #667eea; padding-bottom: 10px;
    }
    .summary ul { margin: 0; padding-left: 0; list-style: none; }
    .summary li {
      margin-bottom: 10px; padding: 8px 12px; background: #f8f9fa;
      border-radius: 6px; border-left: 3px solid #667eea;
    }
    .summary li.priority {
      background: #fff8e6; border-left: 4px solid #f5a623;
    }
    .summary a { color: #333; text-decoration: none; display: block; }
    .summary a:hover { color: #667eea; }
    .summary .car-name { font-weight: bold; }
    .summary .price { color: #667eea; font-weight: bold; }
    .summary .year { color: #666; }
    .summary .location { color: #888; font-size: 13px; }
    .summary .priority-badge {
      background: #f5a623; color: white; font-size: 11px;
      padding: 2px 6px; border-radius: 4px; margin-right: 6px; font-weight: bold;
    }
    .priority-header {
      background: linear-gradient(135deg, #f5a623 0%, #f09819 100%);
      color: white; padding: 10px 15px; border-radius: 8px;
      margin-bottom: 15px; font-weight: bold;
    }
    .car-card {
      background: white; border-radius: 10px; margin-bottom: 20px;
      overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .car-card.priority { border: 2px solid #f5a623; }
    .car-image { width: 100%; height: 200px; object-fit: cover; }
    .car-details { padding: 15px; }
    .car-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #333; }
    .car-price { font-size: 24px; color: #667eea; font-weight: bold; margin-bottom: 10px; }
    .car-info { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
    .info-badge {
      background: #f0f0f0; padding: 5px 10px; border-radius: 5px;
      font-size: 14px; color: #666;
    }
    .info-badge.priority { background: #f5a623; color: white; }
    .view-button {
      display: block;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white; text-align: center; padding: 12px;
      border-radius: 8px; text-decoration: none; font-weight: bold;
    }
    .footer { text-align: center; color: #999; margin-top: 30px; font-size: 14px; }
  </style>
</head>
```

Each car card renders as:

```html
<div class="car-card priority">  <!-- add "priority" class if applicable -->
  <img src="{thumbnail}" class="car-image" alt="{car_title}"
       onerror="this.style.display='none'">
  <div class="car-details">
    <div class="car-title">🚛 {car_title}</div>  <!-- 🚛 prefix for priority -->
    <div class="car-price">{price}</div>
    <div class="car-info">
      <span class="info-badge priority">PICKUP/VAN/SKÅP</span>  <!-- if priority -->
      <span class="info-badge">📅 {year}</span>
      <span class="info-badge">🛣️ {mileage_display}</span>
      <span class="info-badge">⛽ {fuel}</span>
      <span class="info-badge">⚙️ {gearbox}</span>
      <span class="info-badge">📍 {location}</span>
    </div>
    <a href="{url}" class="view-button">Se annons på Blocket →</a>
  </div>
</div>
```

---

## 8. Data Persistence (Google Sheets)

### 8.1 Spreadsheet

| Property | Value |
|----------|-------|
| Spreadsheet ID | `1xFREypf8fvBjyBX3ul2_PTMAcKGKyV-ednJqLpjf6AI` |
| Name | Blocket Scraper V3 |

### 8.2 Sheet: Seen_IDs (gid=2079567462)

Purpose: Deduplication tracking.

| Column | Type | Description |
|--------|------|-------------|
| `ad_id` | string | Blocket ad identifier |
| `first_seen` | ISO datetime | When the ad was first scraped |

### 8.3 Sheet: Price_History (gid=621950292)

Purpose: Market research and price trend analysis.

| Column | Type | Description |
|--------|------|-------------|
| `scraped_at` | ISO datetime | Scrape timestamp |
| `ad_id` | string | Blocket ad identifier |
| `car_title` | string | Ad title |
| `make` | string | Manufacturer |
| `year` | string | Model year |
| `mileage_raw` | string | Raw mileage from API |
| `mileage_km` | number | Converted to km (mil×10 if < 1000) |
| `price_raw` | string | Formatted price string |
| `price_sek` | number | Numeric price in SEK |
| `fuel` | string | Fuel type |
| `gearbox` | string | Transmission |
| `location` | string | Municipality |
| `ad_url` | string | Link to Blocket ad |

---

## 9. Scheduling & Operational Rules

### 9.1 Schedule

Run every 60 minutes, but **ONLY** during operating hours: **06:00 – 00:00 Swedish time** (Europe/Stockholm timezone). Runs from hour 6 through hour 23, plus hour 0 (midnight). Do NOT run between 01:00 and 05:59.

### 9.2 Timezone Handling

> **CRITICAL:** Always use `Europe/Stockholm` explicitly. Do not rely on server time, which will be UTC on Google Cloud. The original n8n workflow had a bug where server time was used instead of Swedish time.

### 9.3 API Rate Limiting

Be respectful to the blocket-api.se service:
- 500ms delay between page fetches
- 200ms delay between individual ad page fetches
- 30s timeout on API calls
- 15s timeout on ad page fetches

---

## 10. Known Bugs & Fixes (Critical History)

These bugs were discovered and fixed during the n8n development. The new implementation **must not** re-introduce them:

| Bug | Impact | Fix |
|-----|--------|-----|
| AI failure = floodgate open | If Claude API timed out, ALL cars passed through unfiltered | Fail closed: reject all cars on API error |
| Mileage threshold too low | 25,000 mil (250,000 km) treated as 25,000 km, passed filter | Raised mil/km detection threshold from 1,000 to 50,000 |
| Leasing context blindness | "Ej leasing" and "Säljes pga privatleasing" triggered rejection | Check for negative context (ej, inte) before leasing keywords |
| Server timezone = UTC | Operating hours check used server time (UTC), not Swedish time | Explicitly use Europe/Stockholm via Intl API |
| Race condition: parallel write/send | IDs written to sheet in parallel with email send; next run sees same cars as new | Sequential: write IDs first, wait for completion, then send email |
| Merge mode: cross-product | "All Possible Combinations" merge returned nothing when Seen_IDs was empty | Changed to Append mode |
| bytbil.com false positive | bytbil.com appears on ALL Blocket pages, was flagging every car as dealer | Removed bytbil.com from dealer URL list |
| Image objects not unpacked | Thumbnail stored as `{url: "..."}` object instead of the URL string | Handle both string and object formats for thumbnail/image fields |
| Pagination = page 1 only | Older or less popular ads missed because only first page was fetched | Expanded to fetch pages 1–5 with 500ms delay |

---

## 11. Grace Gateway (Proxy Fallback)

Grace GW is a proxy service available as an MCP server at `dvbrain.ai/mcp/sse`. If the blocket-api.se API fails (returns errors, empty results, or is unreachable), the system should attempt to use Grace GW to fetch Blocket listings directly.

Implementation strategy:

1. Try blocket-api.se first (primary source)
2. If primary fails: log the error and attempt Grace GW
3. If both fail: send an error notification email and skip the cycle

The exact Grace GW API contract should be determined during implementation by querying the MCP server's tool definitions.

---

## 12. Style Guide Reference

The email templates and any web-facing components should follow the Autostore Sverige visual identity:

| Element | Value |
|---------|-------|
| Primary background | `#1A1A2E` (dark navy) |
| Accent / CTA color | `#667EEA` (purple-blue) |
| Gradient | `linear-gradient(135deg, #667EEA 0%, #764BA2 100%)` |
| Priority badge | `#F5A623` (orange) |
| Body font | `-apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif` |
| Card style | White, `border-radius: 10px`, `box-shadow: 0 2px 8px rgba(0,0,0,0.1)` |
| Background | `#F5F5F5` (light gray) |
| Logo | `https://autostoresverige.com/autostore-wht.svg` |
| Website | `autostoresverige.com` |

The email footer should read: "Autostore Sverige AB — Automatisk bilsökning" with a timestamp in sv-SE locale format.

---

## 13. Deployment Target: Google Cloud

Recommended deployment options (in order of simplicity):

1. **Cloud Run + Cloud Scheduler:** Containerized app triggered by HTTP on a cron schedule. Most straightforward.
2. **Cloud Functions (2nd gen) + Cloud Scheduler:** Serverless function, no container needed. Good for simple workloads.
3. **Compute Engine + cron:** VM with system cron. Most control but most maintenance.

The application needs:
- Outbound HTTPS access to: `blocket-api.se`, `api.anthropic.com`, `blocket.se`, `sheets.googleapis.com`, `gmail.googleapis.com`, `dvbrain.ai`
- Google Cloud service account with Sheets and Gmail API access
- Secrets management for the Anthropic API key

---

## 14. Environment Variables & Secrets

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for brand/type classification |
| `GOOGLE_SHEETS_CREDENTIALS` | Service account JSON for Sheets API |
| `GMAIL_CREDENTIALS` | OAuth2 or service account for sending email |
| `SPREADSHEET_ID` | `1xFREypf8fvBjyBX3ul2_PTMAcKGKyV-ednJqLpjf6AI` |
| `SEEN_IDS_SHEET` | `Seen_IDs` (gid=2079567462) |
| `PRICE_HISTORY_SHEET` | `Price_History` (gid=621950292) |
| `EMAIL_RECIPIENTS` | `erik+blocket@autostoresverige.com, serge+autostore@lachapelle.se` |
| `TIMEZONE` | `Europe/Stockholm` |
| `PAGES_TO_FETCH` | `5` |
| `MILEAGE_LIMIT_KM` | `200000` |
| `LEASING_PRICE_THRESHOLD` | `15000` |
| `EMPTY_EMAIL_THROTTLE_HOURS` | `4` |
| `BATCH_SIZE` | `20` |
| `GRACE_GW_URL` | `https://dvbrain.ai/mcp/sse` |

---

## 15. Testing Checklist

Before declaring the migration complete, verify all of the following:

### 15.1 Data Fetching

- [ ] API returns cars and parses `response.docs[]` correctly
- [ ] Pagination fetches pages 1–5 with delay
- [ ] Empty page stops pagination early
- [ ] API timeout/error handled gracefully
- [ ] Grace GW fallback triggers on API failure

### 15.2 Filtering

- [ ] Dealer with `dealer_segment="Företag"` is rejected
- [ ] Dealer with `organisation_name` is rejected
- [ ] Car with price < 15,000 SEK is rejected (leasing)
- [ ] "Ej leasing" in title is NOT rejected (negation handling)
- [ ] Brand-new 2026 car with 0 km is rejected
- [ ] AI classifies Volvo V60 as ACCEPT, Kia Ceed as REJECT
- [ ] AI failure causes all cars to be rejected (fail-closed)
- [ ] Page with dealer URL (e.g., bilia.se) causes rejection
- [ ] Page with bytbil.com does NOT cause rejection
- [ ] 200,000 km passenger car passes, 200,001 km is rejected
- [ ] Commercial vehicle with 300,000 km passes (no limit)
- [ ] 250 mil correctly converts to 2,500 km

### 15.3 Deduplication

- [ ] Same car appearing on pages 1 and 3 only appears once
- [ ] Car already in Seen_IDs sheet is filtered out
- [ ] New car IDs are written to sheet BEFORE email is sent
- [ ] Empty Seen_IDs sheet does not crash the system

### 15.4 Email

- [ ] Priority vehicles (pickups/vans) appear before passenger cars
- [ ] Priority badge shows on qualifying vehicles
- [ ] Images load in email client
- [ ] Blocket links are clickable and correct
- [ ] Empty notification only sends every 4 hours
- [ ] > 20 cars creates multiple email batches
- [ ] Subject line reflects car count and batch info

### 15.5 Operations

- [ ] Runs only between 06:00–00:00 Swedish time
- [ ] Does not run at 03:00 Swedish time
- [ ] Price history is written to Price_History sheet
- [ ] Logs are structured and include key metrics per run

---

*— End of Specification —*
