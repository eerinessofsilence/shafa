import json
from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from core.context import new_context_with_storage, storage_state_has_cookies
from core.core import get_csrftoken_from_context, base_headers, read_response_json
from data.const import HEADLESS, REFERER_URL, STORAGE_STATE_PATH, API_V5_URL

# Категории для парсинга
SLUGS_SET = (
    "verhnyaya-odezhda/palto", 
    "verhnyaya-odezhda/palto", 
    "verhnyaya-odezhda/plashi", 
    "verhnyaya-odezhda/kurtki", 
    "verhnyaya-odezhda/shuby", 
    "verhnyaya-odezhda/zhiletki", 
    "verhnyaya-odezhda/pidzhaki-i-zhakety", "verhnyaya-odezhda/puhoviki", "verhnyaya-odezhda/parki", "verhnyaya-odezhda/dublenki", "verhnyaya-odezhda/dozhdeviki", "verhnyaya-odezhda/vetrovki", "platya/mini", "platya/midi", "platya/maksi", "platya/vechernie", "platya/svadebnye", "platya/sarafany", "platya/tuniki", "yubki/mini", "yubki/midi", "yubki/maksi", "mayki-i-futbolki/futbolki", "mayki-i-futbolki/mayki", "mayki-i-futbolki/polo", "mayki-i-futbolki/topy", "rubashki-i-bluzy/rubashki", "rubashki-i-bluzy/bluzy", "rubashki-i-bluzy/vyshivanki", "kofty/dzhempery", "kofty/svitery", "kofty/kardigany", "kofty/vodolazki", "kofty/svitshoty", "kofty/hudi", "kofty/pulovery", "kofty/tolstovky", "kofty/nakidki", "kofty/bolero", "kofty/poncho", "kofty/reglan", "kofty/longslivy", "kofty/zhilety", "nizhnee-bele-i-kupalniki/lifchiki", "nizhnee-bele-i-kupalniki/trusiki", "nizhnee-bele-i-kupalniki/komplekty", "nizhnee-bele-i-kupalniki/kupalniki", "nizhnee-bele-i-kupalniki/noski", "nizhnee-bele-i-kupalniki/bodi", "nizhnee-bele-i-kupalniki/korsety", "nizhnee-bele-i-kupalniki/chulki", "nizhnee-bele-i-kupalniki/kolgotki", "nizhnee-bele-i-kupalniki/penyuary", "nizhnee-bele-i-kupalniki/termobelye", "nizhnee-bele-i-kupalniki/portupei", "nizhnee-bele-i-kupalniki/eroticheskoye", "nizhnee-bele-i-kupalniki/eroticheskiye-kostyumy", "nizhnee-bele-i-kupalniki/belyevyye-mayki", "nizhnee-bele-i-kupalniki/aksessuary", "sport-otdyh/sportivnyye-kostyumy", "sport-otdyh/sportivnyye-shtany", "sport-otdyh/losiny", "sport-otdyh/shorty", "sport-otdyh/topy", "sport-otdyh/kofty", "sport-otdyh/mayki", "sport-otdyh/kapri", "sport-otdyh/kombinezony", "sport-otdyh/belye", "sport-otdyh/gornolyzhnyye/kurtki", "sport-otdyh/gornolyzhnyye/kostyumy", "sport-otdyh/gornolyzhnyye/shtany", "sport-otdyh/gornolyzhnyye/kombinezony", "zhenskie-kostyumy/kostyumy-s-platem", "zhenskie-kostyumy/kostyumy-s-shortami", "zhenskie-kostyumy/kostyumy-s-yubkoj", "zhenskie-kostyumy/bryuchnye-kostyumy", "zhenskie-kombinezony/dzhinsovye-kombinezony", "zhenskie-kombinezony/bryuchnye-kombinezony", "zhenskie-kombinezony/kombinezony-s-shortami", "odezhda-dlya-doma-i-sna/domashnyaya-odezhda", "odezhda-dlya-doma-i-sna/pizhamy", "odezhda-dlya-doma-i-sna/nochnushki", "odezhda-dlya-doma-i-sna/halaty", "odezhda-dlya-doma-i-sna/masky-dlya-sna", "odezhda-dlya-doma-i-sna/kigurumi", "specodezhda/sfera-obsluzhivaniya", "specodezhda/medicinskaya", "specodezhda/rabochaya", "specodezhda/zashchitnaya", "specodezhda/akademicheskaya", "specodezhda/formennaya", "dlya-beremennyh/verhnyaya-odezhda", "dlya-beremennyh/platya", "dlya-beremennyh/sarafany", "dlya-beremennyh/futbolki", "dlya-beremennyh/dzhinsy", "dlya-beremennyh/shtany", "dlya-beremennyh/bele/kolgoty", "dlya-beremennyh/bele/bandazhi", "dlya-beremennyh/bele/trusy", "dlya-beremennyh/bele/byustgaltery", "dlya-beremennyh/bele/komplekty", "dlya-beremennyh/bele/kupalnyky", "dlya-beremennyh/bele/halaty", "dlya-beremennyh/bele/pizhamy", "dlya-beremennyh/bele/sorochki", "dlya-beremennyh/drugoe", "dlya-beremennyh/losiny", "dlya-beremennyh/kombinezony", "dlya-beremennyh/kofty", "dlya-beremennyh/longslivy", "dlya-beremennyh/yubki", "dlya-beremennyh/rubashki", "shtany/bryuki", "shtany/dzhinsy", "shtany/losiny-i-legginsy", "shtany/shorty", "shtany/bridzhi", )


