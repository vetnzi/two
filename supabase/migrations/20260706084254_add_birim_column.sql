/*
# Add birim (unit) column to fiyat_kayitlari

1. Modified Tables
- `fiyat_kayitlari`
  - Added `birim` (text, nullable) — unit of the product: "adet", "kg", "100 gr", "paket", "dilim", etc.
  - Added `guven_skoru` (text, nullable) — confidence score: "yuksek", "guvenli", "zayif", "kritik"
  - Added `fiyat_norm` (numeric(12,2), nullable) — normalized price per kg/adet for comparison

2. Notes
- birim is nullable so existing records without unit info still work
- fiyat_norm stores a normalized price (e.g. price per kg) for cross-source comparison
- guven_skoru is set by the edge function based on data quality heuristics
*/

ALTER TABLE fiyat_kayitlari
  ADD COLUMN IF NOT EXISTS birim text,
  ADD COLUMN IF NOT EXISTS guven_skoru text,
  ADD COLUMN IF NOT EXISTS fiyat_norm numeric(12,2);

CREATE INDEX IF NOT EXISTS idx_fiyat_birim ON fiyat_kayitlari (birim);
