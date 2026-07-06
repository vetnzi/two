import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

// ─── Product matching ───

const URUN_ES_ANLAMLI: Record<string, string[]> = {
  "Simit": ["simit", "tereyağlı simit", "sütlü simit", "pastane simidi", "ankara simidi", "kandil simidi", "çikolatalı simit", "susamlı simit"],
  "Poğaça": ["poğaça", "pogaca", "peynirli poğaça", "kaşarlı poğaça", "sade poğaça", "patatesli poğaça", "dereotlu poğaça", "sosisli poğaça", "haşhaşlı poğaça", "talaş poğaça", "kıymalı poğaça", "sucuklu poğaça", "zeytinli poğaça"],
  "Açma": ["açma", "acma", "sade açma", "zeytinli açma", "çikolatalı açma", "haşhaşlı açma", "sosisli açma"],
  "Yaş Pasta": ["yaş pasta", "pasta", "çikolatalı pasta", "meyveli pasta", "karaorman", "blackforest", "mozaik pasta", "rulo pasta", "ekler pasta", "tane pasta", "pasta dilimi", "pasta slice"],
  "Baklava": ["baklava", "fıstıklı baklava", "cevizli baklava", "kuru baklava", "şöbiyet", "burma", "sarı burma", "bulgur baklava", "havuç dilimi", "baklava dilimi", "sarıburma"],
  "Su Böreği": ["su böreği", "su boregi", "peynirli su böreği", "ıspanaklı su böreği", "tepsi su böreği", "tepsili su böreği", "su borek", "taze su böreği"],
};

const HARIC_KELIMELER = ["kuru pasta", "kuru kek", "pasta tarifi", "pasta yapımı", "pasta kalıbı", "böreklik", "börekçi", "pasta tozu", "pasta kreması", "kek", "kurabiye", "sufle", "tiramisu", "sütlaç", "kazandibi", "puding", "muhallebi", "revani", "lokma", "tulumba", "künefe", "ekler", "cookie", "brownie", "macaron", "donut", "muffin", "cupcake"];

function urunEslestir(isim: string): string | null {
  const lower = isim.toLowerCase();
  for (const haric of HARIC_KELIMELER) {
    if (lower.includes(haric)) return null;
  }
  for (const [anaUrun, esAnlamlar] of Object.entries(URUN_ES_ANLAMLI)) {
    for (const kelime of esAnlamlar) {
      if (lower.includes(kelime.toLowerCase())) return anaUrun;
    }
  }
  return null;
}

// ─── Unit detection ───

function birimTespit(metin: string): string {
  const lower = metin.toLowerCase();
  if (/(\d+)\s*(kg|kilo|kilogram)/.test(lower)) return "kg";
  if (/(\d+)\s*(gr|g|gram)\b/.test(lower)) {
    const m = lower.match(/(\d+)\s*(gr|g|gram)\b/);
    if (m) return `${m[1]} gr`;
    return "gr";
  }
  if (/(\d+)\s*adet/.test(lower)) {
    const m = lower.match(/(\d+)\s*adet/);
    if (m) return `${m[1]} adet`;
    return "adet";
  }
  if (/(\d+)\s*(li|lu|lu paket|li paket)/.test(lower)) return "paket";
  if (/paket/.test(lower)) return "paket";
  if (/dilim/.test(lower)) return "dilim";
  if (/tepsi/.test(lower)) return "tepsi";
  if (/(\d+)\s*parça/.test(lower)) {
    const m = lower.match(/(\d+)\s*parça/);
    if (m) return `${m[1]} parça`;
    return "parça";
  }
  if (/(\d+)\s*(adet|tane|pcs)/.test(lower)) return "adet";
  return "adet";
}

function fiyatNormalize(fiyat: number, birim: string): number {
  if (birim === "kg") return fiyat;
  if (birim.endsWith(" gr")) {
    const gr = parseInt(birim);
    if (gr > 0) return (fiyat / gr) * 1000;
  }
  if (birim === "100 gr") return fiyat * 10;
  if (birim === "adet" || birim.endsWith(" adet") || birim.endsWith(" parça")) return fiyat;
  return fiyat;
}

// ─── Price cleaning ───

function fiyatTemizle(metin: string): number {
  if (!metin) return 0;
  let m = metin.toUpperCase().replace("TL", "").replace("₺", "").replace("KDV", "").trim();
  m = m.replace("DAHİL", "").replace("HARİÇ", "").trim();
  if (m.includes(",") && m.includes(".")) m = m.replace(/\./g, "");
  m = m.replace(",", ".");
  const sayilar = m.match(/[-+]?\d*\.?\d+/g);
  if (sayilar && sayilar.length > 0) {
    const val = parseFloat(sayilar[sayilar.length - 1]);
    return isNaN(val) ? 0 : val;
  }
  return 0;
}

