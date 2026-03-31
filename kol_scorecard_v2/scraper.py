"""
scraper.py — KOL Scorecard v2
플랫폼별 스크래퍼 (세션 쿠키 지원)
TikTok: views, likes, comments, saves, shares
Instagram Feed/Reels: likes, comments, views
YouTube: views, likes, comments
"""
from __future__ import annotations
import re, random
from typing import Optional


def _parse_num(text: str) -> float:
    if not text:
        return 0.0
    text = text.strip().replace(",", "").replace(" ", "")
    m = re.match(r"([\d.]+)\s*([KkMmBb万億]?)", text)
    if not m:
        return 0.0
    val = float(m.group(1))
    s = m.group(2).upper()
    if s == "K":   val *= 1_000
    elif s == "M": val *= 1_000_000
    elif s == "B": val *= 1_000_000_000
    elif s == "万": val *= 10_000
    elif s == "億": val *= 100_000_000
    return val


def _norm_url(url: str, platform: str) -> str:
    if not url:
        return ""
    url = re.sub(r"\?.*", "", url.strip())
    if not url.startswith("http"):
        if platform == "tiktok":
            url = "https://www.tiktok.com/@" + url.lstrip("@")
        elif platform == "instagram":
            url = "https://www.instagram.com/" + url.lstrip("@/")
        elif platform == "youtube":
            url = "https://www.youtube.com/@" + url.lstrip("@")
    if platform == "instagram" and not url.endswith("/"):
        url += "/"
    return url


def _get_browser(p, cookies=None, locale="ja-JP"):
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-setuid-sandbox",
              "--disable-dev-shm-usage","--disable-gpu",
              "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale=locale,
        timezone_id="Asia/Tokyo",
        viewport={"width": 1280, "height": 900},
    )
    if cookies:
        ctx.add_cookies(cookies)
    return browser, ctx


def _err(msg):
    return {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
            "posts_scraped":0,"error":msg}


