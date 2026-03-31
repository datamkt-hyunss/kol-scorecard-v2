"""
scraper.py — KOL Scorecard v2
TikTok: API JSON 파싱 방식 (봇 감지 우회)
Instagram: 세션쿠키 + 다중 셀렉터
YouTube: 공개 데이터 수집
"""
from __future__ import annotations
import re, random, json, time

# ── 숫자 파싱 ─────────────────────────────────────────────
def _parse_num(text: str) -> float:
    if not text: return 0.0
    text = str(text).strip().replace(",","").replace(" ","")
    m = re.match(r"([\d.]+)\s*([KkMmBb万億]?)", text)
    if not m: return 0.0
    val = float(m.group(1))
    s = m.group(2).upper()
    if s=="K": val*=1_000
    elif s=="M": val*=1_000_000
    elif s=="B": val*=1_000_000_000
    elif s=="万": val*=10_000
    elif s=="億": val*=100_000_000
    return val


def _norm_url(url: str, platform: str) -> str:
    if not url: return ""
    url = re.sub(r"\?.*","",url.strip())
    if not url.startswith("http"):
        if platform=="tiktok":
            url="https://www.tiktok.com/@"+url.lstrip("@")
        elif platform=="instagram":
            url="https://www.instagram.com/"+url.lstrip("@/")
        elif platform=="youtube":
            url="https://www.youtube.com/@"+url.lstrip("@")
    if platform=="instagram" and not url.endswith("/"):
        url+="/"
    return url


