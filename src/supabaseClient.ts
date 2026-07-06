import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

export interface FiyatKaydi {
  id: string;
  isletme: string;
  kaynak_turu: string;
  urun: string;
  cekilen_isim: string;
  fiyat: number;
  birim: string | null;
  fiyat_norm: number | null;
  guven_skoru: string | null;
  kaynak_url: string;
  cekilme_tarihi: string;
}

export const URUNLER = [
  "Simit",
  "Poğaça",
  "Açma",
  "Yaş Pasta",
  "Baklava",
  "Su Böreği",
] as const;

export type UrunTipi = (typeof URUNLER)[number];
