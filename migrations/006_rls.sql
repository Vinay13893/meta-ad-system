-- 006_rls.sql
-- Row-level security for the app layer.
-- Pipeline uses service-role key → bypasses RLS entirely (by design).
-- App uses anon key + JWT → restricted to what RLS grants.

-- ── Helper functions ──────────────────────────────────────────────────────────

-- Returns true if the calling user is a member of the given org.
create or replace function is_org_member(org_id uuid)
returns boolean
language sql
security definer
stable
as $$
  select exists (
    select 1 from organization_members
    where organization_id = org_id
      and user_id = auth.uid()
  )
$$;

-- Returns true if the calling user belongs to the org that owns the brand.
create or replace function has_brand_access(b_id uuid)
returns boolean
language sql
security definer
stable
as $$
  select exists (
    select 1
    from brands b
    join organization_members om on om.organization_id = b.organization_id
    where b.id = b_id
      and om.user_id = auth.uid()
  )
$$;

-- ── Enable RLS ────────────────────────────────────────────────────────────────
alter table organizations           enable row level security;
alter table organization_members    enable row level security;
alter table brand_members           enable row level security;
alter table brands                  enable row level security;
alter table integration_connections enable row level security;
alter table raw_meta_insights       enable row level security;
alter table raw_shopify_orders      enable row level security;
alter table raw_shopify_products    enable row level security;
alter table ad_metrics_daily        enable row level security;
alter table orders                  enable row level security;
alter table order_items             enable row level security;
alter table product_costs           enable row level security;
alter table daily_brief_log         enable row level security;
alter table creatives               enable row level security;
alter table creative_tags           enable row level security;

-- ── Policies ─────────────────────────────────────────────────────────────────

-- organizations: visible to members only
create policy "orgs_select" on organizations
  for select using (is_org_member(id));

-- organization_members: members can see their co-members
create policy "org_members_select" on organization_members
  for select using (is_org_member(organization_id));

-- brand_members: org members can see brand membership within their org
create policy "brand_members_select" on brand_members
  for select using (is_org_member(organization_id));

-- brands: visible to org members
-- (organization_id is null guard keeps legacy rows accessible until backfill)
create policy "brands_select" on brands
  for select using (
    organization_id is null
    or is_org_member(organization_id)
  );

-- integration_connections: visible to org members
create policy "int_conn_select" on integration_connections
  for select using (is_org_member(organization_id));

-- data tables: visible to users with brand access
create policy "raw_meta_select"       on raw_meta_insights    for select using (has_brand_access(brand_id));
create policy "raw_orders_select"     on raw_shopify_orders   for select using (has_brand_access(brand_id));
create policy "raw_products_select"   on raw_shopify_products for select using (has_brand_access(brand_id));
create policy "ad_metrics_select"     on ad_metrics_daily     for select using (has_brand_access(brand_id));
create policy "orders_select"         on orders               for select using (has_brand_access(brand_id));
create policy "order_items_select"    on order_items          for select using (has_brand_access(brand_id));
create policy "product_costs_select"  on product_costs        for select using (has_brand_access(brand_id));
create policy "brief_log_select"      on daily_brief_log      for select using (has_brand_access(brand_id));
create policy "creatives_select"      on creatives            for select using (has_brand_access(brand_id));
create policy "creative_tags_select"  on creative_tags        for select using (has_brand_access(brand_id));
