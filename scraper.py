"""
scraper.py — KOL Scorecard v2
TikTok: requests로 페이지 JSON 직접 파싱 (Playwright 최소 사용)
Instagram: 세션쿠키 + Playwright
"""
from __future__ import annotations
import re, random, json, time

# ── 숫자 파싱 ─────────────────────────────────────────────
def _parse_num(text) -> float:
    if text is None: return 0.0
    text = str(text).strip().replace(",","").replace(" ","")
    m = re.match(r"([\d.]+)\s*([KkMmBb万億]?)", text)
    if not m: return 0.0
    val = float(m.group(1))
    s = m.group(2).upper()
    if s == "K":   val *= 1_000
    elif s == "M": val *= 1_000_000
    elif s == "B": val *= 1_000_000_000
    elif s == "万": val *= 10_000
    elif s == "億": val *= 100_000_000
    return val

def _norm_url(url: str, platform: str) -> str:
    if not url: return ""
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

def _get_username(url: str) -> str:
    m = re.search(r"@([\w.]+)", url)
    return m.group(1) if m else ""

def _err(msg):
    return {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
            "posts_scraped":0,"error":msg}

# ── TikTok 요청용 헤더 (실제 브라우저와 최대한 유사하게) ──
def _tk_headers(session_id: str = None) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.tiktok.com/",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "Connection": "keep-alive",
    }
    cookies = {
        "ttwid": "1",
        "tt_chain_token": "placeholder",
        "msToken": "placeholder",
    }
    if session_id:
        cookies["sessionid"] = session_id
        cookies["sessionid_ss"] = session_id
    return headers, cookies


# ═══════════════════════════════════════════════════════════
# TikTok — 3단계 전략
# 1) requests로 프로필 페이지 HTML → JSON 파싱 (가장 빠름)
# 2) requests로 TikTok 비공개 API 직접 호출
# 3) Playwright 폴백 (API 인터셉트 + DOM)
# ═══════════════════════════════════════════════════════════
def scrape_tiktok(profile_url: str, n_posts: int = 10,
                  skip_pinned: bool = True, session_id: str = None) -> dict:

    url = _norm_url(profile_url, "tiktok")
    username = _get_username(url)

    # ── 1단계: requests로 프로필 페이지 HTML 파싱 ──────────
    result = _try_requests_html(url, username, n_posts, skip_pinned, session_id)
    if result and not result.get("error"):
        return result

    # ── 2단계: requests로 API 직접 호출 ───────────────────
    result2 = _try_requests_api(username, n_posts, skip_pinned, session_id)
    if result2 and not result2.get("error"):
        return result2

    # ── 3단계: Playwright 폴백 ────────────────────────────
    return _try_playwright(url, n_posts, skip_pinned, session_id)


