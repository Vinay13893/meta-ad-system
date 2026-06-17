# CLAUDE.md — D2C Growth Engine (Project Spec & Working Agreement)

> This file is the single source of truth for how this project is built.
> Every AI coding agent (Claude Code, Codex, Cursor, etc.) and every human
> MUST read this before writing code, and MUST follow it. If a request
> conflicts with this file, stop and flag it instead of silently diverging.

---

## 1. What we are building

An internal decision engine for a Shopify D2C brand running Meta Ads (India).
It pulls Meta Ads + Shopify data daily, computes **RTO-adjusted contribution
margin** (not vanity ROAS), detects **creative/audience fatigue**, and sends a
**morning brief** with observations and *suggested tests* — not blind orders.

We are building for ONE brand first (single-tenant). It will later become a
multi-tenant SaaS for other founders, and will later add Google Ads. The
architecture must make those two transitions cheap. See §3.

### Current phase: SINGLE-TENANT v1
- One brand. Tokens are pasted/configured by us, not obtained via OAuth.
- No UI. Output is a scheduled message (email/Telegram/WhatsApp).
- No user login, no billing, no onboarding wizard. DO NOT BUILD THESE YET.

---

## 2. Tech stack (do not deviate without updating this file)

- **Language:** Python 3.11+
- **Database:** Postgres via Supabase (two separate projects: `dev` and `prod`)
- **Scheduling:** GitHub Actions cron (v1). Move to Supabase scheduled
  functions or a worker later if needed.
- **Source control:** GitHub. Branches + Pull Requests only. No commits to `main`.
- **Secrets:** environment variables / GitHub Actions secrets / Supabase secrets.
  NEVER in code, NEVER committed. There is a `.env.example` but never a real `.env`.
- **Dependencies:** keep them boring and mainstream (`requests`, `psycopg`/
  `supabase-py`, `pydantic`, `python-dotenv`). Avoid niche libraries — agents
  hallucinate APIs for them.

---

## 3. The three architecture rules that keep the SaaS door open

These are nearly free now and brutal to retrofit. They are mandatory.

1. **`brand_id` on every table.** Even though there is exactly one brand today,
   every row of every table carries a `brand_id`. No exceptions. All queries
   filter by `brand_id`.
2. **No hardcoded brand or tokens in logic.** Sync functions take
   `(brand_id, credentials)` as parameters, read from the `connections` table.
   Adding brand #2 = inserting a row, never editing code.
3. **Connector abstraction, not platform spaghetti.** Each platform (Meta now,
   Google Ads later) implements a shared interface and writes into ONE
   normalized shape. Adding a platform = a new module implementing the
   interface. See §6.

---

## 4. The three data-integrity rules (mandatory)

1. **Store raw API responses immutably.** Every fetch writes the raw JSON to a
   `raw_*` table with `brand_id`, `fetched_at`, and a natural key. Computed
   metrics are derived from raw tables in separate steps. When an API changes a
   field, we recompute history — we never lose it.
2. **Every sync is idempotent.** Re-running a sync for the same day must not
   create duplicates or corrupt data. Use upserts keyed on natural keys
   (e.g. `(brand_id, platform, ad_id, date)`).
3. **Secrets only via env.** Restating rule from §2 because it is the most
   common agent mistake. If you see a token or key literal in code, that is a bug.

---

## 5. Database schema (v1)

> Apply via SQL migration files in `/migrations`, numbered and append-only.
> Never edit an applied migration; write a new one.

