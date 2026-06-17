-- 005_integration_connections.sql
-- New app-facing connections table. Supports multiple accounts per platform
-- per brand (e.g. Brand A → Meta Account 1 + Meta Account 2 + Shopify Store 1).
-- The old `connections` table stays for pipeline backwards-compat.
-- Phase 3 will migrate the pipeline to read from this table instead.

create table if not exists integration_connections (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  brand_id        uuid not null references brands(id) on delete cascade,
  platform        text not null check (platform in (
    'meta', 'shopify', 'google_ads',
    'amazon_seller', 'amazon_ads',
    'flipkart', 'meesho'
  )),
  account_id      text not null,
  account_name    text,
  credentials     jsonb not null default '{}',
  status          text not null default 'pending'
                  check (status in ('active', 'inactive', 'error', 'pending')),
  last_synced_at  timestamptz,
  sync_error      text,
  metadata        jsonb not null default '{}',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (brand_id, platform, account_id)
);

create index if not exists ic_brand_id  on integration_connections(brand_id);
create index if not exists ic_org_id    on integration_connections(organization_id);
create index if not exists ic_platform  on integration_connections(platform);
