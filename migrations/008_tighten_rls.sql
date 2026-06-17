-- 008_tighten_rls.sql
-- Remove the organization_id IS NULL carve-out from the brands policy now that
-- every brands row has a non-NULL organization_id. Before applying, verify:
--   SELECT id, name, organization_id FROM brands WHERE organization_id IS NULL;
-- must return zero rows.

drop policy "brands_select" on brands;

create policy "brands_select" on brands
  for select using (is_org_member(organization_id));
