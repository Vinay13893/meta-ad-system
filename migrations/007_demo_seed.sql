-- 007_demo_seed.sql
-- Seeds the demo organization, two demo brands, products, campaigns,
-- ad metrics (30 days), and orders (90 orders across 30 days).
-- Run this AFTER creating a demo user in Supabase Auth and replacing
-- the placeholder UUID below with the real auth.users.id.
--
-- To create the demo user:
--   Supabase Dashboard → Authentication → Users → Add User
--   Email: demo@sociomonkey.com  |  Password: Demo@12345
--   Copy the generated user UUID and replace DEMO_USER_ID below.
--
-- Fixed UUIDs so this script is idempotent (safe to re-run).

do $$
declare
  -- ── Replace this with the actual UUID from Supabase Auth → Users ───────────
  -- Step: Dashboard → Authentication → Users → Add User (demo@sociomonkey.com)
  -- Then paste the generated UUID here before running this migration.
  DEMO_USER_ID      uuid := '81b2dd21-a14a-4773-82f8-17a4e5d237f5';

  -- ── Fixed UUIDs for demo data ───────────────────────────────────────────────
  DEMO_ORG_ID       uuid := '00000000-0000-0000-0000-000000000001';
  BEAUTY_BRAND_ID   uuid := '00000000-0000-0000-0000-000000000011';
  FASHION_BRAND_ID  uuid := '00000000-0000-0000-0000-000000000012';

  -- product UUIDs (beauty)
  BP1 text := '00000000-0000-0000-0001-000000000001';
  BP2 text := '00000000-0000-0000-0001-000000000002';
  BP3 text := '00000000-0000-0000-0001-000000000003';
  BP4 text := '00000000-0000-0000-0001-000000000004';
  BP5 text := '00000000-0000-0000-0001-000000000005';

  -- product UUIDs (fashion)
  FP1 text := '00000000-0000-0000-0002-000000000001';
  FP2 text := '00000000-0000-0000-0002-000000000002';
  FP3 text := '00000000-0000-0000-0002-000000000003';
  FP4 text := '00000000-0000-0000-0002-000000000004';

  d date;
  i int;
begin

-- ── Organization ─────────────────────────────────────────────────────────────
insert into organizations (id, name, slug, plan)
values (DEMO_ORG_ID, 'Sociomonkey Demo', 'sociomonkey-demo', 'pro')
on conflict (id) do nothing;

-- ── Brands ───────────────────────────────────────────────────────────────────
insert into brands (id, organization_id, name, slug, currency)
values
  (BEAUTY_BRAND_ID,  DEMO_ORG_ID, 'Demo Beauty Brand',  'demo-beauty',  'INR'),
  (FASHION_BRAND_ID, DEMO_ORG_ID, 'Demo Fashion Brand', 'demo-fashion', 'INR')
on conflict (id) do nothing;

-- ── Organization member ───────────────────────────────────────────────────────
insert into organization_members (organization_id, user_id, role)
values (DEMO_ORG_ID, DEMO_USER_ID, 'owner')
on conflict (organization_id, user_id) do nothing;

-- ── Integration connections (showing realistic multi-account setup) ───────────
insert into integration_connections
  (organization_id, brand_id, platform, account_id, account_name, status, last_synced_at)
values
  (DEMO_ORG_ID, BEAUTY_BRAND_ID,  'meta',    'act_111111111', 'Demo Beauty — Meta Ads',   'active', now() - interval '2 hours'),
  (DEMO_ORG_ID, BEAUTY_BRAND_ID,  'shopify', 'demo-beauty.myshopify.com', 'Demo Beauty Shopify', 'active', now() - interval '2 hours'),
  (DEMO_ORG_ID, FASHION_BRAND_ID, 'meta',    'act_222222222', 'Demo Fashion — Meta Ads',  'active', now() - interval '3 hours'),
  (DEMO_ORG_ID, FASHION_BRAND_ID, 'shopify', 'demo-fashion.myshopify.com', 'Demo Fashion Shopify', 'active', now() - interval '3 hours'),
  (DEMO_ORG_ID, FASHION_BRAND_ID, 'google_ads', 'cid_333333333', 'Demo Fashion — Google Ads', 'pending', null)
