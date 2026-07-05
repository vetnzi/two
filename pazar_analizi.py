import customtkinter as ctk
import tkinter.ttk as ttk
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import threading
import json
import os

from veri_tabani import VeriTabani
from fiyat_parserleri import tum_kaynaklari_tara, urun_eslestir, URUN_ES_ANLAMLI

# --- Modern Renk Paleti ---
RENK_ARKA_PLAN = "#0B0F17"
RENK_KART = "#161C2A"
RENK_BORDER = "#242F47"
RENK_YAZI_ANA = "#E2E8F0"
RENK_YAZI_IKINCI = "#94A3B8"
RENK_ACCENT = "#38BDF8"
RENK_BASARI = "#34D399"
RENK_HATA = "#F87171"
RENK_SARI = "#FBBF24"

ctk.set_appearance_mode("Dark")

URUNLER = ["Simit", "Poğaça", "Açma", "Yaş Pasta", "Baklava", "Su Böreği"]


class FiyatKonsensusMotoru:
    def __init__(self):
        self.vt = VeriTabani()
        self.urunler = URUNLER
        self.veri_cercevesi = pd.DataFrame()
        self.gecmis_veri = pd.DataFrame()
        self.verileri_yukle()

    def verileri_yukle(self):
        kayitlar = self.vt.guncel_verileri_getir()
        if kayitlar:
            self.veri_cercevesi = pd.DataFrame(kayitlar)
            if "fiyat" in self.veri_cercevesi.columns:
                self.veri_cercevesi["fiyat"] = pd.to_numeric(self.veri_cercevesi["fiyat"], errors="coerce")
        else:
            self.veri_cercevesi = pd.DataFrame(columns=["isletme", "kaynak_turu", "urun", "cekilen_isim", "fiyat", "kaynak_url", "cekilme_tarihi"])

    def gecmisi_yukle(self, urun, gun=30):
        kayitlar = self.vt.gecmis_verileri_getir(urun, gun)
        if kayitlar:
            self.gecmis_veri = pd.DataFrame(kayitlar)
            if "fiyat" in self.gecmis_veri.columns:
                self.gecmis_veri["fiyat"] = pd.to_numeric(self.gecmis_veri["fiyat"], errors="coerce")
        else:
            self.gecmis_veri = pd.DataFrame()

    def tum_gecmisi_yukle(self, urun):
        kayitlar = self.vt.tum_gecmisi_getir(urun)
        if kayitlar:
            self.gecmis_veri = pd.DataFrame(kayitlar)
            if "fiyat" in self.gecmis_veri.columns:
                self.gecmis_veri["fiyat"] = pd.to_numeric(self.gecmis_veri["fiyat"], errors="coerce")
        else:
            self.gecmis_veri = pd.DataFrame()

    def canli_cek(self, ilerleme_callback=None, tamamlama_callback=None):
        def calisma():
            veriler, basarili, basarisiz = tum_kaynaklari_tara(ilerleme_callback)
            if veriler:
                self.vt.kayit_ekle(veriler)
                self.verileri_yukle()
            if tamamlama_callback:
                tamamlama_callback(veriler, basarili, basarisiz)
        thread = threading.Thread(target=calisma, daemon=True)
        thread.start()

    def anomali_ve_guven_analizi(self, secili_urun):
        if self.veri_cercevesi.empty or "urun" not in self.veri_cercevesi.columns:
            return pd.DataFrame()

        urun_verisi = self.veri_cercevesi[self.veri_cercevesi["urun"] == secili_urun].copy()
        if urun_verisi.empty:
            return urun_verisi

        fiyatlar = urun_verisi["fiyat"].dropna()
        if len(fiyatlar) < 2:
            urun_verisi["Durum"] = "Doğrulandı"
            urun_verisi["Güven Skoru"] = "Tek Kaynak"
            return urun_verisi

        q1 = np.percentile(fiyatlar, 25)
        q3 = np.percentile(fiyatlar, 75)
        iqr = q3 - q1
        alt_sinir = q1 - (1.5 * iqr) if iqr > 0 else q1 * 0.5
        ust_sinir = q3 + (1.5 * iqr) if iqr > 0 else q3 * 1.5

        analiz_sonuclari = []
        for _, row in urun_verisi.iterrows():
            fiyat = row["fiyat"]
            if pd.isna(fiyat):
                continue
            if fiyat < alt_sinir or fiyat > ust_sinir:
                durum = "Sapma / Hatalı"
                skor = "Kritik"
            else:
                durum = "Doğrulandı"
                medyan = fiyatlar.median()
                sapma_orani = abs(fiyat - medyan) / medyan if medyan > 0 else 0
                if sapma_orani <= 0.10:
                    skor = "Yüksek"
                elif sapma_orani <= 0.25:
                    skor = "Güvenli"
                else:
                    skor = "Zayıf"

            row_dict = row.to_dict()
            row_dict["Durum"] = durum
            row_dict["Güven Skoru"] = skor
            analiz_sonuclari.append(row_dict)

        return pd.DataFrame(analiz_sonuclari)

    def trend_analizi(self, secili_urun, gun=30):
        self.gecmisi_yukle(secili_urun, gun)
        if self.gecmis_veri.empty:
            return {}

        fiyatlar = self.gecmis_veri["fiyat"].dropna()
        if fiyatlar.empty:
            return {}

        return {
            "min": float(fiyatlar.min()),
            "max": float(fiyatlar.max()),
            "ortalama": float(fiyatlar.mean()),
            "medyan": float(fiyatlar.median()),
            "ilk_fiyat": float(fiyatlar.iloc[0]),
            "son_fiyat": float(fiyatlar.iloc[-1]),
            "degisim_yuzdesi": ((float(fiyatlar.iloc[-1]) - float(fiyatlar.iloc[0])) / float(fiyatlar.iloc[0]) * 100) if float(fiyatlar.iloc[0]) > 0 else 0,
            "kayit_sayisi": len(fiyatlar),
            "tarih_araligi": f"{self.gecmis_veri['cekilme_tarihi'].iloc[0][:10]} - {self.gecmis_veri['cekilme_tarihi'].iloc[-1][:10]}",
        }


