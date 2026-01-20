import json
import os
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

import requests


REG_API_URL = os.environ.get("REG_API_URL", "https://reg.algocode.ru/_api/reg_2026.json")
TARGET_NAME = os.environ.get("TARGET_NAME", "Сагдуллин Марсель")
TARGET_FORM = int(os.environ.get("TARGET_FORM", "11"))

# Keep a short cache to avoid hammering the upstream.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "30"))


INDEX_HTML = """<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Место</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0b0f19;
        color: #e8eefc;
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      }
      #place {
        font-size: clamp(96px, 20vw, 260px);
        font-weight: 800;
        letter-spacing: -0.04em;
        line-height: 1;
      }
      #status { margin-top: 14px; font-size: 14px; opacity: 0.75; }
    </style>
  </head>
  <body>
    <div>
      <div id="place">—</div>
      <div id="status"></div>
    </div>
    <script>
      const placeEl = document.getElementById("place");
      const statusEl = document.getElementById("status");
      async function refresh() {
        try {
          statusEl.textContent = "обновление…";
          const r = await fetch("/api/place", { cache: "no-store" });
          const j = await r.json();
          placeEl.textContent = j.place ?? "не найден";
          statusEl.textContent = new Date().toLocaleTimeString("ru-RU");
        } catch (e) {
          placeEl.textContent = "ошибка";
          statusEl.textContent = "";
        }
      }
      refresh();
      setInterval(refresh, 30_000);
    </script>
  </body>
</html>
"""


@dataclass
class Cache:
    fetched_at: float = 0.0
    data: Optional[list[dict[str, Any]]] = None


cache = Cache()


def _fetch_data() -> list[dict[str, Any]]:
    global cache
    now = time.time()
    if cache.data is not None and (now - cache.fetched_at) < CACHE_TTL_SECONDS:
        return cache.data

    r = requests.get(REG_API_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError("Unexpected API response: expected a JSON list")

    cache = Cache(fetched_at=now, data=data)
    return data


def _sort_key(row: dict[str, Any]) -> tuple:
    # Matches reg.algocode.ru sorting:
    # sumRank desc, disqual asc, automatic asc, form asc, name asc
    sum_rank = row.get("sumRank", 0)
    disqual = bool(row.get("disqual", False))
    automatic = bool(row.get("automatic", False))
    form = row.get("form", -1)
    name = row.get("name", "")
    return (-float(sum_rank), int(disqual), int(automatic), int(form), str(name))


def _compute_place(rows: list[dict[str, Any]], *, name: str, form: int) -> Optional[int]:
    # Filter to target form (class)
    filtered = [r for r in rows if r.get("form") == form]
    filtered.sort(key=_sort_key)

    non_disqual_i = 0
    last_non_disqual_sum_rank: float = -1.0
    last_place: Optional[int] = None

    def norm(s: str) -> str:
        return " ".join(str(s).strip().lower().split())

    target = norm(name)

    for row in filtered:
        sum_rank = float(row.get("sumRank", 0.0))
        disqual = bool(row.get("disqual", False))

        # Same condition as in showData() on reg.algocode.ru:
        # if sumRank changed and NOT disqual => show (nonDisqualI + 1), else blank.
        if (abs(sum_rank - last_non_disqual_sum_rank) > 1e-5) and (not disqual):
            last_non_disqual_sum_rank = sum_rank
            last_place = non_disqual_i + 1

        row_name = norm(row.get("name", ""))
        if row_name == target or row_name.startswith(target + " "):
            return last_place

        if not disqual:
            non_disqual_i += 1

    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, *, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, INDEX_HTML.encode("utf-8"), content_type="text/html; charset=utf-8")
            return

        if self.path == "/api/place":
            try:
                rows = _fetch_data()
                place = _compute_place(rows, name=TARGET_NAME, form=TARGET_FORM)
                payload = {
                    "name": TARGET_NAME,
                    "form": TARGET_FORM,
                    "place": place,
                    "source": REG_API_URL,
                }
                self._send(
                    200,
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    content_type="application/json; charset=utf-8",
                )
            except Exception as e:
                self._send(
                    500,
                    json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"),
                    content_type="application/json; charset=utf-8",
                )
            return

        self._send(404, b"Not found", content_type="text/plain; charset=utf-8")


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Listening on http://localhost:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
