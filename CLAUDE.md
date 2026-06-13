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
flows, onboarding wizards, a web dashboard/frontend, row-level security,
multi-brand UI, Google Ads. These belong to the SaaS phase. Building them now is
wasted effort. When we reach the SaaS phase, this file will be updated first.