function fiyatIlkBul(metin: string): number {
  if (!metin) return 0;
  let m = metin.toUpperCase().replace("TL", "").replace("₺", "").replace("KDV", "").trim();
  m = m.replace("DAHİL", "").replace("HARİÇ", "").trim();
  if (m.includes(",") && m.includes(".")) m = m.replace(/\./g, "");
  m = m.replace(",", ".");
  const sayilar = m.match(/[-+]?\d*\.?\d+/g);
  if (sayilar && sayilar.length > 0) {
    const val = parseFloat(sayilar[0]);
    return isNaN(val) ? 0 : val;
  }
  return 0;
}

// ─── Name cleaning ───

const GECERSIZ_KELIMELER = new Set([
  "sepete", "ekle", "favorilere", "favori", "incele", "azalt", "artır",
  "stokta", "tükendi", "yeni", "indirim", "kampanya", "kdv", "dahil",
  "haric", "kargo", "teslimat", "sepette", "kupon", "puan",
  "degerlendirme", "yildiz", "★", "az", "cok", "satan", "240derece",
  "ürünü", "adet", "sepet", "eklendi", "tıkla", "devam", "öde",
  "göster", "gizle", "yorum", "yorumlar", "tümü", "tumu", "filtre",
  "sırala", "sıralama", "kategori", "menü", "ara", "search",
]);

function isimTemizle(metin: string): string {
  let m = metin.replace(/\s+/g, " ").trim();
  m = m.replace(/[\d.,]+\s*[₺TL].*$/i, "").trim();
  m = m.replace(/\(\s*\)/g, "").trim();
  const kelimeler = m.split(" ");
  const temiz = kelimeler.filter(k => !GECERSIZ_KELIMELER.has(k.toLowerCase()));
  const result = temiz.join(" ").replace(/^[-,|•·\s]+|[-,|•·\s]+$/g, "").trim();
  return result || m;
}

// ─── Confidence scoring ───

function guvenSkoruHesapla(fiyat: number, urun: string, birim: string, kaynakTuru: string): string {
  let skor = 0;
  if (kaynakTuru === "Esnaf Odası") skor += 3;
  else if (kaynakTuru === "Pastane") skor += 1;
  if (birim && birim !== "adet") skor += 1;
  if (fiyat > 0) {
    const beklenenAraliklar: Record<string, [number, number]> = {
      "Simit": [5, 50],
      "Poğaça": [5, 50],
      "Açma": [5, 50],
      "Yaş Pasta": [200, 8000],
      "Baklava": [200, 5000],
      "Su Böreği": [200, 4000],
    };
    const aralik = beklenenAraliklar[urun];
    if (aralik && fiyat >= aralik[0] && fiyat <= aralik[1]) skor += 2;
    else if (aralik) skor -= 1;
  }
  if (skor >= 4) return "yuksek";
  if (skor >= 2) return "guvenli";
  if (skor >= 0) return "zayif";
  return "kritik";
}

// ─── Sources (80+ sources, 3x expansion) ───

interface Kaynak {
  isletme: string;
  tur: "esnaf_odasi_tablo" | "esnaf_odasi_pdf" | "pastane" | "pastane_json";
  url: string;
  kategori?: string;
}

