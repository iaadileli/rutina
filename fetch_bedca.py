#!/usr/bin/env python3
"""
Descarga el catálogo completo de BEDCA y lo guarda en bedca_completo.csv
Uso: python3 fetch_bedca.py

Requiere: pip install requests
"""

import csv
import re
import time
import sys

try:
    import requests
except ImportError:
    sys.exit("Instala requests: pip install requests")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; nutrition-research/1.0)",
    "Accept": "application/json, text/xml, */*",
})

# ─── OPCIÓN A: API REST de BEDCA ───────────────────────────────────────────
BEDCA_BASE = "https://www.bedca.net/bdpub/procquery.php"

def bedca_food_list():
    """Devuelve lista de (food_id, food_name) vía SOAP/REST de bedca.net"""
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body>"
        '<v1:foodlistsearch xmlns:v1="http://www.bedca.net/bdpub/v1">'
        "<language>es</language>"
        "<food_name></food_name>"   # vacío = todos
        "</v1:foodlistsearch>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    r = SESSION.post(BEDCA_BASE, data=body,
                     headers={"Content-Type": "text/xml; charset=utf-8"},
                     timeout=20)
    r.raise_for_status()
    ids   = re.findall(r"<food_id>(\d+)</food_id>", r.text)
    names = re.findall(r"<food_name>(.*?)</food_name>", r.text)
    return list(zip(ids, names))

def bedca_food_values(food_id):
    """Devuelve dict con nutrientes para un food_id."""
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body>"
        '<v1:foodvaluesbyid xmlns:v1="http://www.bedca.net/bdpub/v1">'
        "<language>es</language>"
        f"<food_id>{food_id}</food_id>"
        "</v1:foodvaluesbyid>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    r = SESSION.post(BEDCA_BASE, data=body,
                     headers={"Content-Type": "text/xml; charset=utf-8"},
                     timeout=10)
    r.raise_for_status()

    # IDs de nutrientes BEDCA: 1=kcal, 4=proteínas, 5=lípidos, 6=hidratos, 7=fibra, 3=agua
    NUTRIENT_IDS = {"1": "energia_kcal", "4": "proteinas_g",
                    "5": "lipidos_g",    "6": "hidratos_g",
                    "7": "fibra_g",      "3": "agua_g"}
    result = {}
    for cid, cval in re.findall(
            r"<c_class_id>(\d+)</c_class_id>.*?<c_value>([\d.,]*)</c_value>",
            r.text, re.DOTALL):
        if cid in NUTRIENT_IDS:
            try:
                result[NUTRIENT_IDS[cid]] = float(cval.replace(",", "."))
            except ValueError:
                result[NUTRIENT_IDS[cid]] = ""
    return result

# ─── OPCIÓN B: Open Food Facts (fallback, solo productos envasados) ─────────
OFF_BASE = "https://world.openfoodfacts.org"

def off_search_all(pages=50):
    """Descarga las primeras `pages` páginas de productos españoles de OFF."""
    foods = []
    for page in range(1, pages + 1):
        url = (f"{OFF_BASE}/cgi/search.pl?action=process&json=1"
               f"&cc=es&lc=es&page={page}&page_size=200"
               "&fields=code,product_name,nutriments")
        try:
            r = SESSION.get(url, timeout=20)
            data = r.json()
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                nut = p.get("nutriments", {})
                foods.append({
                    "food_id": p.get("code", ""),
                    "nombre":  p.get("product_name", ""),
                    "energia_kcal": nut.get("energy-kcal_100g", ""),
                    "proteinas_g":  nut.get("proteins_100g", ""),
                    "lipidos_g":    nut.get("fat_100g", ""),
                    "hidratos_g":   nut.get("carbohydrates_100g", ""),
                    "fibra_g":      nut.get("fiber_100g", ""),
                    "agua_g":       "",
                })
            print(f"  OFF página {page}: {len(products)} productos")
            time.sleep(0.5)
        except Exception as e:
            print(f"  OFF página {page} falló: {e}")
            break
    return foods

# ───────────────────────────────────────────────────────────────────────────

FIELDNAMES = ["food_id", "nombre", "energia_kcal", "proteinas_g",
              "lipidos_g", "hidratos_g", "fibra_g", "agua_g"]

def save_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"✅ Guardado: {path}  ({len(rows)} alimentos)")


def main():
    # ── Intento 1: BEDCA oficial ────────────────────────────────────────────
    print("▶ Intentando BEDCA oficial (bedca.net)...")
    try:
        food_list = bedca_food_list()
        print(f"  {len(food_list)} alimentos en el catálogo. Descargando nutrientes...")
        rows = []
        for i, (fid, fname) in enumerate(food_list, 1):
            nut = bedca_food_values(fid)
            rows.append({"food_id": fid, "nombre": fname, **nut})
            if i % 100 == 0:
                print(f"  {i}/{len(food_list)}...")
            time.sleep(0.1)
        save_csv(rows, "bedca_completo.csv")
        return
    except Exception as e:
        print(f"  BEDCA falló: {e}")

    # ── Intento 2: Open Food Facts (productos españoles envasados) ──────────
    print("\n▶ Usando Open Food Facts como alternativa...")
    try:
        rows = off_search_all(pages=50)   # ~10 000 productos
        if rows:
            save_csv(rows, "openfoodfacts_es.csv")
            return
    except Exception as e:
        print(f"  OFF falló: {e}")

    print("\n❌ No se pudo descargar ninguna fuente.")
    print("   Descarga manual BEDCA: https://www.bedca.net/bdpub/index.php")
    print("   Descarga manual OFF:   https://world.openfoodfacts.org/data")


if __name__ == "__main__":
    main()