on conflict (brand_id, platform, account_id) do nothing;

-- ── Products + costs (Beauty) ─────────────────────────────────────────────────
insert into raw_shopify_products (brand_id, organization_id, product_id, payload)
values
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP1, '{"title":"Kumkumadi Face Oil 30ml","vendor":"Demo Beauty","status":"active","variants":[{"price":"1499"}]}'),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP2, '{"title":"Ubtan Face Pack 100g","vendor":"Demo Beauty","status":"active","variants":[{"price":"699"}]}'),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP3, '{"title":"Saffron Glow Serum 15ml","vendor":"Demo Beauty","status":"active","variants":[{"price":"1999"}]}'),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP4, '{"title":"Rose Water Toner 200ml","vendor":"Demo Beauty","status":"active","variants":[{"price":"399"}]}'),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP5, '{"title":"Aloe Vera Gel 150ml","vendor":"Demo Beauty","status":"active","variants":[{"price":"299"}]}')
on conflict (brand_id, product_id) do nothing;

insert into product_costs (brand_id, organization_id, product_id, cogs, shipping_cost, packaging_cost, cod_rto_rate, reverse_ship_cost)
values
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP1, 450,  100, 0, 0.12, 100),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP2, 210,  100, 0, 0.15, 100),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP3, 600,  100, 0, 0.10, 100),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP4, 120,  100, 0, 0.18, 100),
  (BEAUTY_BRAND_ID, DEMO_ORG_ID, BP5, 90,   100, 0, 0.18, 100)
on conflict (brand_id, product_id) do nothing;

-- ── Products + costs (Fashion) ────────────────────────────────────────────────
insert into raw_shopify_products (brand_id, organization_id, product_id, payload)
values
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP1, '{"title":"Linen Kurta Set","vendor":"Demo Fashion","status":"active","variants":[{"price":"2499"}]}'),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP2, '{"title":"Cotton Co-ord Set","vendor":"Demo Fashion","status":"active","variants":[{"price":"1899"}]}'),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP3, '{"title":"Silk Saree","vendor":"Demo Fashion","status":"active","variants":[{"price":"3999"}]}'),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP4, '{"title":"Embroidered Dupatta","vendor":"Demo Fashion","status":"active","variants":[{"price":"999"}]}')
on conflict (brand_id, product_id) do nothing;

insert into product_costs (brand_id, organization_id, product_id, cogs, shipping_cost, packaging_cost, cod_rto_rate, reverse_ship_cost)
values
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP1, 750,  150, 0, 0.22, 150),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP2, 570,  150, 0, 0.25, 150),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP3, 1200, 150, 0, 0.20, 150),
  (FASHION_BRAND_ID, DEMO_ORG_ID, FP4, 300,  100, 0, 0.28, 100)
on conflict (brand_id, product_id) do nothing;

