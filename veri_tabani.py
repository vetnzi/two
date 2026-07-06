import os
import re
import io
import json
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pdfplumber


# Supabase proje bilgileri (.env yoksa bu degerler kullanilir)
_FALLBACK_URL = "https://bqloternirlrrgpdyxad.supabase.co"
_FALLBACK_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJxbG90ZXJuaXJscnJncGR5eGFkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMyNjI2NDgsImV4cCI6MjA5ODgzODY0OH0.TKzvEt0xxuYsGSXPVKh84JPMF-VwxKn0fYhSynnrvmI"


def _env_yukle():
    """Supabase URL ve key'i .env dosyasından, ortam değişkenlerinden veya fallback'ten okur."""
    url = os.environ.get("VITE_SUPABASE_URL", "")
    key = os.environ.get("VITE_SUPABASE_ANON_KEY", "")

    if not url or not key:
        # .env dosyasını ara: script dizini, cwd, üst dizinler, home
        arama_dizinleri = [
            os.path.dirname(os.path.abspath(__file__)),
            os.getcwd(),
            os.path.dirname(os.getcwd()),
            os.path.expanduser("~"),
        ]
        for dizin in arama_dizinleri:
            env_path = os.path.join(dizin, ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("VITE_SUPABASE_URL="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                url = val
                        elif line.startswith("VITE_SUPABASE_ANON_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                key = val
                if url and key:
                    break

    # .env veya ortam degiskenleri yoksa fallback degerleri kullan
    if not url:
        url = _FALLBACK_URL
    if not key:
        key = _FALLBACK_KEY

    return url, key


SUPABASE_URL, SUPABASE_KEY = _env_yukle()


class VeriTabani:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "Supabase URL veya ANON KEY bulunamadi!\n"
                "Lutfen proje kokunde .env dosyasi olusturun:\n"
                "  VITE_SUPABASE_URL=https://xxxx.supabase.co\n"
                "  VITE_SUPABASE_ANON_KEY=eyJhbGciOi...\n"
                "Veya ortam degiskenlerini ayarlayin:\n"
                "  export VITE_SUPABASE_URL=...\n"
                "  export VITE_SUPABASE_ANON_KEY=..."
            )
        self.base_url = f"{SUPABASE_URL}/rest/v1/fiyat_kayitlari"
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

    def kayit_ekle(self, kayitlar):
        if not kayitlar:
            return 0
        url = self.base_url
        hdrs = {**self.headers, "Prefer": "return=minimal"}
        basarili = 0
        for k in kayitlar:
            try:
                r = requests.post(url, headers=hdrs, json=k, timeout=15)
                if r.status_code == 201:
                    basarili += 1
            except Exception:
                pass
        return basarili

    def guncel_verileri_getir(self, urun=None):
        params = {"order": "cekilme_tarihi.desc", "limit": "2000"}
        if urun:
            params["urun"] = f"eq.{urun}"
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        return []

    def gecmis_verileri_getir(self, urun, gun=30):
        baslangic = (datetime.now() - timedelta(days=gun)).isoformat()
        params = {
            "urun": f"eq.{urun}",
            "cekilme_tarihi": f"gte.{baslangic}",
            "order": "cekilme_tarihi.asc",
            "limit": "5000",
        }
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        return []

    def tum_gecmisi_getir(self, urun):
        params = {
            "urun": f"eq.{urun}",
            "order": "cekilme_tarihi.asc",
            "limit": "5000",
        }
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        return []

    def bugun_cekildi_mi(self, isletme, urun, cekilen_isim):
        bugun = datetime.now().strftime("%Y-%m-%d")
        params = {
            "isletme": f"eq.{isletme}",
            "urun": f"eq.{urun}",
            "cekilme_tarihi": f"gte.{bugun}T00:00:00",
            "limit": "1",
        }
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200 and r.json():
            return True
        return False
