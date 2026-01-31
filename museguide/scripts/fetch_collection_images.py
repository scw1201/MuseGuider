#!/usr/bin/env python3
import argparse
import io
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


@dataclass(frozen=True)
class FetchConfig:
    provider: str
    domain_json: Path
    out_root: Path
    google_key: str | None
    google_cx: str | None
    baidu_cookie: str | None
    force: bool
    delay: float
    only_terms: set[str]
    ratio_target: float
    ratio_tol: float
    min_width: int
    google_num: int
    google_img_size: str
    google_img_type: str
    retries: int
    retry_delay: float
    query_overrides: dict[str, list[str]]


DEFAULT_QUERY_OVERRIDES = {
    "商代后母戊鼎（复制件）": [
        "后母戊鼎",
        "司母戊鼎",
        "Houmuwu Ding",
        "Simuwu Ding",
    ],
    "达·芬奇《蒙娜丽莎》（复制）": [
        "Mona Lisa painting",
        "Leonardo da Vinci Mona Lisa",
    ],
}


def _http_get(url: str, headers: dict[str, str], retries: int, retry_delay: float) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                req, timeout=10, context=ssl._create_unverified_context()
            ) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(retry_delay)
                continue
            raise
    raise RuntimeError("Failed to fetch URL")


def _fetch_baidu_image(query: str, config: FetchConfig) -> tuple[bytes, str | None]:
    params = {
        "tn": "resultjson_com",
        "ipn": "rj",
        "ct": "201326592",
        "fp": "result",
        "ie": "utf-8",
        "oe": "utf-8",
        "word": query,
    }
    url = "https://image.baidu.com/search/acjson?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://image.baidu.com/",
    }
    if config.baidu_cookie:
        headers["Cookie"] = config.baidu_cookie

    raw = _http_get(url, headers, config.retries, config.retry_delay).decode(
        "utf-8", errors="ignore"
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise
        data = json.loads(raw[start : end + 1])

    if isinstance(data, dict) and data.get("antiFlag") == 1:
        raise RuntimeError("Baidu blocked the request; provide a valid cookie.")

    for item in data.get("data", []):
        if not isinstance(item, dict):
            continue
        img_url = item.get("thumbURL") or item.get("middleURL") or item.get("objURL")
        if not img_url:
            continue
        img_bytes = _http_get(
            img_url,
            {"User-Agent": "Mozilla/5.0"},
            config.retries,
            config.retry_delay,
        )
        return img_bytes, None

    raise RuntimeError("No image found")


def _build_google_queries(query: str, overrides: dict[str, list[str]]) -> list[str]:
    raw = query
    cleaned = re.sub(r"[《》]", "", raw)
    cleaned = re.sub(r"[（(].*?[)）]", "", cleaned).strip()
    candidates: list[str] = []
    for override in overrides.get(raw, []):
        if override not in candidates:
            candidates.append(override)
    for q in (raw, cleaned, f"{cleaned} 图片", f"{cleaned} 文物"):
        q = q.strip()
        if q and q not in candidates:
            candidates.append(q)
    return candidates


def _score_candidate(width: int, ratio: float, config: FetchConfig) -> tuple[float, int]:
    ratio_delta = abs(ratio - config.ratio_target)
    width_score = width if width >= config.min_width else int(width * 0.5)
    return (ratio_delta, -width_score)


def _fetch_google_image(query: str, config: FetchConfig) -> tuple[bytes, str | None]:
    if not config.google_key or not config.google_cx:
        raise RuntimeError("Missing Google API key/cx; set GOOGLE_API_KEY and GOOGLE_CSE_ID.")

    for q in _build_google_queries(query, config.query_overrides):
        params = {
            "q": q,
            "cx": config.google_cx,
            "key": config.google_key,
            "searchType": "image",
            "num": config.google_num,
            "imgSize": config.google_img_size,
            "imgType": config.google_img_type,
            "safe": "off",
        }
        url = "https://customsearch.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
        raw = _http_get(url, {"User-Agent": "Mozilla/5.0"}, config.retries, config.retry_delay)
        data = json.loads(raw.decode("utf-8", errors="ignore"))

        items = data.get("items") or []
        if not items:
            continue

        candidates: list[dict[str, object]] = []
        for item in items:
            image_meta = item.get("image") or {}
            width = image_meta.get("width")
            height = image_meta.get("height")
            if not width or not height:
                continue
            ratio = width / height if height else 0
            candidates.append(
                {
                    "link": item.get("link"),
                    "thumb": image_meta.get("thumbnailLink"),
                    "width": int(width),
                    "ratio": float(ratio),
                }
            )

        if not candidates:
            continue

        candidates.sort(key=lambda cand: _score_candidate(int(cand["width"]), float(cand["ratio"]), config))

        for cand in candidates:
            if abs(float(cand["ratio"]) - config.ratio_target) > config.ratio_tol and int(
                cand["width"]
            ) < config.min_width:
                continue
            for url in (cand.get("link"), cand.get("thumb")):
                if not url:
                    continue
                headers_list = [
                    {"User-Agent": "Mozilla/5.0", "Referer": "https://www.google.com/"},
                    {"User-Agent": "Mozilla/5.0"},
                ]
                for headers in headers_list:
                    try:
                        img_bytes = _http_get(
                            str(url), headers, config.retries, config.retry_delay
                        )
                        return img_bytes, None
                    except HTTPError:
                        continue

    raise RuntimeError("No image found")


def _ext_from_content_type(content_type: str | None) -> str:
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    return ".jpg"


def _normalize_ratio(img_bytes: bytes, config: FetchConfig) -> tuple[bytes, str | None]:
    if not PIL_AVAILABLE:
        return img_bytes, None
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            width, height = img.size
            if not width or not height:
                return img_bytes, None
            ratio = width / height
            if abs(ratio - config.ratio_target) <= config.ratio_tol:
                return img_bytes, None

            if ratio > config.ratio_target:
                new_width = int(height * config.ratio_target)
                left = max((width - new_width) // 2, 0)
                box = (left, 0, left + new_width, height)
            else:
                new_height = int(width / config.ratio_target)
                top = max((height - new_height) // 2, 0)
                box = (0, top, width, top + new_height)

            cropped = img.crop(box).convert("RGB")
            out = io.BytesIO()
            cropped.save(out, format="JPEG", quality=92)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return img_bytes, None


def _iter_exhibits(data: dict) -> Iterable[tuple[dict, dict]]:
    for zone in data.get("zones", []):
        yield zone, zone.get("exhibits", [])


def _should_fetch(exhibit: dict, config: FetchConfig) -> bool:
    name = exhibit.get("name", "").strip()
    if not name:
        return False
    if config.only_terms:
        exhibit_id = str(exhibit.get("id", "")).strip()
        if name not in config.only_terms and exhibit_id not in config.only_terms:
            return False
    if exhibit.get("image") and not config.force:
        return False
    return True


def _fetch_image(name: str, config: FetchConfig) -> tuple[bytes, str | None]:
    if config.provider == "google":
        return _fetch_google_image(name, config)
    return _fetch_baidu_image(name, config)


def _load_domain(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_domain(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["baidu", "google"], default="google")
    parser.add_argument("--cookie", help="Baidu cookie string (optional).")
    parser.add_argument("--google-key", help="Google Custom Search API key.")
    parser.add_argument("--google-cx", help="Google Custom Search engine id (cx).")
    parser.add_argument("--force", action="store_true", help="Re-download even if image exists.")
    parser.add_argument("--delay", type=float, default=1.2, help="Seconds to wait between downloads.")
    parser.add_argument("--only", help="Comma-separated exhibit ids or names to fetch.")
    parser.add_argument("--ratio-target", type=float, default=2.0)
    parser.add_argument("--ratio-tol", type=float, default=0.25)
    parser.add_argument("--min-width", type=int, default=1200)
    parser.add_argument("--domain", type=Path, default=Path("museguide/configs/domain_prior.json"))
    parser.add_argument("--out", type=Path, default=Path("frontend/public/imgs/collection"))
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=1.5)
    parser.add_argument("--google-num", type=int, default=6)
    parser.add_argument("--google-img-size", default="xxlarge")
    parser.add_argument("--google-img-type", default="photo")
    args = parser.parse_args()

    only_terms = set()
    if args.only:
        only_terms = {item.strip() for item in args.only.split(",") if item.strip()}

    config = FetchConfig(
        provider=args.provider,
        domain_json=args.domain,
        out_root=args.out,
        google_key=args.google_key or os.getenv("GOOGLE_API_KEY"),
        google_cx=args.google_cx or os.getenv("GOOGLE_CSE_ID"),
        baidu_cookie=args.cookie or os.getenv("BAIDU_COOKIE"),
        force=args.force,
        delay=args.delay,
        only_terms=only_terms,
        ratio_target=args.ratio_target,
        ratio_tol=args.ratio_tol,
        min_width=args.min_width,
        google_num=args.google_num,
        google_img_size=args.google_img_size,
        google_img_type=args.google_img_type,
        retries=args.retries,
        retry_delay=args.retry_delay,
        query_overrides=DEFAULT_QUERY_OVERRIDES,
    )

    data = _load_domain(config.domain_json)
    updated = False

    for zone, exhibits in _iter_exhibits(data):
        zone_id = zone.get("id", "unknown")
        zone_dir = config.out_root / zone_id
        zone_dir.mkdir(parents=True, exist_ok=True)

        for exhibit in exhibits:
            name = exhibit.get("name", "").strip()
            if not _should_fetch(exhibit, config):
                continue

            try:
                img_bytes, content_type = _fetch_image(name, config)
                img_bytes, normalized_type = _normalize_ratio(img_bytes, config)
                if normalized_type:
                    content_type = normalized_type
                ext = _ext_from_content_type(content_type)
            except Exception as exc:
                print(f"[WARN] {name}: {exc}")
                continue

            file_name = f"{exhibit.get('id', name)}{ext}"
            out_path = zone_dir / file_name
            out_path.write_bytes(img_bytes)

            exhibit["image"] = f"/imgs/collection/{zone_id}/{file_name}"
            updated = True
            print(f"[OK] {name} -> {exhibit['image']}")

            time.sleep(config.delay)

    if updated:
        _write_domain(config.domain_json, data)
        print("Updated domain_prior.json with image paths.")
    else:
        print("No updates made.")


if __name__ == "__main__":
    main()