class UIKart(ctk.CTkFrame):
    def __init__(self, master, baslik, deger, alt_bilgi="", renk=RENK_ACCENT, **kwargs):
        super().__init__(master, fg_color=RENK_KART, border_color=RENK_BORDER, border_width=1, corner_radius=12, **kwargs)
        self.lbl_baslik = ctk.CTkLabel(self, text=baslik, font=ctk.CTkFont(size=12, weight="bold"), text_color=RENK_YAZI_IKINCI)
        self.lbl_baslik.pack(anchor="w", padx=15, pady=(12, 2))
        self.lbl_deger = ctk.CTkLabel(self, text=deger, font=ctk.CTkFont(size=20, weight="bold"), text_color=renk)
        self.lbl_deger.pack(anchor="w", padx=15, pady=(0, 2))
        if alt_bilgi:
            self.lbl_alt = ctk.CTkLabel(self, text=alt_bilgi, font=ctk.CTkFont(size=11), text_color=RENK_YAZI_IKINCI)
            self.lbl_alt.pack(anchor="w", padx=15, pady=(0, 12))

    def guncelle(self, yeni_deger, yeni_alt=""):
        self.lbl_deger.configure(text=yeni_deger)
        if yeni_alt and hasattr(self, "lbl_alt"):
            self.lbl_alt.configure(text=yeni_alt)