```sql
-- Tenants. One row in v1.
create table brands (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  currency      text not null default 'INR',
  created_at    timestamptz not null default now()
);

-- Credentials per platform per brand. v1: rows inserted manually by us.
create table connections (
  id            uuid primary key default gen_random_uuid(),
  brand_id      uuid not null references brands(id),
  platform      text not null check (platform in ('meta','shopify','google_ads')),
  account_id    text not null,           -- ad account id / shop domain
  credentials   jsonb not null,          -- token(s); encrypt at rest later
  status        text not null default 'active',
  created_at    timestamptz not null default now(),
  unique (brand_id, platform, account_id)
);

-- RAW immutable layer ---------------------------------------------------------
create table raw_meta_insights (
  id            bigserial primary key,
  brand_id      uuid not null references brands(id),
  date          date not null,
  level         text not null,           -- 'campaign' | 'adset' | 'ad'
  object_id     text not null,
  payload       jsonb not null,          -- full raw response row
  fetched_at    timestamptz not null default now(),
  unique (brand_id, date, level, object_id)
);

create table raw_shopify_orders (
  id            bigserial primary key,
  brand_id      uuid not null references brands(id),
  order_id      text not null,
  payload       jsonb not null,
  fetched_at    timestamptz not null default now(),
  unique (brand_id, order_id)
);

create table raw_shopify_products (
  id            bigserial primary key,
  brand_id      uuid not null references brands(id),
  product_id    text not null,
  payload       jsonb not null,
  fetched_at    timestamptz not null default now(),
  unique (brand_id, product_id)
);

-- NORMALIZED / COMPUTED layer -------------------------------------------------
create table ad_metrics_daily (
  brand_id      uuid not null references brands(id),
  platform      text not null,           -- 'meta' | 'google_ads'
  date          date not null,
  campaign_id   text, campaign_name text,
  adset_id      text, adset_name text,
  ad_id         text, ad_name text,
  spend         numeric not null default 0,
  impressions   bigint not null default 0,
  clicks        bigint not null default 0,
  reach         bigint,
  frequency     numeric,
  ctr           numeric,
  cpm           numeric,
  purchases     numeric default 0,       -- platform-reported
  revenue_rep   numeric default 0,       -- platform-reported revenue
  cpa           numeric,
  primary key (brand_id, platform, date, ad_id)
);

create table orders (
  brand_id        uuid not null references brands(id),
  order_id        text not null,
  created_at      timestamptz not null,
  gross_value     numeric not null,      -- order subtotal
  payment_method  text not null,         -- 'cod' | 'prepaid'
  status          text not null,         -- 'confirmed'|'rto'|'delivered'|'cancelled'
  primary key (brand_id, order_id)
);

create table order_items (
  brand_id      uuid not null references brands(id),
  order_id      text not null,
  product_id    text not null,
  quantity      int not null,
  unit_price    numeric not null,
  primary key (brand_id, order_id, product_id)
);

-- Cost inputs we maintain by hand (no API gives these). One row per product.
create table product_costs (
  brand_id          uuid not null references brands(id),
  product_id        text not null,
  cogs              numeric not null default 0,   -- per unit
  shipping_cost     numeric not null default 0,   -- per order/unit assumption
  packaging_cost    numeric not null default 0,
  cod_rto_rate      numeric not null default 0,   -- 0..1, COD return-to-origin rate
  reverse_ship_cost numeric not null default 0,   -- cost incurred on an RTO
  primary key (brand_id, product_id)
);

-- Append-only log of what we flagged, so we can check later if we were right.
create table daily_brief_log (
  id            bigserial primary key,
  brand_id      uuid not null references brands(id),
  date          date not null,
  summary       jsonb not null,          -- metrics + flags + suggestions
  created_at    timestamptz not null default now(),
  unique (brand_id, date)
);
```

---

## 6. Connector interface (the abstraction in §3.3)

```python
# connectors/base.py
from dataclasses import dataclass
from datetime import date

@dataclass
class AdMetricRecord:
    platform: str
    date: date
    campaign_id: str | None; campaign_name: str | None
    adset_id: str | None;    adset_name: str | None
    ad_id: str | None;       ad_name: str | None
    spend: float; impressions: int; clicks: int
    reach: int | None; frequency: float | None
    purchases: float; revenue_rep: float

class AdPlatformConnector:
    """Meta now; Google Ads later. Both implement this."""
    def fetch_ad_metrics(self, brand_id: str, creds: dict,
                         start: date, end: date) -> list[AdMetricRecord]: ...

@dataclass
class OrderRecord:
    order_id: str
    created_at: str
    gross_value: float
    payment_method: str      # 'cod' | 'prepaid'
    status: str
    items: list[dict]        # {product_id, quantity, unit_price}

class EcommerceConnector:
    """Shopify now."""
    def fetch_orders(self, brand_id: str, creds: dict,
                     start: date, end: date) -> list[OrderRecord]: ...
    def fetch_products(self, brand_id: str, creds: dict) -> list[dict]: ...
```

Concrete modules: `connectors/meta.py`, `connectors/shopify.py`,
later `connectors/google_ads.py`. Each module ONLY knows its own API + how to
return the normalized record. No business logic in connectors.

---

## 7. Core logic

### 7.1 RTO-adjusted contribution margin (the India edge)
For each order, realized value depends on payment method and product RTO risk:

- **Prepaid order:** realized = `gross_value` (money already collected).
- **COD order:** realized = `gross_value * (1 - cod_rto_rate)` and we still
  incur `reverse_ship_cost` on the RTO fraction.

Per order, contribution margin =
`realized_value − cogs − shipping_cost − packaging_cost − (rto_fraction * reverse_ship_cost)`
then subtract allocated ad spend at the day level to get net profit.

Headline metric for the brief is **RTO-adjusted contribution margin**, NOT ROAS.
Always show platform-reported revenue and realized revenue side by side so the
gap is visible.

