import json
import re
import difflib
import Levenshtein
from typing import List

# Загружаем материалы из JSON
with open("materials_compact.json", "r", encoding="utf-8") as f:
    materials = json.load(f)  # структура: {id: {"title": str, "slugs": [str,...]}}

# Создаем словарь для быстрого поиска по title
FABRIC_DICT = {f["title"].lower(): int(fid) for fid, f in materials.items()}

def extract_fabric_ids_from_description(description: str, slug: str | None = None) -> List[int]:
    """
    Извлекает список ID тканей из описания по указанному slug.
    Поддерживает точное совпадение, fuzzy match и Levenshtein distance.
    """
    match = re.search(r"Тканина\s*:\s*(.+?)(?:\n|$)", description, flags=re.IGNORECASE)
    if not match:
        return []

    fabric_text = match.group(1).lower().strip()
    parts = re.split(r"[,/\-]", fabric_text)  # разделители: запятая, слеш, тире
    result_ids = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 1) Точное совпадение по title + slug
        for fid, mat in materials.items():
            if slug and slug not in mat["slugs"]:
                continue
            if part == mat["title"].lower() and int(fid) not in result_ids:
                result_ids.append(int(fid))

        # 2) fuzzy match через difflib
        cutoff = 0.7 if len(part) > 5 else 0.5
        matches = difflib.get_close_matches(part, FABRIC_DICT.keys(), n=1, cutoff=cutoff)
        if matches:
            fid = FABRIC_DICT[matches[0]]
            if (not slug or slug in materials[str(fid)]["slugs"]) and fid not in result_ids:
                result_ids.append(fid)

        # 3) Levenshtein distance
        for fid, mat in materials.items():
            if slug and slug not in mat["slugs"]:
                continue
            distance = Levenshtein.distance(part, mat["title"].lower())
            max_dist = 1 if len(part) <= 5 else 2
            if distance <= max_dist and int(fid) not in result_ids:
                result_ids.append(int(fid))

    return result_ids

# ------------------- Пример использования -------------------

if __name__ == "__main__":
    # описание товара
    desc = "Тканина: джинс-катон"
    slug = "verhnyaya-odezhda/plashi"

    ids = extract_fabric_ids_from_description(desc, slug)
    print("Найденные ID:", ids)