const KAYNAKLAR: Kaynak[] = [
  // Esnaf / Ticaret Odaları
  { isletme: "İnegöl TSO", tur: "esnaf_odasi_tablo", url: "https://www.itso.org.tr/simit-acma-pogaca-vb" },
  { isletme: "Kütahya TSO", tur: "esnaf_odasi_pdf", url: "https://www.kutso.org.tr/kutso-storage/page/49/qAGrYJTPQnGFuKpNU9rfgSiZl7KSUZbPCjiQs1KX.pdf" },
  { isletme: "Ankara TSO", tur: "esnaf_odasi_pdf", url: "https://www.atonet.org.tr/Uploads/Birimler/Internet/Hizmetlerimiz/Azami%20Fiyat%20Tarifeleri/2025_azami_fiyat_tarifesi/2025_pasta_cikolata_tatlicilar.pdf" },

  // Pastane e-ticaret siteleri
  { isletme: "Tarihi Karaköy Fırını", tur: "pastane", url: "https://www.tarihikarakoyfirini.com.tr/pogaca--simit--acma" },
  { isletme: "Tarihi Karaköy Fırını (Baklava)", tur: "pastane", url: "https://www.tarihikarakoyfirini.com.tr/baklavalar-13" },
  { isletme: "Tarihi Karaköy Fırını (Börek)", tur: "pastane", url: "https://www.tarihikarakoyfirini.com.tr/borekler-karakoy-" },
  { isletme: "Karaköy Güllüoğlu", tur: "pastane", url: "https://www.karakoygulluoglu.com/baklavalar" },
  { isletme: "Hafız Mustafa 1864", tur: "pastane", url: "https://online.hafizmustafa.com/baklava" },
  { isletme: "Saray Muhallebicisi (Börek)", tur: "pastane", url: "https://online.saraymuhallebicisi.com/borekler" },
  { isletme: "Saray Muhallebicisi (Tatlı)", tur: "pastane", url: "https://online.saraymuhallebicisi.com/hamurlu-tatlilar" },
  { isletme: "Divan Pastaneleri", tur: "pastane", url: "https://www.divanpastaneleri.com.tr/pasta" },
  { isletme: "Divan Pastaneleri (Tatlı)", tur: "pastane", url: "https://www.divanpastaneleri.com.tr/tatli-tuzlu" },
  { isletme: "Özsüt", tur: "pastane", url: "https://www.ozsut.com.tr" },
  { isletme: "Liva Pastacılık", tur: "pastane", url: "https://www.livapastacilik.com" },
  { isletme: "Zahire Pastanesi", tur: "pastane", url: "https://www.zahirepastanesi.com" },
  { isletme: "Linaria", tur: "pastane", url: "https://www.linaria.com.tr" },
  { isletme: "Pastannecim", tur: "pastane", url: "https://www.pastannecim.com.tr" },
  { isletme: "Ankara Pasta", tur: "pastane", url: "https://www.ankarapasta.com" },
  { isletme: "Misbaşak", tur: "pastane", url: "https://www.misbasakonline.com" },
  { isletme: "Şireli Baklava", tur: "pastane", url: "https://sirelibaklava.com.tr/products/su-boregi" },
  { isletme: "Sini Börek", tur: "pastane", url: "https://siniborek.com.tr" },
  { isletme: "Çelebioğulları", tur: "pastane", url: "https://www.celebiogullari.com.tr/su-boregi-1-kg-paket" },
  { isletme: "Cumba Baklava", tur: "pastane", url: "https://cumbabaklava.com/su-boregi" },
  { isletme: "TazeMasa", tur: "pastane", url: "https://www.tazemasa.com/simit-pogaca-322" },
  { isletme: "Özgür Unlu Mamulleri", tur: "pastane", url: "https://ozgurunlumamulleri.com/simit-pogaca-cesitleri" },
  { isletme: "Tepsi Börek", tur: "pastane", url: "https://www.tepsiborek.com.tr" },
  { isletme: "Faruk Güllü", tur: "pastane", url: "https://www.farukgullu.com.tr" },

  // ─── NEW: 50+ additional sources (3x expansion) ───

  // Baklava specialists
  { isletme: "Karaköy Güllüoğlu (Pasta)", tur: "pastane", url: "https://www.karakoygulluoglu.com/pastalar" },
  { isletme: "Hafız Mustafa (Pasta)", tur: "pastane", url: "https://online.hafizmustafa.com/pasta" },
  { isletme: "Hafız Mustafa (Börek)", tur: "pastane", url: "https://online.hafizmustafa.com/borek" },
  { isletme: "Baklava Dilim", tur: "pastane", url: "https://www.baklavadilim.com" },
  { isletme: "Güllüoğlu Baklava", tur: "pastane", url: "https://www.gulluoglu.com" },
  { isletme: "Antep Baklava", tur: "pastane", url: "https://www.antepbaklava.com.tr" },
  { isletme: "Baklava House", tur: "pastane", url: "https://www.baklavahouse.com.tr" },
  { isletme: "Köşkeroğlu Baklava", tur: "pastane", url: "https://www.koskeroglu.com.tr" },
  { isletme: "Halil Baklava", tur: "pastane", url: "https://www.halilbaklava.com" },
  { isletme: "Sait Baklava", tur: "pastane", url: "https://www.saitbaklava.com" },
  { isletme: "Baklavacı Güllü", tur: "pastane", url: "https://www.baklavacigullu.com" },

  // Pasta & cake specialists
  { isletme: "Divan (Pasta Dilimi)", tur: "pastane", url: "https://www.divanpastaneleri.com.tr/pasta-dilimi" },
  { isletme: "Özsüt (Pasta)", tur: "pastane", url: "https://www.ozsut.com.tr/pasta" },
  { isletme: "Özsüt (Baklava)", tur: "pastane", url: "https://www.ozsut.com.tr/baklava" },
  { isletme: "Pastane 2000", tur: "pastane", url: "https://www.pastane2000.com" },
  { isletme: "İstanbul Pasta", tur: "pastane", url: "https://www.istanbulpasta.com" },
  { isletme: "Pasta Sepeti", tur: "pastane", url: "https://www.pastasepeti.com" },
  { isletme: "Mavi Pastane", tur: "pastane", url: "https://www.mavipastane.com" },
  { isletme: "Pasta Durağı", tur: "pastane", url: "https://www.pastaduragi.com" },
  { isletme: "Erdem Pastanesi", tur: "pastane", url: "https://www.erdempastanesi.com" },
  { isletme: "Banabaklava", tur: "pastane", url: "https://www.banabaklava.com" },
  { isletme: "Pasta Keyfi", tur: "pastane", url: "https://www.pastakeyfi.com" },
  { isletme: "Sütiş", tur: "pastane", url: "https://www.sutis.com.tr" },
  { isletme: "Saray Muhallebicisi (Pasta)", tur: "pastane", url: "https://online.saraymuhallebicisi.com/pasta" },

  // Börek specialists
  { isletme: "Tepsi Börek (Su Böreği)", tur: "pastane", url: "https://www.tepsiborek.com.tr/su-boregi" },
  { isletme: "Börekçi Tevfik", tur: "pastane", url: "https://www.borekcitevfik.com" },
  { isletme: "Üsküdar Börekçisi", tur: "pastane", url: "https://www.uskudarborekcisi.com" },
  { isletme: "Börekçilik", tur: "pastane", url: "https://www.borekcilik.com" },
  { isletme: "Sarıyer Börekçisi", tur: "pastane", url: "https://www.sariyerborekcisi.com" },
  { isletme: "Börek Evi", tur: "pastane", url: "https://www.borekevi.com.tr" },
  { isletme: "Kadıköy Börekçisi", tur: "pastane", url: "https://www.kadikoyborekcisi.com" },

  // Simit & unlu mamul
  { isletme: "Simit Sarayı", tur: "pastane", url: "https://www.simitsarayi.com.tr" },
  { isletme: "Simitçi", tur: "pastane", url: "https://www.simitci.com.tr" },
  { isletme: "TazeMasa (Pasta)", tur: "pastane", url: "https://www.tazemasa.com/pasta-323" },
  { isletme: "TazeMasa (Börek)", tur: "pastane", url: "https://www.tazemasa.com/borek-324" },
  { isletme: "Unlu Mamul", tur: "pastane", url: "https://www.unlumamul.com.tr" },
  { isletme: "Fırın Express", tur: "pastane", url: "https://www.firinexpress.com" },

  // Online food delivery platforms (JSON API attempts)
  { isletme: "Tarihi Karaköy Fırını (Pasta)", tur: "pastane", url: "https://www.tarihikarakoyfirini.com.tr/pastalar-12" },
  { isletme: "Tarihi Karaköy Fırını (Su Böreği)", tur: "pastane", url: "https://www.tarihikarakoyfirini.com.tr/su-boregi" },
  { isletme: "Karaköy Güllüoğlu (Şöbiyet)", tur: "pastane", url: "https://www.karakoygulluoglu.com/sobiyet" },
  { isletme: "Karaköy Güllüoğlu (Burma)", tur: "pastane", url: "https://www.karakoygulluoglu.com/sarali-burma-baklava" },
  { isletme: "Hafız Mustafa (Şöbiyet)", tur: "pastane", url: "https://online.hafizmustafa.com/sobiyet" },
  { isletme: "Hafız Mustafa (Burma)", tur: "pastane", url: "https://online.hafizmustafa.com/burma" },
  { isletme: "Saray Muhallebicisi (Su Böreği)", tur: "pastane", url: "https://online.saraymuhallebicisi.com/su-boregi" },
  { isletme: "Saray Muhallebicisi (Baklava)", tur: "pastane", url: "https://online.saraymuhallebicisi.com/baklava" },
  { isletme: "Divan (Baklava)", tur: "pastane", url: "https://www.divanpastaneleri.com.tr/baklava" },
  { isletme: "Divan (Börek)", tur: "pastane", url: "https://www.divanpastaneleri.com.tr/borek" },
  { isletme: "Özsüt (Börek)", tur: "pastane", url: "https://www.ozsut.com.tr/borek" },
  { isletme: "Liva (Baklava)", tur: "pastane", url: "https://www.livapastacilik.com/baklava" },
  { isletme: "Liva (Su Böreği)", tur: "pastane", url: "https://www.livapastacilik.com/su-boregi" },
  { isletme: "Liva (Pasta)", tur: "pastane", url: "https://www.livapastacilik.com/pasta" },
  { isletme: "Misbaşak (Baklava)", tur: "pastane", url: "https://www.misbasakonline.com/baklava" },
  { isletme: "Misbaşak (Pasta)", tur: "pastane", url: "https://www.misbasakonline.com/pasta" },
  { isletme: "Şireli (Baklava)", tur: "pastane", url: "https://sirelibaklava.com.tr/products/baklava" },
  { isletme: "Sini Börek (Baklava)", tur: "pastane", url: "https://siniborek.com.tr/baklava" },
  { isletme: "Cumba (Baklava)", tur: "pastane", url: "https://cumbabaklava.com/baklava" },
  { isletme: "Tepsi Börek (Baklava)", tur: "pastane", url: "https://www.tepsiborek.com.tr/baklava" },
  { isletme: "Faruk Güllü (Pasta)", tur: "pastane", url: "https://www.farukgullu.com.tr/pasta" },
  { isletme: "Faruk Güllü (Börek)", tur: "pastane", url: "https://www.farukgullu.com.tr/borek" },
  { isletme: "Ankara Pasta (Baklava)", tur: "pastane", url: "https://www.ankarapasta.com/baklava" },
  { isletme: "Ankara Pasta (Börek)", tur: "pastane", url: "https://www.ankarapasta.com/borek" },
  { isletme: "Pastannecim (Baklava)", tur: "pastane", url: "https://www.pastannecim.com.tr/baklava" },
  { isletme: "Pastannecim (Börek)", tur: "pastane", url: "https://www.pastannecim.com.tr/borek" },
  { isletme: "Zahire (Baklava)", tur: "pastane", url: "https://www.zahirepastanesi.com/baklava" },
  { isletme: "Zahire (Börek)", tur: "pastane", url: "https://www.zahirepastanesi.com/borek" },
  { isletme: "Linaria (Baklava)", tur: "pastane", url: "https://www.linaria.com.tr/baklava" },
  { isletme: "Linaria (Börek)", tur: "pastane", url: "https://www.linaria.com.tr/borek" },
  { isletme: "Çelebioğulları (Baklava)", tur: "pastane", url: "https://www.celebiogullari.com.tr/baklava" },
  { isletme: "Özgür (Börek)", tur: "pastane", url: "https://ozgurunlumamulleri.com/borek-cesitleri" },
  { isletme: "Özgür (Açma)", tur: "pastane", url: "https://ozgurunlumamulleri.com/acma-cesitleri" },
];

