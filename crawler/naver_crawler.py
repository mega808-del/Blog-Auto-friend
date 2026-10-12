"""
네이버 블로그 크롤러 — Playwright 기반
- 네이버 검색에서 블로그 ID 수집
- 각 블로그 방문하여 상세 정보 수집 (제목/본문/해시태그/이미지)
- 키워드 관련성 점수 산출 (제목 > 본문 > 해시태그 순)
- 하드 필터 ALL-TRUE: 개설년도 / 이웃수 / 누적방문자 / 일일방문자 / 게시글수
- 모바일 스텔스 UA 사용 (스마트폰처럼 보이게)
"""

import asyncio
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Callable, Tuple, Dict
from playwright.async_api import async_playwright, Page, Browser


# ── 모바일 스텔스 User-Agent ─────────────────────────────
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class BloggerInfo:
    blog_id: str = ""
    blog_name: str = ""
    category: str = ""
    description: str = ""
    post_titles: str = ""          # 포스트 제목 (최근 5개)
    post_contents: str = ""        # 포스트 본문 (최근 3개 요약)
    hashtags: str = ""             # 해시태그 목록
    image_alts: str = ""           # 이미지 alt 텍스트
    post_count: int = 0            # 게시글 수
    neighbor_count: int = 0        # 이웃 수
    visitor_count: int = 0         # 누적 방문자 수
    daily_visitor_count: int = 0   # 일일 방문자 수
    blog_open_date: str = ""       # 개설일 (YYYY-MM-DD 또는 YYYY)
    blog_open_year: int = 0        # 개설 연도
    recent_post_date: str = ""     # 최근 포스팅 날짜
    blog_url: str = ""
    relevance_score: int = 0       # 키워드 관련성 점수 (0~100)
    parse_failed: bool = False     # 파싱 실패 여부

    def to_dict(self):
        return asdict(self)


