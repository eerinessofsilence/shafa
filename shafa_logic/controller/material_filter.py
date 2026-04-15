import difflib
import json
import re
from pathlib import Path
from typing import List, Optional

try:
    import Levenshtein  # type: ignore
except ImportError:  # pragma: no cover - exercised via fallback helper
    Levenshtein = None


def _distance(left: str, right: str) -> int:
    if Levenshtein is not None:
        return Levenshtein.distance(left, right)

    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous_row = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current_row = [i]
        for j, right_char in enumerate(right, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (left_char != right_char)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


MATERIALS_PATH = Path(__file__).resolve().parent.parent / "data" / "materials_compact.json"

with MATERIALS_PATH.open("r", encoding="utf-8") as f:
    materials = json.load(f)

FABRIC_DICT = {f["title"].lower(): int(fid) for fid, f in materials.items()}
MATERIAL_LABEL_PATTERN = re.compile(
    r"(?:Тканина|Матеріал|Материал)\s*:\s*(.+?)(?:\n|$)",
    flags=re.IGNORECASE,
)
MATERIAL_WORD_ALIASES = {
    "коттон": "котон",
    "cotton": "бавовна",
    "шерсть": "вовна",
    "шерстяна": "вовна",
    "шерстяний": "вовна",
    "шерстяне": "вовна",
    "шерстяные": "вовна",
    "шерстяное": "вовна",
    "шерстяной": "вовна",
    "шерстяная": "вовна",
    "шерстяні": "вовна",
    "шерстяний": "вовна",
    "эко": "еко",
    "кожа": "шкіра",
    "кожа": "шкіра",
    "искусственная": "штучна",
    "искусственный": "штучний",
    "искусственное": "штучне",
    "натуральная": "натуральна",
    "натуральный": "натуральний",
    "натуральное": "натуральне",
    "лен": "льон",
    "лён": "льон",
    "вискоза": "віскоза",
    "полиэстер": "поліестер",
    "полиамид": "поліамід",
    "трикотажный": "трикотаж",
    "трикотажна": "трикотаж",
    "трикотажне": "трикотаж",
    "трикотажні": "трикотаж",
    "шелк": "шовк",
    "шелковый": "шовк",
    "замш": "замша",
}


def _normalize_material_part(part: str) -> str:
    normalized = part.strip().lower()
    normalized = normalized.replace("ё", "е").replace("`", "'")
    normalized = re.sub(r"\d+[%]?", " ", normalized)
    normalized = re.sub(r"[^\w\s']", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .;:'")
    words = [MATERIAL_WORD_ALIASES.get(word, word) for word in normalized.split()]
    normalized = " ".join(words)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _candidate_materials(slug: Optional[str]) -> dict[str, dict]:
    if not slug:
        return materials
    return {fid: mat for fid, mat in materials.items() if slug in mat["slugs"]}


def _build_normalized_candidate_index(candidates: dict[str, dict]) -> dict[str, int]:
    normalized_index: dict[str, int] = {}
    for fid, mat in candidates.items():
        normalized_title = _normalize_material_part(mat["title"])
        normalized_index.setdefault(normalized_title, int(fid))
    return normalized_index


def _find_by_exact_or_fuzzy(
    part: str,
    candidates: dict[str, dict],
    normalized_index: dict[str, int],
) -> Optional[int]:
    for fid, mat in candidates.items():
        if part == mat["title"].lower():
            return int(fid)

    exact_normalized_match = normalized_index.get(part)
    if exact_normalized_match is not None:
        return exact_normalized_match

    for normalized_title, fid in normalized_index.items():
        if normalized_title and (
            normalized_title in part.split(" / ")
            or normalized_title in part
            or part in normalized_title
        ):
            return fid

    candidate_titles = list(normalized_index.keys())
    cutoff = 0.7 if len(part) > 5 else 0.5
    matches = difflib.get_close_matches(part, candidate_titles, n=1, cutoff=cutoff)
    if matches:
        return normalized_index.get(matches[0])
    return None


def _find_by_distance(
    part: str,
    normalized_index: dict[str, int],
) -> Optional[int]:
    best_fid = None
    best_dist = float("inf")
    max_dist = 1 if len(part) <= 5 else 2

    for normalized_title, fid in normalized_index.items():
        distance = _distance(part, normalized_title)
        if distance <= max_dist and distance < best_dist:
            best_dist = distance
            best_fid = fid

    return best_fid

def extract_fabric_ids_from_description(description: str, slug: Optional[str] = None) -> List[int]:
    match = MATERIAL_LABEL_PATTERN.search(description)
    if not match:
        return []

    fabric_text = match.group(1).lower().strip()
    parts = re.split(r"[,/\-]", fabric_text)  # разделители: запятая, слеш, тире
    result_ids = []
    candidates = _candidate_materials(slug)
    if not candidates:
        return []
    normalized_index = _build_normalized_candidate_index(candidates)

    for part in parts:
        part = _normalize_material_part(part)
        if not part:
            continue

        exact_or_fuzzy_match = _find_by_exact_or_fuzzy(part, candidates, normalized_index)
        if exact_or_fuzzy_match is not None:
            result_ids.append(exact_or_fuzzy_match)
            continue

        best_fid = _find_by_distance(part, normalized_index)
        if best_fid is not None:
            result_ids.append(best_fid)

    return list(dict.fromkeys(result_ids))