// ─── HTML Parsing ───

function parseHtmlTable(html: string, kaynakUrl: string, isletme: string): any[] {
  const sonuclar: any[] = [];
  const tabloRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
  let tabloMatch;
  while ((tabloMatch = tabloRegex.exec(html)) !== null) {
    const tabloIcerik = tabloMatch[1];
    const satirRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let satirMatch;
    while ((satirMatch = satirRegex.exec(tabloIcerik)) !== null) {
      const satir = satirMatch[1];
      const hucreRegex = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
      const hucreler: string[] = [];
      let hucreMatch;
      while ((hucreMatch = hucreRegex.exec(satir)) !== null) {
        hucreler.push(hucreMatch[1].replace(/<[^>]*>/g, "").trim());
      }
      if (hucreler.length >= 3) {
        const isim = hucreler[0];
        const gramaj = hucreler[1] || "";
        const fiyatMetni = hucreler[hucreler.length - 1];
        if (isim && fiyatMetni && (fiyatMetni.includes("TL") || fiyatMetni.includes("₺") || /\d/.test(fiyatMetni))) {
          const urun = urunEslestir(isim);
          if (urun) {
            const fiyat = fiyatTemizle(fiyatMetni);
            if (fiyat > 0) {
              const birim = birimTespit(`${isim} ${gramaj}`);
              const fiyatNorm = fiyatNormalize(fiyat, birim);
              const guven = guvenSkoruHesapla(fiyat, urun, birim, "Esnaf Odası");
              sonuclar.push({
                isletme,
                kaynak_turu: "Esnaf Odası",
                urun,
                cekilen_isim: gramaj ? `${isim} (${gramaj})` : isim,
                fiyat,
                birim,
                fiyat_norm: fiyatNorm,
                guven_skoru: guven,
                kaynak_url: kaynakUrl,
                cekilme_tarihi: new Date().toISOString(),
              });
            }
          }
        }
      }
    }
  }
  return sonuclar;
}

