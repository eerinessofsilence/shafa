import json
import re
import difflib
import Levenshtein
from typing import List, Optional

# Загружаем материалы из JSON
with open("materials_compact.json", "r", encoding="utf-8") as f:
    materials = json.load(f)  # структура: {id: {"title": str, "slugs": [str,...]}}

# создаем словарь для быстрого поиска по title
FABRIC_DICT = {f["title"].lower(): int(fid) for fid, f in materials.items()}

def extract_fabric_ids_from_description(description: str, slug: Optional[str] = None) -> List[int]:
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

        found = False

        # 1) Точное совпадение
        for fid, mat in materials.items():
            if slug and slug not in mat["slugs"]:
                continue
            if part == mat["title"].lower():
                result_ids.append(int(fid))
                found = True
                break
        if found:
            continue

        # 2) Fuzzy match через difflib
        cutoff = 0.7 if len(part) > 5 else 0.5
        matches = difflib.get_close_matches(part, FABRIC_DICT.keys(), n=1, cutoff=cutoff)
        if matches:
            fid = FABRIC_DICT[matches[0]]
            if (not slug or slug in materials[str(fid)]["slugs"]):
                result_ids.append(fid)
                found = True
                continue

        # 3) Levenshtein distance: ищем ближайший по всем материалам
        best_fid = None
        best_dist = float("inf")
        for fid, mat in materials.items():
            if slug and slug not in mat["slugs"]:
                continue
            distance = Levenshtein.distance(part, mat["title"].lower())
            max_dist = 1 if len(part) <= 5 else 2
            if distance <= max_dist and distance < best_dist:
                best_dist = distance
                best_fid = int(fid)
        if best_fid is not None:
            result_ids.append(best_fid)
        
        if not found and slug:
            best_fid = None
            best_dist = float("inf")
            for fid, mat in materials.items():
                if slug not in mat["slugs"]:
                    continue
                distance = Levenshtein.distance(part, mat["title"].lower())
                if distance < best_dist:
                    best_dist = distance
                    best_fid = int(fid)
            if best_fid is not None:
                result_ids.append(best_fid)

    return result_ids