### 7.2 Fatigue detection (descriptive only in v1)
Compare trailing 7 days vs the prior 7 days, per ad. Flag **creative fatigue**
when ALL hold:
- frequency increased (e.g. +25% or crossed ~3.0),
- CTR fell (e.g. −20% or more),
- CPA rose (e.g. +20% or more),
- spend was non-trivial (above a floor so we ignore noise).

Flag **audience fatigue** when frequency ↑ AND reach is flat/declining AND CPM ↑.

Output is an observation with the actual numbers and a SUGGESTED TEST
("frequency 2.1→4.3, CTR −38%: pattern consistent with creative fatigue —
consider testing fresh creatives against this ad"). Do NOT assert causation or
state a confident profit number in v1. We earn that right later by logging
flags and checking outcomes.

### 7.3 Morning brief
A templated message: yesterday's platform revenue, realized revenue,
RTO-adjusted contribution margin, total spend, MER, and any fatigue/overspend
flags with their numbers. Write the full payload to `daily_brief_log` too.

---

## 8. Repo layout

```
/migrations         numbered .sql files, append-only
/connectors         base.py, meta.py, shopify.py  (google_ads.py later)
/sync               orchestration: pull raw -> upsert normalized
/logic              profit.py, fatigue.py, brief.py
/jobs               daily_run.py (entry point for the cron)
/tests              pytest; at minimum test profit + fatigue math on fixtures
CLAUDE.md           this file
.cursorrules        -> "Read CLAUDE.md and follow it."
.env.example        names of required env vars, no values
```

---

## 9. How we work together (you + intern + AI agents)

- **Branches + PRs only.** `main` is always working. Each feature on its own
  branch, merged via PR. Never push to `main` directly.
- **Module ownership to avoid collisions.** Split by directory. Example: one
  person owns `/logic`, the other owns a new file in `/connectors`. Two agents
  editing the same file is the main way this codebase rots.
- **Dev vs prod DBs are separate Supabase projects.** Interns/experiments run
  against `dev` data only. The real brand's live token lives in `prod` secrets
  and is not shared.
- **Every PR must:** keep §3 and §4 rules intact, include/adjust a test for any
  profit or fatigue math, and not introduce a hardcoded secret or brand.

---

## 10. Explicitly OUT OF SCOPE until told otherwise

Do not build, even if it seems helpful: user auth/login, billing, OAuth connect
flows, onboarding wizards, row-level security, multi-brand UI, Google Ads.
These belong to the SaaS phase. Building them now is wasted effort. When we
reach the SaaS phase, this file will be updated first.

**Note on dashboard (revised from original "no dashboard" rule):** a minimal
read-only viewer is now in scope, as a separate parallel track from the data
pipeline (see §12). It starts simple (render existing tables) and grows a
creative gallery once §12 lands. It is single-tenant, no auth, read-only —
do not let it grow login/multi-brand/editing features without updating this
file first.

---

## 11. Backlog / Deferred (do not forget these)

These are real, scoped follow-ups — not abandoned ideas. Pick them up when
their dependency is ready. Remove an item from this list only when it's been
built or deliberately dropped (with a note why).

- **Video retention metrics.** Meta's Insights API returns video-specific
  metrics (25/50/75/95% watch-through, thruplay, avg watch time) at the ad
  level. Join these into `creative_tags`/analysis once creative tagging
  (§12) is producing data for long enough to find patterns. This is the
  data source for "what creative format works for which campaign objective"
  (awareness vs consideration vs conversion vs retargeting).
- **Demo seed data time-drift (007_demo_seed.sql).** Order dates and
  `ad_metrics_daily` dates are anchored to `now()` / `current_date` at the
  time the seed script runs, not to a rolling window. As a result, the
  dashboard's "last 30 days" filter shows progressively fewer rows each day
  after the seed is run — and will show fully empty data ~30 days after the
  last seed run (estimated fully empty: **~July 14–15, 2026** based on the
  seed run of ~June 14–15, 2026). Two fix directions to consider:
  - **(a) Periodic re-seed cron** — simplest: truncate demo data and re-run
    `007_demo_seed.sql` on a schedule (e.g. weekly). Downside: `random()`
    values change each run, producing inconsistent KPI numbers across
    demos — bad for client/investor presentations where the audience may
    see different numbers on different days.
  - **(b) Deterministic rolling seed** — use `setseed()` (fixed seed value)
    plus formula-based values derived from the loop index instead of
    `random()`, and anchor dates to `now()` at run time. Re-running
    produces identical KPI numbers every time, regardless of when it's run.
    More work upfront, but produces a stable, presentable demo indefinitely.
  **Recommendation:** if the dashboard is ever used for client or investor
  demos where consistency matters, implement option (b). Option (a) is
  acceptable for internal dev use only.
- **Gifting/influencer order COGS as a marketing expense.** Influencer
  orders are correctly excluded from `orders`/`order_items` (so they don't
  inflate revenue), but the COGS of gifted product currently isn't counted
  as a cost anywhere. Raw data is preserved in `raw_shopify_orders`. When
  ready, add a lightweight `marketing_orders` view/table and fold gifting
  COGS into the profit picture as a marketing line item.
- **Publish creatives to Meta as ads (capstone capability — LAST).** Meta's
  Marketing API supports creating ad creatives/ads/adsets/campaigns
  programmatically via the same connector/token already in use
  (`connectors/meta.py`), just write endpoints instead of read endpoints.
  This is explicitly the LAST major capability to build, after creative
  tagging (§12), RCA, alert prioritization, and budget-allocation logic are
  all built AND validated against real outcomes — publishing without that
  context is just "upload a video," not the intelligent placement that makes
  it valuable.

  **MANDATORY SAFETY RULE, not negotiable by convenience or user request at
  build time:** any ad/adset/campaign created by this system via the API
  MUST be created in `PAUSED` status. The system NEVER activates an ad. A
  human reviews, edits anything they disagree with, and activates manually
  in Ads Manager or via an explicit separate human action. If a future
  prompt asks to "auto-activate" or "go live automatically," that is a
  scope change to this file requiring explicit, deliberate sign-off — flag
  it rather than building it.

---

## 12. Creative Intelligence module (in progress)

### 12.1 Purpose
Automated creative analysis: classify uploaded video/image creatives against
an evolving taxonomy (content type, structure, hook type), extract ad copy,
and — once enough tagged data + performance data exists (see §11) — surface
which creative patterns work best per campaign objective.

### 12.2 Taxonomy is DATA, not an enum
The taxonomy (content_type, structure, hook_type, objective values) WILL
change over time as new creative formats emerge. Do not hardcode as a SQL
enum or Python Literal/Enum that requires a migration or code change to add
a value. Store as free text. A simple reference list can live in a config
file or table for documentation/autocomplete, but must not constrain inserts.

Current working taxonomy (expect this to grow):
- content_type: ugc, talking_head, founder_led, broll_voiceover, educational,
  studio_product_demo, meme_text, animation
- structure: hook_problem_solution, hook_story_cta, testimonial,
  before_after, unboxing, comparison, listicle, direct_offer
- hook_type: problem_first, curiosity_pattern_interrupt, bold_claim_stat,
  question, relatable_scenario
- objective (from the Meta campaign, not the creative itself): awareness,
  consideration, conversion, retargeting

### 12.3 Schema
```sql
-- One row per uploaded creative (video or image/carousel).
create table creatives (
  id            uuid primary key default gen_random_uuid(),
  brand_id      uuid not null references brands(id),
  file_url      text not null,        -- Supabase Storage URL
  file_type     text not null,        -- 'video' | 'image' | 'carousel'
  ad_id         text,                 -- nullable; manual mapping to a live
                                       -- Meta ad_id, filled in when known
  uploaded_at   timestamptz not null default now()
);

-- Tags/analysis for a creative. One row per creative (re-run = update).
create table creative_tags (
  creative_id   uuid primary key references creatives(id),
  brand_id      uuid not null references brands(id),
  content_type  text,                 -- free text, see §12.2
  structure     text,
  hook_type     text,
  objective     text,
  description   text,                 -- short free-text visual description
  hook_text     text,                 -- transcribed/extracted hook or headline
  offer_cta     text,
  source        text not null,        -- 'manual' | 'ai:<model_name>'
  notes         text,
  tagged_at     timestamptz not null default now()
);
```
`source` lets manual ground-truth tags and AI-generated tags coexist and be
compared (e.g. `source='manual'` vs `source='ai:gpt-4o'` for the same
creative, before deciding to trust the AI tags as primary).

### 12.4 Analyzer interface (pluggable, like connectors)
```python
# analysis/base.py
from dataclasses import dataclass

@dataclass
class CreativeTags:
    content_type: str | None
    structure: str | None
    hook_type: str | None
    description: str | None
    hook_text: str | None
    offer_cta: str | None

class CreativeAnalyzer:
    """One implementation per AI provider (OpenAI, Anthropic, etc.)."""
    def analyze(self, file_url: str, file_type: str, taxonomy: dict) -> CreativeTags: ...
```
Concrete modules: `analysis/openai_analyzer.py`, etc. Swappable so different
providers/models can be compared against manual ground-truth tags before
picking a default.

### 12.5 Sequencing notes
1. Schema + Supabase Storage upload (plumbing, no AI) — current step.
2. Manual tagging of ~10-15 creatives as ground truth (`source='manual'`).
3. First AI analyzer implementation, run on the same creatives, compared
   against manual tags before trusting it on the full library.
4. Dashboard gallery (§10) reads from `creatives` + `creative_tags`.
5. §11 retention-metrics join, once enough tagged + performance data exists.
