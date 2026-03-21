import json
from playwright.sync_api import BrowserContext
from core.core import base_headers, read_response_json
from data.const import API_V5_URL

def get_materials(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str,
) -> list[dict]:
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
        headers={
            **base_headers(csrftoken),
            "Accept": "*/*",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
    )

    data = read_response_json(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    catalog = data.get("data", {}).get("catalog") or {}
    characteristics = catalog.get("characteristics") or []

    materials: list[dict] = []
    seen_ids: set[int] = set()

    for char in characteristics:
        if char.get("title", "").lower() in ("материал", "матеріал"):
            choices = char.get("choices") or []
            for choice in choices:
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
                    "__typename": choice.get("__typename") or "ProductCharacteristicChoiceType",
                })

    # Можно сохранить в базу или JSON так же, как save_sizes
    # save_sizes(materials, catalog_slug=catalog_slug)
    return materials