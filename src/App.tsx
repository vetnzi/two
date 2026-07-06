import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, Cell,
} from "recharts";
import { supabase, FiyatKaydi, URUNLER, UrunTipi } from "./supabaseClient";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

interface ScrapeResult {
  success: boolean;
  toplam_kayit: number;
  basarili_kaynak: number;
  basarisiz_kaynak: number;
  eklenen: number;
  kaynak_sayisi: number;
  detaylar: { isletme: string; kayit: number; durum: string }[];
  error?: string;
}

interface TrendData {
  min: number;
  max: number;
  ortalama: number;
  medyan: number;
  ilk_fiyat: number;
  son_fiyat: number;
  degisim_yuzdesi: number;
  kayit_sayisi: number;
  tarih_araligi: string;
}

interface AnalizSatiri extends FiyatKaydi {
  Durum: string;
  GuvenSkoru: string;
}

function anomaliVeGuvenAnalizi(veriler: FiyatKaydi[], seciliUrun: string): AnalizSatiri[] {
  const urunVerisi = veriler.filter((v) => v.urun === seciliUrun && v.fiyat > 0);
  if (urunVerisi.length === 0) return [];

  const fiyatlar = urunVerisi.map((v) => v.fiyat);
  if (fiyatlar.length < 2) {
    return urunVerisi.map((v) => ({
      ...v,
      Durum: "Doğrulandı",
      GuvenSkoru: v.guven_skoru || "guvenli",
    }));
  }

  const sorted = [...fiyatlar].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length * 0.25)];
  const q3 = sorted[Math.floor(sorted.length * 0.75)];
  const iqr = q3 - q1;
  const altSinir = iqr > 0 ? q1 - 1.5 * iqr : q1 * 0.5;
  const ustSinir = iqr > 0 ? q3 + 1.5 * iqr : q3 * 1.5;
  const medyan = sorted[Math.floor(sorted.length / 2)];

  return urunVerisi.map((v) => {
    let durum = "Doğrulandı";
    let skor = v.guven_skoru || "guvenli";
    if (v.fiyat < altSinir || v.fiyat > ustSinir) {
      durum = "Sapma / Hatalı";
      skor = "kritik";
    } else {
      const sapmaOrani = medyan > 0 ? Math.abs(v.fiyat - medyan) / medyan : 0;
      if (sapmaOrani <= 0.1) skor = "yuksek";
      else if (sapmaOrani <= 0.25) skor = "guvenli";
      else skor = "zayif";
    }
    return { ...v, Durum: durum, GuvenSkoru: skor };
  });
}

function trendAnalizi(veriler: FiyatKaydi[]): TrendData | null {
  const gecerli = veriler.filter((v) => v.fiyat > 0);
  if (gecerli.length === 0) return null;

  const fiyatlar = gecerli.map((v) => v.fiyat);
  const sorted = [...fiyatlar].sort((a, b) => a - b);
  return {
    min: sorted[0],
    max: sorted[sorted.length - 1],
    ortalama: fiyatlar.reduce((a, b) => a + b, 0) / fiyatlar.length,
    medyan: sorted[Math.floor(sorted.length / 2)],
    ilk_fiyat: fiyatlar[0],
    son_fiyat: fiyatlar[fiyatlar.length - 1],
    degisim_yuzdesi:
      fiyatlar[0] > 0
        ? ((fiyatlar[fiyatlar.length - 1] - fiyatlar[0]) / fiyatlar[0]) * 100
        : 0,
    kayit_sayisi: fiyatlar.length,
    tarih_araligi: gecerli.length > 0
      ? `${gecerli[0].cekilme_tarihi.slice(0, 10)} - ${gecerli[gecerli.length - 1].cekilme_tarihi.slice(0, 10)}`
      : "",
  };
}

function guvenRengi(skor: string): string {
  switch (skor) {
    case "yuksek": return "#34d399";
    case "guvenli": return "#38bdf8";
    case "zayif": return "#fbbf24";
    case "kritik": return "#f87171";
    default: return "#94a3b8";
  }
}