function parsePdfText(text: string, kaynakUrl: string, isletme: string): any[] {
  const sonuclar: any[] = [];
  const satirlar = text.split("\n");
  for (const satir of satirlar) {
    const trimmed = satir.trim();
    if (trimmed.length < 3) continue;
    // Try multiple regex patterns for PDF text
    const patterns = [
      /([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+(?:\.\d+)?)\s+(\d+[.,]?\d*)\s*TL?/,
      /([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+₺\s*(\d+[.,]?\d*)/,
      /([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+[.,]?\d*)\s*₺/,
      /([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+[.,]?\d*)\s*TL/,
    ];
    for (const pattern of patterns) {
      const eslesme = trimmed.match(pattern);
      if (eslesme) {
        const isim = eslesme[1].trim();
        const fiyatStr = eslesme[eslesme.length - 1];
        const fiyat = fiyatTemizle(fiyatStr + " TL");
        if (fiyat > 0) {
          const urun = urunEslestir(isim);
          if (urun) {
            const birim = birimTespit(isim);
            const fiyatNorm = fiyatNormalize(fiyat, birim);
            const guven = guvenSkoruHesapla(fiyat, urun, birim, "Esnaf Odası");
            sonuclar.push({
              isletme,
              kaynak_turu: "Esnaf Odası",
              urun,
              cekilen_isim: isim,
              fiyat,
              birim,
              fiyat_norm: fiyatNorm,
              guven_skoru: guven,
              kaynak_url: kaynakUrl,
              cekilme_tarihi: new Date().toISOString(),
            });
          }
        }
        break;
      }
    }
  }
  return sonuclar;
}

function parseGenericPastane(html: string, kaynakUrl: string, isletme: string): any[] {
  const sonuclar: any[] = [];
  const gorulen = new Set<string>();

  // Strategy 1: Look for product cards with price (common e-commerce pattern)
  // Match elements containing both a product name keyword and a price
  const etiketRegex = /<(?:div|li|article|span|a|h2|h3|h4|p)[^>]*>([\s\S]*?)<\/(?:div|li|article|span|a|h2|h3|h4|p)>/gi;
  let match;
  while ((match = etiketRegex.exec(html)) !== null) {
    const hamMetin = match[1].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    if (!hamMetin || hamMetin.length > 250 || hamMetin.length < 5) continue;
    if (!hamMetin.includes("₺") && !hamMetin.includes("TL") && !hamMetin.includes("tl")) continue;

    // Try to find price - prefer the LAST price (discounted/active price)
    const fiyatEslesme = hamMetin.match(/(\d{2,}(?:[.,]\d{1,2})?|\d{1,3}(?:\.\d{3})+[.,]\d{1,2})\s*[₺TLtl]/);
    if (!fiyatEslesme) continue;
    const fiyat = fiyatTemizle(fiyatEslesme[1] + " ₺");
    if (fiyat < 5) continue;

    const urun = urunEslestir(hamMetin);
    if (!urun) continue;

    const temizIsim = isimTemizle(hamMetin);
    if (!temizIsim || temizIsim.length < 3) continue;

    const birim = birimTespit(hamMetin);
    const fiyatNorm = fiyatNormalize(fiyat, birim);
    const guven = guvenSkoruHesapla(fiyat, urun, birim, "Pastane");

    const anahtar = `${isletme}|${urun}|${temizIsim}|${fiyat}`;
    if (gorulen.has(anahtar)) continue;
    gorulen.add(anahtar);

    sonuclar.push({
      isletme,
      kaynak_turu: "Pastane",
      urun,
      cekilen_isim: temizIsim,
      fiyat,
      birim,
      fiyat_norm: fiyatNorm,
      guven_skoru: guven,
      kaynak_url: kaynakUrl,
      cekilme_tarihi: new Date().toISOString(),
    });
  }

  // Strategy 2: Look for JSON-LD structured data
  const jsonLdRegex = /<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi;
  let jsonMatch;
  while ((jsonMatch = jsonLdRegex.exec(html)) !== null) {
    try {
      const jsonStr = jsonMatch[1].trim();
      const data = JSON.parse(jsonStr);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item["@type"] === "Product" || item.offers) {
          const isim = item.name || "";
          const offers = item.offers;
          const offerList = Array.isArray(offers) ? offers : [offers];
          for (const offer of offerList) {
            const fiyatStr = offer.price || "";
            const fiyat = parseFloat(fiyatStr);
            if (fiyat > 0 && isim) {
              const urun = urunEslestir(isim);
              if (urun) {
                const birim = birimTespit(isim);
                const fiyatNorm = fiyatNormalize(fiyat, birim);
                const guven = guvenSkoruHesapla(fiyat, urun, birim, "Pastane");
                const anahtar = `${isletme}|${urun}|${isim}|${fiyat}`;
                if (!gorulen.has(anahtar)) {
                  gorulen.add(anahtar);
                  sonuclar.push({
                    isletme,
                    kaynak_turu: "Pastane",
                    urun,
                    cekilen_isim: isim,
                    fiyat,
                    birim,
                    fiyat_norm: fiyatNorm,
                    guven_skoru: guven,
                    kaynak_url: kaynakUrl,
                    cekilme_tarihi: new Date().toISOString(),
                  });
                }
              }
            }
          }
        }
      }
    } catch {
      // Invalid JSON, skip
    }
  }

  // Strategy 3: Look for data-price attributes
  const dataPriceRegex = /data-price="(\d+(?:[.,]\d{1,2})?)"[^>]*data-name="([^"]+)"/gi;
  let dpMatch;
  while ((dpMatch = dataPriceRegex.exec(html)) !== null) {
    const fiyat = fiyatTemizle(dpMatch[1] + " ₺");
    const isim = dpMatch[2];
    if (fiyat > 0 && isim) {
      const urun = urunEslestir(isim);
      if (urun) {
        const birim = birimTespit(isim);
        const fiyatNorm = fiyatNormalize(fiyat, birim);
        const guven = guvenSkoruHesapla(fiyat, urun, birim, "Pastane");
        const anahtar = `${isletme}|${urun}|${isim}|${fiyat}`;
        if (!gorulen.has(anahtar)) {
          gorulen.add(anahtar);
          sonuclar.push({
            isletme,
            kaynak_turu: "Pastane",
            urun,
            cekilen_isim: isim,
            fiyat,
            birim,
            fiyat_norm: fiyatNorm,
            guven_skoru: guven,
            kaynak_url: kaynakUrl,
            cekilme_tarihi: new Date().toISOString(),
          });
        }
      }
    }
  }

  return sonuclar;
}

// ─── PDF text extraction (improved) ───

async function extractPdfText(buffer: ArrayBuffer): Promise<string> {
  try {
    const decoder = new TextDecoder("utf-8");
    const bytes = new Uint8Array(buffer);
    let text = "";

    // Method 1: Extract text from PDF stream objects (BT...ET blocks)
    let i = 0;
    while (i < bytes.length - 1) {
      // Look for "BT" (Begin Text) marker
      if (bytes[i] === 0x42 && bytes[i + 1] === 0x54) {
        // Find "ET" (End Text)
        let end = i + 2;
        while (end < bytes.length - 1) {
          if (bytes[end] === 0x45 && bytes[end + 1] === 0x54) break;
          end++;
        }
        if (end < bytes.length) {
          const chunk = decoder.decode(bytes.slice(i + 2, end));
          // Extract text from Tj and TJ operators
          const tjMatches = chunk.match(/\(([^)]*)\)\s*Tj/g);
          if (tjMatches) {
            for (const tj of tjMatches) {
              const t = tj.match(/\(([^)]*)\)/);
              if (t) text += t[1] + " ";
            }
          }
          // Also try array form: [(text1) -25 (text2)] TJ
          const tjArrayMatches = chunk.match(/\[([^\]]*)\]\s*TJ/g);
          if (tjArrayMatches) {
            for (const tj of tjArrayMatches) {
              const parts = tj.match(/\(([^)]*)\)/g);
              if (parts) {
                for (const p of parts) {
                  text += p.slice(1, -1) + " ";
                }
              }
            }
          }
          text += "\n";
          i = end + 2;
        } else {
          i += 2;
        }
      } else {
        i++;
      }
    }

    // Method 2: Fallback - extract all readable text between parentheses
    if (!text.trim()) {
      const fullText = decoder.decode(buffer);
      const parenMatches = fullText.match(/\(([^)]{2,})\)/g);
      if (parenMatches) {
        for (const m of parenMatches) {
          const inner = m.slice(1, -1);
          // Only keep if it contains letters
          if (/[a-zA-ZÇĞİÖŞÜçğıöşü]/.test(inner)) {
            text += inner + "\n";
          }
        }
      }
    }

    // Method 3: Last resort - raw decode and filter
    if (!text.trim()) {
      text = decoder.decode(buffer).replace(/[^\x20-\x7EÇĞİÖŞÜçğıöşü\n]/g, " ");
    }

    return text;
  } catch {
    return "";
  }
}

