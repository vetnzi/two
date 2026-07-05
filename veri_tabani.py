import os
import json
import re
import io
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pdfplumber

SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VITE_SUPABASE_URL="):
                    SUPABASE_URL = line.split("=", 1)[1]
                elif line.startswith("VITE_SUPABASE_ANON_KEY="):
                    SUPABASE_KEY = line.split("=", 1)[1]


class VeriTabani:
    def __init__(self):
        self.base_url = f"{SUPABASE_URL}/rest/v1/fiyat_kayitlari"
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

    def kayit_ekle(self, kayitlar):
        if not kayitlar:
            return 0
        url = f"{self.base_url}"
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
        params = {"order": "cekilme_tarihi.desc", "limit": "500"}
        if urun:
            params["urun"] = f"eq.{urun}"
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        return []

    def son_kayit_tarihini_getir(self, urun, isletme):
        params = {
            "urun": f"eq.{urun}",
            "isletme": f"eq.{isletme}",
            "order": "cekilme_tarihi.desc",
            "limit": "1",
        }
        r = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
        if r.status_code == 200 and r.json():
            return r.json()[0].get("cekilme_tarihi", "")
        return ""

    def gecmis_verileri_getir(self, urun, gun=30):
        baslangic = (datetime.now() - timedelta(days=gun)).isoformat()
        params = {
            "urun": f"eq.{urun}",
            "cekilme_tarihi": f"gte.{baslangic}",
            "order": "cekilme_tarihi.asc",
            "limit": "2000",
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
