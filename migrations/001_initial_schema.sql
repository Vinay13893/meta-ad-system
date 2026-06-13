-- Migration 001: initial schema
-- Apply once against the dev Supabase project.
-- Never edit this file after applying — write a new migration instead.

-- Tenants. One row in v1 (Sage Royal Ayurveda).
create table if not exists brands (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  currency    text not null default 'INR',
  created_at  timestamptz not null default now()
);

-- Credentials per platform per brand.
-- v1: rows inserted manually (see seed below).
create table if not exists connections (
  id          uuid primary key default gen_random_uuid(),
  brand_id    uuid not null references brands(id),
  platform    text not null check (platform in ('meta','shopify','google_ads')),
  account_id  text not null,
  credentials jsonb not null,
  status      text not null default 'active',
  created_at  timestamptz not null default now(),
  unique (brand_id, platform, account_id)
);

-- RAW immutable layer ---------------------------------------------------------

create table if not exists raw_meta_insights (
  id          bigserial primary key,
  brand_id    uuid not null references brands(id),
  date        date not null,
  level       text not null check (level in ('campaign','adset','ad')),
  object_id   text not null,
  payload     jsonb not null,
  fetched_at  timestamptz not null default now(),
  unique (brand_id, date, level, object_id)
);

create table if not exists raw_shopify_orders (
  id          bigserial primary key,
  brand_id    uuid not null references brands(id),
  order_id    text not null,
  payload     jsonb not null,
  fetched_at  timestamptz not null default now(),
  unique (brand_id, order_id)
);

create table if not exists raw_shopify_products (
  id          bigserial primary key,
  brand_id    uuid not null references brands(id),
  product_id  text not null,
  payload     jsonb not null,
  fetched_at  timestamptz not null default now(),
  unique (brand_id, product_id)
);

-- NORMALIZED / COMPUTED layer -------------------------------------------------

create table if not exists ad_metrics_daily (
  brand_id        uuid not null references brands(id),
  platform        text not null,
  date            date not null,
  campaign_id     text,
  campaign_name   text,
  adset_id        text,
  adset_name      text,
  ad_id           text,
  ad_name         text,
  spend           numeric not null default 0,
  impressions     bigint not null default 0,
  clicks          bigint not null default 0,
  reach           bigint,
  frequency       numeric,
  ctr             numeric,
  cpm             numeric,
  purchases       numeric default 0,
  revenue_rep     numeric default 0,
  cpa             numeric,
  primary key (brand_id, platform, date, ad_id)
);

create table if not exists orders (
  brand_id        uuid not null references brands(id),
  order_id        text not null,
  created_at      timestamptz not null,
  gross_value     numeric not null,
  payment_method  text not null,
  status          text not null,
  primary key (brand_id, order_id)
);

create table if not exists order_items (
  brand_id    uuid not null references brands(id),
  order_id    text not null,
  product_id  text not null,
  quantity    int not null,
  unit_price  numeric not null,
  primary key (brand_id, order_id, product_id)
);

create table if not exists product_costs (
  brand_id          uuid not null references brands(id),
  product_id        text not null,
  cogs              numeric not null default 0,
  shipping_cost     numeric not null default 0,
  packaging_cost    numeric not null default 0,
  cod_rto_rate      numeric not null default 0,
  reverse_ship_cost numeric not null default 0,
  primary key (brand_id, product_id)
);

create table if not exists daily_brief_log (
  id          bigserial primary key,
  brand_id    uuid not null references brands(id),
  date        date not null,
  summary     jsonb not null,
  created_at  timestamptz not null default now(),
  unique (brand_id, date)
);

-- SEED: insert the one brand for v1 -------------------------------------------
-- Returns the brand id so the connections insert can reference it.

insert into brands (name, currency)
values ('Sage Royal Ayurveda', 'INR')
on conflict do nothing;
