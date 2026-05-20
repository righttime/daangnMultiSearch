__version__ = "1.1.0"
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, StreamingResponse, Response
import requests as http_requests
from bs4 import BeautifulSoup
import json
import time
import re
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

app = FastAPI(title="당근마켓 다중 동네 검색")
templates = Jinja2Templates(directory="templates")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.daangn.com/",
}

HISTORY_FILE = os.environ.get("HISTORY_FILE", "/app/data/history.json")

def load_regions():
    with open("regions.json", "r", encoding="utf-8") as f:
        return json.load(f)

ALL_REGIONS = load_regions()

def load_history() -> list:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(history: list):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    # 최대 100개 유지
    history = history[:100]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def add_history(query: str, region_count: int, found: int):
    history = load_history()
    # 같은 검색어가 있으면 업데이트
    for h in history:
        if h["query"] == query:
            h["last_searched"] = datetime.now().isoformat()
            h["region_count"] = region_count
            h["found"] = found
            h["count"] = h.get("count", 0) + 1
            # 맨 앞으로
            history.remove(h)
            history.insert(0, h)
            save_history(history)
            return
    history.insert(0, {
        "query": query,
        "last_searched": datetime.now().isoformat(),
        "region_count": region_count,
        "found": found,
        "count": 1
    })
    save_history(history)

def fetch_page(url: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        resp = http_requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code in (429, 403):
            wait = 2 * (attempt + 1)  # 2s, 4s, 6s
            time.sleep(wait)
            continue
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        return resp.text
    raise Exception(f"429 Too Many Requests after {max_retries} retries")

def parse_items(html: str) -> list:
    items = []
    soup = BeautifulSoup(html, "html.parser")
    
    # time 태그에서 등록 시간 추출
    time_tags = soup.find_all("time", attrs={"datetime": True})
    time_list = [t["datetime"] for t in time_tags]
    
    idx = 0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if data.get("@type") == "ItemList" and "itemListElement" in data:
                for elem in data["itemListElement"]:
                    item = elem.get("item", {})
                    offers = item.get("offers", {})
                    name = item.get("name", "").strip()
                    if not name:
                        continue
                    availability = offers.get("availability", "")
                    if "OutOfStock" in availability:
                        idx += 1
                        continue
                    posted = time_list[idx] if idx < len(time_list) else ""
                    items.append({
                        "name": name,
                        "price": offers.get("price", ""),
                        "url": item.get("url", ""),
                        "image": item.get("image", ""),
                        "posted": posted,
                    })
                    idx += 1
        except (json.JSONDecodeError, KeyError):
            continue
    return items

def search_region(region_id: str, query: str) -> dict:
    name = region_id.rsplit("-", 1)[0] if "-" in region_id else region_id
    url = f"https://www.daangn.com/kr/buy-sell/?in={region_id}&search={query}"
    try:
        html = fetch_page(url)
        items = parse_items(html)
        return {"region": name, "region_id": region_id, "items": items, "error": None}
    except Exception as e:
        return {"region": name, "region_id": region_id, "items": [], "error": str(e)}

@app.get("/")
async def index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache"})

@app.get("/regions.json")
async def get_all_regions():
    content = json.dumps(ALL_REGIONS, ensure_ascii=False)
    return Response(content=content, media_type="application/json; charset=utf-8")

@app.get("/history")
async def get_history():
    history = load_history()
    return Response(content=json.dumps(history, ensure_ascii=False), media_type="application/json; charset=utf-8")

@app.delete("/history")
async def clear_history():
    save_history([])
    return Response(content=json.dumps({"ok": True}, ensure_ascii=False), media_type="application/json; charset=utf-8")

@app.get("/explore")
async def explore_regions(lat: float = Query(default=37.309), lng: float = Query(default=126.904)):
    try:
        resp = http_requests.get(
            f"https://www.daangn.com/kr/api/v1/regions/coord?lat={lat}&lng={lng}",
            headers=HEADERS, timeout=10
        )
        data = resp.json()
        regions = {}
        for loc in data.get("locations", []):
            name3 = loc.get("name3", loc.get("name", ""))
            name2 = loc.get("name2", "")
            rid = loc.get("id", "")
            key = f"{name3}-{rid}"
            regions[key] = f"{name3} ({name2})"
        return Response(content=json.dumps({"regions": regions}, ensure_ascii=False), media_type="application/json; charset=utf-8")
    except Exception as e:
        return Response(content=json.dumps({"regions": {}, "error": str(e)}, ensure_ascii=False), media_type="application/json; charset=utf-8")

@app.get("/search/stream")
async def search_stream(query: str = Query(...), idx: str = Query(default=""), regions: str = Query(default="")):
    """SSE 스트리밍 — idx(인덱스) 또는 regions(직접) 지원"""
    region_ids = []
    all_keys = list(ALL_REGIONS.keys())
    
    if idx:
        for i in idx.split(","):
            try:
                region_ids.append(all_keys[int(i.strip())])
            except (ValueError, IndexError):
                pass
    elif regions:
        region_ids = [r.strip() for r in regions.split(",") if r.strip()]
    
    if not region_ids:
        def empty():
            yield f"data: {json.dumps({'type': 'done', 'total': 0}, ensure_ascii=False)}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")
    
    total_regions = len(region_ids)
    
    def generate():
        total_items = 0
        done = 0
        for rid in region_ids:
            try:
                result = search_region(rid, query)
                done += 1
                if result["items"]:
                    total_items += len(result["items"])
                data = json.dumps({
                    "type": "result",
                    "data": result,
                    "progress": {"done": done, "total": total_regions, "found": total_items}
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"
            except Exception as e:
                done += 1
                data = json.dumps({"type": "error", "region_id": rid, "error": str(e)}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            time.sleep(0.3)
        # 히스토리 저장
        add_history(query, total_regions, total_items)
        data = json.dumps({"type": "done", "total": total_items}, ensure_ascii=False)
        yield f"data: {data}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

@app.get("/search")
async def search(query: str = Query(...), regions: str = Query(...)):
    region_ids = [r.strip() for r in regions.split(",") if r.strip()]
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for rid in region_ids:
            future = executor.submit(search_region, rid, query)
            futures[future] = rid
            time.sleep(0.5)
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda x: (-len(x["items"]), x["region"]))
    total = sum(len(r["items"]) for r in results)
    add_history(query, len(region_ids), total)
    content = json.dumps({"query": query, "total": total, "results": results}, ensure_ascii=False)
    return Response(content=content, media_type="application/json; charset=utf-8")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9095)
