/*
# Create fiyat_kayitlari table for historical price tracking

1. New Tables
- `fiyat_kayitlari`
  - `id` (uuid, primary key) — unique record ID
  - `isletme` (text, not null) — name of the bakery/chamber/platform
  - `kaynak_turu` (text, not null) — "Pastane", "Esnaf Odası", or "Platform"
  - `urun` (text, not null) — tracked product: Simit, Poğaça, Açma, Yaş Pasta, Baklava, Su Böreği
  - `cekilen_isim` (text) — original product name as it appeared on the source site
  - `fiyat` (numeric(12,2), not null) — cleaned float price in TL
  - `kaynak_url` (text) — URL the price was scraped from
  - `cekilme_tarihi` (timestamptz, default now()) — when the price was scraped

2. Indexes
- Composite index on (urun, cekilme_tarihi) for fast historical queries by product
- Index on isletme for filtering by business
- Index on cekilme_tarihi for date-range queries

3. Security
- Enable RLS on fiyat_kayitlari.
- Single-tenant app (no sign-in screen), so policies use TO anon, authenticated.
- All CRUD operations allowed for anon + authenticated since data is intentionally public/shared.

4. Notes
- This table stores every price scrape as a new row, enabling time-series analysis.
- No user_id column — this is a single-tenant app with no auth.
- Duplicate prevention is handled in application logic (same isletme + urun + cekilen_isim on same day).
*/

CREATE TABLE IF NOT EXISTS fiyat_kayitlari (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme text NOT NULL,
  kaynak_turu text NOT NULL,
  urun text NOT NULL,
  cekilen_isim text,
  fiyat numeric(12,2) NOT NULL,
  kaynak_url text,
  cekilme_tarihi timestamptz NOT NULL DEFAULT now()
);

-- Indexes for historical queries
CREATE INDEX IF NOT EXISTS idx_fiyat_urun_tarih ON fiyat_kayitlari (urun, cekilme_tarihi);
CREATE INDEX IF NOT EXISTS idx_fiyat_isletme ON fiyat_kayitlari (isletme);
CREATE INDEX IF NOT EXISTS idx_fiyat_tarih ON fiyat_kayitlari (cekilme_tarihi);

-- Enable RLS
ALTER TABLE fiyat_kayitlari ENABLE ROW LEVEL SECURITY;

-- Single-tenant: allow anon + authenticated full CRUD (data is intentionally public)
DROP POLICY IF EXISTS "anon_select_fiyatlar" ON fiyat_kayitlari;
CREATE POLICY "anon_select_fiyatlar" ON fiyat_kayitlari FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_fiyatlar" ON fiyat_kayitlari;
CREATE POLICY "anon_insert_fiyatlar" ON fiyat_kayitlari FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_fiyatlar" ON fiyat_kayitlari;
CREATE POLICY "anon_update_fiyatlar" ON fiyat_kayitlari FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_fiyatlar" ON fiyat_kayitlari;
CREATE POLICY "anon_delete_fiyatlar" ON fiyat_kayitlari FOR DELETE
  TO anon, authenticated USING (true);
