import re
import io
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

URUN_ES_ANLAMLI = {
    "Simit": ["simit", "tereyağlı simit", "sütlü simit", "pastane simidi", "ankara simidi", "kandil simidi", "çikolatalı simit", "susamlı simit"],
    "Poğaça": ["poğaça", "pogaca", "peynirli poğaça", "kaşarlı poğaça", "sade poğaça", "patatesli poğaça", "dereotlu poğaça", "sosisli poğaça", "haşhaşlı poğaça", "talaş poğaça", "kıymalı poğaça", "sucuklu poğaça", "zeytinli poğaça"],
    "Açma": ["açma", "acma", "sade açma", "zeytinli açma", "çikolatalı açma", "haşhaşlı açma", "sosisli açma"],
    "Yaş Pasta": ["yaş pasta", "pasta", "çikolatalı pasta", "meyveli pasta", "karaorman", "blackforest", "mozaik pasta", "rulo pasta", "ekler pasta", "tane pasta", "pasta dilimi"],
    "Baklava": ["baklava", "fıstıklı baklava", "cevizli baklava", "kuru baklava", "şöbiyet", "burma", "sarı burma", "bulgur baklava", "havuç dilimi", "baklava dilimi", "sarıburma"],
    "Su Böreği": ["su böreği", "su boregi", "peynirli su böreği", "ıspanaklı su böreği", "tepsi su böreği", "tepsili su böreği", "su borek", "taze su böreği"],
}

HARIC_KELIMELER = ["kuru pasta", "kuru kek", "pasta tarifi", "pasta yapımı", "pasta kalıbı", "böreklik", "börekçi", "pasta tozu", "pasta kreması", "kek", "kurabiye", "sufle", "tiramisu", "sütlaç", "kazandibi", "puding", "muhallebi", "revani", "lokma", "tulumba", "künefe", "ekler", "cookie", "brownie", "macaron", "donut", "muffin", "cupcake"]

BEKLENEN_FIYAT_ARALIKLARI = {
    "Simit": (5, 50),
    "Poğaça": (5, 50),
    "Açma": (5, 50),
    "Yaş Pasta": (200, 8000),
    "Baklava": (200, 5000),
    "Su Böreği": (200, 4000),
}


def urun_eslestir(isim):
    isim_lower = isim.lower()
    for haric in HARIC_KELIMELER:
        if haric in isim_lower:
            return None
    for ana_urun, es_anlamlar in URUN_ES_ANLAMLI.items():
        for kelime in es_anlamlar:
            if kelime.lower() in isim_lower:
                return ana_urun
    return None


def birim_tespit(metin):
    lower = metin.lower()
    m = re.search(r"(\d+)\s*(kg|kilo|kilogram)", lower)
    if m:
        return "kg"
    m = re.search(r"(\d+)\s*(gr|g|gram)\b", lower)
    if m:
        return f"{m.group(1)} gr"
    m = re.search(r"(\d+)\s*adet", lower)
    if m:
        return f"{m.group(1)} adet"
    if re.search(r"(\d+)\s*(li|lu)\s*paket", lower):
        return "paket"
    if "paket" in lower:
        return "paket"
    if "dilim" in lower:
        return "dilim"
    if "tepsi" in lower:
        return "tepsi"
    m = re.search(r"(\d+)\s*parça", lower)
    if m:
        return f"{m.group(1)} parça"
    return "adet"


def fiyat_normalize(fiyat, birim):
    if birim == "kg":
        return fiyat
    if birim.endswith(" gr"):
        gr = int(birim.split()[0])
        if gr > 0:
            return (fiyat / gr) * 1000
    if birim == "100 gr":
        return fiyat * 10
    return fiyat


def fiyat_temizle(fiyat_metni):
    if not fiyat_metni:
        return 0.0
    metin = fiyat_metni.upper().replace("TL", "").replace("₺", "").replace("KDV", "").strip()
    metin = metin.replace("DAHİL", "").replace("HARİÇ", "").strip()
    if "," in metin and "." in metin:
        metin = metin.replace(".", "")
    metin = metin.replace(",", ".")
    sayilar = re.findall(r"[-+]?\d*\.\d+|\d+", metin)
    if sayilar:
        try:
            return float(sayilar[-1])
        except ValueError:
            return 0.0
    return 0.0


def guven_skoru_hesapla(fiyat, urun, birim, kaynak_turu):
    skor = 0
    if kaynak_turu == "Esnaf Odası":
        skor += 3
    elif kaynak_turu == "Pastane":
        skor += 1
    if birim and birim != "adet":
        skor += 1
    aralik = BEKLENEN_FIYAT_ARALIKLARI.get(urun)
    if aralik and aralik[0] <= fiyat <= aralik[1]:
        skor += 2
    elif aralik:
        skor -= 1
    if skor >= 4:
        return "yuksek"
    if skor >= 2:
        return "guvenli"
    if skor >= 0:
        return "zayif"
    return "kritik"


