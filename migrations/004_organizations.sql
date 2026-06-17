-- 004_organizations.sql
-- Adds the organization layer (Organization → Brand → Connected Accounts).
-- All existing tables gain organization_id (nullable → backfill → enforce later).
-- Pipeline keeps working: brand_id is still the operational scope; org_id is the
-- tenancy boundary for the app and for RLS.

-- ── 1. Organizations ─────────────────────────────────────────────────────────
create table if not exists organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text not null unique,   -- URL-safe identifier, e.g. "acme-consumer"
  logo_url    text,
  plan        text not null default 'free',
  created_at  timestamptz not null default now()
);

-- ── 2. Organization ↔ User membership ────────────────────────────────────────
create table if not exists organization_members (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  role            text not null default 'member'
                  check (role in ('owner', 'admin', 'member', 'viewer')),
  created_at      timestamptz not null default now(),
  unique (organization_id, user_id)
);

-- ── 3. Extend brands ─────────────────────────────────────────────────────────
alter table brands
  add column if not exists organization_id uuid references organizations(id),
  add column if not exists slug            text;

-- Unique slug per org (slugs can be reused across orgs)
create unique index if not exists brands_org_slug_unique
  on brands(organization_id, slug)
  where slug is not null;

-- ── 4. Brand ↔ User membership (optional per-brand ACL) ──────────────────────
create table if not exists brand_members (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  brand_id        uuid not null references brands(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  role            text not null default 'member',
  created_at      timestamptz not null default now(),
  unique (brand_id, user_id)
);

-- ── 5. Add organization_id to existing tables (nullable for pipeline compat) ──
alter table connections            add column if not exists organization_id uuid references organizations(id);
alter table raw_meta_insights      add column if not exists organization_id uuid references organizations(id);
alter table raw_shopify_orders     add column if not exists organization_id uuid references organizations(id);
alter table raw_shopify_products   add column if not exists organization_id uuid references organizations(id);
alter table ad_metrics_daily       add column if not exists organization_id uuid references organizations(id);
alter table orders                 add column if not exists organization_id uuid references organizations(id);
alter table order_items            add column if not exists organization_id uuid references organizations(id);
alter table product_costs          add column if not exists organization_id uuid references organizations(id);
alter table daily_brief_log        add column if not exists organization_id uuid references organizations(id);
alter table creatives              add column if not exists organization_id uuid references organizations(id);
alter table creative_tags          add column if not exists organization_id uuid references organizations(id);
