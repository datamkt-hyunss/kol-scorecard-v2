"""
scraper.py — KOL Scorecard v2
TikTok & Instagram scraping via Playwright (headless Chromium)
TikTok: views, likes, comments, saves, shares (v2 신규)
Instagram Feed: likes, comments
"""

from __future__ import annotations
import re, time, json, random
from typing import Optional

# ── 유틸 ──────────────────────────────────────────────────
def _parse_num(text: str) -> float:
    """'1.2M' '34.5K' '1,234' 형식 숫자 파싱"""
    if not text:
        return 0.0
    text = text.strip().replace(",", "")
    m = re.match(r"([\d.]+)\s*([KkMmBb]?)", text)
    if not m:
        return 0.0
    val = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":
        val *= 1_000
    elif suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def _normalize_url(url: str, platform: str) -> str:
    if platform == "tiktok":
        url = re.sub(r"\?.*", "", url)
        if not url.startswith("http"):
            url = "https://" + url
    elif platform == "instagram":
        url = url.rstrip("/")
        if not url.startswith("http"):
            url = "https://www.instagram.com/" + url.lstrip("@/")
    return url


# ═══════════════════════════════════════════════════════════
# TikTok Scraper
# ═══════════════════════════════════════════════════════════
def scrape_tiktok(
    profile_url: str,
    n_posts: int = 10,
    skip_pinned: bool = True,
) -> dict:
    """
    TikTok 프로필에서 최근 n개 게시물의 평균 지표 반환.
    Returns:
        {
          "views": float, "likes": float, "comments": float,
          "saves": float, "shares": float,   # ← v2 신규
          "posts_scraped": int, "error": str|None
        }
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return _error_result("playwright not installed")

    url = _normalize_url(profile_url, "tiktok")
    result = {
        "views": 0.0, "likes": 0.0, "comments": 0.0,
        "saves": 0.0, "shares": 0.0,
        "posts_scraped": 0, "error": None,
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()

            # 프로필 페이지 로드
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)

            # 비디오 카드 수집
            video_cards = page.query_selector_all('[data-e2e="user-post-item"]')
            if not video_cards:
                video_cards = page.query_selector_all('div[class*="DivItemContainerV2"]')
            if not video_cards:
                video_cards = page.query_selector_all('a[href*="/video/"]')

            collected = []
            for card in video_cards:
                if len(collected) >= n_posts:
                    break

                # 핀 게시물 스킵
                if skip_pinned:
                    pin_indicator = card.query_selector('[data-e2e="video-card-badge"]')
                    if not pin_indicator:
                        pin_indicator = card.query_selector('[class*="PinnedVideoLabel"]')
                    if pin_indicator:
                        continue

                # 조회수 (썸네일 위 숫자)
                views_el = card.query_selector('[data-e2e="video-views"]')
                if not views_el:
                    views_el = card.query_selector('strong[class*="StrongVideoCount"]')
                views_text = views_el.inner_text() if views_el else "0"

                collected.append({
                    "card": card,
                    "views_text": views_text,
                    "url": None,
                })

                # 비디오 URL 추출
                link_el = card.query_selector("a[href*='/video/']")
                if link_el:
                    collected[-1]["url"] = link_el.get_attribute("href")

            if not collected:
                result["error"] = "게시물을 찾을 수 없습니다 (핀 제외 후 0건)"
                browser.close()
                return result

            # 각 게시물 상세 페이지에서 좋아요·댓글·저장·공유 수집
            totals = {"views": 0.0, "likes": 0.0, "comments": 0.0,
                      "saves": 0.0, "shares": 0.0}
            scraped = 0

            for item in collected:
                post_url = item["url"]
                if not post_url:
                    continue
                if not post_url.startswith("http"):
                    post_url = "https://www.tiktok.com" + post_url

                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=25_000)
                    page.wait_for_timeout(random.randint(1500, 2500))

                    def _get_count(selectors):
                        for sel in selectors:
                            el = page.query_selector(sel)
                            if el:
                                txt = el.inner_text().strip()
                                if txt:
                                    return _parse_num(txt)
                        return 0.0

                    views = _get_count([
                        '[data-e2e="video-views"]',
                        'strong[data-e2e="video-views"]',
                        '[class*="SpanCount"][aria-label*="views"]',
                    ]) or _parse_num(item["views_text"])

                    likes = _get_count([
                        '[data-e2e="like-count"]',
                        'strong[data-e2e="like-count"]',
                        'button[aria-label*="like"] strong',
                    ])
                    comments = _get_count([
                        '[data-e2e="comment-count"]',
                        'strong[data-e2e="comment-count"]',
                        'button[aria-label*="comment"] strong',
                    ])
                    saves = _get_count([
                        '[data-e2e="collect-count"]',
                        'strong[data-e2e="collect-count"]',
                        'button[aria-label*="collect"] strong',
                        'button[aria-label*="favorite"] strong',
                    ])
                    # ── 공유수 (v2 신규 추가) ──────────────────────
                    shares = _get_count([
                        '[data-e2e="share-count"]',
                        'strong[data-e2e="share-count"]',
                        'button[aria-label*="share"] strong',
                        'span[class*="share"] strong',
                        '[class*="ShareCount"]',
                    ])

                    totals["views"]    += views
                    totals["likes"]    += likes
                    totals["comments"] += comments
                    totals["saves"]    += saves
                    totals["shares"]   += shares
                    scraped += 1

                except Exception:
                    continue

            if scraped == 0:
                result["error"] = "게시물 상세 데이터를 수집할 수 없습니다"
            else:
                for k in totals:
                    result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped

            browser.close()

    except Exception as e:
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════
# Instagram Feed Scraper
# ═══════════════════════════════════════════════════════════
def scrape_instagram_feed(
    profile_url: str,
    n_posts: int = 10,
    skip_pinned: bool = True,
) -> dict:
    """
    Instagram 피드에서 최근 n개 게시물의 평균 좋아요·댓글 반환.
    Returns:
        {
          "likes": float, "comments": float,
          "posts_scraped": int, "error": str|None
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"likes": 0, "comments": 0, "posts_scraped": 0,
                "error": "playwright not installed"}

    url = _normalize_url(profile_url, "instagram")
    if not url.endswith("/"):
        url += "/"

    result = {"likes": 0.0, "comments": 0.0, "posts_scraped": 0, "error": None}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"
                ),
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                viewport={"width": 390, "height": 844},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)

            # 게시물 링크 수집
            post_links = page.query_selector_all('a[href*="/p/"]')
            urls = []
            seen = set()
            for lnk in post_links:
                href = lnk.get_attribute("href") or ""
                if "/p/" in href and href not in seen:
                    seen.add(href)
                    full = "https://www.instagram.com" + href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts + 3:  # 핀 여유분
                    break

            totals = {"likes": 0.0, "comments": 0.0}
            scraped = 0

            for post_url in urls:
                if scraped >= n_posts:
                    break
                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(random.randint(1200, 2000))

                    # 좋아요
                    likes = 0.0
                    like_selectors = [
                        'span[class*="like"] span',
                        'section span span',
                        'span[aria-label*="like"]',
                        'a[href*="liked_by"] span',
                    ]
                    for sel in like_selectors:
                        el = page.query_selector(sel)
                        if el:
                            txt = el.inner_text().strip()
                            if re.search(r"[\d,KMk]", txt):
                                likes = _parse_num(txt)
                                break

                    # 댓글
                    comments = 0.0
                    cmt_selectors = [
                        'span[aria-label*="comment"]',
                        'ul li span span',
                    ]
                    for sel in cmt_selectors:
                        els = page.query_selector_all(sel)
                        for el in els:
                            txt = el.inner_text().strip()
                            if re.search(r"^[\d,KMk.]+$", txt):
                                comments = _parse_num(txt)
                                break
                        if comments:
                            break

                    totals["likes"]    += likes
                    totals["comments"] += comments
                    scraped += 1

                except Exception:
                    continue

            if scraped == 0:
                result["error"] = "게시물 데이터를 수집할 수 없습니다"
            else:
                for k in totals:
                    result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped

            browser.close()

    except Exception as e:
        result["error"] = str(e)

    return result


def _error_result(msg: str) -> dict:
    return {
        "views": 0.0, "likes": 0.0, "comments": 0.0,
        "saves": 0.0, "shares": 0.0,
        "posts_scraped": 0, "error": msg,
    }