// ─── Fetch with retry ───

async function fetchWithRetry(url: string, maxRetries = 2, timeoutMs = 12000): Promise<Response | null> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const r = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
          "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        signal: controller.signal,
        redirect: "follow",
      });
      clearTimeout(timeout);
      if (r.ok) return r;
      if (r.status === 403 || r.status === 429) {
        // Rate limited or blocked, wait before retry
        if (attempt < maxRetries) await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }
      return null;
    } catch {
      if (attempt < maxRetries) {
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)));
        continue;
      }
      return null;
    }
  }
  return null;
}

// ─── Parallel batch processing ───

async function processBatch(kaynaklar: Kaynak[], batchSize: number): Promise<{ veriler: any[]; basarili: number; basarisiz: number; detaylar: any[] }> {
  const tumVeriler: any[] = [];
  let basarili = 0;
  let basarisiz = 0;
  const detaylar: any[] = [];

  for (let i = 0; i < kaynaklar.length; i += batchSize) {
    const batch = kaynaklar.slice(i, i + batchSize);
    const results = await Promise.allSettled(
      batch.map(async (kaynak) => {
        try {
          const response = await fetchWithRetry(kaynak.url);
          if (!response) return { kaynak, sonuclar: [], ok: false };

          let sonuclar: any[] = [];
          if (kaynak.tur === "esnaf_odasi_tablo") {
            const html = await response.text();
            sonuclar = parseHtmlTable(html, kaynak.url, kaynak.isletme);
          } else if (kaynak.tur === "esnaf_odasi_pdf") {
            const pdfBuffer = await response.arrayBuffer();
            const pdfText = await extractPdfText(pdfBuffer);
            sonuclar = parsePdfText(pdfText, kaynak.url, kaynak.isletme);
          } else {
            const html = await response.text();
            sonuclar = parseGenericPastane(html, kaynak.url, kaynak.isletme);
          }

          return { kaynak, sonuclar, ok: sonuclar.length > 0 };
        } catch {
          return { kaynak, sonuclar: [], ok: false };
        }
      })
    );

    for (const result of results) {
      if (result.status === "fulfilled") {
        const { kaynak, sonuclar, ok } = result.value;
        if (ok && sonuclar.length > 0) {
          tumVeriler.push(...sonuclar);
          basarili++;
          detaylar.push({ isletme: kaynak.isletme, kayit: sonuclar.length, durum: "basarili" });
        } else {
          basarisiz++;
          detaylar.push({ isletme: kaynak.isletme, kayit: 0, durum: "basarisiz" });
        }
      } else {
        basarisiz++;
        detaylar.push({ isletme: batch[results.indexOf(result)]?.isletme || "?", kayit: 0, durum: "hata" });
      }
    }
  }

  return { veriler: tumVeriler, basarili, basarisiz, detaylar };
}