def _sayfa_cek(url, timeout=12, retry=2):
    for deneme in range(retry + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429) and deneme < retry:
                time.sleep(1 * (deneme + 1))
                continue
        except Exception:
            if deneme < retry:
                time.sleep(0.5 * (deneme + 1))
                continue
    return None


def _pdf_cek(url, timeout=20, retry=2):
    for deneme in range(retry + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True, allow_redirects=True)
            if r.status_code == 200:
                return r.content
        except Exception:
            if deneme < retry:
                time.sleep(0.5 * (deneme + 1))
                continue
    return None


# ─────────────────────────────────────────────────────────────
# ESNAF / TİCARET ODASI PARSER'LARI
# ─────────────────────────────────────────────────────────────

def parse_itso_simit_pogaca(html_doc, kaynak_url):
    sonuclar = []
    soup = BeautifulSoup(html_doc, "html.parser")
    tablolar = soup.find_all("table")
    for tablo in tablolar:
        satirlar = tablo.find_all("tr")
        for satir in satirlar:
            hucreler = satir.find_all(["td", "th"])
            if len(hucreler) >= 3:
                isim = hucreler[0].get_text(strip=True)
                fiyat_metni = hucreler[-1].get_text(strip=True)
                gramaj = hucreler[1].get_text(strip=True) if len(hucreler) > 2 else ""
                if isim and fiyat_metni and ("TL" in fiyat_metni or "₺" in fiyat_metni or re.search(r"\d", fiyat_metni)):
                    urun = urun_eslestir(isim)
                    if urun:
                        fiyat = fiyat_temizle(fiyat_metni)
                        if fiyat > 0:
                            birim = birim_tespit(f"{isim} {gramaj}")
                            fnorm = fiyat_normalize(fiyat, birim)
                            guven = guven_skoru_hesapla(fiyat, urun, birim, "Esnaf Odası")
                            sonuclar.append({
                                "isletme": "İnegöl TSO",
                                "kaynak_turu": "Esnaf Odası",
                                "urun": urun,
                                "cekilen_isim": f"{isim} ({gramaj})" if gramaj else isim,
                                "fiyat": fiyat,
                                "birim": birim,
                                "fiyat_norm": fnorm,
                                "guven_skoru": guven,
                                "kaynak_url": kaynak_url,
                                "cekilme_tarihi": datetime.now().isoformat(),
                            })
    return sonuclar


def _pdf_generic_parse(pdf_bytes, kaynak_url, isletme_adi):
    sonuclar = []
    if not pdf_bytes:
        return sonuclar
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tam_metin = ""
            for sayfa in pdf.pages:
                metin = sayfa.extract_text()
                if metin:
                    tam_metin += metin + "\n"
        satirlar = tam_metin.split("\n")
        for satir in satirlar:
            satir = satir.strip()
            if len(satir) < 3:
                continue
            desenler = [
                r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+(?:\.\d+)?)\s+(\d+[.,]?\d*)\s*TL?",
                r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+₺\s*(\d+[.,]?\d*)",
                r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+[.,]?\d*)\s*₺",
                r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]{3,}?)\s+(\d+[.,]?\d*)\s*TL",
            ]
            for desen in desenler:
                eslesme = re.search(desen, satir)
                if eslesme:
                    isim = eslesme.group(1).strip()
                    fiyat_str = eslesme.group(eslesme.lastindex)
                    fiyat = fiyat_temizle(fiyat_str + " TL")
                    if fiyat > 0:
                        urun = urun_eslestir(isim)
                        if urun:
                            birim = birim_tespit(isim)
                            fnorm = fiyat_normalize(fiyat, birim)
                            guven = guven_skoru_hesapla(fiyat, urun, birim, "Esnaf Odası")
                            sonuclar.append({
                                "isletme": isletme_adi,
                                "kaynak_turu": "Esnaf Odası",
                                "urun": urun,
                                "cekilen_isim": isim,
                                "fiyat": fiyat,
                                "birim": birim,
                                "fiyat_norm": fnorm,
                                "guven_skoru": guven,
                                "kaynak_url": kaynak_url,
                                "cekilme_tarihi": datetime.now().isoformat(),
                            })
                    break
    except Exception:
        pass
    return sonuclar


def parse_kutso_pastacilar(pdf_bytes, kaynak_url):
    return _pdf_generic_parse(pdf_bytes, kaynak_url, "Kütahya TSO")