OUTPUT_FILE = Path("materials.txt")

def get_materials(ctx, csrftoken: str, catalog_slug: str) -> list[dict]:
    """Парсит материалы для конкретного catalog_slug"""
    query = """
    query WEB_CatalogCharacteristics($catalogSlug: String!) {
      catalog(slug: $catalogSlug) {
        id
        characteristics {
          id
          title
          choices {
            id
            title
            __typename
          }
        }
        __typename
      }
    }
    """
    payload = {
        "operationName": "WEB_CatalogCharacteristics",
        "variables": {"catalogSlug": catalog_slug},
        "query": query,
    }

    resp = ctx.request.post(
        API_V5_URL,
        headers={**base_headers(csrftoken), "Accept": "*/*", "Content-Type": "application/json"},
        data=json.dumps(payload),
    )

    data = read_response_json(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    catalog = data.get("data", {}).get("catalog") or {}
    characteristics = catalog.get("characteristics") or []

    materials = []
    seen_ids = set()

    for char in characteristics:
        if char.get("title", "").lower() in ("материал", "матеріал"):
            for choice in char.get("choices") or []:
                material_id = choice.get("id")
                material_title = choice.get("title")
                if not material_id or not material_title:
                    continue
                try:
                    material_id_int = int(material_id)
                except (TypeError, ValueError):
                    continue
                if material_id_int in seen_ids:
                    continue
                seen_ids.add(material_id_int)
                materials.append({
                    "id": material_id_int,
                    "title": material_title,
                    "slug": catalog_slug,
                })
    return materials

def main():
    all_materials = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = new_context_with_storage(browser)
            page = ctx.new_page()
            page.set_default_timeout(60000)

            page.goto(REFERER_URL, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            if not storage_state_has_cookies(STORAGE_STATE_PATH):
                input("Log in in the browser window, then press Enter...")
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("csrftoken not found in context cookies")

            for catalog_slug in SLUGS_SET:
                materials = get_materials(ctx, csrftoken, catalog_slug)
                all_materials.extend(materials)
                print(f"[{catalog_slug}] Materials fetched: {len(materials)}")

        finally:
            browser.close()

    # Сохраняем в TXT как JSON
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_materials, f, ensure_ascii=False, indent=2)

    print(f"Total materials saved: {len(all_materials)} -> {OUTPUT_FILE}")

if __name__ == "__main__":
    main()