// ─── Main handler ───

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

    // Process all sources in parallel batches of 8
    const { veriler: tumVeriler, basarili, basarisiz, detaylar } = await processBatch(KAYNAKLAR, 8);

    // Dedup: remove entries with same isletme + urun + cekilen_isim + fiyat from this batch
    const gorulen = new Set<string>();
    const temizVeriler = tumVeriler.filter((v) => {
      const anahtar = `${v.isletme}|${v.urun}|${v.cekilen_isim}|${v.fiyat}`;
      if (gorulen.has(anahtar)) return false;
      gorulen.add(anahtar);
      return true;
    });

    // Batch insert in chunks of 500 (Supabase limit)
    let eklenen = 0;
    for (let i = 0; i < temizVeriler.length; i += 500) {
      const chunk = temizVeriler.slice(i, i + 500);
      const { error } = await supabase.from("fiyat_kayitlari").insert(chunk);
      if (!error) eklenen += chunk.length;
    }

    return new Response(
      JSON.stringify({
        success: true,
        toplam_kayit: temizVeriler.length,
        basarili_kaynak: basarili,
        basarisiz_kaynak: basarisiz,
        eklenen,
        kaynak_sayisi: KAYNAKLAR.length,
        detaylar: detaylar.filter((d) => d.durum === "basarili"),
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return new Response(
      JSON.stringify({ success: false, error: msg }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