def parse_atonet_pastacilar(pdf_bytes, kaynak_url):
    return _pdf_generic_parse(pdf_bytes, kaynak_url, "Ankara TSO")


# ─────────────────────────────────────────────────────────────
# PASTANE E-TİCARET SİTESİ PARSER'I (GENEL AMAÇLI)
# ─────────────────────────────────────────────────────────────

_GECERSIZ_KELIMELER = {"sepete", "ekle", "favorilere", "favori", "incele", "azalt", "artır",
                       "stokta", "tükendi", "yeni", "indirim", "kampanya", "kdv", "dahil",
                       "haric", "kargo", "teslimat", "sepette", "kupon", "puan",
                       "degerlendirme", "yildiz", "★", "az", "cok", "satan", "240derece",
                       "ürünü", "adet", "sepet", "eklendi", "tıkla", "devam", "öde",
                       "göster", "gizle", "yorum", "yorumlar", "tümü", "tumu", "filtre",
                       "sırala", "sıralama", "kategori", "menü", "ara", "search"}


def _isim_temizle(metin):
    metin = re.sub(r"\s+", " ", metin).strip()
    metin = re.sub(r"[\d.,]+\s*[₺TL].*$", "", metin).strip()
    metin = re.sub(r"\d+\s*(gr|kg|adet|g|ml|lt|l)\.?", "", metin, flags=re.IGNORECASE).strip()
    metin = re.sub(r"\(\s*\)", "", metin).strip()
    kelimeler = metin.split()
    temiz = [k for k in kelimeler if k.lower() not in _GECERSIZ_KELIMELER]
    return " ".join(temiz).strip(" -,|•·") if temiz else metin


def _genel_pastane_parser(html_doc, kaynak_url, isletme_adi):
    sonuclar = []
    soup = BeautifulSoup(html_doc, "html.parser")
    gorulen = set()

    for etiket in soup.find_all(["div", "li", "article", "span", "a", "h2", "h3", "h4", "p"]):
        metin = etiket.get_text(" ", strip=True)
        if not metin or len(metin) > 250 or len(metin) < 5:
            continue
        if "₺" not in metin and "TL" not in metin and "tl" not in metin:
            continue

        fiyat_eslesme = re.search(r"(\d{2,}(?:[.,]\d{1,2})?|\d{1,3}(?:\.\d{3})+[.,]\d{1,2})\s*[₺TLtl]", metin)
        if not fiyat_eslesme:
            continue
        fiyat = fiyat_temizle(fiyat_eslesme.group(1) + " ₺")
        if fiyat < 5:
            continue

        urun = urun_eslestir(metin)
        if not urun:
            continue

        temiz_isim = _isim_temizle(metin)
        if not temiz_isim or len(temiz_isim) < 3:
            continue

        birim = birim_tespit(metin)
        fnorm = fiyat_normalize(fiyat, birim)
        guven = guven_skoru_hesapla(fiyat, urun, birim, "Pastane")

        anahtar = (isletme_adi, urun, temiz_isim, fiyat)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)

        sonuclar.append({
            "isletme": isletme_adi,
            "kaynak_turu": "Pastane",
            "urun": urun,
            "cekilen_isim": temiz_isim,
            "fiyat": fiyat,
            "birim": birim,
            "fiyat_norm": fnorm,
            "guven_skoru": guven,
            "kaynak_url": kaynak_url,
            "cekilme_tarihi": datetime.now().isoformat(),
        })

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Product" or item.get("offers"):
                    isim = item.get("name", "")
                    offers = item.get("offers", [])
                    offer_list = offers if isinstance(offers, list) else [offers]
                    for offer in offer_list:
                        fiyat_str = str(offer.get("price", ""))
                        fiyat = fiyat_temizle(fiyat_str + " TL")
                        if fiyat > 0 and isim:
                            urun = urun_eslestir(isim)
                            if urun:
                                birim = birim_tespit(isim)
                                fnorm = fiyat_normalize(fiyat, birim)
                                guven = guven_skoru_hesapla(fiyat, urun, birim, "Pastane")
                                anahtar = (isletme_adi, urun, isim, fiyat)
                                if anahtar not in gorulen:
                                    gorulen.add(anahtar)
                                    sonuclar.append({
                                        "isletme": isletme_adi,
                                        "kaynak_turu": "Pastane",
                                        "urun": urun,
                                        "cekilen_isim": isim,
                                        "fiyat": fiyat,
                                        "birim": birim,
                                        "fiyat_norm": fnorm,
                                        "guven_skoru": guven,
                                        "kaynak_url": kaynak_url,
                                        "cekilme_tarihi": datetime.now().isoformat(),
                                    })
        except Exception:
            pass

    # data-price attributes
    for tag in soup.find_all(attrs={"data-price": True}):
        fiyat = fiyat_temizle(tag.get("data-price", "") + " ₺")
        isim = tag.get("data-name", "")
        if fiyat > 0 and isim:
            urun = urun_eslestir(isim)
            if urun:
                birim = birim_tespit(isim)
                fnorm = fiyat_normalize(fiyat, birim)
                guven = guven_skoru_hesapla(fiyat, urun, birim, "Pastane")
                anahtar = (isletme_adi, urun, isim, fiyat)
                if anahtar not in gorulen:
                    gorulen.add(anahtar)
                    sonuclar.append({
                        "isletme": isletme_adi,
                        "kaynak_turu": "Pastane",
                        "urun": urun,
                        "cekilen_isim": isim,
                        "fiyat": fiyat,
                        "birim": birim,
                        "fiyat_norm": fnorm,
                        "guven_skoru": guven,
                        "kaynak_url": kaynak_url,
                        "cekilme_tarihi": datetime.now().isoformat(),
                    })

    return sonuclar


