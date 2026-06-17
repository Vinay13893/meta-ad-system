-- Add Meta Ads attribution columns to orders.
-- Both are nullable: populated only when utm_source=fb is present on the order.
-- meta_adset_id = utm_term  (Meta's numeric adset ID)
-- meta_ad_name  = utm_content (human-readable ad creative name)

alter table orders
  add column if not exists meta_adset_id text,
  add column if not exists meta_ad_name  text;
