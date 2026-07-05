import re
import io
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pdfplumber

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

URUN_ES_ANLAMLI = {
    "Simit": ["simit", "tereyağlı simit", "sütlü simit", "pastane simidi", "ankara simidi", "kandil simidi", "çikolatalı simit"],
    "Poğaça": ["poğaça", "pogaca", "peynirli poğaça", "kaşarlı poğaça", "sade poğaça", "patatesli poğaça", "dereotlu poğaça", "sosisli poğaça", "haşhaşlı poğaça", "talaş poğaça"],
    "Açma": ["açma", "acma", "sade açma", "zeytinli açma", "çikolatalı açma", "haşhaşlı açma"],
    "Yaş Pasta": ["yaş pasta", "pasta", "çikolatalı pasta", "meyveli pasta", "karaorman", "blackforest", "mozaik pasta", "rulo pasta", "ekler pasta", "tane pasta"],
    "Baklava": ["baklava", "fıstıklı baklava", "cevizli baklava", "kuru baklava", "şöbiyet", "burma", "sarı burma", "bulgur baklava", "havuç dilimi"],
    "Su Böreği": ["su böreği", "su boregi", "peynirli su böreği", "ıspanaklı su böreği", "tepsi su böreği", "tepsili su böreği"],
}

HARIC_KELIMELER = ["kuru pasta", "kuru kek", "pasta tarifi", "pasta yapımı", "pasta kalıbı", "böreklik", "börekçi"]


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


def _sayfa_cek(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
    except Exception:
        pass
    return None


def _pdf_cek(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# ESNAF / TİCARET ODASI PARSER'LARI
# ─────────────────────────────────────────────────────────────

def parse_itso_simit_pogaca(html_doc, kaynak_url):
    """İnegöl Ticaret ve Sanayi Odası - HTML tablo formatında simit/poğaça/açma tarifesi"""
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
                            sonuclar.append({
                                "isletme": "İnegöl TSO",
                                "kaynak_turu": "Esnaf Odası",
                                "urun": urun,
                                "cekilen_isim": f"{isim} ({gramaj})" if gramaj else isim,
                                "fiyat": fiyat,
                                "kaynak_url": kaynak_url,
                                "cekilme_tarihi": datetime.now().isoformat(),
                            })
    return sonuclar


def parse_kutso_pastacilar(pdf_bytes, kaynak_url):
    """Kütahya TSO - PDF pastacılar azami fiyat tarifesini parse eder"""
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
            eslesmeler = re.findall(r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]+?)\s+(\d+(?:\.\d+)?)\s+(\d+[.,]?\d*)\s*TL?", satir)
            for eslesme in eslesmeler:
                isim = eslesme[0].strip()
                fiyat = fiyat_temizle(eslesme[2] + " TL")
                if fiyat > 0:
                    urun = urun_eslestir(isim)
                    if urun:
                        sonuclar.append({
                            "isletme": "Kütahya TSO",
                            "kaynak_turu": "Esnaf Odası",
                            "urun": urun,
                            "cekilen_isim": isim,
                            "fiyat": fiyat,
                            "kaynak_url": kaynak_url,
                            "cekilme_tarihi": datetime.now().isoformat(),
                        })
    except Exception:
        pass
    return sonuclar


def parse_atonet_pastacilar(pdf_bytes, kaynak_url):
    """Ankara Ticaret Odası - PDF lüks pastacılar azami fiyat tarifesini parse eder"""
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
            eslesmeler = re.findall(r"([A-ZÇĞİÖŞÜa-zçğıöşü\s]+?)\s+(\d+(?:\.\d+)?)\s+(₺\s*\d+[.,]?\d*|\d+[.,]?\d*\s*₺|\d+[.,]?\d*\s*TL)", satir)
            for eslesme in eslesmeler:
                isim = eslesme[0].strip()
                fiyat_metni = eslesme[2]
                fiyat = fiyat_temizle(fiyat_metni)
                if fiyat > 0:
                    urun = urun_eslestir(isim)
                    if urun:
                        sonuclar.append({
                            "isletme": "Ankara TSO",
                            "kaynak_turu": "Esnaf Odası",
                            "urun": urun,
                            "cekilen_isim": isim,
                            "fiyat": fiyat,
                            "kaynak_url": kaynak_url,
                            "cekilme_tarihi": datetime.now().isoformat(),
                        })
    except Exception:
        pass
    return sonuclar


# ─────────────────────────────────────────────────────────────
# PASTANE E-TİCARET SİTESİ PARSER'I (GENEL AMAÇLI)
# ─────────────────────────────────────────────────────────────

_GECERSIZ_KELIMELER = {"sepete ekle", "favorilere ekle", "favori", "incele", "azalt", "artır",
                       "stokta", "tükendi", "yeni", "indirim", "kampanya", "kdv", "dahil",
                       "haric", "kargo", "teslimat", "sepette", "kupon", "puan",
                       "degerlendirme", "yildiz", "★", "az", "cok", "satan"}

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

    for etiket in soup.find_all(["div", "li", "article", "span", "a", "h2", "h3", "h4"]):
        metin = etiket.get_text(" ", strip=True)
        if not metin or len(metin) > 200 or len(metin) < 5:
            continue
        if "₺" not in metin and "TL" not in metin:
            continue

        fiyat_eslesme = re.search(r"(\d{2,}(?:[.,]\d{1,2})?|\d{1,3}(?:\.\d{3})+[.,]\d{1,2})\s*[₺TL]", metin)
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
            temiz_isim = metin[:80]

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
            "kaynak_url": kaynak_url,
            "cekilme_tarihi": datetime.now().isoformat(),
        })

    return sonuclar