def _try_requests_html(url, username, n_posts, skip_pinned, session_id) -> dict | None:
    """requests로 TikTok 프로필 페이지 HTML 가져와서 내장 JSON 파싱"""
    try:
        import requests
        headers, cookies = _tk_headers(session_id)
        resp = requests.get(url, headers=headers, cookies=cookies,
                            timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return None

        html = resp.text

        # TikTok은 __UNIVERSAL_DATA_FOR_REHYDRATION__ 또는
        # SIGI_STATE에 모든 데이터를 JSON으로 내장
        data = None
        for pattern in [
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'window\[\'SIGI_STATE\'\]\s*=\s*(\{.*?\});',
            r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    break
                except Exception:
                    continue

        if not data:
            return None

        # 여러 경로에서 itemList 찾기
        item_list = _extract_item_list(data)
        if not item_list:
            return None

        return _calc_averages(item_list, n_posts, skip_pinned)

    except Exception:
        return None


def _try_requests_api(username, n_posts, skip_pinned, session_id) -> dict | None:
    """TikTok 비공개 웹 API 직접 호출"""
    try:
        import requests
        headers, cookies = _tk_headers(session_id)

        # API 엔드포인트들 순서대로 시도
        endpoints = [
            f"https://www.tiktok.com/api/post/item_list/?aid=1988&count={n_posts+5}&cursor=0&uniqueId={username}",
            f"https://www.tiktok.com/api/creator/item_list/?aid=1988&count={n_posts+5}&cursor=0&secUid=&uniqueId={username}",
        ]

        for endpoint in endpoints:
            try:
                resp = requests.get(endpoint, headers=headers, cookies=cookies, timeout=12)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                items = (data.get("itemList") or data.get("aweme_list") or
                         data.get("data", {}).get("aweme_list", []) or [])
                if items:
                    return _calc_averages(items, n_posts, skip_pinned)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _try_playwright(url, n_posts, skip_pinned, session_id) -> dict:
    """Playwright 폴백 — API 인터셉트 우선, DOM 셀렉터 보조"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _err("playwright not installed")

    result = {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.,
              "posts_scraped":0,"error":None}

    cookies_list = [
        {"name":"ttwid","value":"1","domain":".tiktok.com","path":"/"},
        {"name":"tt_chain_token","value":"1","domain":".tiktok.com","path":"/"},
    ]
    if session_id:
        cookies_list += [
            {"name":"sessionid","value":session_id,"domain":".tiktok.com",
             "path":"/","httpOnly":True,"secure":True},
            {"name":"sessionid_ss","value":session_id,"domain":".tiktok.com",
             "path":"/","httpOnly":True,"secure":True},
        ]

    try:
        with sync_playwright() as p:
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
                locale="ja-JP", timezone_id="Asia/Tokyo",
                viewport={"width":1280,"height":900},
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
                Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});
                window.chrome={runtime:{}};
            """)
            ctx.add_cookies(cookies_list)
            page = ctx.new_page()

            # API 응답 인터셉트
            api_items = []
            def on_response(resp):
                try:
                    if any(x in resp.url for x in [
                        "api/post/item_list", "api/user/post",
                        "aweme/v1/web/aweme/post", "aweme/v1/web/user/post",
                        "api/creator/item_list",
                    ]):
                        d = resp.json()
                        items = (d.get("aweme_list") or d.get("itemList") or
                                 d.get("data",{}).get("aweme_list",[]) or [])
                        api_items.extend(items)
                except Exception:
                    pass
            page.on("response", on_response)

            page.goto(url, wait_until="domcontentloaded", timeout=35_000)

            # 스크롤로 API 트리거
            for _ in range(5):
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollBy(0,500)")
            page.wait_for_timeout(2000)

            # API 인터셉트 성공
            if api_items:
                r = _calc_averages(api_items, n_posts, skip_pinned)
                browser.close()
                return r

            # HTML에서 JSON 파싱
            try:
                html = page.content()
                for pattern in [
                    r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                    r'window\[\'SIGI_STATE\'\]\s*=\s*(\{.*?\});',
                ]:
                    m = re.search(pattern, html, re.DOTALL)
                    if m:
                        try:
                            data = json.loads(m.group(1))
                            items = _extract_item_list(data)
                            if items:
                                r = _calc_averages(items, n_posts, skip_pinned)
                                browser.close()
                                return r
                        except Exception:
                            pass
            except Exception:
                pass

            # DOM 셀렉터로 링크 수집 후 개별 페이지 방문
            dom_items = _pw_dom_scrape(page, n_posts, skip_pinned)
            browser.close()

            if dom_items:
                return _calc_averages_raw(dom_items, n_posts)

            result["error"] = (
                "TikTok 데이터 수집 불가 — Streamlit Cloud IP가 TikTok에서 차단되었을 수 있습니다.\n"
                "아래 '실패 KOL 수동 입력' 폼에 데이터를 직접 입력해주세요."
            )
    except Exception as e:
        result["error"] = f"오류: {str(e)[:120]}\n→ 수동 입력 탭을 이용해주세요."
    return result


def _extract_item_list(data: dict) -> list:
    """다양한 TikTok JSON 구조에서 itemList 추출"""
    # __UNIVERSAL_DATA_FOR_REHYDRATION__ 구조
    try:
        # 경로 1: default-scope > webapp.user-detail > itemList
        for scope_key in data:
            scope = data[scope_key]
            if not isinstance(scope, dict): continue
            for key in scope:
                val = scope[key]
                if isinstance(val, dict):
                    items = (val.get("itemList") or val.get("aweme_list") or
                             val.get("items") or [])
                    if items and isinstance(items, list) and len(items) > 0:
                        return items
    except Exception:
        pass

    # 경로 2: 직접 itemList
    for key in ["itemList", "aweme_list", "items"]:
        items = data.get(key, [])
        if items:
            return items

    # 경로 3: 중첩 탐색
    def deep_find(obj, depth=0):
        if depth > 5: return []
        if isinstance(obj, dict):
            for k in ["itemList", "aweme_list"]:
                if k in obj and isinstance(obj[k], list) and obj[k]:
                    return obj[k]
            for v in obj.values():
                r = deep_find(v, depth+1)
                if r: return r
        return []

    return deep_find(data)


def _calc_averages(items: list, n_posts: int, skip_pinned: bool) -> dict:
    """items 리스트에서 평균 지표 계산"""
    totals = {"views":0.,"likes":0.,"comments":0.,"saves":0.,"shares":0.}
    count = 0

    for item in items:
        if count >= n_posts: break
        # 핀 게시물 체크
        if skip_pinned:
            if item.get("is_top") or item.get("isPinnedPost"): continue
        stats = (item.get("statistics") or item.get("stats") or
                 item.get("statsV2") or {})
        totals["views"]    += float(stats.get("play_count",0) or stats.get("playCount",0) or 0)
        totals["likes"]    += float(stats.get("digg_count",0) or stats.get("diggCount",0) or 0)
        totals["comments"] += float(stats.get("comment_count",0) or stats.get("commentCount",0) or 0)
        totals["saves"]    += float(stats.get("collect_count",0) or stats.get("collectCount",0) or 0)
        totals["shares"]   += float(stats.get("share_count",0) or stats.get("shareCount",0) or 0)
        count += 1

    if count == 0:
        return _err("게시물 데이터 없음 (JSON 파싱 성공했으나 유효 항목 0건)")

    return {
        "views":    totals["views"]    / count,
        "likes":    totals["likes"]    / count,
        "comments": totals["comments"] / count,
        "saves":    totals["saves"]    / count,
        "shares":   totals["shares"]   / count,
        "posts_scraped": count,
        "error": None,
    }


def _calc_averages_raw(items: list, n_posts: int) -> dict:
    """DOM에서 수집한 raw dict 리스트 평균 계산"""
    if not items:
        return _err("DOM 수집 결과 없음")
    n = min(len(items), n_posts)
    sub = items[:n]
    return {
        "views":    sum(v.get("views",0)    for v in sub) / n,
        "likes":    sum(v.get("likes",0)    for v in sub) / n,
        "comments": sum(v.get("comments",0) for v in sub) / n,
        "saves":    sum(v.get("saves",0)    for v in sub) / n,
        "shares":   sum(v.get("shares",0)   for v in sub) / n,
        "posts_scraped": n, "error": None,
    }


def _pw_dom_scrape(page, n_posts, skip_pinned) -> list:
    """Playwright DOM에서 비디오 링크 수집 후 상세 방문"""
    items = []
    try:
        links, seen = [], set()
        for a in page.query_selector_all("a[href*='/video/']"):
            href = a.get_attribute("href") or ""
            if "/video/" in href and href not in seen:
                seen.add(href); links.append(href)
            if len(links) >= n_posts + 3: break

        def get_stat(sels):
            for s in sels:
                el = page.query_selector(s)
                if el:
                    t = el.inner_text().strip()
                    if t and re.search(r"[\d]", t): return _parse_num(t)
            return 0.

        for href in links[:n_posts]:
            if not href.startswith("http"):
                href = "https://www.tiktok.com" + href
            try:
                page.goto(href, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(random.randint(1500, 2500))
                items.append({
                    "views":    get_stat(['[data-e2e="video-views"]','strong[data-e2e="video-views"]','span[data-e2e="browse-video-views"]']),
                    "likes":    get_stat(['[data-e2e="like-count"]','strong[data-e2e="like-count"]','span[data-e2e="browse-like-count"]']),
                    "comments": get_stat(['[data-e2e="comment-count"]','strong[data-e2e="comment-count"]']),
                    "saves":    get_stat(['[data-e2e="collect-count"]','strong[data-e2e="collect-count"]']),
                    "shares":   get_stat(['[data-e2e="share-count"]','strong[data-e2e="share-count"]']),
                })
            except Exception:
                continue
    except Exception:
        pass
    return items


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
                locale="ja-JP", timezone_id="Asia/Tokyo",
                viewport={"width":1280,"height":900},
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
            if cookies:
                ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)

            link_pat = "/p/" if content_type == "feed" else "/reel/"
            links_els = page.query_selector_all(f'a[href*="{link_pat}"]')
            urls, seen = [], set()
            for lnk in links_els:
                href = lnk.get_attribute("href") or ""
                if href and href not in seen:
                    seen.add(href)
                    full = "https://www.instagram.com"+href if href.startswith("/") else href
                    urls.append(full)
                if len(urls) >= n_posts + 3: break

            if not urls:
                result["error"] = ("Instagram 게시물 링크를 찾을 수 없습니다.\n"
                                   "세션ID가 올바른지 확인하거나 수동 입력을 이용해주세요.")
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
                        for sel in ['span[class*="view"] span','span[aria-label*="view"]']:
                            el = page.query_selector(sel)
                            if el:
                                t = el.inner_text().strip()
                                if re.search(r"[\d,KMk]", t): views=_parse_num(t); break

                    for sel in ['section span[class*="like"] span',
                                'a[href*="liked_by"] span','section span span']:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk. ]+$", t) and len(t) < 15:
                                v = _parse_num(t)
                                if v > 0: likes = v; break
                        if likes: break

                    for sel in ['span[aria-label*="comment"]','a[href*="comments"] span']:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if re.search(r"^[\d,KMk.]+$", t):
                                v = _parse_num(t)
                                if v > 0: comments = v; break
                        if comments: break

                    totals["views"] += views; totals["likes"] += likes
                    totals["comments"] += comments; scraped += 1
                except Exception:
                    continue

            if scraped == 0:
                result["error"] = "Instagram 데이터 수집 불가. 비공개 계정은 세션ID가 필요합니다."
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
    tab = "/shorts" if content_type == "shorts" else "/videos"
    if tab not in url: url = url.rstrip("/") + tab
    result = {"views":0.,"likes":0.,"comments":0.,"posts_scraped":0,"error":None}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="ja-JP", viewport={"width":1280,"height":900})
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            for _ in range(4):
                page.keyboard.press("End"); page.wait_for_timeout(1500)
            links = page.query_selector_all('a[href*="/shorts/"],a#video-title-link,a#thumbnail')
            urls, seen = [], set()
            for lnk in links:
                href = lnk.get_attribute("href") or ""
                if content_type == "shorts" and "/shorts/" not in href: continue
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
            if scraped == 0: result["error"] = "YouTube 데이터 수집 불가"
            else:
                for k in totals: result[k] = totals[k]/scraped
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