def _get_browser(p, locale="ja-JP"):
    """스텔스 브라우저 — 봇 감지 최소화"""
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--window-size=1280,900",
        ],
    )
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale=locale,
        timezone_id="Asia/Tokyo",
        viewport={"width":1280,"height":900},
        java_script_enabled=True,
        # navigator.webdriver 숨기기
        extra_http_headers={
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
    )
    # webdriver 플래그 제거
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP','ja','en']});
        window.chrome = {runtime: {}};
    """)
    return browser, ctx


def _err(msg):
    return {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
            "posts_scraped":0,"error":msg}


# ═══════════════════════════════════════════════════════════
# TikTok: API JSON 인터셉트 + HTML 폴백
# ═══════════════════════════════════════════════════════════
def scrape_tiktok(profile_url: str, n_posts: int = 10,
                  skip_pinned: bool = True, session_id: str = None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")

    url = _norm_url(profile_url, "tiktok")
    result = {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
              "posts_scraped":0,"error":None}

    # 쿠키 준비
    base_cookies = [
        {"name":"ttwid","value":"1","domain":".tiktok.com","path":"/"},
        {"name":"tt_chain_token","value":"1","domain":".tiktok.com","path":"/"},
    ]
    if session_id:
        base_cookies += [
            {"name":"sessionid","value":session_id,"domain":".tiktok.com","path":"/","httpOnly":True,"secure":True},
            {"name":"sessionid_ss","value":session_id,"domain":".tiktok.com","path":"/","httpOnly":True,"secure":True},
        ]

    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, "ja-JP")
            # 쿠키 주입 (컨텍스트 생성 후)
            ctx.add_cookies(base_cookies)
            page = ctx.new_page()

            # ── API 응답 인터셉트 ────────────────────────
            api_videos = []

            def handle_response(response):
                try:
                    if ("api/post/item_list" in response.url or
                        "api/user/post" in response.url or
                        "aweme/v1/web/aweme/post" in response.url):
                        data = response.json()
                        # 다양한 API 응답 구조 처리
                        items = (data.get("aweme_list") or
                                 data.get("itemList") or
                                 data.get("data",{}).get("aweme_list",[]) or [])
                        for item in items:
                            try:
                                stats = item.get("statistics",{}) or item.get("stats",{}) or {}
                                is_pinned = bool(item.get("is_top",0) or item.get("isPinnedPost",False))
                                if skip_pinned and is_pinned:
                                    continue
                                api_videos.append({
                                    "views":    float(stats.get("play_count",0) or stats.get("playCount",0) or 0),
                                    "likes":    float(stats.get("digg_count",0) or stats.get("diggCount",0) or 0),
                                    "comments": float(stats.get("comment_count",0) or stats.get("commentCount",0) or 0),
                                    "saves":    float(stats.get("collect_count",0) or stats.get("collectCount",0) or 0),
                                    "shares":   float(stats.get("share_count",0) or stats.get("shareCount",0) or 0),
                                })
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", handle_response)

            # 프로필 페이지 접속
            page.goto(url, wait_until="domcontentloaded", timeout=35_000)

            # 스크롤해서 API 요청 트리거
            for _ in range(4):
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollBy(0, 600)")

            page.wait_for_timeout(2000)

            # ── API 데이터가 있으면 사용 ─────────────────
            if api_videos:
                videos = api_videos[:n_posts]
                n = len(videos)
                result["views"]    = sum(v["views"]    for v in videos) / n
                result["likes"]    = sum(v["likes"]    for v in videos) / n
                result["comments"] = sum(v["comments"] for v in videos) / n
                result["saves"]    = sum(v["saves"]    for v in videos) / n
                result["shares"]   = sum(v["shares"]   for v in videos) / n
                result["posts_scraped"] = n
                browser.close()
                return result

            # ── API 실패 시 HTML 파싱 폴백 ───────────────
            # __UNIVERSAL_DATA_FOR_REHYDRATION__ 스크립트에서 JSON 추출
            html_videos = _parse_tiktok_html(page, n_posts, skip_pinned)
            if html_videos:
                n = len(html_videos)
                result["views"]    = sum(v["views"]    for v in html_videos) / n
                result["likes"]    = sum(v["likes"]    for v in html_videos) / n
                result["comments"] = sum(v["comments"] for v in html_videos) / n
                result["saves"]    = sum(v["saves"]    for v in html_videos) / n
                result["shares"]   = sum(v["shares"]   for v in html_videos) / n
                result["posts_scraped"] = n
                browser.close()
                return result

            # ── HTML 폴백: 비디오 카드 셀렉터 ────────────
            dom_videos = _parse_tiktok_dom(page, n_posts, skip_pinned)
            if dom_videos:
                n = len(dom_videos)
                result["views"]    = sum(v.get("views",0)    for v in dom_videos) / n
                result["likes"]    = sum(v.get("likes",0)    for v in dom_videos) / n
                result["comments"] = sum(v.get("comments",0) for v in dom_videos) / n
                result["saves"]    = sum(v.get("saves",0)    for v in dom_videos) / n
                result["shares"]   = sum(v.get("shares",0)   for v in dom_videos) / n
                result["posts_scraped"] = n
                browser.close()
                return result

            result["error"] = "게시물을 수집할 수 없습니다. 세션ID를 확인하거나 잠시 후 다시 시도해주세요."
            browser.close()

    except Exception as e:
        result["error"] = str(e)
    return result


def _parse_tiktok_html(page, n_posts: int, skip_pinned: bool) -> list:
    """페이지 내 JSON 데이터 직접 파싱"""
    videos = []
    try:
        # SIGI_STATE 또는 UNIVERSAL_DATA 스크립트 탐색
        scripts = page.query_selector_all("script")
        for script in scripts:
            try:
                content = script.text_content() or ""
                # JSON 데이터 블록 찾기
                for pattern in [
                    r'"itemList"\s*:\s*(\[.*?\])',
                    r'"aweme_list"\s*:\s*(\[.*?\])',
                    r'"VideoList"\s*:\s*(\[.*?\])',
                ]:
                    m = re.search(pattern, content, re.DOTALL)
                    if m:
                        try:
                            items = json.loads(m.group(1))
                            for item in items:
                                stats = item.get("statistics",{}) or item.get("stats",{}) or {}
                                is_pinned = bool(item.get("is_top",0) or item.get("isPinnedPost",False))
                                if skip_pinned and is_pinned:
                                    continue
                                videos.append({
                                    "views":    float(stats.get("play_count",0) or stats.get("playCount",0) or 0),
                                    "likes":    float(stats.get("digg_count",0) or stats.get("diggCount",0) or 0),
                                    "comments": float(stats.get("comment_count",0) or stats.get("commentCount",0) or 0),
                                    "saves":    float(stats.get("collect_count",0) or stats.get("collectCount",0) or 0),
                                    "shares":   float(stats.get("share_count",0) or stats.get("shareCount",0) or 0),
                                })
                                if len(videos) >= n_posts:
                                    break
                            if videos:
                                return videos
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass
    return videos


def _parse_tiktok_dom(page, n_posts: int, skip_pinned: bool) -> list:
    """DOM 셀렉터로 비디오 링크 수집 후 상세 페이지 방문"""
    videos = []
    try:
        # 다양한 셀렉터 시도 (2024~2025 TikTok DOM 구조)
        CARD_SELS = [
            '[data-e2e="user-post-item"]',
            'div[class*="DivItemContainerV2"]',
            'div[class*="css-"][class*="item"]',
            'li[class*="video-feed-item"]',
            'article',
        ]
        LINK_SELS = [
            "a[href*='/video/']",
            "a[href*='/@']",
        ]

        links = []
        seen = set()

        # 방법1: 카드 내 링크
        for card_sel in CARD_SELS:
            cards = page.query_selector_all(card_sel)
            if not cards: continue
            for card in cards:
                if len(links) >= n_posts + 3: break
                for link_sel in LINK_SELS:
                    a = card.query_selector(link_sel)
                    if a:
                        href = a.get_attribute("href") or ""
                        if "/video/" in href and href not in seen:
                            seen.add(href)
                            links.append(href)
                            break
            if links: break

        # 방법2: 페이지 전체 비디오 링크 직접 수집
        if not links:
            all_links = page.query_selector_all("a[href*='/video/']")
            for a in all_links:
                if len(links) >= n_posts + 3: break
                href = a.get_attribute("href") or ""
                if "/video/" in href and href not in seen:
                    seen.add(href)
                    links.append(href)

        if not links:
            return []

        # 각 비디오 페이지 방문해서 지표 수집
        for href in links[:n_posts]:
            if not href.startswith("http"):
                href = "https://www.tiktok.com" + href
            try:
                page.goto(href, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(random.randint(1500, 2500))

                def get_stat(sels):
                    for s in sels:
                        el = page.query_selector(s)
                        if el:
                            t = el.inner_text().strip()
                            if t and re.search(r"[\d]", t):
                                return _parse_num(t)
                    return 0.

                video_data = {
                    "views": get_stat([
                        '[data-e2e="video-views"]',
                        'strong[data-e2e="video-views"]',
                        'span[data-e2e="video-views"]',
                    ]),
                    "likes": get_stat([
                        '[data-e2e="like-count"]',
                        'strong[data-e2e="like-count"]',
                        'button[aria-label*="like"] strong',
                        'span[data-e2e="browse-like-count"]',
                    ]),
                    "comments": get_stat([
                        '[data-e2e="comment-count"]',
                        'strong[data-e2e="comment-count"]',
                        'span[data-e2e="browse-comment-count"]',
                    ]),
                    "saves": get_stat([
                        '[data-e2e="collect-count"]',
                        'strong[data-e2e="collect-count"]',
                        'button[aria-label*="collect"] strong',
                        'button[aria-label*="favorite"] strong',
                        'span[data-e2e="browse-collect-count"]',
                    ]),
                    "shares": get_stat([
                        '[data-e2e="share-count"]',
                        'strong[data-e2e="share-count"]',
                        'button[aria-label*="share"] strong',
                        'span[data-e2e="browse-share-count"]',
                    ]),
                }
                videos.append(video_data)
            except Exception:
                continue
    except Exception:
        pass
    return videos


# ═══════════════════════════════════════════════════════════
# Instagram
# ═══════════════════════════════════════════════════════════
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
        cookies = [
            {"name":"sessionid","value":session_id,"domain":".instagram.com",
             "path":"/","httpOnly":True,"secure":True},
            {"name":"ds_user_id","value":"0","domain":".instagram.com","path":"/"},
            {"name":"csrftoken","value":"placeholder","domain":".instagram.com","path":"/"},
        ]

    result = {"views":0.,"likes":0.,"comments":0.,"posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, "ja-JP")
            if cookies:
                ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)

            # 게시물 링크 수집 (피드: /p/ | 릴스: /reel/)
            link_pattern = "/p/" if content_type == "feed" else "/reel/"
            link_sel = f'a[href*="{link_pattern}"]'
            links = page.query_selector_all(link_sel)
            urls, seen = [], set()
            for lnk in links:
                href = lnk.get_attribute("href") or ""
                if href and href not in seen:
                    seen.add(href)
                    full = "https://www.instagram.com" + href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts + 3: break

            if not urls:
                result["error"] = "게시물 링크를 찾을 수 없습니다. 세션ID를 확인하세요."
                browser.close(); return result

            totals = {"views":0.,"likes":0.,"comments":0.}
            scraped = 0
            for post_url in urls:
                if scraped >= n_posts: break
                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(random.randint(1500, 2500))

                    views, likes, comments = 0., 0., 0.

                    if content_type == "reels":
                        for sel in [
                            'span[class*="view"] span', 'span[aria-label*="view"]',
                            'div[class*="view"] span', 'span[class*="VideoViewCount"]',
                        ]:
                            el = page.query_selector(sel)
                            if el:
                                t = el.inner_text().strip()
                                if re.search(r"[\d,KMk]", t): views = _parse_num(t); break

                    # 좋아요
                    LIKE_SELS = [
                        'section span[class*="like"] span',
                        'a[href*="liked_by"] span',
                        'button[aria-label*="like"] span',
                        'span[class*="_aacl"]',
                        'section span span',
                    ]
                    for sel in LIKE_SELS:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk. ]+$", t) and len(t) < 15:
                                v = _parse_num(t)
                                if v > 0: likes = v; break
                        if likes: break

                    # 댓글
                    CMT_SELS = [
                        'span[aria-label*="comment"]',
                        'a[href*="comments"] span',
                        'ul li span span',
                    ]
                    for sel in CMT_SELS:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk.]+$", t):
                                v = _parse_num(t)
                                if v > 0: comments = v; break
                        if comments: break

                    totals["views"]    += views
                    totals["likes"]    += likes
                    totals["comments"] += comments
                    scraped += 1
                except Exception:
                    continue

            if scraped == 0:
                result["error"] = "게시물 데이터 수집 불가. 비공개 계정은 세션ID가 필요합니다."
            else:
                for k in totals: result[k] = totals[k] / scraped
                result["posts_scraped"] = scraped
            browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


# ═══════════════════════════════════════════════════════════
# YouTube
# ═══════════════════════════════════════════════════════════
def scrape_youtube(channel_url: str, n_posts: int = 10,
                   content_type: str = "shorts") -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")
    url = _norm_url(channel_url, "youtube")
    tab = "/shorts" if content_type=="shorts" else "/videos"
    if tab not in url: url = url.rstrip("/")+tab
    result = {"views":0.,"likes":0.,"comments":0.,"posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser, ctx = _get_browser(p, "ja-JP")
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            for _ in range(4):
                page.keyboard.press("End")
                page.wait_for_timeout(1500)
            links = page.query_selector_all('a[href*="/shorts/"],a#video-title-link,a#thumbnail')
            urls, seen = [], set()
            for lnk in links:
                href = lnk.get_attribute("href") or ""
                if content_type=="shorts" and "/shorts/" not in href: continue
                if href and href not in seen:
                    seen.add(href)
                    full = "https://www.youtube.com"+href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts+3: break
            totals = {"views":0.,"likes":0.,"comments":0.}
            scraped = 0
            for video_url in urls[:n_posts]:
                try:
                    page.goto(video_url, wait_until="domcontentloaded", timeout=25_000)
                    page.wait_for_timeout(2000)
                    views = 0.
                    for sel in ['span[class*="view-count"]','#count .view-count','#info span']:
                        el = page.query_selector(sel)
                        if el:
                            t = el.inner_text().strip()
                            nums = re.findall(r'[\d]+', t.replace(",",""))
                            if nums: views = float(nums[0]); break
                    totals["views"] += views; scraped += 1
                except Exception:
                    continue
            if scraped==0: result["error"]="영상 데이터 수집 불가"
            else:
                for k in totals: result[k]=totals[k]/scraped
                result["posts_scraped"]=scraped
            browser.close()
    except Exception as e:
        result["error"]=str(e)
    return result


# 하위 호환
def scrape_instagram_feed(url, n=10, session_id=None):
    return scrape_instagram(url, n, "feed", session_id)

def scrape_instagram_reels(url, n=10, session_id=None):
    return scrape_instagram(url, n, "reels", session_id)
