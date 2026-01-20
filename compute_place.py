import json
import os
import time
import urllib.request


REG_API_URL = os.environ.get("REG_API_URL", "https://reg.algocode.ru/_api/reg_2026.json")
TARGET_NAME = os.environ.get("TARGET_NAME", "Сагдуллин Марсель")
TARGET_FORM = int(os.environ.get("TARGET_FORM", "11"))
OUT_FILE = os.environ.get("OUT_FILE", "place.json")


def fetch_rows(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Unexpected API response: expected JSON list")
    return data


def sort_key(row: dict) -> tuple:
    # Matches reg.algocode.ru sorting:
    # sumRank desc, disqual asc, automatic asc, form asc, name asc
    sum_rank = float(row.get("sumRank", 0))
    disqual = bool(row.get("disqual", False))
    automatic = bool(row.get("automatic", False))
    form = int(row.get("form", -1))
    name = str(row.get("name", ""))
    return (-sum_rank, int(disqual), int(automatic), form, name)


def norm(s: str) -> str:
    return " ".join(str(s).strip().lower().split())


def compute_place(rows: list[dict], *, name: str, form: int) -> int | None:
    filtered = [r for r in rows if r.get("form") == form]
    filtered.sort(key=sort_key)

    non_disqual_i = 0
    last_non_disqual_sum_rank = -1.0
    last_place: int | None = None

    target = norm(name)

    for row in filtered:
        sum_rank = float(row.get("sumRank", 0.0))
        disqual = bool(row.get("disqual", False))

        if (abs(sum_rank - last_non_disqual_sum_rank) > 1e-5) and (not disqual):
            last_non_disqual_sum_rank = sum_rank
            last_place = non_disqual_i + 1

        row_name = norm(row.get("name", ""))
        if row_name == target or row_name.startswith(target + " "):
            return last_place

        if not disqual:
            non_disqual_i += 1

    return None


def main() -> None:
    rows = fetch_rows(REG_API_URL)
    place = compute_place(rows, name=TARGET_NAME, form=TARGET_FORM)
    payload = {
        "name": TARGET_NAME,
        "form": TARGET_FORM,
        "place": place,
        "source": REG_API_URL,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