def parse_tarihikarakoyfirini(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Tarihi Karaköy Fırını")

def parse_karakoygulluoglu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Karaköy Güllüoğlu")

def parse_hafizmustafa(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Hafız Mustafa 1864")

def parse_saraymuhallebicisi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Saray Muhallebicisi")

def parse_divan(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Divan Pastaneleri")

def parse_ozsut(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Özsüt")

def parse_liva(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Liva Pastacılık")

def parse_zahire(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Zahire Pastanesi")

def parse_linaria(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Linaria")

def parse_pastannecim(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pastannecim")

def parse_ankarapasta(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Ankara Pasta")

def parse_misbasak(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Misbaşak")

def parse_sirelibaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Şireli Baklava")

def parse_siniborek(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sini Börek")

def parse_celebiogullari(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Çelebioğulları")

def parse_cumba(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Cumba Baklava")

def parse_tazemasa(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "TazeMasa")

def parse_ozgurunlu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Özgür Unlu Mamulleri")

def parse_tepsiborek(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Tepsi Börek")

def parse_farukgullu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Faruk Güllü")

def parse_baklavadilim(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Baklava Dilim")

def parse_gulluoglu_baklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Güllüoğlu Baklava")

def parse_antepbaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Antep Baklava")

def parse_baklavahouse(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Baklava House")

def parse_koskeroglu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Köşkeroğlu Baklava")

def parse_halilbaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Halil Baklava")

def parse_saitbaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sait Baklava")

def parse_baklavacigullu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Baklavacı Güllü")

def parse_pastane2000(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pastane 2000")

def parse_istanbulpasta(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "İstanbul Pasta")

def parse_pastasepeti(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pasta Sepeti")

def parse_mavipastane(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Mavi Pastane")

def parse_pastaduragi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pasta Durağı")

def parse_erdempastanesi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Erdem Pastanesi")

def parse_banabaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Banabaklava")

def parse_pastakeyfi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pasta Keyfi")

def parse_sutis(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sütiş")

def parse_borekcitevfik(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Börekçi Tevfik")

def parse_uskudarborekcisi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Üsküdar Börekçisi")

def parse_borekcilik(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Börekçilik")

def parse_sariyerborekcisi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sarıyer Börekçisi")

def parse_borekevi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Börek Evi")

def parse_kadikoyborekcisi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Kadıköy Börekçisi")

def parse_simitsarayi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Simit Sarayı")

def parse_simitci(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Simitçi")

def parse_unlumamul(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Unlu Mamul")

def parse_firinexpress(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Fırın Express")


# ─────────────────────────────────────────────────────────────
# KAYNAK LİSTESİ (97 kaynak — 3x genişletilmiş)
# ─────────────────────────────────────────────────────────────

KAYNAKLAR = [
    # Esnaf / Ticaret Odaları
    {"isletme": "İnegöl TSO", "tur": "esnaf_odasi_tablo", "url": "https://www.itso.org.tr/simit-acma-pogaca-vb", "parser": "parse_itso_simit_pogaca"},
    {"isletme": "Kütahya TSO", "tur": "esnaf_odasi_pdf", "url": "https://www.kutso.org.tr/kutso-storage/page/49/qAGrYJTPQnGFuKpNU9rfgSiZl7KSUZbPCjiQs1KX.pdf", "parser": "parse_kutso_pastacilar"},
    {"isletme": "Ankara TSO", "tur": "esnaf_odasi_pdf", "url": "https://www.atonet.org.tr/Uploads/Birimler/Internet/Hizmetlerimiz/Azami%20Fiyat%20Tarifeleri/2025_azami_fiyat_tarifesi/2025_pasta_cikolata_tatlicilar.pdf", "parser": "parse_atonet_pastacilar"},

    # Pastane e-ticaret siteleri (orijinal)
    {"isletme": "Tarihi Karaköy Fırını", "tur": "pastane", "url": "https://www.tarihikarakoyfirini.com.tr/pogaca--simit--acma", "parser": "parse_tarihikarakoyfirini"},
    {"isletme": "Tarihi Karaköy Fırını (Baklava)", "tur": "pastane", "url": "https://www.tarihikarakoyfirini.com.tr/baklavalar-13", "parser": "parse_tarihikarakoyfirini"},
    {"isletme": "Tarihi Karaköy Fırını (Börek)", "tur": "pastane", "url": "https://www.tarihikarakoyfirini.com.tr/borekler-karakoy-", "parser": "parse_tarihikarakoyfirini"},
    {"isletme": "Karaköy Güllüoğlu", "tur": "pastane", "url": "https://www.karakoygulluoglu.com/baklavalar", "parser": "parse_karakoygulluoglu"},
    {"isletme": "Hafız Mustafa 1864", "tur": "pastane", "url": "https://online.hafizmustafa.com/baklava", "parser": "parse_hafizmustafa"},
    {"isletme": "Saray Muhallebicisi (Börek)", "tur": "pastane", "url": "https://online.saraymuhallebicisi.com/borekler", "parser": "parse_saraymuhallebicisi"},
    {"isletme": "Saray Muhallebicisi (Tatlı)", "tur": "pastane", "url": "https://online.saraymuhallebicisi.com/hamurlu-tatlilar", "parser": "parse_saraymuhallebicisi"},
    {"isletme": "Divan Pastaneleri", "tur": "pastane", "url": "https://www.divanpastaneleri.com.tr/pasta", "parser": "parse_divan"},
    {"isletme": "Divan Pastaneleri (Tatlı)", "tur": "pastane", "url": "https://www.divanpastaneleri.com.tr/tatli-tuzlu", "parser": "parse_divan"},
    {"isletme": "Özsüt", "tur": "pastane", "url": "https://www.ozsut.com.tr", "parser": "parse_ozsut"},
    {"isletme": "Liva Pastacılık", "tur": "pastane", "url": "https://www.livapastacilik.com", "parser": "parse_liva"},
    {"isletme": "Zahire Pastanesi", "tur": "pastane", "url": "https://www.zahirepastanesi.com", "parser": "parse_zahire"},
    {"isletme": "Linaria", "tur": "pastane", "url": "https://www.linaria.com.tr", "parser": "parse_linaria"},
    {"isletme": "Pastannecim", "tur": "pastane", "url": "https://www.pastannecim.com.tr", "parser": "parse_pastannecim"},
    {"isletme": "Ankara Pasta", "tur": "pastane", "url": "https://www.ankarapasta.com", "parser": "parse_ankarapasta"},
    {"isletme": "Misbaşak", "tur": "pastane", "url": "https://www.misbasakonline.com", "parser": "parse_misbasak"},
    {"isletme": "Şireli Baklava", "tur": "pastane", "url": "https://sirelibaklava.com.tr/products/su-boregi", "parser": "parse_sirelibaklava"},
    {"isletme": "Sini Börek", "tur": "pastane", "url": "https://siniborek.com.tr", "parser": "parse_siniborek"},
    {"isletme": "Çelebioğulları", "tur": "pastane", "url": "https://www.celebiogullari.com.tr/su-boregi-1-kg-paket", "parser": "parse_celebiogullari"},
    {"isletme": "Cumba Baklava", "tur": "pastane", "url": "https://cumbabaklava.com/su-boregi", "parser": "parse_cumba"},
    {"isletme": "TazeMasa", "tur": "pastane", "url": "https://www.tazemasa.com/simit-pogaca-322", "parser": "parse_tazemasa"},
    {"isletme": "Özgür Unlu Mamulleri", "tur": "pastane", "url": "https://ozgurunlumamulleri.com/simit-pogaca-cesitleri", "parser": "parse_ozgurunlu"},
    {"isletme": "Tepsi Börek", "tur": "pastane", "url": "https://www.tepsiborek.com.tr", "parser": "parse_tepsiborek"},
    {"isletme": "Faruk Güllü", "tur": "pastane", "url": "https://www.farukgullu.com.tr", "parser": "parse_farukgullu"},

    # ─── Yeni: Baklava uzmanları ───
    {"isletme": "Karaköy Güllüoğlu (Pasta)", "tur": "pastane", "url": "https://www.karakoygulluoglu.com/pastalar", "parser": "parse_karakoygulluoglu"},
    {"isletme": "Hafız Mustafa (Pasta)", "tur": "pastane", "url": "https://online.hafizmustafa.com/pasta", "parser": "parse_hafizmustafa"},
    {"isletme": "Hafız Mustafa (Börek)", "tur": "pastane", "url": "https://online.hafizmustafa.com/borek", "parser": "parse_hafizmustafa"},
    {"isletme": "Baklava Dilim", "tur": "pastane", "url": "https://www.baklavadilim.com", "parser": "parse_baklavadilim"},
    {"isletme": "Güllüoğlu Baklava", "tur": "pastane", "url": "https://www.gulluoglu.com", "parser": "parse_gulluoglu_baklava"},
    {"isletme": "Antep Baklava", "tur": "pastane", "url": "https://www.antepbaklava.com.tr", "parser": "parse_antepbaklava"},
    {"isletme": "Baklava House", "tur": "pastane", "url": "https://www.baklavahouse.com.tr", "parser": "parse_baklavahouse"},
    {"isletme": "Köşkeroğlu Baklava", "tur": "pastane", "url": "https://www.koskeroglu.com.tr", "parser": "parse_koskeroglu"},
    {"isletme": "Halil Baklava", "tur": "pastane", "url": "https://www.halilbaklava.com", "parser": "parse_halilbaklava"},
    {"isletme": "Sait Baklava", "tur": "pastane", "url": "https://www.saitbaklava.com", "parser": "parse_saitbaklava"},
    {"isletme": "Baklavacı Güllü", "tur": "pastane", "url": "https://www.baklavacigullu.com", "parser": "parse_baklavacigullu"},

    # ─── Yeni: Pasta & kek uzmanları ───
    {"isletme": "Divan (Pasta Dilimi)", "tur": "pastane", "url": "https://www.divanpastaneleri.com.tr/pasta-dilimi", "parser": "parse_divan"},
    {"isletme": "Özsüt (Pasta)", "tur": "pastane", "url": "https://www.ozsut.com.tr/pasta", "parser": "parse_ozsut"},
    {"isletme": "Özsüt (Baklava)", "tur": "pastane", "url": "https://www.ozsut.com.tr/baklava", "parser": "parse_ozsut"},
    {"isletme": "Pastane 2000", "tur": "pastane", "url": "https://www.pastane2000.com", "parser": "parse_pastane2000"},
    {"isletme": "İstanbul Pasta", "tur": "pastane", "url": "https://www.istanbulpasta.com", "parser": "parse_istanbulpasta"},
    {"isletme": "Pasta Sepeti", "tur": "pastane", "url": "https://www.pastasepeti.com", "parser": "parse_pastasepeti"},
    {"isletme": "Mavi Pastane", "tur": "pastane", "url": "https://www.mavipastane.com", "parser": "parse_mavipastane"},
    {"isletme": "Pasta Durağı", "tur": "pastane", "url": "https://www.pastaduragi.com", "parser": "parse_pastaduragi"},
    {"isletme": "Erdem Pastanesi", "tur": "pastane", "url": "https://www.erdempastanesi.com", "parser": "parse_erdempastanesi"},
    {"isletme": "Banabaklava", "tur": "pastane", "url": "https://www.banabaklava.com", "parser": "parse_banabaklava"},
    {"isletme": "Pasta Keyfi", "tur": "pastane", "url": "https://www.pastakeyfi.com", "parser": "parse_pastakeyfi"},
    {"isletme": "Sütiş", "tur": "pastane", "url": "https://www.sutis.com.tr", "parser": "parse_sutis"},
    {"isletme": "Saray Muhallebicisi (Pasta)", "tur": "pastane", "url": "https://online.saraymuhallebicisi.com/pasta", "parser": "parse_saraymuhallebicisi"},

    # ─── Yeni: Börek uzmanları ───
    {"isletme": "Tepsi Börek (Su Böreği)", "tur": "pastane", "url": "https://www.tepsiborek.com.tr/su-boregi", "parser": "parse_tepsiborek"},
    {"isletme": "Börekçi Tevfik", "tur": "pastane", "url": "https://www.borekcitevfik.com", "parser": "parse_borekcitevfik"},
    {"isletme": "Üsküdar Börekçisi", "tur": "pastane", "url": "https://www.uskudarborekcisi.com", "parser": "parse_uskudarborekcisi"},
    {"isletme": "Börekçilik", "tur": "pastane", "url": "https://www.borekcilik.com", "parser": "parse_borekcilik"},
    {"isletme": "Sarıyer Börekçisi", "tur": "pastane", "url": "https://www.sariyerborekcisi.com", "parser": "parse_sariyerborekcisi"},
    {"isletme": "Börek Evi", "tur": "pastane", "url": "https://www.borekevi.com.tr", "parser": "parse_borekevi"},
    {"isletme": "Kadıköy Börekçisi", "tur": "pastane", "url": "https://www.kadikoyborekcisi.com", "parser": "parse_kadikoyborekcisi"},

    # ─── Yeni: Simit & unlu mamul ───
    {"isletme": "Simit Sarayı", "tur": "pastane", "url": "https://www.simitsarayi.com.tr", "parser": "parse_simitsarayi"},
    {"isletme": "Simitçi", "tur": "pastane", "url": "https://www.simitci.com.tr", "parser": "parse_simitci"},
    {"isletme": "TazeMasa (Pasta)", "tur": "pastane", "url": "https://www.tazemasa.com/pasta-323", "parser": "parse_tazemasa"},
    {"isletme": "TazeMasa (Börek)", "tur": "pastane", "url": "https://www.tazemasa.com/borek-324", "parser": "parse_tazemasa"},
    {"isletme": "Unlu Mamul", "tur": "pastane", "url": "https://www.unlumamul.com.tr", "parser": "parse_unlumamul"},
    {"isletme": "Fırın Express", "tur": "pastane", "url": "https://www.firinexpress.com", "parser": "parse_firinexpress"},

    # ─── Yeni: Ek kategori sayfaları ───
    {"isletme": "Tarihi Karaköy Fırını (Pasta)", "tur": "pastane", "url": "https://www.tarihikarakoyfirini.com.tr/pastalar-12", "parser": "parse_tarihikarakoyfirini"},
    {"isletme": "Tarihi Karaköy Fırını (Su Böreği)", "tur": "pastane", "url": "https://www.tarihikarakoyfirini.com.tr/su-boregi", "parser": "parse_tarihikarakoyfirini"},
    {"isletme": "Karaköy Güllüoğlu (Şöbiyet)", "tur": "pastane", "url": "https://www.karakoygulluoglu.com/sobiyet", "parser": "parse_karakoygulluoglu"},
    {"isletme": "Karaköy Güllüoğlu (Burma)", "tur": "pastane", "url": "https://www.karakoygulluoglu.com/sarali-burma-baklava", "parser": "parse_karakoygulluoglu"},
    {"isletme": "Hafız Mustafa (Şöbiyet)", "tur": "pastane", "url": "https://online.hafizmustafa.com/sobiyet", "parser": "parse_hafizmustafa"},
    {"isletme": "Hafız Mustafa (Burma)", "tur": "pastane", "url": "https://online.hafizmustafa.com/burma", "parser": "parse_hafizmustafa"},
    {"isletme": "Saray Muhallebicisi (Su Böreği)", "tur": "pastane", "url": "https://online.saraymuhallebicisi.com/su-boregi", "parser": "parse_saraymuhallebicisi"},
    {"isletme": "Saray Muhallebicisi (Baklava)", "tur": "pastane", "url": "https://online.saraymuhallebicisi.com/baklava", "parser": "parse_saraymuhallebicisi"},
    {"isletme": "Divan (Baklava)", "tur": "pastane", "url": "https://www.divanpastaneleri.com.tr/baklava", "parser": "parse_divan"},
    {"isletme": "Divan (Börek)", "tur": "pastane", "url": "https://www.divanpastaneleri.com.tr/borek", "parser": "parse_divan"},
    {"isletme": "Özsüt (Börek)", "tur": "pastane", "url": "https://www.ozsut.com.tr/borek", "parser": "parse_ozsut"},
    {"isletme": "Liva (Baklava)", "tur": "pastane", "url": "https://www.livapastacilik.com/baklava", "parser": "parse_liva"},
    {"isletme": "Liva (Su Böreği)", "tur": "pastane", "url": "https://www.livapastacilik.com/su-boregi", "parser": "parse_liva"},
    {"isletme": "Liva (Pasta)", "tur": "pastane", "url": "https://www.livapastacilik.com/pasta", "parser": "parse_liva"},
    {"isletme": "Misbaşak (Baklava)", "tur": "pastane", "url": "https://www.misbasakonline.com/baklava", "parser": "parse_misbasak"},
    {"isletme": "Misbaşak (Pasta)", "tur": "pastane", "url": "https://www.misbasakonline.com/pasta", "parser": "parse_misbasak"},
    {"isletme": "Şireli (Baklava)", "tur": "pastane", "url": "https://sirelibaklava.com.tr/products/baklava", "parser": "parse_sirelibaklava"},
    {"isletme": "Sini Börek (Baklava)", "tur": "pastane", "url": "https://siniborek.com.tr/baklava", "parser": "parse_siniborek"},
    {"isletme": "Cumba (Baklava)", "tur": "pastane", "url": "https://cumbabaklava.com/baklava", "parser": "parse_cumba"},
    {"isletme": "Tepsi Börek (Baklava)", "tur": "pastane", "url": "https://www.tepsiborek.com.tr/baklava", "parser": "parse_tepsiborek"},
    {"isletme": "Faruk Güllü (Pasta)", "tur": "pastane", "url": "https://www.farukgullu.com.tr/pasta", "parser": "parse_farukgullu"},
    {"isletme": "Faruk Güllü (Börek)", "tur": "pastane", "url": "https://www.farukgullu.com.tr/borek", "parser": "parse_farukgullu"},
    {"isletme": "Ankara Pasta (Baklava)", "tur": "pastane", "url": "https://www.ankarapasta.com/baklava", "parser": "parse_ankarapasta"},
    {"isletme": "Ankara Pasta (Börek)", "tur": "pastane", "url": "https://www.ankarapasta.com/borek", "parser": "parse_ankarapasta"},
    {"isletme": "Pastannecim (Baklava)", "tur": "pastane", "url": "https://www.pastannecim.com.tr/baklava", "parser": "parse_pastannecim"},
    {"isletme": "Pastannecim (Börek)", "tur": "pastane", "url": "https://www.pastannecim.com.tr/borek", "parser": "parse_pastannecim"},
    {"isletme": "Zahire (Baklava)", "tur": "pastane", "url": "https://www.zahirepastanesi.com/baklava", "parser": "parse_zahire"},
    {"isletme": "Zahire (Börek)", "tur": "pastane", "url": "https://www.zahirepastanesi.com/borek", "parser": "parse_zahire"},
    {"isletme": "Linaria (Baklava)", "tur": "pastane", "url": "https://www.linaria.com.tr/baklava", "parser": "parse_linaria"},
    {"isletme": "Linaria (Börek)", "tur": "pastane", "url": "https://www.linaria.com.tr/borek", "parser": "parse_linaria"},
    {"isletme": "Çelebioğulları (Baklava)", "tur": "pastane", "url": "https://www.celebiogullari.com.tr/baklava", "parser": "parse_celebiogullari"},
    {"isletme": "Özgür (Börek)", "tur": "pastane", "url": "https://ozgurunlumamulleri.com/borek-cesitleri", "parser": "parse_ozgurunlu"},
    {"isletme": "Özgür (Açma)", "tur": "pastane", "url": "https://ozgurunlumamulleri.com/acma-cesitleri", "parser": "parse_ozgurunlu"},
]


def _tek_kaynak_tara(kaynak):
    parser_adi = kaynak["parser"]
    url = kaynak["url"]
    tur = kaynak["tur"]
    try:
        if tur == "esnaf_odasi_pdf":
            pdf_bytes = _pdf_cek(url)
            if pdf_bytes:
                parser_fn = globals().get(parser_adi)
                if parser_fn:
                    sonuclar = parser_fn(pdf_bytes, url)
                    if sonuclar:
                        return kaynak["isletme"], sonuclar, True
        else:
            response = _sayfa_cek(url)
            if response:
                parser_fn = globals().get(parser_adi)
                if parser_fn:
                    sonuclar = parser_fn(response.content, url)
                    if sonuclar:
                        return kaynak["isletme"], sonuclar, True
    except Exception:
        pass
    return kaynak["isletme"], [], False


def tum_kaynaklari_tara(ilerleme_callback=None):
    """Tüm kaynakları paralel olarak tarar ve fiyat verilerini toplar."""
    tum_veriler = []
    basarili_sayisi = 0
    basarisiz_sayisi = 0
    detaylar = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_kaynak = {executor.submit(_tek_kaynak_tara, k): k for k in KAYNAKLAR}
        tamamlanan = 0
        for future in as_completed(future_to_kaynak):
            tamamlanan += 1
            isletme, sonuclar, basarili = future.result()
            if basarili and sonuclar:
                tum_veriler.extend(sonuclar)
                basarili_sayisi += 1
                detaylar.append({"isletme": isletme, "kayit": len(sonuclar), "durum": "basarili"})
            else:
                basarisiz_sayisi += 1
            if ilerleme_callback:
                ilerleme_callback(tamamlanan, len(KAYNAKLAR), isletme)

    if ilerleme_callback:
        ilerleme_callback(len(KAYNAKLAR), len(KAYNAKLAR), "Tamamlandı")

    return tum_veriler, basarili_sayisi, basarisiz_sayisi, detaylar