-- ── Ad metrics — Beauty brand (last 30 days, 3 ads) ──────────────────────────
-- Campaign: Acquisition | Adset: Lookalike 1% | Ads: UGC_v1, UGC_v2, Testimonial
for i in 0..29 loop
  d := current_date - i;

  -- UGC_v1 (performing well, slight fatigue last 7 days)
  insert into ad_metrics_daily
    (brand_id, organization_id, platform, date,
     campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
     spend, impressions, clicks, reach, frequency, ctr, cpm, purchases, revenue_rep, cpa)
  values
    (BEAUTY_BRAND_ID, DEMO_ORG_ID, 'meta', d,
     'camp_b001', 'Acquisition — Beauty', 'ags_b001', 'Lookalike 1%', 'ad_b001', 'UGC_Face_Oil_v1',
     round((2800 + (random()*400)::numeric - (case when i < 7 then 200 else 0 end))::numeric, 2),
     round((38000 + random()*5000)::numeric, 0)::bigint,
     round((420 + random()*60)::numeric, 0)::bigint,
     round((18000 + random()*2000)::numeric, 0)::bigint,
     round((1.8 + (case when i < 7 then 0.9 else 0.2 end) + random()*0.3)::numeric, 2),
     round((1.1 + (case when i < 7 then -0.35 else 0.0 end) + random()*0.1)::numeric, 3),
     round((73 + random()*8)::numeric, 2),
     round((6 + random()*2)::numeric, 1),
     round((8970 + random()*1000)::numeric, 2),
     round((380 + (case when i < 7 then 120 else 0 end) + random()*40)::numeric, 2))
  on conflict (brand_id, platform, date, ad_id) do nothing;

  -- UGC_v2 (newer, ramping up)
  insert into ad_metrics_daily
    (brand_id, organization_id, platform, date,
     campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
     spend, impressions, clicks, reach, frequency, ctr, cpm, purchases, revenue_rep, cpa)
  values
    (BEAUTY_BRAND_ID, DEMO_ORG_ID, 'meta', d,
     'camp_b001', 'Acquisition — Beauty', 'ags_b001', 'Lookalike 1%', 'ad_b002', 'UGC_Face_Oil_v2',
     round((case when i > 20 then 0 else 1200 + random()*300 end)::numeric, 2),
     round((case when i > 20 then 0 else 16000 + random()*3000 end)::numeric, 0)::bigint,
     round((case when i > 20 then 0 else 190 + random()*40 end)::numeric, 0)::bigint,
     round((case when i > 20 then 0 else 9000 + random()*1500 end)::numeric, 0)::bigint,
     round((1.3 + random()*0.2)::numeric, 2),
     round((1.25 + random()*0.15)::numeric, 3),
     round((68 + random()*6)::numeric, 2),
     round((case when i > 20 then 0 else 3 + random()*1 end)::numeric, 1),
     round((case when i > 20 then 0 else 4500 + random()*600 end)::numeric, 2),
     round((case when i > 20 then 0 else 320 + random()*40 end)::numeric, 2))
  on conflict (brand_id, platform, date, ad_id) do nothing;

  -- Testimonial (retargeting, lower spend)
  insert into ad_metrics_daily
    (brand_id, organization_id, platform, date,
     campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
     spend, impressions, clicks, reach, frequency, ctr, cpm, purchases, revenue_rep, cpa)
  values
    (BEAUTY_BRAND_ID, DEMO_ORG_ID, 'meta', d,
     'camp_b002', 'Retargeting — Beauty', 'ags_b002', 'Website Visitors 30D', 'ad_b003', 'Testimonial_Saffron_v1',
     round((600 + random()*150)::numeric, 2),
     round((5200 + random()*800)::numeric, 0)::bigint,
     round((88 + random()*20)::numeric, 0)::bigint,
     round((3000 + random()*500)::numeric, 0)::bigint,
     round((4.2 + random()*0.5)::numeric, 2),
     round((1.7 + random()*0.2)::numeric, 3),
     round((115 + random()*12)::numeric, 2),
     round((4 + random()*2)::numeric, 1),
     round((7200 + random()*800)::numeric, 2),
     round((150 + random()*30)::numeric, 2))
  on conflict (brand_id, platform, date, ad_id) do nothing;
end loop;

-- ── Ad metrics — Fashion brand (last 30 days, 2 ads) ─────────────────────────
for i in 0..29 loop
  d := current_date - i;

  insert into ad_metrics_daily
    (brand_id, organization_id, platform, date,
     campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
     spend, impressions, clicks, reach, frequency, ctr, cpm, purchases, revenue_rep, cpa)
  values
    (FASHION_BRAND_ID, DEMO_ORG_ID, 'meta', d,
     'camp_f001', 'Acquisition — Fashion', 'ags_f001', 'Broad — Women 25-45', 'ad_f001', 'Kurta_Lifestyle_v1',
     round((3500 + random()*500)::numeric, 2),
     round((42000 + random()*6000)::numeric, 0)::bigint,
     round((380 + random()*60)::numeric, 0)::bigint,
     round((24000 + random()*3000)::numeric, 0)::bigint,
     round((1.5 + random()*0.3)::numeric, 2),
     round((0.90 + random()*0.15)::numeric, 3),
     round((83 + random()*9)::numeric, 2),
     round((5 + random()*2)::numeric, 1),
     round((12500 + random()*2000)::numeric, 2),
     round((580 + random()*80)::numeric, 2))
  on conflict (brand_id, platform, date, ad_id) do nothing;

  insert into ad_metrics_daily
    (brand_id, organization_id, platform, date,
     campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
     spend, impressions, clicks, reach, frequency, ctr, cpm, purchases, revenue_rep, cpa)
  values
    (FASHION_BRAND_ID, DEMO_ORG_ID, 'meta', d,
     'camp_f001', 'Acquisition — Fashion', 'ags_f001', 'Broad — Women 25-45', 'ad_f002', 'CoordSet_UGC_v1',
     round((1800 + random()*300)::numeric, 2),
     round((19000 + random()*3000)::numeric, 0)::bigint,
     round((210 + random()*40)::numeric, 0)::bigint,
     round((12000 + random()*2000)::numeric, 0)::bigint,
     round((1.4 + random()*0.2)::numeric, 2),
     round((1.10 + random()*0.12)::numeric, 3),
     round((78 + random()*8)::numeric, 2),
     round((3 + random()*1)::numeric, 1),
     round((5700 + random()*1000)::numeric, 2),
     round((490 + random()*70)::numeric, 2))
  on conflict (brand_id, platform, date, ad_id) do nothing;
