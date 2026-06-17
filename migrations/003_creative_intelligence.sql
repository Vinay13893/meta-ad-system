-- Creative Intelligence module — §12.3 of CLAUDE.md.
-- Storage bucket ("creatives") is created on first run of creatives/upload.py
-- via the Supabase Storage API (sb.storage.create_bucket). Alternatively,
-- create it manually: Supabase Dashboard → Storage → New bucket → "creatives"
-- (private). The upload script handles either case idempotently.

create table if not exists creatives (
  id          uuid primary key default gen_random_uuid(),
  brand_id    uuid not null references brands(id),
  file_url    text not null,        -- Supabase Storage signed URL
  file_type   text not null,        -- 'video' | 'image' | 'carousel'
  ad_id       text,                 -- nullable; manual mapping to a live Meta ad_id
  uploaded_at timestamptz not null default now()
);

-- One row per creative. Re-running analysis = update (upsert) on creative_id.
-- source tracks who set the current tags: 'manual' | 'ai:<model_name>'
create table if not exists creative_tags (
  creative_id  uuid primary key references creatives(id),
  brand_id     uuid not null references brands(id),
  content_type text,                -- free text — see §12.2 taxonomy
  structure    text,
  hook_type    text,
  objective    text,
  description  text,
  hook_text    text,
  offer_cta    text,
  source       text not null,       -- 'manual' | 'ai:<model_name>'
  notes        text,
  tagged_at    timestamptz not null default now()
);
