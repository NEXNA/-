"""Small no-key web search helper (Sogou, fallback 360)."""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _clean(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split()).strip()


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read().decode("utf-8", "replace")


def _sogou(query: str, limit: int) -> list[dict]:
    page = _fetch("https://www.sogou.com/web?query=" + urllib.parse.quote(query))
    blocks = re.findall(
        r'<h3 class="vr-title.*?</h3>.*?(?=<h3 class="vr-title|$)',
        page, re.S | re.I,
    )
    results = []
    for block in blocks:
        heading = re.search(r"<h3[^>]*>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not heading:
            continue
        href = html.unescape(heading.group(1))
        if href.startswith("/"):
            href = "https://www.sogou.com" + href
        title = _clean(heading.group(2))
        snippet_match = re.search(
            r'<div[^>]*class="[^"]*space-txt[^"]*"[^>]*>(.*?)</div>', block, re.S
        )
        snippet = _clean(snippet_match.group(1)) if snippet_match else ""
        if title:
            results.append({"title": title, "snippet": snippet[:300], "url": href})
        if len(results) >= limit:
            break
    return results


def _so(query: str, limit: int) -> list[dict]:
    page = _fetch("https://www.so.com/s?q=" + urllib.parse.quote(query))
    results = []
    for match in re.finditer(
        r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)</h3>',
        page, re.S,
    ):
        href = html.unescape(match.group(1))
        if href.startswith("/"):
            href = "https://www.so.com" + href
        title = _clean(match.group(2))
        snippet_match = re.search(r'<p[^>]*class="[^"]*res-desc[^"]*"[^>]*>(.*?)</p>', page[match.start():match.start() + 3000], re.S)
        snippet = _clean(snippet_match.group(1)) if snippet_match else ""
        if title:
            results.append({"title": title, "snippet": snippet[:300], "url": href})
        if len(results) >= limit:
            break
    return results


def search_web(query: str, limit: int = 4) -> list[dict]:
    query = " ".join(str(query or "").split()).strip()[:120]
    if not query:
        return []
    for backend in (_sogou, _so):
        try:
            results = backend(query, limit)
            if results:
                return results
        except Exception:  # noqa: BLE001
            continue
    return []


def format_context(results: list[dict]) -> str:
    if not results:
        return ""
    lines = ["【刚刚检索到的网页摘要】"]
    for item in results[:4]:
        lines.append(f"- {item['title']}：{item['snippet']}")
    lines.append("只在与问题相关时使用这些信息；不确定就说不确定，不要编造来源。")
    return "\n".join(lines)