def parse_tarihikarakoyfirini(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Tarihi Karakoy Firini")

def parse_karakoygulluoglu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Karakoy Gulluoglu")

def parse_hafizmustafa(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Hafiz Mustafa 1864")

def parse_saraymuhallebicisi(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Saray Muhallebicisi")

def parse_divan(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Divan Pastaneleri")

def parse_ozsut(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Ozsut")

def parse_liva(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Liva Pastacilik")

def parse_zahire(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Zahire Pastanesi")

def parse_linaria(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Linaria")

def parse_pastannecim(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Pastannecim")

def parse_ankarapasta(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Ankara Pasta")

def parse_misbasak(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Misbasak")

def parse_sirelibaklava(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sireli Baklava")

def parse_siniborek(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Sini Borek")

def parse_celebiogullari(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Celebiogullari")

def parse_cumba(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Cumba Baklava")

def parse_tazemasa(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "TazeMasa")

def parse_ozgurunlu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Ozgur Unlu Mamulleri")

def parse_tepsiborek(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Tepsi Borek")

def parse_farukgullu(html_doc, kaynak_url):
    return _genel_pastane_parser(html_doc, kaynak_url, "Faruk Gullu")


# ─────────────────────────────────────────────────────────────
# KAYNAK LİSTESİ
# ─────────────────────────────────────────────────────────────

KAYNAKLAR = [
    # Esnaf / Ticaret Odaları
    {"isletme": "İnegöl TSO", "tur": "esnaf_odasi_tablo", "url": "https://www.itso.org.tr/simit-acma-pogaca-vb", "parser": "parse_itso_simit_pogaca"},
    {"isletme": "Kütahya TSO", "tur": "esnaf_odasi_pdf", "url": "https://www.kutso.org.tr/kutso-storage/page/49/qAGrYJTPQnGFuKpNU9rfgSiZl7KSUZbPCjiQs1KX.pdf", "parser": "parse_kutso_pastacilar"},
    {"isletme": "Ankara TSO", "tur": "esnaf_odasi_pdf", "url": "https://www.atonet.org.tr/Uploads/Birimler/Internet/Hizmetlerimiz/Azami%20Fiyat%20Tarifeleri/2025_azami_fiyat_tarifesi/2025_pasta_cikolata_tatlicilar.pdf", "parser": "parse_atonet_pastacilar"},

    # Pastane e-ticaret siteleri
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
]


def tum_kaynaklari_tara(ilerleme_callback=None):
    """Tüm kaynakları tarar ve fiyat verilerini toplar."""
    tum_veriler = []
    basarili_sayisi = 0
    basarisiz_sayisi = 0

    for i, kaynak in enumerate(KAYNAKLAR):
        if ilerleme_callback:
            ilerleme_callback(i, len(KAYNAKLAR), kaynak["isletme"])

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
                            tum_veriler.extend(sonuclar)
                            basarili_sayisi += 1
                        else:
                            basarisiz_sayisi += 1
                    else:
                        basarisiz_sayisi += 1
                else:
                    basarisiz_sayisi += 1
            else:
                response = _sayfa_cek(url)
                if response:
                    parser_fn = globals().get(parser_adi)
                    if parser_fn:
                        sonuclar = parser_fn(response.content, url)
                        if sonuclar:
                            tum_veriler.extend(sonuclar)
                            basarili_sayisi += 1
                        else:
                            basarisiz_sayisi += 1
                    else:
                        basarisiz_sayisi += 1
                else:
                    basarisiz_sayisi += 1
        except Exception:
            basarisiz_sayisi += 1

    if ilerleme_callback:
        ilerleme_callback(len(KAYNAKLAR), len(KAYNAKLAR), "Tamamlandı")

    return tum_veriler, basarili_sayisi, basarisiz_sayisi