function guvenEtiket(skor: string): string {
  switch (skor) {
    case "yuksek": return "Yuksek";
    case "guvenli": return "Guvenli";
    case "zayif": return "Zayif";
    case "kritik": return "Kritik";
    default: return skor;
  }
}

export default function App() {
  const [seciliUrun, setSeciliUrun] = useState<UrunTipi>("Simit");
  const [tumVeriler, setTumVeriler] = useState<FiyatKaydi[]>([]);
  const [gecmisVeriler, setGecmisVeriler] = useState<FiyatKaydi[]>([]);
  const [cekiliyor, setCekiliyor] = useState(false);
  const [trendModu, setTrendModu] = useState(false);
  const [gunSecimi, setGunSecimi] = useState("30");
  const [statusText, setStatusText] = useState("● Veritabani: Hazir\n● Kaynak: 80+ site/odalar\n● Filtre: IQR + Guven Skoru\n● Durum: Hazir");
  const [statusColor, setStatusColor] = useState("#34d399");
  const [progressText, setProgressText] = useState("");
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);

  const verileriYukle = useCallback(async () => {
    const { data, error } = await supabase
      .from("fiyat_kayitlari")
      .select("*")
      .order("cekilme_tarihi", { ascending: false })
      .limit(2000);
    if (!error && data) {
      setTumVeriler(data as FiyatKaydi[]);
    }
  }, []);

  useEffect(() => {
    verileriYukle();
  }, [verileriYukle]);

  const kaynaklariTara = async () => {
    if (cekiliyor) return;
    setCekiliyor(true);
    setTrendModu(false);
    setStatusText("● Veritabani: Baglandi\n● Kaynak: 80+ site/odalar\n● Filtre: IQR + Guven Skoru\n● Durum: Veri Cekiliyor...");
    setStatusColor("#fbbf24");
    setProgressText("Baslatiliyor... 80+ kaynak taraniyor");

    try {
      const apiUrl = `${SUPABASE_URL}/functions/v1/scrape-prices`;
      const r = await fetch(apiUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          "Content-Type": "application/json",
          apikey: SUPABASE_ANON_KEY,
        },
      });

      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const result: ScrapeResult = await r.json();
      setScrapeResult(result);

      if (result.success) {
        const detayOzet = result.detaylar
          .slice(0, 5)
          .map((d) => `  ${d.isletme}: ${d.kayit} kayit`)
          .join("\n");
        setStatusText(
          `● Cekilen: ${result.toplam_kayit} kayit\n● Basarili: ${result.basarili_kaynak} / Basarisiz: ${result.basarisiz_kaynak}\n● Eklenen: ${result.eklenen}\n● Durum: Tamamlandi`
        );
        setStatusColor("#34d399");
        setProgressText(
          `Tamamlandi!\n${result.basarili_kaynak} basarili kaynak\n${result.eklenen} kayit eklendi\n\nEn basarili kaynaklar:\n${detayOzet}`
        );
        await verileriYukle();
      } else {
        throw new Error(result.error || "Bilinmeyen hata");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusText(`● Durum: Hata\n● ${msg}`);
      setStatusColor("#f87171");
      setProgressText(`Hata: ${msg}`);
    } finally {
      setCekiliyor(false);
    }
  };

  const trendGoster = async () => {
    const gun = gunSecimi === "Tum" ? 999999 : parseInt(gunSecimi);
    const baslangic = new Date(Date.now() - gun * 86400000).toISOString();

    const { data, error } = await supabase
      .from("fiyat_kayitlari")
      .select("*")
      .eq("urun", seciliUrun)
      .gte("cekilme_tarihi", baslangic)
      .order("cekilme_tarihi", { ascending: true })
      .limit(5000);

    if (!error && data) {
      setGecmisVeriler(data as FiyatKaydi[]);
      setTrendModu(true);
    }
  };

  const analizVerisi = anomaliVeGuvenAnalizi(tumVeriler, seciliUrun);
  const dogrulanmis = analizVerisi.filter((a) => a.Durum === "Doğrulandı");
  const trend = trendModu ? trendAnalizi(gecmisVeriler) : null;

  const medyan = dogrulanmis.length > 0
    ? [...dogrulanmis].sort((a, b) => a.fiyat - b.fiyat)[Math.floor(dogrulanmis.length / 2)].fiyat
    : 0;
  const minFiyat = dogrulanmis.length > 0 ? Math.min(...dogrulanmis.map((d) => d.fiyat)) : 0;
  const maxFiyat = dogrulanmis.length > 0 ? Math.max(...dogrulanmis.map((d) => d.fiyat)) : 0;
  const isletmeSayisi = new Set(analizVerisi.map((a) => a.isletme)).size;
  const sonTarih = analizVerisi.length > 0 ? analizVerisi[0].cekilme_tarihi.slice(0, 16) : "-";

  const barData = analizVerisi
    .filter((a) => a.fiyat > 0)
    .map((a) => ({
      isletme: a.isletme.length > 15 ? a.isletme.slice(0, 13) + "..." : a.isletme,
      fiyat: a.fiyat,
      durum: a.Durum,
    }))
    .sort((a, b) => a.fiyat - b.fiyat);

  const trendChartData = trendModu && gecmisVeriler.length > 0
    ? (() => {
        const gunluk: Record<string, { mean: number; min: number; max: number; count: number }> = {};
        for (const v of gecmisVeriler) {
          if (v.fiyat <= 0) continue;
          const tarih = v.cekilme_tarihi.slice(0, 10);
          if (!gunluk[tarih]) gunluk[tarih] = { mean: 0, min: Infinity, max: 0, count: 0 };
          gunluk[tarih].mean += v.fiyat;
          gunluk[tarih].min = Math.min(gunluk[tarih].min, v.fiyat);
          gunluk[tarih].max = Math.max(gunluk[tarih].max, v.fiyat);
          gunluk[tarih].count++;
        }
        return Object.entries(gunluk)
          .map(([tarih, d]) => ({
            tarih,
            ortalama: parseFloat((d.mean / d.count).toFixed(2)),
            min: parseFloat(d.min.toFixed(2)),
            max: parseFloat(d.max.toFixed(2)),
          }))
          .sort((a, b) => a.tarih.localeCompare(b.tarih));
      })()
    : [];

  const degisimRengi = trend && trend.degisim_yuzdesi >= 0 ? "#34d399" : "#f87171";

  return (
    <div className="app">
      {/* ─── SIDEBAR ─── */}
      <div className="sidebar">
        <div className="sidebar-title">PIYASA ANALIZ PRO</div>
        <div className="sidebar-label">Gozlem Alani</div>
        <select
          className="select"
          value={seciliUrun}
          onChange={(e) => {
            setSeciliUrun(e.target.value as UrunTipi);
            setTrendModu(false);
          }}
        >
          {URUNLER.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>

        <button className="btn-primary" onClick={kaynaklariTara} disabled={cekiliyor}>
          {cekiliyor ? "Cekiliyor... Lutfen Bekleyin" : "Web Sitelerinden Canli Cek"}
        </button>

        <button className="btn-secondary" onClick={trendGoster} disabled={cekiliyor}>
          Gecmis Trend Analizi
        </button>

        <div>
          <div className="sidebar-label" style={{ marginBottom: "4px" }}>Trend Donemi (Gun)</div>
          <select
            className="select"
            value={gunSecimi}
            onChange={(e) => setGunSecimi(e.target.value)}
          >
            <option value="7">7 Gun</option>
            <option value="30">30 Gun</option>
            <option value="90">90 Gun</option>
            <option value="365">365 Gun</option>
            <option value="Tum">Tum Gecmis</option>
          </select>
        </div>

        <div className="status-box">
          <div className="status-text" style={{ color: statusColor }}>{statusText}</div>
        </div>

        <div className="status-box">
          <div className="progress-text">{progressText}</div>
        </div>

        {scrapeResult && scrapeResult.detaylar && scrapeResult.detaylar.length > 0 && (
          <div className="status-box">
            <div className="sidebar-label" style={{ marginBottom: "8px" }}>Basarili Kaynaklar</div>
            {scrapeResult.detaylar.map((d, i) => (
              <div key={i} style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "2px" }}>
                {d.isletme}: {d.kayit} kayit
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ─── MAIN PANEL ─── */}
      <div className="main">
        {/* Canli Fiyat Kartlari */}
        <div className="cards-row">
          <div className="card">
            <div className="card-label">PAZAR MEDYANI</div>
            <div className="card-value">{medyan > 0 ? `${medyan.toFixed(2)} TL` : "Veri Yok"}</div>
            <div className="card-sub">Dogrulanmis Pazar Fiyati</div>
          </div>
          <div className="card">
            <div className="card-label">GUVENLI FIYAT ARALIGI</div>
            <div className="card-value success">
              {minFiyat > 0 ? `${minFiyat.toFixed(1)} - ${maxFiyat.toFixed(1)} TL` : "Veri Yok"}
            </div>
            <div className="card-sub">Gercek Islem Bandi</div>
          </div>
          <div className="card">
            <div className="card-label">SON CEKIM ZAMANI</div>
            <div className="card-value neutral">{sonTarih}</div>
            <div className="card-sub">Veri Tabani Kaydi</div>
          </div>
          <div className="card">
            <div className="card-label">AKTIF KAYNAK</div>
            <div className="card-value warning">{isletmeSayisi > 0 ? isletmeSayisi : "-"}</div>
            <div className="card-sub">Basarili Site Sayisi</div>
          </div>
        </div>

        {/* Trend Kartlari */}
        <div className="cards-row">
          <div className="card">
            <div className="card-label">ORTALAMA FIYAT</div>
            <div className="card-value">
              {trend ? `${trend.ortalama.toFixed(2)} TL` : analizVerisi.length > 0
                ? `${(analizVerisi.reduce((a, b) => a + b.fiyat, 0) / analizVerisi.length).toFixed(2)} TL`
                : "-"}
            </div>
            <div className="card-sub">{trend ? "Secili Donem Ortalamasi" : "Anlik ortalama"}</div>
          </div>
          <div className="card">
            <div className="card-label">FIYAT DEGISIMI</div>
            <div className="card-value" style={{ color: trend ? degisimRengi : "#94a3b8" }}>
              {trend ? `${trend.degisim_yuzdesi >= 0 ? "+" : ""}${trend.degisim_yuzdesi.toFixed(1)}%` : "-"}
            </div>
            <div className="card-sub">{trend ? trend.tarih_araligi : "Trend icin butona tiklayin"}</div>
          </div>
          <div className="card">
            <div className="card-label">MIN - MAX</div>
            <div className="card-value warning">
              {trend ? `${trend.min.toFixed(0)} - ${trend.max.toFixed(0)} TL`
                : analizVerisi.length > 0
                ? `${Math.min(...analizVerisi.map(a => a.fiyat)).toFixed(0)} - ${Math.max(...analizVerisi.map(a => a.fiyat)).toFixed(0)} TL`
                : "-"}
            </div>
            <div className="card-sub">{trend ? "Donem En Dusuk/En Yuksek" : "Anlik min-max"}</div>
          </div>
          <div className="card">
            <div className="card-label">TOPLAM KAYIT</div>
            <div className="card-value neutral">
              {trend ? trend.kayit_sayisi : analizVerisi.length}
            </div>
            <div className="card-sub">{trend ? "Donem Kayit Sayisi" : "Veritabanindaki Kayit"}</div>
          </div>
        </div>

        {/* Grafik */}
        <div className="chart-container">
          <div className="chart-title">
            {trendModu
              ? `Fiyat Trendi: ${seciliUrun} (Gecmis Veri)`
              : `Canli Fiyat Dagilimi: ${seciliUrun}`}
          </div>
          {trendModu && trendChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={trendChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#242f47" />
                <XAxis dataKey="tarih" stroke="#94a3b8" fontSize={9} angle={-30} textAnchor="end" height={50} />
                <YAxis stroke="#94a3b8" fontSize={10} />
                <Tooltip
                  contentStyle={{ background: "#161c2a", border: "1px solid #242f47", borderRadius: "8px", fontSize: "12px" }}
                  labelStyle={{ color: "#e2e8f0" }}
                />
                <Legend wrapperStyle={{ fontSize: "11px" }} />
                <Line type="monotone" dataKey="ortalama" stroke="#38bdf8" strokeWidth={2} name="Ortalama" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="min" stroke="#34d399" strokeWidth={1} name="Min" dot={false} />
                <Line type="monotone" dataKey="max" stroke="#fbbf24" strokeWidth={1} name="Max" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : !trendModu && barData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#242f47" />
                <XAxis dataKey="isletme" stroke="#94a3b8" fontSize={8} angle={-45} textAnchor="end" height={70} />
                <YAxis stroke="#94a3b8" fontSize={10} />
                <Tooltip
                  contentStyle={{ background: "#161c2a", border: "1px solid #242f47", borderRadius: "8px", fontSize: "12px" }}
                  labelStyle={{ color: "#e2e8f0" }}
                  formatter={(value: number) => [`${value.toFixed(2)} TL`, "Fiyat"]}
                />
                <Bar dataKey="fiyat" radius={[4, 4, 0, 0]}>
                  {barData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.durum === "Sapma / Hatalı" ? "#f87171" : "#38bdf8"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">
              {cekiliyor ? (
                <><span className="loading-spinner" />Veri cekiliyor...</>
              ) : (
                `${seciliUrun} icin veri bulunamadi. "Canli Cek" butonuna tiklayin.`
              )}
            </div>
          )}
        </div>

        {/* Tablo */}
        <div className="table-container" style={{ overflow: "auto" }}>
          {analizVerisi.length === 0 ? (
            <div className="empty-state">
              {cekiliyor
                ? "Veri cekiliyor..."
                : "Veri yok. 'Web Sitelerinden Canli Cek' butonuna tiklayarak fiyat toplamaya baslayin."}
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Isletme</th>
                  <th>Kaynak Turu</th>
                  <th>Sitedeki Orijinal Isim</th>
                  <th>Birim</th>
                  <th>Net Fiyat</th>
                  <th>Normalize (kg)</th>
                  <th>Cekim Zamani</th>
                  <th>Dogrulama</th>
                  <th>Guven</th>
                </tr>
              </thead>
              <tbody>
                {[...analizVerisi]
                  .sort((a, b) => a.fiyat - b.fiyat)
                  .map((satir) => (
                    <tr key={satir.id}>
                      <td>{satir.isletme}</td>
                      <td>{satir.kaynak_turu}</td>
                      <td>{satir.cekilen_isim}</td>
                      <td>
                        {satir.birim ? (
                          <span className="badge badge-neutral">{satir.birim}</span>
                        ) : "-"}
                      </td>
                      <td style={{ fontWeight: 700 }}>{satir.fiyat.toFixed(2)} TL</td>
                      <td style={{ color: "#94a3b8" }}>
                        {satir.fiyat_norm ? `${satir.fiyat_norm.toFixed(2)} TL/kg` : "-"}
                      </td>
                      <td style={{ color: "#94a3b8" }}>{satir.cekilme_tarihi.slice(0, 16)}</td>
                      <td>
                        <span className={`badge ${satir.Durum === "Doğrulandı" ? "badge-success" : "badge-error"}`}>
                          {satir.Durum}
                        </span>
                      </td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            background: `${guvenRengi(satir.GuvenSkoru)}22`,
                            color: guvenRengi(satir.GuvenSkoru),
                          }}
                        >
                          {guvenEtiket(satir.GuvenSkoru)}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