end loop;

-- ── Orders — Beauty brand (90 orders, last 30 days) ───────────────────────────
for i in 0..89 loop
  declare
    order_date timestamptz := now() - (random()*30)::int * interval '1 day' - random() * interval '20 hours';
    is_cod     boolean     := random() < 0.58;  -- 58% COD (realistic for India D2C beauty)
    prod_id    text        := (array[BP1,BP2,BP3,BP4,BP5])[1 + (random()*4)::int];
    price      numeric     := case prod_id
                                when BP1 then 1499
                                when BP2 then 699
                                when BP3 then 1999
                                when BP4 then 399
                                else 299
                              end;
    o_status   text        := case
                                when is_cod and random() < 0.14 then 'rto'
                                when random() < 0.03 then 'cancelled'
                                else 'delivered'
                              end;
    o_id       text        := 'DEMO-BEAUTY-' || lpad(i::text, 5, '0');
  begin
    insert into orders
      (brand_id, organization_id, order_id, created_at, gross_value, payment_method, status)
    values
      (BEAUTY_BRAND_ID, DEMO_ORG_ID, o_id, order_date, price,
       case when is_cod then 'cod' else 'prepaid' end, o_status)
    on conflict (brand_id, order_id) do nothing;

    insert into order_items
      (brand_id, organization_id, order_id, product_id, quantity, unit_price)
    values
      (BEAUTY_BRAND_ID, DEMO_ORG_ID, o_id, prod_id, 1, price)
    on conflict (brand_id, order_id, product_id) do nothing;
  end;
end loop;

-- ── Orders — Fashion brand (60 orders, last 30 days) ─────────────────────────
for i in 0..59 loop
  declare
    order_date timestamptz := now() - (random()*30)::int * interval '1 day' - random() * interval '20 hours';
    is_cod     boolean     := random() < 0.65;  -- higher COD for fashion
    prod_id    text        := (array[FP1,FP2,FP3,FP4])[1 + (random()*3)::int];
    price      numeric     := case prod_id
                                when FP1 then 2499
                                when FP2 then 1899
                                when FP3 then 3999
                                else 999
                              end;
    o_status   text        := case
                                when is_cod and random() < 0.23 then 'rto'
                                when random() < 0.04 then 'cancelled'
                                else 'delivered'
                              end;
    o_id       text        := 'DEMO-FASHION-' || lpad(i::text, 5, '0');
  begin
    insert into orders
      (brand_id, organization_id, order_id, created_at, gross_value, payment_method, status)
    values
      (FASHION_BRAND_ID, DEMO_ORG_ID, o_id, order_date, price,
       case when is_cod then 'cod' else 'prepaid' end, o_status)
    on conflict (brand_id, order_id) do nothing;

    insert into order_items
      (brand_id, organization_id, order_id, product_id, quantity, unit_price)
    values
      (FASHION_BRAND_ID, DEMO_ORG_ID, o_id, prod_id, 1, price)
    on conflict (brand_id, order_id, product_id) do nothing;
  end;
end loop;

end $$;