class NaverBlogCrawler:
    """Playwright 기반 네이버 블로그 크롤러 (모바일 스텔스 지원)"""

    BLOG_HOME = "https://blog.naver.com"

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.log_callback: Optional[Callable] = None
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        """세션 초기화 (쿠키 포함) — 네이버 차단 방지"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self.MOBILE_HEADERS)
            # 네이버 메인에서 쿠키 획득
            try:
                self._session.get(
                    "https://www.naver.com",
                    headers={
                        "User-Agent": DESKTOP_UA,
                        "Accept-Language": "ko-KR,ko;q=0.9",
                    },
                    timeout=5,
                )
            except Exception:
                pass
        return self._session

    def _new_session(self) -> requests.Session:
        """새 세션 생성 (스레드 안전)"""
        sess = requests.Session()
        sess.headers.update(self.MOBILE_HEADERS)
        try:
            sess.get(
                "https://www.naver.com",
                headers={
                    "User-Agent": DESKTOP_UA,
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
                timeout=5,
            )
        except Exception:
            pass
        return sess

    def set_log_callback(self, callback: Callable):
        self.log_callback = callback

    def _log(self, message: str, level: str = "info"):
        if self.log_callback:
            self.log_callback(message, level)

    # ──────────────────────────────────────────────────────
    #  브라우저 시작/종료
    # ──────────────────────────────────────────────────────
    async def start(self, headless: bool = True, mobile: bool = True):
        """브라우저 시작
        Args:
            headless: 브라우저 창 숨김 여부
            mobile: 모바일 스텔스 모드 (스마트폰 UA 사용)
        """
        ua = MOBILE_UA if mobile else DESKTOP_UA
        mode_label = "모바일 스텔스" if mobile else "데스크톱"
        self._log(f"크롤러 브라우저 시작 ({mode_label})...", "system")

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await self.browser.new_context(
            user_agent=ua,
            viewport={"width": 412, "height": 915} if mobile else {"width": 1280, "height": 800},
            locale="ko-KR",
            is_mobile=mobile,
            has_touch=mobile,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self.page = await context.new_page()
        self._log(f"크롤러 브라우저 준비 완료 ({mode_label})", "success")

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._log("크롤러 브라우저 종료", "system")

    # ──────────────────────────────────────────────────────
    #  HTTP 기반 경량 사전 필터링 (브라우저 없이)
    # ──────────────────────────────────────────────────────
    MOBILE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def http_prefilter(self, blog_id: str, keyword: str = "", search_meta: dict = None) -> Optional[Dict]:
        """
        HTTP GET으로 블로그 페이지를 빠르게 가져와 사전 필터링.
        브라우저 없이 requests로 수행 (수백 ms).
        세션 기반으로 네이버 차단(403)을 방지.
        search_meta: 검색 결과에서 미리 추출한 포스트 URL/제목 데이터

        Returns:
            dict: 블로그 기본 정보
            None: 네트워크 오류 시
        """
        # 스레드 안전 세션 생성
        session = self._new_session()
        blog_headers = {
            "User-Agent": MOBILE_UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://www.naver.com/",
        }

        # 시도할 URL 목록 (모바일 → 데스크톱 순)
        urls = [
            f"https://m.blog.naver.com/{blog_id}?tab=1",
            f"https://blog.naver.com/{blog_id}",
        ]

        resp = None
        for url in urls:
            try:
                resp = session.get(
                    url, headers=blog_headers, timeout=10,
                    allow_redirects=True,
                )
                if resp.status_code == 200:
                    break
                resp = None
            except requests.RequestException:
                resp = None
                continue

        if resp is None or resp.status_code != 200:
            return None

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            # 네이버 에러 페이지 감지 (삭제/비공개/존재하지 않는 페이지)
            error_patterns = [
                "페이지 주소를 확인해주세요",
                "존재하지 않는 페이지",
                "이 페이지는 더 이상",
                "삭제된 게시물",
                "비공개 블로그",
                "페이지를 찾을 수 없습니다",
                "서비스 준비중",
            ]
            for err_pat in error_patterns:
                if err_pat in text:
                    self._log(
                        f"  [제외] 에러 페이지 감지: {blog_id} ('{err_pat}')",
                        "warning",
                    )
                    return None

            info = {
                "blog_id": blog_id,
                "blog_name": "",
                "description": "",
                "category": "",
                "post_titles": [],
                "neighbor_count": 0,
                "visitor_count": 0,
                "daily_visitor_count": 0,
                "post_count": 0,
                "blog_open_year": 0,
            }

            # 블로그 이름: title 태그에서 추출
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                m = re.match(r"^(.+?)\s*:\s*네이버\s*블로그", title_text)
                if m:
                    info["blog_name"] = m.group(1).strip()

            # 카테고리, 이웃수, 방문자수 텍스트에서 추출
            # 이웃 수: 여러 패턴으로 시도 (최신 네이버 구조 대응)
            neighbor_patterns = [
                r"([0-9,]+)명의\s*이웃",              # "1,419명의 이웃"
                r"이웃\s*([0-9,]+)",                   # "이웃 1,419"
                r"이웃\s*:*\s*([0-9,]+)",              # "이웃: 1,419"
                r"이웃수\s*:*\s*([0-9,]+)",            # "이웃수: 1,419"
                r"이웃\s*([0-9,]+)명",                  # "이웃 1,419명"
                r"([0-9,]+)\s*이웃",                    # "1,419 이웃"
            ]
            for pat in neighbor_patterns:
                neighbor_m = re.search(pat, text)
                if neighbor_m:
                    val = int(neighbor_m.group(1).replace(",", ""))
                    if val > 0:
                        info["neighbor_count"] = val
                        break
            # 프로필 영역에서 이웃 수 추출 시도 (CSS 클래스 기반)
            if info["neighbor_count"] == 0:
                for sel in [".neighbor_count", ".blog2_neighbor", ".count_neigh"]:
                    el = soup.select_one(sel)
                    if el:
                        el_text = el.get_text(strip=True)
                        el_m = re.search(r"([0-9,]+)", el_text)
                        if el_m:
                            val = int(el_m.group(1).replace(",", ""))
                            if val > 0:
                                info["neighbor_count"] = val
                                break

            # 방문자 수: 여러 패턴으로 시도
            visitor_patterns_total = [
                r"전체\s*([0-9,]+)",                   # "전체 49,777"
                r"누적\s*([0-9,]+)",                   # "누적 49,777"
                r"총\s*방문자\s*([0-9,]+)",            # "총 방문자 49,777"
                r"방문자[^0-9]*([0-9,]+)",              # "방문자 49,777"
            ]
            for pat in visitor_patterns_total:
                total_m = re.search(pat, text)
                if total_m:
                    val = int(total_m.group(1).replace(",", ""))
                    if val > 0:
                        info["visitor_count"] = val
                        break

            visitor_patterns_daily = [
                r"오늘\s*([0-9,]+)",                    # "오늘 282"
                r"일일\s*([0-9,]+)",                    # "일일 282"
                r"오늘의\s*방문자\s*([0-9,]+)",          # "오늘의 방문자 282"
            ]
            for pat in visitor_patterns_daily:
                today_m = re.search(pat, text)
                if today_m:
                    val = int(today_m.group(1).replace(",", ""))
                    if val > 0:
                        info["daily_visitor_count"] = val
                        break

            # 카테고리: "맛집", "여행" 등
            cat_m = re.search(
                r"(맛집|여행|육아|IT|패션|뷰티|건강|인테리어|반려동물|일상|요리|국내여행)",
                text,
            )
            if cat_m:
                info["category"] = cat_m.group(1)

            # 블로그 설명: "소개" 뒤 텍스트
            desc_m = re.search(r"소개\s*(.{5,200}?)(?:인기글|글감|대표글)", text)
            if desc_m:
                info["description"] = desc_m.group(1).strip()

            # ── 포스트 링크 추출 ──
            # 우선: 검색 결과에서 미리 추출한 포스트 URL 사용
            post_urls = []
            seen_urls = set()
            if search_meta and search_meta.get("post_urls"):
                for url in search_meta["post_urls"]:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        post_urls.append(url)
                # 검색 결과에서 추출한 제목도 사전 등록
                for title in search_meta.get("post_titles", []):
                    if title not in info["post_titles"]:
                        info["post_titles"].append(title)
            # 없으면 블로그 페이지에서 <a> 태그로 추출 (fallback)
            if not post_urls:
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if re.search(r"/\d{10,}$", href) or "PostView.naver" in href:
                        if href.startswith("/"):
                            full_url = f"https://m.blog.naver.com{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = f"https://m.blog.naver.com/{blog_id}/{href}"
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            post_urls.append(full_url)
                    elif "blog.naver.com" in href and re.search(r"/\d{10,}", href):
                        if href.startswith("http"):
                            full_url = href
                        elif href.startswith("/"):
                            full_url = f"https://blog.naver.com{href}"
                        else:
                            full_url = f"https://blog.naver.com/{href}"
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            post_urls.append(full_url)

            # <strong>에서 포스트 수 추출
            for strong in soup.find_all("strong"):
                t = strong.get_text(strip=True)
                if not t:
                    continue
                pc_m = re.search(r"포스트\s*수\s*:?\s*([0-9,]+)", t)
                if pc_m:
                    info["post_count"] = int(pc_m.group(1).replace(",", ""))
                    break
            # 텍스트에서도 포스트 수 추출 시도
            if info["post_count"] == 0:
                pc_m = re.search(r"포스트\s*수\s*:?\s*([0-9,]+)", text)
                if pc_m:
                    info["post_count"] = int(pc_m.group(1).replace(",", ""))

            # ── 포스트 제목 수집: 실제 포스트 페이지에서 텍스트 추출 ──
            # 최대 5개 포스트에 접속하여 제목 + 본문 텍스트 수집
            max_posts_to_fetch = min(len(post_urls), 5)
            fetched_contents = []

            for i in range(max_posts_to_fetch):
                if len(info["post_titles"]) >= 5:
                    break
                try:
                    post_resp = session.get(
                        post_urls[i],
                        headers=blog_headers,
                        timeout=8,
                        allow_redirects=True,
                    )
                    if post_resp.status_code != 200:
                        continue
                    post_soup = BeautifulSoup(post_resp.text, "html.parser")

                    # 개별 포스트 에러 페이지 감지
                    post_text = post_soup.get_text(separator=" ", strip=True)
                    post_error_found = False
                    for err_pat in ["페이지 주소를 확인해주세요", "존재하지 않는 페이지", "삭제된 게시물"]:
                        if err_pat in post_text:
                            post_error_found = True
                            break
                    if post_error_found:
                        continue  # 이 포스트는 건너뜀

                    # 제목 추출: <title> 태그, <strong>, <h3> 등
                    post_title = ""
                    title_tag = post_soup.find("title")
                    if title_tag:
                        raw_title = title_tag.get_text(strip=True)
                        # "제목 : 블로그명 : 네이버 블로그" 패턴
                        tm = re.match(r"^(.+?)\s*:\s*.+?:\s*네이버\s*블로그", raw_title)
                        if tm:
                            post_title = tm.group(1).strip()
                        else:
                            post_title = raw_title

                    if not post_title:
                        for sel in [".se-text-paragraph", ".post-title", "h3", ".title"]:
                            el = post_soup.select_one(sel)
                            if el:
                                post_title = el.get_text(strip=True)
                                if len(post_title) > 5:
                                    break

                    if post_title and 3 < len(post_title) < 200:
                        if post_title not in seen_urls:  # 중복 방지
                            info["post_titles"].append(post_title)
                            seen_urls.add(post_title)

                    # 본문 텍스트 추출 (스마트에디터 ONE + 구형 에디터)
                    body_text = ""
                    for body_sel in [
                        ".se-main-container",        # 스마트에디터 ONE
                        ".post-view",                 # 구형 에디터
                        ".post_ct",                   # 구형 에디터 본문
                        "#postViewArea",              # 구형 에디터 ID
                        ".se-component-content",      # 스마트에디터 컴포넌트
                    ]:
                        body_el = post_soup.select_one(body_sel)
                        if body_el:
                            body_text = body_el.get_text(separator=" ", strip=True)
                            if len(body_text) > 50:
                                break

                    # 본문이 없으면 페이지 전체 텍스트에서 본문 영역 추출
                    if not body_text or len(body_text) < 50:
                        body_text = post_soup.get_text(separator=" ", strip=True)

                    if body_text:
                        fetched_contents.append(body_text[:3000])  # 최대 3000자

                except requests.RequestException:
                    continue
                except Exception:
                    continue

            # 본문 텍스트를 info에 저장 (키워드 매칭용)
            info["post_contents"] = " ".join(fetched_contents)

            # 포스트 수가 없으면 수집한 제목 개수로 추정
            if info["post_count"] == 0 and info["post_titles"]:
                info["post_count"] = len(info["post_titles"])
            elif info["post_count"] == 0 and post_urls:
                info["post_count"] = len(post_urls)

            # ── 개설 연도 추출 (RSS 피드의 가장 오래된 글 기준 근사) ──
            # [v3.1.1] HTTP 경로에서 개설일은 공식 제공되지 않아 항상 0이었다.
            # RSS 피드(최근 글)를 받아와 RSS가 커버하는 기간에서 가장 오래된 글의
            # 연도를 '최초 활동 시점(근사)'으로 사용한다.
            # RSS는 최근 글만 제공하므로 실제 개설년도보다 최근일 수 있다 → 근사치.
            if info["blog_open_year"] == 0:
                try:
                    rss_resp = session.get(
                        f"https://rss.blog.naver.com/{blog_id}.xml",
                        headers=blog_headers, timeout=6, allow_redirects=True,
                    )
                    if rss_resp.status_code == 200 and "<rss" in rss_resp.text[:300]:
                        pub_dates = re.findall(
                            r"<pubDate>([^<]+)</pubDate>", rss_resp.text
                        )
                        years = []
                        for ds in pub_dates:
                            ym = re.search(r"(20\d{2})", ds)
                            if ym:
                                years.append(int(ym.group(1)))
                        if years:
                            # RSS 항목 중 가장 오래된 연도
                            info["blog_open_year"] = min(years)
                            info["blog_open_year_is_approx"] = True

                        # ── 게시글 수: RSS 항목 개수 (하한 보장) ──
                        # 네이버 RSS는 최근 글 최대 ~50개 제공.
                        # - RSS 개수 < 50 → 실제 전체 글 수와 일치
                        # - RSS 개수 >= 50 → 전체 글 수는 '최소 50개' (하한)
                        # 검색 URL 개수로 추정한 값(len(post_urls))보다 정확하므로 덮어씀.
                        item_count = len(re.findall(r"<item>", rss_resp.text))
                        if item_count > 0:
                            info["post_count"] = item_count
                            info["post_count_source"] = "rss"
                            if item_count >= 50:
                                info["post_count_is_lower_bound"] = True
                except requests.RequestException:
                    pass

            # ── 누적 방문자 보정: NVisitorgp4Ajax 일별 합계 ──
            # [v3.1.1] '전체 방문자' 문구가 페이지에 없어 0이 되는 블로그가 많아
            # 일별 방문자(최대 5일) 합계를 누적 방문자 대신 사용한다.
            # (최근 활동성 지표 — 누적과는 다르지만 방문 기준 필터의 실용적 근사)
            try:
                v_resp = session.get(
                    f"https://blog.naver.com/NVisitorgp4Ajax.naver?blogId={blog_id}",
                    headers={**blog_headers, "Referer": f"https://blog.naver.com/{blog_id}"},
                    timeout=6, allow_redirects=True,
                )
                if v_resp.status_code == 200:
                    cnts = re.findall(r'cnt="(\d+)"', v_resp.text)
                    if cnts:
                        daily_sum = sum(int(x) for x in cnts)
                        info["visitor_is_daily_sum"] = True
                        # 일별 합계가 기존 추정보다 크면 보정 (누적 추정 실패 보완)
                        if daily_sum > info["visitor_count"]:
                            info["visitor_count"] = daily_sum
                        # 일일 방문자: 마지막 cnt(가장 최근 날) — 이미 있으면 유지
                        if not info["daily_visitor_count"]:
                            info["daily_visitor_count"] = int(cnts[-1])
            except requests.RequestException:
                pass

            return info

        except requests.RequestException:
            return None
        except Exception:
            return None

    def http_prefilter_batch(
        self,
        blog_ids: List[str],
        keyword: str = "",
        max_candidates: int = 150,
        callback: Optional[Callable] = None,
        stop_flag: Optional[Callable] = None,
        max_workers: int = 10,
    ) -> List[Dict]:
        """
        여러 블로그를 병렬 HTTP로 사전 필터링 (최대 속도).
        ThreadPoolExecutor로 동시 요청 수행.

        Args:
            stop_flag: callable — True를 반환하면 중지
            max_workers: 동시 요청 수 (기본10개)

        Returns:
            사전 필터를 통과한 블로그 정보 리스트
        """
        results = []
        checked = 0
        lock = __import__('threading').Lock()

        def check_one(blog_id):
            """단일 블로그 HTTP 체크 (스레드 안전)"""
            nonlocal checked

            if stop_flag and stop_flag():
                return None

            # 검색 결과에서 미리 추출한 메타데이터 전달
            search_meta = getattr(self, '_search_metadata', {}).get(blog_id, None)
            info = self.http_prefilter(blog_id, keyword, search_meta=search_meta)
            if not info:
                return None

            # 검색 메타데이터의 블로그 이름이 있으면 info에 병합
            if search_meta and search_meta.get("blog_name") and not info.get("blog_name"):
                info["blog_name"] = search_meta["blog_name"]

            return info

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(check_one, bid): bid
                for bid in blog_ids
            }

            for future in as_completed(futures):
                if stop_flag and stop_flag():
                    executor.shutdown(wait=False, cancel_futures=True)
                    if callback:
                        callback("  [HTTP] 사용자에 의해 중지됨", "warning")
                    break

                bid = futures[future]
                try:
                    info = future.result()
                except Exception:
                    info = None

                with lock:
                    checked += 1
                    if info and len(results) < max_candidates:
                        results.append(info)
                        if callback:
                            callback(
                                f"  [HTTP] [{checked}/{len(blog_ids)}] {bid} - "
                                f"{info['blog_name'] or '(이름 없음)'}"
                                f" 이웃:{info['neighbor_count']} 방문:{info['visitor_count']}",
                                "info",
                            )
                    elif callback and checked % 30 == 0:
                        try:
                            callback(
                                f"  [HTTP] [{checked}/{len(blog_ids)}] 진행 중..."
                                f" (통과: {len(results)}건)",
                                "info",
                            )
                        except Exception:
                            pass

        return results

    # ──────────────────────────────────────────────────────
    #  키워드 검증 — 블로그 포스트에서 키워드 일치 확인 (5회 이상)
    # ──────────────────────────────────────────────────────
    def verify_keyword_match(self, blog_id: str, keyword: str, blog_info: dict = None, search_meta: dict = None) -> dict:
        """
        HTTP로 블로그 페이지를 가져와 키워드 일치 여부 확인.
        종합 판단: 포스트 제목 + 블로그 이름 + 카테고리 + 설명에서 키워드 매칭.
        1개 이상의 항목에서 키워드가 발견되면 검증 통과.

        Args:
            blog_id: 블로그 ID
            keyword: 검색 키워드
            blog_info: 사전 필터에서 수집한 블로그 정보 (선택)

        Returns:
            {
                "verified": bool,
                "match_count": int,
                "total_posts": int,
                "post_titles": list,
                "matched_titles": list,
                "match_sources": list,  # 매칭된 소스 목록
                "message": str
            }
        """
        result = {
            "verified": False,
            "match_count": 0,
            "total_posts": 0,
            "post_titles": [],
            "matched_titles": [],
            "match_sources": [],
            "message": "",
        }

        session = self._new_session()
        blog_headers = {
            "User-Agent": MOBILE_UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://www.naver.com/",
        }

        # 모바일 블로그 페이지에서 포스트 목록 추출
        urls = [
            f"https://m.blog.naver.com/{blog_id}?tab=1",
            f"https://blog.naver.com/{blog_id}",
        ]

        resp = None
        for url in urls:
            try:
                resp = session.get(url, headers=blog_headers, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    break
                resp = None
            except requests.RequestException:
                resp = None
                continue

        if resp is None or resp.status_code != 200:
            result["message"] = "페이지 로드 실패"
            return result

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            kw = keyword.lower().strip()

            # 블로그 메인 페이지 에러 감지
            page_text_check = soup.get_text(separator=" ", strip=True)
            for err_p in ["페이지 주소를 확인해주세요", "존재하지 않는 페이지", "비공개 블로그"]:
                if err_p in page_text_check:
                    result["message"] = f"에러 페이지 감지: {err_p}"
                    return result

            # ── 0. 블로그 이름, 카테고리, 설명 (사전 데이터에서) ──
            blog_name = ""
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                m = re.match(r"^(.+?)\s*:\s*네이버\s*블로그", title_text)
                if m:
                    blog_name = m.group(1).strip()
            if not blog_name and blog_info:
                blog_name = blog_info.get("blog_name", "")

            name_match = False
            if blog_name and kw in blog_name.lower():
                name_match = True
                result["match_sources"].append(f"블로그명 '{blog_name}'")

            category = ""
            cat_m = re.search(
                r"(맛집|여행|육아|IT|패션|뷰티|건강|인테리어|반려동물|일상|요리|국내여행|카페|동물|교육|스포츠|자동차|음악|영화|도서)",
                soup.get_text(separator=" ", strip=True),
            )
            if cat_m:
                category = cat_m.group(1)
            elif blog_info:
                category = blog_info.get("category", "")

            cat_match = False
            if category and kw in category.lower():
                cat_match = True
                result["match_sources"].append(f"카테고리 '{category}'")

            description = ""
            desc_m = re.search(r"소개\s*(.{5,200}?)(?:인기글|글감|대표글)", soup.get_text(separator=" ", strip=True))
            if desc_m:
                description = desc_m.group(1).strip()
            elif blog_info:
                description = blog_info.get("description", "")

            desc_match = False
            if description and kw in description.lower():
                desc_match = True
                result["match_sources"].append(f"설명에 키워드 포함")

            # ── 1. 포스트 링크 수집 ──
            # 우선: 검색 결과에서 미리 추출한 포스트 URL 사용
            post_urls = []
            seen_urls = set()
            post_titles = []
            seen_titles = set()
            if search_meta and search_meta.get("post_urls"):
                for url in search_meta["post_urls"]:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        post_urls.append(url)
                # 검색 결과에서 추출한 제목도 사전 등록
                for title in search_meta.get("post_titles", []):
                    if title not in seen_titles:
                        seen_titles.add(title)
                        post_titles.append(title)
            # 없으면 블로그 페이지에서 <a> 태그로 추출 (fallback)
            if not post_urls:
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if re.search(r"/\d{10,}$", href) or "PostView.naver" in href:
                        if href.startswith("/"):
                            full_url = f"https://m.blog.naver.com{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = f"https://m.blog.naver.com/{blog_id}/{href}"
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            post_urls.append(full_url)
                    elif "blog.naver.com" in href and re.search(r"/\d{10,}", href):
                        if href.startswith("http"):
                            full_url = href
                        elif href.startswith("/"):
                            full_url = f"https://blog.naver.com{href}"
                        else:
                            full_url = f"https://blog.naver.com/{href}"
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            post_urls.append(full_url)

            # ── 2. 개별 포스트에서 제목 + 본문 텍스트 수집 ──
            all_body_texts = []
            max_fetch = min(len(post_urls), 8)  # 최대 8개 포스트 확인

            for i in range(max_fetch):
                try:
                    post_resp = session.get(
                        post_urls[i],
                        headers=blog_headers,
                        timeout=8,
                        allow_redirects=True,
                    )
                    if post_resp.status_code != 200:
                        continue
                    post_soup = BeautifulSoup(post_resp.text, "html.parser")

                    # 개별 포스트 에러 페이지 감지
                    post_text_check = post_soup.get_text(separator=" ", strip=True)
                    post_err = False
                    for err_p in ["페이지 주소를 확인해주세요", "존재하지 않는 페이지", "삭제된 게시물"]:
                        if err_p in post_text_check:
                            post_err = True
                            break
                    if post_err:
                        continue  # 이 포스트는 건너뜀

                    # 제목 추출
                    post_title = ""
                    ptitle_tag = post_soup.find("title")
                    if ptitle_tag:
                        raw_title = ptitle_tag.get_text(strip=True)
                        tm = re.match(r"^(.+?)\s*:\s*.+?:\s*네이버\s*블로그", raw_title)
                        if tm:
                            post_title = tm.group(1).strip()
                        else:
                            post_title = raw_title

                    if not post_title:
                        for sel in [".se-text-paragraph", ".post-title", "h3", ".title"]:
                            el = post_soup.select_one(sel)
                            if el:
                                post_title = el.get_text(strip=True)
                                if len(post_title) > 5:
                                    break

                    if post_title and 3 < len(post_title) < 200 and post_title not in seen_titles:
                        seen_titles.add(post_title)
                        post_titles.append(post_title)

                    # 본문 텍스트 추출 (스마트에디터 ONE + 구형 에디터)
                    body_text = ""
                    for body_sel in [
                        ".se-main-container",
                        ".post-view",
                        ".post_ct",
                        "#postViewArea",
                        ".se-component-content",
                    ]:
                        body_el = post_soup.select_one(body_sel)
                        if body_el:
                            body_text = body_el.get_text(separator=" ", strip=True)
                            if len(body_text) > 50:
                                break

                    if not body_text or len(body_text) < 50:
                        body_text = post_soup.get_text(separator=" ", strip=True)

                    if body_text:
                        all_body_texts.append(body_text[:5000])

                except requests.RequestException:
                    continue
                except Exception:
                    continue

            result["total_posts"] = len(post_titles)
            result["post_titles"] = post_titles[:20]

            # ── 3. 키워드 매칭 ──
            post_matched = []
            for title in post_titles:
                if kw in title.lower():
                    post_matched.append(title)

            if post_matched:
                result["match_sources"].append(f"포스트 제목 {len(post_matched)}개")

            # 본문 텍스트에서 키워드 카운팅
            combined_body = " ".join(all_body_texts).lower()
            body_keyword_count = combined_body.count(kw) if kw else 0

            if body_keyword_count >= 3:
                result["match_sources"].append(f"본문 키워드 {body_keyword_count}회")

            # 페이지 전체 텍스트에서 키워드 매칭 (블로그 메인 페이지)
            page_text = soup.get_text(separator=" ", strip=True).lower()
            total_match = page_text.count(kw) if kw else 0

            # ── 4. 종합 판단 ──
            all_sources = (
                name_match or cat_match or desc_match
                or len(post_matched) > 0
                or body_keyword_count >= 3
            )
            has_enough_content = total_match >= 3 or body_keyword_count >= 3

            result["match_count"] = len(post_matched) + (1 if body_keyword_count >= 3 else 0)
            result["matched_titles"] = post_matched[:10]

            if all_sources or has_enough_content:
                result["verified"] = True
                sources_str = ", ".join(result["match_sources"]) if result["match_sources"] else f"페이지 내 키워드 {total_match}회"
                result["message"] = f"검증 통과: {sources_str}"
            else:
                result["verified"] = False
                result["message"] = f"검증 미통과: 키워드 '{keyword}' 매칭 없음 (페이지 키워드 {total_match}회, 본문 키워드 {body_keyword_count}회)"

        except Exception as e:
            result["message"] = f"검증 오류: {e}"

        return result

    def verify_keyword_batch(
        self,
        bloggers: List[BloggerInfo],
        keyword: str,
        min_matches: int = 1,
        callback: Optional[Callable] = None,
        stop_flag: Optional[Callable] = None,
        max_workers: int = 5,
    ) -> Tuple[List[BloggerInfo], List[Dict]]:
        """
        여러 블로그의 키워드 일치도를 병렬 검증.
        min_matches 이상의 포스트에서 키워드가 발견된 블로그만 통과.

        Returns:
            (통과 블로그 목록, 탈락 블로그 목록)
        """
        verified_bloggers = []
        rejected_bloggers = []
        lock = __import__('threading').Lock()
        checked_count = [0]

        def check_one(blogger):
            if stop_flag and stop_flag():
                return None

            bid = blogger.blog_id
            # 검색 결과에서 미리 추출한 메타데이터 전달
            search_meta = getattr(self, '_search_metadata', {}).get(bid, None)
            vr = self.verify_keyword_match(bid, keyword, search_meta=search_meta)

            with lock:
                checked_count[0] += 1
                if callback:
                    status = "✅" if vr["verified"] else "❌"
                    callback(
                        f"  [검증] [{checked_count[0]}/{len(bloggers)}] "
                        f"{blogger.blog_name or bid} - {status} "
                        f"({vr['match_count']}/{min_matches}개 일치)",
                        "info" if vr["verified"] else "warning",
                    )

            return (blogger, vr)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(check_one, b): b
                for b in bloggers
            }

            for future in as_completed(futures):
                if stop_flag and stop_flag():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                try:
                    result_tuple = future.result()
                except Exception:
                    result_tuple = None

                if result_tuple is None:
                    continue

                blogger, vr = result_tuple
                with lock:
                    if vr["verified"]:
                        verified_bloggers.append(blogger)
                    else:
                        rejected_bloggers.append({
                            "blog_id": blogger.blog_id,
                            "blog_name": blogger.blog_name or blogger.blog_id,
                            "reasons": [vr["message"]],
                            "match_count": vr["match_count"],
                            "total_posts": vr["total_posts"],
                            "matched_titles": vr["matched_titles"],
                        })

        # 관련성 점수순 정렬
        verified_bloggers.sort(key=lambda x: x.relevance_score, reverse=True)
        return verified_bloggers, rejected_bloggers

    # ──────────────────────────────────────────────────────
    #  네이버 검색에서 블로그 ID 수집
    def search_blog_ids_http(self, keyword: str, max_pages: int = 3) -> List[str]:
        """
        requests로 네이버 검색에서 블로그 ID 수집 (초고속, 브라우저 불필요).
        세션 기반으로 네이버 차단(403)을 방지.
        블로그 ID와 함께 검색 결과에서 포스트 URL, 제목, 블로그명 등을 추출.
        """
        all_blog_ids = []
        seen = set()
        t_start = time.time()

        # 블로그별 검색 결과 메타데이터 저장
        # {blog_id: {"post_urls": [...], "post_titles": [...], "blog_name": str, "description": str}}
        self._search_metadata = {}

        # 세션 초기화 (쿠키 포함)
        session = self._get_session()
        search_headers = {
            "User-Agent": DESKTOP_UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://www.naver.com/",
        }

        for page_num in range(1, max_pages + 1):
            start = (page_num - 1) * 15 + 1
            url = (
                f"https://search.naver.com/search.naver"
                f"?where=blog&query={keyword}"
                f"&sm=tab_opt&start={start}"
                f"&ssc=tab.blog.all"
            )

            try:
                resp = session.get(url, headers=search_headers, timeout=10)
                if resp.status_code != 200:
                    self._log(f"  페이지 {page_num}: HTTP {resp.status_code}", "warning")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # ── 검색 결과에서 블로그 ID + 포스트 URL + 제목 추출 ──
                # 네이버 검색 결과 HTML 구조:
                #   <a href="https://blog.naver.com/{blog_id}/{post_no}">제목</a>
                #   <a href="https://m.blog.naver.com/{blog_id}/{post_no}">제목</a>
                new_count = 0
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]

                    # 포스트 URL 패턴 매칭
                    post_match = re.search(
                        r'blog\.naver\.com/([a-zA-Z0-9_-]{3,20})/(\d{10,})',
                        href,
                    )
                    if not post_match:
                        continue

                    bid = post_match.group(1)
                    post_no = post_match.group(2)

                    # 필수 제외 ID 필터링
                    if bid in ('MyBlog', 'section', '') or len(bid) < 3:
                        continue

                    # 포스트 URL 정규화
                    if "m.blog" in href:
                        post_url = f"https://m.blog.naver.com/{bid}/{post_no}"
                    else:
                        post_url = f"https://blog.naver.com/{bid}/{post_no}"

                    # 블로그 ID 등록
                    if bid not in seen:
                        seen.add(bid)
                        all_blog_ids.append(bid)
                        self._search_metadata[bid] = {
                            "post_urls": [],
                            "post_titles": [],
                            "blog_name": "",
                            "description": "",
                        }
                        new_count += 1

                    # 포스트 URL + 제목 수집 (블로그당 최대 5개)
                    meta = self._search_metadata.get(bid, {})
                    if post_url not in meta.get("post_urls", []):
                        if len(meta.get("post_urls", [])) < 5:
                            meta["post_urls"].append(post_url)
                            # 링크 텍스트에서 제목 추출
                            link_text = a_tag.get_text(strip=True)
                            if link_text and 3 < len(link_text) < 200:
                                meta["post_titles"].append(link_text)

                # ── 블로그 이름/설명 추출 (검색 결과 블록에서) ──
                for bid in list(self._search_metadata.keys()):
                    if self._search_metadata[bid].get("blog_name"):
                        continue
                    # 블로그 이름: <a> 태그의 class 또는 title에서 추출
                    name_selectors = [
                        f'a[href*="{bid}"] .blog_name',
                        f'a[href*="{bid}"] .name',
                    ]
                    for sel in name_selectors:
                        el = soup.select_one(sel)
                        if el:
                            self._search_metadata[bid]["blog_name"] = el.get_text(strip=True)
                            break

                self._log(
                    f"  페이지 {page_num}: {new_count}개 신규 블로그",
                    "success",
                )

            except requests.RequestException as e:
                self._log(f"  페이지 {page_num} 오류: {e}", "error")

        elapsed = time.time() - t_start
        self._log(
            f"총 {len(all_blog_ids)}개 블로그 ID 수집 완료 "
            f"({elapsed:.1f}초)",
            "success",
        )
        return all_blog_ids

    # 기존 Playwright 기반 검색 (백업용)
    async def search_blog_ids(self, keyword: str, max_pages: int = 3) -> List[str]:
        return self.search_blog_ids_http(keyword, max_pages)

    # ──────────────────────────────────────────────────────
    #  개별 블로그 상세 정보 수집
    # ──────────────────────────────────────────────────────
    async def get_blog_detail(self, blog_id: str) -> Optional[BloggerInfo]:
        blogger = BloggerInfo(
            blog_id=blog_id,
            blog_url=f"{self.BLOG_HOME}/{blog_id}",
        )

        try:
            url = f"{self.BLOG_HOME}/{blog_id}"
            await self.page.goto(url, wait_until="networkidle")
            await asyncio.sleep(3)

            detail = await self.page.evaluate(self._extract_blog_info_js())

            # iframe에서도 정보 추출 시도
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                try:
                    frame_detail = await frame.evaluate(self._extract_blog_info_js())
                    for key in [
                        "blogName", "category", "neighborCount",
                        "postCount", "visitorCount", "recentDate",
                        "blogOpenDate", "dailyVisitorCount",
                    ]:
                        if frame_detail.get(key) and not detail.get(key):
                            detail[key] = frame_detail[key]
                    for key in ["postTitles", "postContents", "hashtags", "imageAlts"]:
                        fval = frame_detail.get(key, [])
                        dval = detail.get(key, [])
                        if fval and (not dval or len(fval) > len(dval)):
                            detail[key] = fval
                except Exception:
                    pass

            # BloggerInfo 매핑
            blogger.blog_name = detail.get("blogName", "")
            blogger.category = detail.get("category", "")
            blogger.description = detail.get("text", "")[:300]
            blogger.post_titles = " ".join(detail.get("postTitles", []))
            blogger.post_contents = " ".join(detail.get("postContents", []))[:1500]
            blogger.hashtags = " ".join(detail.get("hashtags", []))
            blogger.image_alts = " ".join(detail.get("imageAlts", []))
            blogger.post_count = detail.get("postCount", 0)
            blogger.neighbor_count = detail.get("neighborCount", 0)
            blogger.visitor_count = detail.get("visitorCount", 0)
            blogger.daily_visitor_count = detail.get("dailyVisitorCount", 0)
            blogger.recent_post_date = detail.get("recentDate", "")
            blogger.blog_open_date = detail.get("blogOpenDate", "")

            # 개설 연도 추출
            blogger.blog_open_year = self._extract_year(blogger.blog_open_date)

            # 카테고리 추론
            if not blogger.category:
                blogger.category = self._infer_category(detail.get("text", ""))

            # 파싱 실패 판정
            if not blogger.blog_name and not detail.get("text", "").strip():
                blogger.parse_failed = True
                self._log(f"  {blog_id}: 파싱 데이터 부족", "warning")

            return blogger

        except Exception as e:
            self._log(f"  블로그 상세 수집 실패 ({blog_id}): {e}", "error")
            return None

    # ──────────────────────────────────────────────────────
    #  하드 필터 — ALL-TRUE (5개 조건)
    # ──────────────────────────────────────────────────────
    def filter_bloggers(
        self,
        bloggers: List[BloggerInfo],
        keyword: str = "",
        min_operating_years: int = 0,
        min_neighbors: int = 0,
        min_visitors: int = 0,
        min_daily_visitors: int = 0,
        min_posts: int = 0,
    ) -> Tuple[List[BloggerInfo], List[Dict]]:
        """
        ALL-TRUE 필터링: 아래 5개 조건을 모두 만족해야 통과.

        1. 운영 기간 (N년 이상) — 개설 연도 기준 현재년도까지 N년 이상 운영
        2. 최소 이웃 수 >= N
        3. 최소 누적 방문자 수 >= N
        4. 최소 일일 방문자 수 >= N
        5. 최소 게시글 수 >= N

        Returns:
            (통과 목록, 탈락 상세 목록)
        """
        filtered = []
        rejected = []
        current_year = datetime.now().year

        for b in bloggers:
            reasons = []

            # ── 파싱 실패 → 즉시 제외 ──
            if b.parse_failed:
                reasons.append("데이터 파싱 실패")
                rejected.append({
                    "blog_id": b.blog_id,
                    "blog_name": b.blog_name or b.blog_id,
                    "reasons": reasons,
                })
                continue

            # ── 키워드 일치도 판정 ──
            if keyword:
                # 이미 점수가 설정되어 있으면 그대로 사용 (기본 점수 포함)
                if b.relevance_score > 0:
                    score = b.relevance_score
                else:
                    score = self._calc_relevance(keyword, b)
                    b.relevance_score = score
                if score == 0:
                    reasons.append(f"키워드 '{keyword}'와 무관 (일치도 0%)")
                    rejected.append({
                        "blog_id": b.blog_id,
                        "blog_name": b.blog_name or b.blog_id,
                        "reasons": reasons,
                    })
                    continue

            # ── 1. 운영 기간 (N년 이상) ──
            # HTTP 응답에서 개설일을 추출할 수 없으므로, 개설 연도 미확인 시 통과 처리
            # (운영 기간 필터는 개설일 확인 가능한 경우에만 적용)
            if min_operating_years > 0 and b.blog_open_year > 0:
                operating_years = current_year - b.blog_open_year
                if operating_years < min_operating_years:
                    reasons.append(
                        f"운영 기간 부족: {operating_years}년 < 기준 {min_operating_years}년"
                    )
            # blog_open_year == 0인 경우: 개설일 미확인 → 통과 처리 (탈락 사유에서 제외)

            # ── 2. 최소 이웃 수 ──
            # neighbor_count == 0인 경우: 데이터 미확인 → 통과 처리
            # (이웃 수를 추출하지 못한 경우 필터에서 제외)
            if min_neighbors > 0 and b.neighbor_count > 0:
                if b.neighbor_count < min_neighbors:
                    reasons.append(
                        f"이웃 수 부족: {b.neighbor_count}명 < 기준 {min_neighbors}명"
                    )

            # ── 3. 최소 누적 방문자 수 ──
            # visitor_count == 0인 경우: 데이터 미확인 → 통과 처리
            if min_visitors > 0 and b.visitor_count > 0:
                if b.visitor_count < min_visitors:
                    reasons.append(
                        f"누적방문자 부족: {b.visitor_count}명 < 기준 {min_visitors}명"
                    )

            # ── 4. 최소 일일 방문자 수 ──
            # daily_visitor_count == 0인 경우: 데이터 미확인 → 통과 처리
            if min_daily_visitors > 0 and b.daily_visitor_count > 0:
                if b.daily_visitor_count < min_daily_visitors:
                    reasons.append(
                        f"일일방문자 부족: {b.daily_visitor_count}명 < 기준 {min_daily_visitors}명"
                    )

            # ── 5. 최소 게시글 수 ──
            # HTTP 응답에서 게시글 수를 추출할 수 없는 경우(post_count==0) 통과 처리
            if min_posts > 0 and b.post_count > 0:
                if b.post_count < min_posts:
                    reasons.append(
                        f"게시글 수 부족: {b.post_count}개 < 기준 {min_posts}개"
                    )

            # ── 판정 ──
            if not reasons:
                filtered.append(b)
            else:
                rejected.append({
                    "blog_id": b.blog_id,
                    "blog_name": b.blog_name or b.blog_id,
                    "reasons": reasons,
                })

        # 관련성 점수순 내림차순 정렬
        filtered.sort(key=lambda x: x.relevance_score, reverse=True)
        return filtered, rejected

    # ──────────────────────────────────────────────────────
    #  키워드 관련성 점수 (제목 > 본문 > 해시태그)
    # ──────────────────────────────────────────────────────
    def _calc_relevance(self, keyword: str, blogger: BloggerInfo) -> int:
        """
        키워드 관련성 점수 (0~100).

        계층적 우선순위:
          1순위: 포스트 제목 (35점)
          2순위: 포스트 본문 (25점)
          3순위: 블로그 설명/소개 (20점) ★추가
          4순위: 해시태그   (15점)
          5순위: 이미지 alt (5점)
        보너스: 블로그 이름 (+10), 카테고리 (+5)
        """
        kw = keyword.lower().strip()
        if not kw:
            return 0

        titles = blogger.post_titles.lower()
        contents = blogger.post_contents.lower()
        description = blogger.description.lower()
        hashtags = blogger.hashtags.lower()
        images = blogger.image_alts.lower()
        blog_name = blogger.blog_name.lower()
        category = blogger.category.lower()

        score = 0
        title_hit = False
        content_hit = False
        desc_hit = False
        hashtag_hit = False

        # 키워드가 여러 단어일 경우 각 단어도 체크
        parts = kw.split()

        # ── 1순위: 포스트 제목 (35점) ──
        if kw in titles:
            score += 35
            title_hit = True
        elif parts and len(parts) > 1:
            ratio = sum(1 for p in parts if p in titles) / len(parts)
            if ratio >= 0.5:
                score += int(35 * ratio)
                title_hit = True

        # ── 2순위: 포스트 본문 (25점) ──
        if kw in contents:
            score += 25
            content_hit = True
        elif parts and len(parts) > 1:
            ratio = sum(1 for p in parts if p in contents) / len(parts)
            if ratio >= 0.5:
                score += int(25 * ratio)
                content_hit = True

        # ── 3순위: 블로그 설명/소개 (20점) ★신규 추가 ──
        if kw in description:
            score += 20
            desc_hit = True
        elif parts and len(parts) > 1:
            ratio = sum(1 for p in parts if p in description) / len(parts)
            if ratio >= 0.5:
                score += int(20 * ratio)
                desc_hit = True

        # ── 4순위: 해시태그 (15점) ──
        if kw in hashtags:
            score += 15
            hashtag_hit = True
        elif parts and len(parts) > 1:
            ratio = sum(1 for p in parts if p in hashtags) / len(parts)
            if ratio >= 0.5:
                score += int(15 * ratio)
                hashtag_hit = True

        # ── 5순위: 이미지 alt (5점) ──
        if kw in images:
            score += 5
        elif parts and len(parts) > 1:
            ratio = sum(1 for p in parts if p in images) / len(parts)
            if ratio >= 0.5:
                score += int(5 * ratio)

        # ── 보너스 ──
        if kw in blog_name:
            score += 10
        if kw in category:
            score += 5

        # ── 풀매칭 보너스 ──
        if title_hit and content_hit and hashtag_hit:
            score += 15
        elif title_hit and content_hit:
            score += 10
        elif title_hit and desc_hit:
            score += 5
        elif content_hit and desc_hit:
            score += 5

        return min(score, 100)

    # ──────────────────────────────────────────────────────
    #  유틸리티
    # ──────────────────────────────────────────────────────
    def _extract_year(self, date_str: str) -> int:
        """날짜 문자열에서 연도 추출"""
        if not date_str:
            return 0
        try:
            m = re.search(r"(\d{4})", date_str)
            if m:
                year = int(m.group(1))
                if 1900 <= year <= 2100:
                    return year
        except Exception:
            pass
        return 0

    def _infer_category(self, text: str) -> str:
        category_keywords = {
            "음식": ["요리", "음식", "레시피", "맛집", "파스타", "스파게티", "한식", "일식", "중식"],
            "여행": ["여행", "관광", "해외", "국내", "숙소", "호텔", "캠핑"],
            "육아": ["육아", "아이", "맘", "임신", "출산", "교육", "키즈"],
            "IT": ["개발", "프로그래밍", "코딩", "테크", "IT", "기술"],
            "패션": ["패션", "옷", "스타일", "코디", "의류"],
            "뷰티": ["뷰티", "화장품", "스킨케어", "메이크업"],
            "건강": ["건강", "운동", "다이어트", "헬스", "요가"],
            "인테리어": ["인테리어", "공간", "가구"],
            "반려동물": ["강아지", "고양이", "반려동물"],
        }
        text_lower = text.lower()
        scores = {}
        for cat, kws in category_keywords.items():
            s = sum(1 for kw in kws if kw in text_lower)
            if s > 0:
                scores[cat] = s
        return max(scores, key=scores.get) if scores else "기타"

    # ──────────────────────────────────────────────────────
    #  JavaScript: 블로그 정보 추출
    # ──────────────────────────────────────────────────────
    def _extract_blog_info_js(self) -> str:
        return r"""() => {
            const result = {
                blogName: '', category: '', description: '',
                postTitles: [], postContents: [], hashtags: [],
                imageAlts: [], postCount: 0, neighborCount: 0,
                recentDate: '', visitorCount: 0, dailyVisitorCount: 0,
                blogOpenDate: '', text: ''
            };

            const allText = document.body ? document.body.innerText : '';
            result.text = allText.substring(0, 8000);

            // ── 블로그 이름 ──
            // 방법1: title 태그에서 추출 ("블로그이름 : 네이버 블로그")
            const titleText = document.title || '';
            const titleMatch = titleText.match(/^(.+?)\s*:\s*네이버\s*블로그/);
            if (titleMatch) {
                result.blogName = titleMatch[1].trim().substring(0, 50);
            }
            // 방법2: 셀렉터로 추출
            if (!result.blogName) {
                for (const sel of [
                    '.blog2_title', '.blog_title', '#titleArea',
                    'a.blog_title', '.area_title', '.blog_name',
                    '.blog2_header .title', '.header_area .blog_title',
                    '.profile_name', '.se-bookmark-area .title',
                    '.title_area', '.nick', '.profile'
                ]) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent.trim()) {
                        result.blogName = el.textContent.trim().substring(0, 50);
                        break;
                    }
                }
            }
            // 방법3: 텍스트에서 블로그 이름 추출
            if (!result.blogName) {
                const nameMatch = allText.match(/^([가-힣a-zA-Z0-9_]+(?:의\s+하루|의\s+일상|의\s+空間|의\s+的故事))\.?/m);
                if (nameMatch) result.blogName = nameMatch[1].trim();
            }

            // ── 카테고리 ──
            for (const sel of [
                '.category', '.nav_item', '.tt_category a',
                '.blog2_category', '.blog_category', '.cate_name'
            ]) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    result.category = el.textContent.trim().substring(0, 20);
                    break;
                }
            }
            // 카테고리가 없으면 텍스트에서 추출
            if (!result.category) {
                const catMatch = allText.match(/(맛집|여행|육아|IT|패션|뷰티|건강|인테리어|반려동물|일상|요리)/);
                if (catMatch) result.category = catMatch[1];
            }

            // ── 포스트 제목 (최근 5개) ──
            const titleSet = new Set();
            // 방법1: <strong> 태그에서 추출 (블로그 목록)
            document.querySelectorAll('strong').forEach(el => {
                const t = el.textContent.trim();
                if (t && t.length > 5 && t.length < 200 && titleSet.size < 5) {
                    titleSet.add(t);
                }
            });
            // 방법2: 기존 셀렉터
            if (titleSet.size === 0) {
                for (const sel of [
                    '.post-title', '.se-text-paragraph', '.title_area a',
                    '.post_list .title', 'a.post-name', '.blog2_list .title',
                    '.post-view a', '.post-title-text', '.total_post_title a',
                    '.sseTITLE', '.title_all'
                ]) {
                    document.querySelectorAll(sel).forEach(el => {
                        const t = el.textContent.trim();
                        if (t && t.length > 5 && t.length < 200 && titleSet.size < 5) {
                            titleSet.add(t);
                        }
                    });
                }
            }
            result.postTitles = Array.from(titleSet);

            // ── 포스트 본문 (최근 3개) ──
            const contentSet = new Set();
            for (const sel of [
                '.se-main-container', '.post-content', '.post-body',
                '.entry-content', '#postContentArea', '.contents_style',
                '.se-document', '.se-paragraph', '#blog-content'
            ]) {
                document.querySelectorAll(sel).forEach(el => {
                    const t = el.textContent.trim().replace(/\s+/g, ' ');
                    if (t && t.length > 20 && contentSet.size < 3) {
                        contentSet.add(t.substring(0, 800));
                    }
                });
            }
            result.postContents = Array.from(contentSet);

            // ── 해시태그 ──
            const tagSet = new Set();
            for (const sel of [
                '.hashtag', '.tag', '.se-hash-tag', 'a[href*="tag"]',
                '.post-tag a', '.tag_area a', '.se-tag'
            ]) {
                document.querySelectorAll(sel).forEach(el => {
                    const t = el.textContent.trim().replace(/^#/, '');
                    if (t && t.length > 0 && t.length < 30) tagSet.add(t);
                });
            }
            const hashMatches = allText.match(/#[\w가-힣]+/g) || [];
            hashMatches.forEach(m => tagSet.add(m.replace(/^#/, '')));
            result.hashtags = Array.from(tagSet);

            // ── 이미지 alt ──
            const imgSet = new Set();
            document.querySelectorAll('img[alt]').forEach(img => {
                const alt = img.alt.trim();
                if (alt && alt.length > 2 && alt.length < 100 && imgSet.size < 10) {
                    imgSet.add(alt);
                }
            });
            result.imageAlts = Array.from(imgSet);

            // ── 수치 추출 (네이버 모바일 블로그 새 구조 대응) ──
            // 방문자: "오늘 N  전체 N" 또는 "방문자 N"
            const todayMatch = allText.match(/오늘\s*([0-9,]+)/);
            const totalVisitorMatch = allText.match(/전체\s*([0-9,]+)/);
            const visitorMatch = allText.match(/방문자[^0-9]*([0-9,]+)/);
            if (totalVisitorMatch) {
                result.visitorCount = parseInt(totalVisitorMatch[1].replace(/,/g, '')) || 0;
            } else if (visitorMatch) {
                result.visitorCount = parseInt(visitorMatch[1].replace(/,/g, '')) || 0;
            }
            if (todayMatch) {
                result.dailyVisitorCount = parseInt(todayMatch[1].replace(/,/g, '')) || 0;
            }

            // 이웃: "N명의 이웃" 또는 "이웃 N"
            const neighborMatch = allText.match(/([0-9,]+)명의\s*이웃/)
                || allText.match(/이웃[^0-9]*([0-9,]+)/);
            if (neighborMatch) {
                result.neighborCount = parseInt(neighborMatch[1].replace(/,/g, '')) || 0;
            }

            // 포스트 수: "포스트 N" 또는 <strong> 태그 개수로 추정
            const postCountMatch = allText.match(/(?:포스트|글\s*수|게시글)[^0-9]*([0-9,]+)/);
            if (postCountMatch) {
                result.postCount = parseInt(postCountMatch[1].replace(/,/g, '')) || 0;
            }
            // <strong> 태그 개수로 포스트 수 추정
            if (result.postCount === 0) {
                let strongCount = 0;
                document.querySelectorAll('strong').forEach(el => {
                    const t = el.textContent.trim();
                    if (t && t.length > 5 && t.length < 200) strongCount++;
                });
                if (strongCount > 0) result.postCount = strongCount;
            }

            // ── 최근 날짜 ──
            const dateMatches = allText.match(/20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}/g) || [];
            if (dateMatches.length > 0) result.recentDate = dateMatches[0];

            // ── 개설일 ──
            const openPatterns = [
                /개설[일때^0-9]*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})/,
                /블로그\s*개설[^0-9]*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})/,
                /시작일[^0-9]*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})/,
                /(\d{4})년\s*\d{1,2}월\s*\d{1,2}일\s*개설/,
                /(\d{4})[.\-/]\d{1,2}[.\-/]\d{1,2}.*개설/,
            ];
            for (const pat of openPatterns) {
                const m = allText.match(pat);
                if (m) {
                    if (m[1] && m[1].length === 4) {
                        result.blogOpenDate = m[1];
                    } else {
                        result.blogOpenDate = m[1] || m[0];
                    }
                    break;
                }
            }

            return result;
        }"""


if __name__ == "__main__":
    import sys

    def test_log(msg, level="info"):
        print(f"[{level.upper()}] {msg}")

    async def main():
        keyword = sys.argv[1] if len(sys.argv) > 1 else "음식"
        target = int(sys.argv[2]) if len(sys.argv) > 2 else 5

        crawler = NaverBlogCrawler()
        crawler.set_log_callback(test_log)

        await crawler.start(headless=False, mobile=True)
        try:
            blog_ids = await crawler.search_blog_ids(keyword, max_pages=3)
            print(f"\n=== 검색 결과: {len(blog_ids)}개 ===\n")

            bloggers = []
            for idx, bid in enumerate(blog_ids[:target]):
                print(f"[{idx+1}/{target}] {bid} 상세 수집 중...")
                detail = await crawler.get_blog_detail(bid)
                if detail:
                    bloggers.append(detail)
                await asyncio.sleep(1.5)

            filtered, rejected = crawler.filter_bloggers(
                bloggers, keyword=keyword,
                min_operating_years=3, min_neighbors=50,
                min_visitors=1000, min_daily_visitors=10,
                min_posts=30,
            )

            print(f"\n=== 통과: {len(filtered)}명 ===")
            for b in filtered:
                print(f"  {b.blog_name}({b.blog_id}) 일치도={b.relevance_score}%")
            print(f"\n=== 탈락: {len(rejected)}명 ===")
            for r in rejected:
                print(f"  {r['blog_name']}: {', '.join(r['reasons'])}")

        finally:
            await crawler.stop()

    asyncio.run(main())