# ══ TikTok ════════════════════════════════════════════════
def scrape_tiktok(profile_url: str, n_posts: int = 10,
                  skip_pinned: bool = True, session_id: str = None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")

    url = _norm_url(profile_url, "tiktok")
    cookies = []
    if session_id:
        cookies = [{"name":"sessionid","value":session_id,
                    "domain":".tiktok.com","path":"/","httpOnly":True,"secure":True}]
    result = {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
              "posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, cookies)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)

            cards = []
            for sel in ['[data-e2e="user-post-item"]','div[class*="DivItemContainerV2"]','a[href*="/video/"]']:
                cards = page.query_selector_all(sel)
                if cards: break

            collected = []
            for card in cards:
                if len(collected) >= n_posts: break
                if skip_pinned:
                    pin = card.query_selector('[data-e2e="video-card-badge"]') or \
                          card.query_selector('[class*="PinnedVideoLabel"]')
                    if pin: continue
                views_el = card.query_selector('[data-e2e="video-views"]') or \
                           card.query_selector('strong[class*="VideoCount"]')
                link_el = card.query_selector("a[href*='/video/']")
                collected.append({
                    "views_text": views_el.inner_text() if views_el else "0",
                    "url": link_el.get_attribute("href") if link_el else None
                })

            if not collected:
                result["error"] = "게시물 없음 (핀 제외 후 0건)"; browser.close(); return result

            totals = {k:0. for k in ["views","likes","comments","saves","shares"]}
            scraped = 0
            for item in collected:
                post_url = item["url"]
                if not post_url: continue
                if not post_url.startswith("http"):
                    post_url = "https://www.tiktok.com" + post_url
                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=25_000)
                    page.wait_for_timeout(random.randint(1500, 2500))
                    def get(sels):
                        for s in sels:
                            el = page.query_selector(s)
                            if el:
                                t = el.inner_text().strip()
                                if t: return _parse_num(t)
                        return 0.
                    totals["views"]    += get(['[data-e2e="video-views"]','strong[data-e2e="video-views"]']) or _parse_num(item["views_text"])
                    totals["likes"]    += get(['[data-e2e="like-count"]','strong[data-e2e="like-count"]','button[aria-label*="like"] strong'])
                    totals["comments"] += get(['[data-e2e="comment-count"]','strong[data-e2e="comment-count"]'])
                    totals["saves"]    += get(['[data-e2e="collect-count"]','strong[data-e2e="collect-count"]','button[aria-label*="collect"] strong'])
                    totals["shares"]   += get(['[data-e2e="share-count"]','strong[data-e2e="share-count"]','button[aria-label*="share"] strong'])
                    scraped += 1
                except Exception:
                    continue

            if scraped == 0: result["error"] = "상세 데이터 수집 불가"
            else:
                for k in totals: result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped
            browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


# ══ Instagram ════════════════════════════════════════════
def scrape_instagram(profile_url: str, n_posts: int = 10,
                     content_type: str = "feed", session_id: str = None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")

    url = _norm_url(profile_url, "instagram")
    if content_type == "reels" and "/reels" not in url:
        url = url.rstrip("/") + "/reels/"
    cookies = []
    if session_id:
        cookies = [{"name":"sessionid","value":session_id,
                    "domain":".instagram.com","path":"/","httpOnly":True,"secure":True}]
    result = {"views":0.,"likes":0.,"comments":0.,"posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, cookies)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            link_sel = 'a[href*="/p/"]' if content_type == "feed" else 'a[href*="/reel/"]'
            links = page.query_selector_all(link_sel)
            urls, seen = [], set()
            for lnk in links:
                href = lnk.get_attribute("href") or ""
                if href and href not in seen:
                    seen.add(href)
                    full = "https://www.instagram.com" + href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts + 3: break
            totals = {"views":0.,"likes":0.,"comments":0.}
            scraped = 0
            for post_url in urls:
                if scraped >= n_posts: break
                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(random.randint(1200, 2000))
                    views, likes, comments = 0., 0., 0.
                    if content_type == "reels":
                        for sel in ['span[class*="view"] span','span[aria-label*="view"]']:
                            el = page.query_selector(sel)
                            if el:
                                t = el.inner_text().strip()
                                if re.search(r"[\d,KMk]", t): views = _parse_num(t); break
                    for sel in ['span[class*="like"] span','section span span','a[href*="liked_by"] span']:
                        el = page.query_selector(sel)
                        if el:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk.]+$", t): likes = _parse_num(t); break
                    for sel in ['span[aria-label*="comment"]']:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk.]+$", t): comments = _parse_num(t); break
                        if comments: break
                    totals["views"] += views; totals["likes"] += likes; totals["comments"] += comments
                    scraped += 1
                except Exception:
                    continue
            if scraped == 0: result["error"] = "게시물 데이터 수집 불가"
            else:
                for k in totals: result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped
            browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


# ══ YouTube ════════════════════════════════════════════
def scrape_youtube(channel_url: str, n_posts: int = 10,
                   content_type: str = "shorts") -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")
    url = _norm_url(channel_url, "youtube")
    tab = "/shorts" if content_type == "shorts" else "/videos"
    if tab not in url:
        url = url.rstrip("/") + tab
    result = {"views":0.,"likes":0.,"comments":0.,"posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, None)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            for _ in range(3):
                page.keyboard.press("End")
                page.wait_for_timeout(1500)
            video_links = page.query_selector_all('a#video-title-link, a[href*="/shorts/"], a#thumbnail')
            urls, seen = [], set()
            for lnk in video_links:
                href = lnk.get_attribute("href") or ""
                if content_type == "shorts" and "/shorts/" not in href: continue
                if href and href not in seen:
                    seen.add(href)
                    full = "https://www.youtube.com" + href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts + 3: break
            totals = {"views":0.,"likes":0.,"comments":0.}
            scraped = 0
            for video_url in urls[:n_posts]:
                try:
                    page.goto(video_url, wait_until="domcontentloaded", timeout=25_000)
                    page.wait_for_timeout(2000)
                    views = 0.
                    for sel in ['span[class*="view-count"]','#count .view-count']:
                        el = page.query_selector(sel)
                        if el:
                            t = el.inner_text().strip()
                            nums = re.findall(r'[\d]+', t.replace(',',''))
                            if nums: views = float(nums[0]); break
                    totals["views"] += views
                    scraped += 1
                except Exception:
                    continue
            if scraped == 0: result["error"] = "영상 데이터 수집 불가"
            else:
                for k in totals: result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped
            browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


# 하위 호환
def scrape_instagram_feed(url, n=10, session_id=None):
    return scrape_instagram(url, n, "feed", session_id)

def scrape_instagram_reels(url, n=10, session_id=None):
    return scrape_instagram(url, n, "reels", session_id)