class PremiumPazarAnalizi(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Piyasa Analiz İstasyonu - Unlu Mamul Fiyat Takibi")
        self.geometry("1440x900")
        self.configure(fg_color=RENK_ARKA_PLAN)

        self.motor = FiyatKonsensusMotoru()
        self.cekiliyor = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.arayuz_insat_et()
        self.ekrani_guncelle(self.urun_secici.get())

    def arayuz_insat_et(self):
        # ─── SIDEBAR ───
        self.sidebar = ctk.CTkFrame(self, width=320, fg_color=RENK_ARKA_PLAN, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(self.sidebar, text="PIYASA ANALIZ PRO", font=ctk.CTkFont(size=18, weight="bold"), text_color=RENK_YAZI_ANA).grid(row=0, column=0, padx=25, pady=(30, 20), sticky="w")
        ctk.CTkLabel(self.sidebar, text="Gozlem Alani", font=ctk.CTkFont(size=12, weight="bold"), text_color=RENK_YAZI_IKINCI).grid(row=1, column=0, padx=25, pady=(10, 5), sticky="w")

        self.urun_secici = ctk.CTkOptionMenu(
            self.sidebar, values=self.motor.urunler, command=self.ekrani_guncelle,
            fg_color=RENK_KART, button_color=RENK_BORDER, button_hover_color=RENK_ACCENT,
            dropdown_fg_color=RENK_KART, dropdown_hover_color=RENK_BORDER,
            font=ctk.CTkFont(size=13), text_color=RENK_YAZI_ANA, corner_radius=8
        )
        self.urun_secici.grid(row=2, column=0, padx=25, pady=(0, 20), sticky="ew")

        self.btn_tarama = ctk.CTkButton(
            self.sidebar, text="Web Sitelerinden Canli Cek", command=self.kaynaklari_tara,
            fg_color=RENK_ACCENT, hover_color="#0EA5E9", text_color=RENK_ARKA_PLAN,
            font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, height=40
        )
        self.btn_tarama.grid(row=3, column=0, padx=25, pady=10, sticky="ew")

        # Trend butonu
        self.btn_trend = ctk.CTkButton(
            self.sidebar, text="Gecmis Trend Analizi", command=self.trend_goster,
            fg_color=RENK_KART, hover_color=RENK_BORDER, text_color=RENK_ACCENT,
            font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, height=36,
            border_color=RENK_BORDER, border_width=1
        )
        self.btn_trend.grid(row=4, column=0, padx=25, pady=(5, 10), sticky="ew")

        # Gun secici (trend icin)
        ctk.CTkLabel(self.sidebar, text="Trend Donemi (Gun)", font=ctk.CTkFont(size=11), text_color=RENK_YAZI_IKINCI).grid(row=5, column=0, padx=25, pady=(5, 2), sticky="w")
        self.gun_secici = ctk.CTkOptionMenu(
            self.sidebar, values=["7", "30", "90", "365", "Tum"],
            command=lambda x: self.ekrani_guncelle(self.urun_secici.get()),
            fg_color=RENK_KART, button_color=RENK_BORDER, button_hover_color=RENK_ACCENT,
            font=ctk.CTkFont(size=12), text_color=RENK_YAZI_ANA, corner_radius=8
        )
        self.gun_secici.set("30")
        self.gun_secici.grid(row=6, column=0, padx=25, pady=(0, 15), sticky="ew")

        # Durum kutusu
        self.sys_box = ctk.CTkFrame(self.sidebar, fg_color=RENK_KART, border_color=RENK_BORDER, border_width=1, corner_radius=10)
        self.sys_box.grid(row=7, column=0, padx=25, pady=10, sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.sys_box,
            text="● Veritabani: Supabase\n● Kaynak: 27 site/odalar\n● Filtre: IQR Algoritmasi\n● Durum: Hazir",
            font=ctk.CTkFont(family="Courier", size=11),
            text_color=RENK_BASARI, justify="left"
        )
        self.status_label.pack(padx=15, pady=15, anchor="w")

        # Ilerleme kutusu
        self.ilerleme_box = ctk.CTkFrame(self.sidebar, fg_color=RENK_KART, border_color=RENK_BORDER, border_width=1, corner_radius=10)
        self.ilerleme_box.grid(row=8, column=0, padx=25, pady=(0, 25), sticky="ew")
        self.ilerleme_label = ctk.CTkLabel(self.ilerleme_box, text="", font=ctk.CTkFont(family="Courier", size=10), text_color=RENK_YAZI_IKINCI, justify="left")
        self.ilerleme_label.pack(padx=15, pady=10, anchor="w")

        # ─── MAIN PANEL ───
        self.main_panel = ctk.CTkFrame(self, fg_color=RENK_ARKA_PLAN, corner_radius=0)
        self.main_panel.grid(row=0, column=1, padx=30, pady=30, sticky="nsew")
        self.main_panel.grid_rowconfigure(3, weight=1)
        self.main_panel.grid_columnconfigure(0, weight=1)

        # Kart grid
        self.kart_grid = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.kart_grid.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        self.kart_konsensus = UIKart(self.kart_grid, "PAZAR MEDYANI", "- TL", "Dogrulanmis Pazar Fiyati", renk=RENK_ACCENT)
        self.kart_konsensus.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self.kart_marj = UIKart(self.kart_grid, "GUVENLI FIYAT ARALIGI", "- TL", "Gercek Islem Bandi", renk=RENK_BASARI)
        self.kart_marj.pack(side="left", expand=True, fill="both", padx=8)
        self.kart_tarih = UIKart(self.kart_grid, "SON CEKIM ZAMANI", "-", "Veri Tabani Kaydi", renk=RENK_YAZI_ANA)
        self.kart_tarih.pack(side="left", expand=True, fill="both", padx=8)
        self.kart_kaynak = UIKart(self.kart_grid, "AKTIF KAYNAK", "-", "Basarili Site Sayisi", renk=RENK_SARI)
        self.kart_kaynak.pack(side="left", expand=True, fill="both", padx=(8, 0))

        # Trend kartlari
        self.trend_grid = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.trend_grid.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        self.kart_ortalama = UIKart(self.trend_grid, "ORTALAMA FIYAT", "- TL", "Secili Donem Ortalamasi", renk=RENK_ACCENT)
        self.kart_ortalama.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self.kart_degisim = UIKart(self.trend_grid, "FIYAT DEGISIMI", "-%", "Ilk vs Son Kayit", renk=RENK_BASARI)
        self.kart_degisim.pack(side="left", expand=True, fill="both", padx=8)
        self.kart_minmax = UIKart(self.trend_grid, "MIN - MAX", "- TL", "Donem En Dusuk/En Yuksek", renk=RENK_SARI)
        self.kart_minmax.pack(side="left", expand=True, fill="both", padx=8)
        self.kart_kayit = UIKart(self.trend_grid, "TOPLAM KAYIT", "-", "Veritabanindaki Kayit", renk=RENK_YAZI_ANA)
        self.kart_kayit.pack(side="left", expand=True, fill="both", padx=(8, 0))

        # Grafik
        self.frame_grafik = ctk.CTkFrame(self.main_panel, fg_color=RENK_KART, border_color=RENK_BORDER, border_width=1, corner_radius=12)
        self.frame_grafik.grid(row=2, column=0, sticky="nsew", pady=(0, 15))

        self.fig, self.ax = plt.subplots(figsize=(10, 3.5), dpi=110)
        self.fig.patch.set_facecolor(RENK_KART)
        self.ax.set_facecolor(RENK_KART)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_grafik)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

        # Tablo
        self.frame_tablo = ctk.CTkFrame(self.main_panel, fg_color=RENK_KART, border_color=RENK_BORDER, border_width=1, corner_radius=12)
        self.frame_tablo.grid(row=3, column=0, sticky="nsew")

        stil = ttk.Style()
        stil.theme_use("default")
        stil.configure("Treeview", background=RENK_KART, foreground=RENK_YAZI_ANA, rowheight=32, fieldbackground=RENK_KART, borderwidth=0, font=("Arial", 10))
        stil.map("Treeview", background=[("selected", RENK_BORDER)], foreground=[("selected", RENK_ACCENT)])
        stil.configure("Treeview.Heading", background=RENK_BORDER, foreground=RENK_YAZI_ANA, relief="flat", font=("Arial", 10, "bold"))

        kolonlar = ("isletme", "kaynak_turu", "cekilen_isim", "fiyat", "tarih", "durum", "skor")
        self.tablo = ttk.Treeview(self.frame_tablo, columns=kolonlar, show="headings")

        self.tablo.heading("isletme", text="Isletme / Domain")
        self.tablo.heading("kaynak_turu", text="Kaynak Turu")
        self.tablo.heading("cekilen_isim", text="Sitedeki Orijinal Isim")
        self.tablo.heading("fiyat", text="Net Fiyat")
        self.tablo.heading("tarih", text="Cekim Zamani")
        self.tablo.heading("durum", text="Dogrulama")
        self.tablo.heading("skor", text="Guven")

        self.tablo.column("isletme", width=180, anchor="w")
        self.tablo.column("kaynak_turu", width=100, anchor="center")
        self.tablo.column("cekilen_isim", width=220, anchor="w")
        self.tablo.column("fiyat", width=90, anchor="center")
        self.tablo.column("tarih", width=130, anchor="center")
        self.tablo.column("durum", width=120, anchor="center")
        self.tablo.column("skor", width=80, anchor="center")
        self.tablo.pack(fill="both", expand=True, padx=10, pady=10)

    def kaynaklari_tara(self):
        if self.cekiliyor:
            return
        self.cekiliyor = True
        self.btn_tarama.configure(text="Cekiliyor... Lutfen Bekleyin", state="disabled")
        self.status_label.configure(text="● Veritabani: Supabase\n● Kaynak: 27 site/odalar\n● Filtre: IQR Algoritmasi\n● Durum: Veri Cekiliyor...", text_color=RENK_SARI)
        self.ilerleme_label.configure(text="Baslatiliyor...")

        def ilerleme(idx, toplam, isletme):
            self.after(0, lambda: self.ilerleme_label.configure(text=f"[{idx}/{toplam}] {isletme}"))

        def tamamlandi(veriler, basarili, basarisiz):
            def guncelle():
                self.cekiliyor = False
                self.btn_tarama.configure(text="Web Sitelerinden Canli Cek", state="normal")
                self.status_label.configure(text=f"● Veritabani: Supabase\n● Cekilen: {len(veriler)} kayit\n● Basarili: {basarili} / Basarisiz: {basarisiz}\n● Durum: Tamamlandi", text_color=RENK_BASARI)
                self.ilerleme_label.configure(text=f"Tamamlandi!\n{basarili} basarili, {basarisiz} basarisiz\n{len(veriler)} kayit eklendi")
                self.ekrani_guncelle(self.urun_secici.get())
            self.after(0, guncelle)

        self.motor.canli_cek(ilerleme, tamamlandi)

    def trend_goster(self):
        secili_urun = self.urun_secici.get()
        gun_str = self.gun_secici.get()

        if gun_str == "Tum":
            self.motor.tum_gecmisi_yukle(secili_urun)
        else:
            gun = int(gun_str)
            self.motor.gecmisi_yukle(secili_urun, gun)

        self.ekrani_guncelle(secili_urun, trend_modu=True)

    def ekrani_guncelle(self, secili_urun, trend_modu=False):
        analiz_df = self.motor.anomali_ve_guven_analizi(secili_urun)

        self.ax.clear()
        for row in self.tablo.get_children():
            self.tablo.delete(row)

        if analiz_df.empty:
            self.kart_konsensus.guncelle("Veri Yok")
            self.kart_marj.guncelle("Veri Yok")
            self.kart_tarih.guncelle("-")
            self.kart_kaynak.guncelle("-")
            self.kart_ortalama.guncelle("-")
            self.kart_degisim.guncelle("-")
            self.kart_minmax.guncelle("-")
            self.kart_kayit.guncelle("-")
            self.ax.set_title(f"{secili_urun} icin veri bulunamadi.", color=RENK_HATA, fontsize=11)
            self.canvas.draw()
            return

        dogrulanmis = analiz_df[analiz_df["Durum"] == "Doğrulandı"]

        if not dogrulanmis.empty:
            self.kart_konsensus.guncelle(f"{dogrulanmis['fiyat'].median():.2f} TL")
            self.kart_marj.guncelle(f"{dogrulanmis['fiyat'].min():.1f} - {dogrulanmis['fiyat'].max():.1f} TL")
        else:
            self.kart_konsensus.guncelle("Hata", "Gecerli fiyat yok")
            self.kart_marj.guncelle("Belirsiz")

        # Tarih
        if "cekilme_tarihi" in analiz_df.columns and not analiz_df.empty:
            tarih = str(analiz_df["cekilme_tarihi"].iloc[0])[:16]
            self.kart_tarih.guncelle(tarih)

        # Kaynak sayisi
        isletme_sayisi = analiz_df["isletme"].nunique() if "isletme" in analiz_df.columns else 0
        self.kart_kaynak.guncelle(str(isletme_sayisi))

        # Trend kartlari
        if trend_modu and not self.motor.gecmis_veri.empty:
            trend = self.motor.trend_analizi(secili_urun, gun=999999 if self.gun_secici.get() == "Tum" else int(self.gun_secici.get()))
            if trend:
                self.kart_ortalama.guncelle(f"{trend['ortalama']:.2f} TL")
                degisim = trend["degisim_yuzdesi"]
                renk = RENK_BASARI if degisim >= 0 else RENK_HATA
                isaret = "+" if degisim >= 0 else ""
                self.kart_degisim.guncelle(f"{isaret}{degisim:.1f}%", trend["tarih_araligi"])
                self.kart_degisim.lbl_deger.configure(text_color=renk)
                self.kart_minmax.guncelle(f"{trend['min']:.0f} - {trend['max']:.0f} TL")
                self.kart_kayit.guncelle(str(trend["kayit_sayisi"]))
        else:
            self.kart_ortalama.guncelle(f"{analiz_df['fiyat'].mean():.2f} TL", "Anlik ortalama")
            self.kart_degisim.guncelle("-", "Trend icin butona tiklayin")
            self.kart_degisim.lbl_deger.configure(text_color=RENK_YAZI_IKINCI)
            self.kart_minmax.guncelle(f"{analiz_df['fiyat'].min():.0f} - {analiz_df['fiyat'].max():.0f} TL")
            self.kart_kayit.guncelle(str(len(analiz_df)))

        # Grafik
        self.ax.grid(axis="y", linestyle="--", alpha=0.1, color=RENK_YAZI_IKINCI)
        self.ax.tick_params(colors=RENK_YAZI_IKINCI, labelsize=9)
        self.ax.xaxis.label.set_color(RENK_YAZI_IKINCI)
        self.ax.yaxis.label.set_color(RENK_YAZI_IKINCI)

        if trend_modu and not self.motor.gecmis_veri.empty:
            self._ciz_trend_grafigi(secili_urun)
        else:
            self._ciz_bar_grafigi(secili_urun, analiz_df)

        self.fig.tight_layout()
        self.canvas.draw()

        # Tablo
        for _, satir in analiz_df.sort_values(by="fiyat").iterrows():
            tarih_str = str(satir.get("cekilme_tarihi", "-"))[:16] if pd.notna(satir.get("cekilme_tarihi")) else "-"
            self.tablo.insert("", "end", values=(
                satir.get("isletme", "-"),
                satir.get("kaynak_turu", "-"),
                satir.get("cekilen_isim", "-"),
                f"{satir['fiyat']:.2f} TL" if pd.notna(satir["fiyat"]) else "-",
                tarih_str,
                satir.get("Durum", "-"),
                satir.get("Güven Skoru", "-"),
            ))

    def _ciz_bar_grafigi(self, secili_urun, analiz_df):
        renkler = [RENK_HATA if d == "Sapma / Hatalı" else RENK_ACCENT for d in analiz_df["Durum"]]
        bars = self.ax.bar(analiz_df["isletme"], analiz_df["fiyat"], color=renkler, width=0.45, edgecolor=RENK_BORDER, linewidth=0.8)
        self.ax.set_title(f"Canli Fiyat Dagilimi: {secili_urun}", color=RENK_YAZI_ANA, pad=15, fontdict={"fontsize": 11, "weight": "bold"})
        self.ax.set_ylabel("Fiyat (TL)")
        self.ax.set_xticklabels(analiz_df["isletme"], rotation=45, ha="right", fontsize=8)

        for spine in ["top", "right"]:
            self.ax.spines[spine].set_visible(False)
        self.ax.spines["bottom"].set_color(RENK_BORDER)
        self.ax.spines["left"].set_color(RENK_BORDER)

        for bar in bars:
            yval = bar.get_height()
            if pd.notna(yval):
                self.ax.text(bar.get_x() + bar.get_width() / 2, yval + (yval * 0.015), f"{yval:.0f}", ha="center", va="bottom", color=RENK_YAZI_ANA, fontsize=7, weight="bold")

    def _ciz_trend_grafigi(self, secili_urun):
        gecmis = self.motor.gecmis_veri.copy()
        if gecmis.empty:
            return

        gecmis["cekilme_tarihi"] = pd.to_datetime(gecmis["cekilme_tarihi"], errors="coerce")
        gecmis = gecmis.dropna(subset=["cekilme_tarihi", "fiyat"])
        gecmis = gecmis.sort_values("cekilme_tarihi")

        # Isletmeye gore gruplandir, gunluk ortalama
        gecmis["tarih"] = gecmis["cekilme_tarihi"].dt.date
        gunluk = gecmis.groupby("tarih")["fiyat"].agg(["mean", "min", "max"]).reset_index()

        self.ax.plot(gunluk["tarih"], gunluk["mean"], color=RENK_ACCENT, linewidth=2, label="Ortalama", marker="o", markersize=4)
        self.ax.fill_between(gunluk["tarih"], gunluk["min"], gunluk["max"], alpha=0.15, color=RENK_ACCENT, label="Min-Max Bandi")

        self.ax.set_title(f"Fiyat Trendi: {secili_urun} (Gecmis Veri)", color=RENK_YAZI_ANA, pad=15, fontdict={"fontsize": 11, "weight": "bold"})
        self.ax.set_ylabel("Fiyat (TL)")
        self.ax.set_xlabel("Tarih")
        self.ax.legend(facecolor=RENK_KART, edgecolor=RENK_BORDER, labelcolor=RENK_YAZI_ANA, fontsize=8)

        for spine in ["top", "right"]:
            self.ax.spines[spine].set_visible(False)
        self.ax.spines["bottom"].set_color(RENK_BORDER)
        self.ax.spines["left"].set_color(RENK_BORDER)

        self.ax.tick_params(axis="x", rotation=30)


if __name__ == "__main__":
    app = PremiumPazarAnalizi()
    app.mainloop()
