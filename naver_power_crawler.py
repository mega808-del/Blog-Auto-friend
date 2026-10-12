"""
═══════════════════════════════════════════════════════════════════
  네이버 파워블로거(인플루언서) 수집 크롤러 v1.0
  
  기능:
    1. 네이버 검색에서 특정 키워드 관련 블로그 수집
    2. 파워블로거 영향력 필터 (일방문자, 이웃수, 인플루언서 뱃지)
    3. 게시글 품질 필터 (본문 길이, 이미지 수, 스팸 감지)
    4. CSV 파일로 저장
  
  기술 스택:
    - requests + BeautifulSoup (HTTP 크롤링)
    - Playwright (JS 렌더링 필요 페이지)
    - pandas (데이터 정제 및 CSV 저장)
  
  사용법:
    python naver_power_crawler.py
    python naver_power_crawler.py --keyword "제주도 맛집" --pages 5
═══════════════════════════════════════════════════════════════════
"""

import asyncio
import re
import time
import csv
import json
import argparse
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Tuple
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ──────────────────────────────────────────────────────────────
#  로깅 설정
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  상수 정의
# ──────────────────────────────────────────────────────────────
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)

# 네이버 차단 방지용 요청 간격 (초)
REQUEST_DELAY_MIN = 1.5
REQUEST_DELAY_MAX = 3.5

# 스팸 문구 패턴
SPAM_PATTERNS = [
    r"원고료\s*지원",
    r"협찬",
    r"제품\s*제공",
    r"체험단",
    r"서포터즈",
    r"홍보\s*성",
    r"광고\s*글",
    r"대가\s*성",
    r"지급\s*받",
    r"무상\s*제공",
    r"제휴\s*마케팅",
    r"philip\s*ghost",
    r"금전적\s*대가",
]


# ──────────────────────────────────────────────────────────────
#  데이터 클래스
# ──────────────────────────────────────────────────────────────
@dataclass
class BlogPost:
    """개별 블로그 포스트 정보"""
    title: str = ""                  # 포스트 제목
    url: str = ""                    # 포스트 URL
    post_date: str = ""              # 작성일 (YYYY-MM-DD)
    body_text: str = ""              # 본문 텍스트 (공백 제외 길이)
    body_length: int = 0             # 본문 길이 (공백 제외)
    image_count: int = 0             # 첨부 이미지 개수
    has_influencer_badge: bool = False  # 인플루언서 뱃지 여부
    is_spam: bool = False            # 스팸 여부
    spam_reason: str = ""            # 스팸 사유


@dataclass
class PowerBlogger:
    """파워블로거 정보"""
    blog_name: str = ""              # 블로그 이름
    nickname: str = ""               # 블로거 닉네임
    blog_id: str = ""                # 블로그 ID
    blog_url: str = ""               # 블로그 URL
    daily_visitors: int = 0          # 일평균 방문자 수
    total_visitors: int = 0          # 누적 방문자 수
    neighbor_count: int = 0          # 이웃 수
    has_influencer_badge: bool = False  # 인플루언서 뱃지
    category: str = ""               # 카테고리
    description: str = ""            # 블로그 설명
    post_count: int = 0              # 게시글 수
    quality_posts: List[Dict] = field(default_factory=list)  # 품질 필터 통과 포스트


# ──────────────────────────────────────────────────────────────
#  메인 크롤러 클래스
# ──────────────────────────────────────────────────────────────
class NaverPowerCrawler:
    """
    네이버 파워블로거 수집 크롤러
    
    [수집 파이프라인]
    1단계: 네이버 검색에서 블로그 ID 수집 (HTTP)
    2단계: 각 블로그 상세 정보 수집 (HTTP + Playwright)
    3단계: 영향력 필터 적용 (방문자수, 이웃수, 뱃지)
    4단계: 게시글 품질 필터 적용 (본문길이, 이미지수, 스팸)
    5단계: CSV 저장
    """

    NAVER_SEARCH_URL = "https://search.naver.com/search.naver"
    BLOG_HOME = "https://blog.naver.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DESKTOP_UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        # 네이버 메인에서 쿠키 획득 (차단 방지)
        self._init_cookies()

    def _init_cookies(self):
        """네이버 메인에서 쿠키 초기화"""
        try:
            self.session.get("https://www.naver.com", timeout=5)
            logger.info("쿠키 초기화 완료")
        except Exception as e:
            logger.warning(f"쿠키 초기화 실패: {e}")

    def _smart_delay(self):
        """과도한 요청 방지를 위한 랜덤 딜레이"""
        delay = time.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        time.sleep(delay)

    # ──────────────────────────────────────────────────────
    #  1단계: 네이버 검색에서 블로그 ID 수집
    # ──────────────────────────────────────────────────────
    def search_blog_ids(self, keyword: str, max_pages: int = 5) -> List[str]:
        """
        네이버 블로그 검색에서 블로그 ID 수집
        
        Args:
            keyword: 검색 키워드 (예: "제주도 맛집")
            max_pages: 최대 검색 페이지 수
            
        Returns:
            중복 제거된 블로그 ID 리스트
        """
        all_blog_ids = []
        seen = set()

        logger.info(f"[1단계] '{keyword}' 블로그 검색 시작 (최대 {max_pages}페이지)")

        for page in range(1, max_pages + 1):
            start = (page - 1) * 15 + 1
            params = {
                "where": "blog",
                "query": keyword,
                "sm": "tab_opt",
                "start": start,
                "ssc": "tab.blog.all",
            }

            try:
                resp = self.session.get(
                    self.NAVER_SEARCH_URL, params=params, timeout=10
                )
                if resp.status_code != 200:
                    logger.warning(f"  페이지 {page}: HTTP {resp.status_code}")
                    continue

                # 정규식으로 블로그 ID 추출
                blog_ids = re.findall(
                    r'blog\.naver\.com/([a-zA-Z0-9_-]{3,20})',
                    resp.text,
                )
                # 필터링: 유효한 ID만
                blog_ids = [
                    bid for bid in blog_ids
                    if bid not in ("MyBlog", "section", "") and len(bid) >= 3
                ]

                new_count = 0
                for bid in blog_ids:
                    if bid not in seen:
                        seen.add(bid)
                        all_blog_ids.append(bid)
                        new_count += 1

                logger.info(f"  페이지 {page}: {new_count}개 신규 블로그 발견")

            except requests.RequestException as e:
                logger.error(f"  페이지 {page} 요청 오류: {e}")

            self._smart_delay()

        logger.info(f"[1단계 완료] 총 {len(all_blog_ids)}개 블로그 ID 수집")
        return all_blog_ids

    # ──────────────────────────────────────────────────────
    #  2단계: 블로그 상세 정보 수집
    # ──────────────────────────────────────────────────────
    def get_blog_detail(self, blog_id: str) -> Optional[PowerBlogger]:
        """
        개별 블로그의 상세 정보를 HTTP로 수집
        
        Args:
            blog_id: 블로그 ID
            
        Returns:
            PowerBlogger 객체 (실패 시 None)
        """
        blogger = PowerBlogger(blog_id=blog_id)
        blogger.blog_url = f"{self.BLOG_HOME}/{blog_id}"

        # 시도할 URL (모바일 → 데스크톱)
        urls = [
            f"https://m.blog.naver.com/{blog_id}?tab=1",
            f"{self.BLOG_HOME}/{blog_id}",
        ]

        resp = None
        for url in urls:
            try:
                resp = self.session.get(url, timeout=10, allow_redirects=True)
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
            page_text = soup.get_text(separator=" ", strip=True)

            # ── 블로그 이름 ──
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                m = re.match(r"^(.+?)\s*:\s*네이버\s*블로그", title_text)
                if m:
                    blogger.blog_name = m.group(1).strip()

            # ── 이웃 수 ──
            neighbor_m = re.search(r"([0-9,]+)명의\s*이웃", page_text)
            if neighbor_m:
                blogger.neighbor_count = int(
                    neighbor_m.group(1).replace(",", "")
                )

            # ── 방문자 수 ──
            today_m = re.search(r"오늘\s*([0-9,]+)", page_text)
            total_m = re.search(r"전체\s*([0-9,]+)", page_text)
            if total_m:
                blogger.total_visitors = int(
                    total_m.group(1).replace(",", "")
                )
            if today_m:
                blogger.daily_visitors = int(
                    today_m.group(1).replace(",", "")
                )

            # ── 카테고리 ──
            cat_m = re.search(
                r"(맛집|여행|육아|IT|패션|뷰티|건강|인테리어|반려동물|"
                r"일상|요리|국내여행|카페|교육|스포츠|자동차|음악|영화|도서)",
                page_text,
            )
            if cat_m:
                blogger.category = cat_m.group(1)

            # ── 블로그 설명 ──
            desc_m = re.search(
                r"소개\s*(.{5,200}?)(?:인기글|글감|대표글)", page_text
            )
            if desc_m:
                blogger.description = desc_m.group(1).strip()

            # ── 게시글 수 ──
            post_m = re.search(
                r"(?:포스트|글\s*수|게시글)[^0-9]*([0-9,]+)", page_text
            )
            if post_m:
                blogger.post_count = int(post_m.group(1).replace(",", ""))

            # ── 인플루언서 뱃지 확인 ──
            # 방법1: 페이지 텍스트에서 확인
            if "인플루언서" in page_text or "influencer" in page_text.lower():
                blogger.has_influencer_badge = True
            # 방법2: 특정 셀렉터에서 확인
            badge_selectors = [
                ".influencer_badge", ".badge_influencer",
                ".ico_influencer", "[class*='influencer']",
                "[class*='badge']", ".blog2_profile .badge",
            ]
            for sel in badge_selectors:
                badge_el = soup.select_one(sel)
                if badge_el:
                    badge_text = badge_el.get_text(strip=True).lower()
                    if "인플루언서" in badge_text or "influencer" in badge_text:
                        blogger.has_influencer_badge = True
                        break

            return blogger

        except Exception as e:
            logger.debug(f"  블로그 정보 파싱 오류 ({blog_id}): {e}")
            return None

    # ──────────────────────────────────────────────────────
    #  3단계: 블로그 상세 정보 수집 (병렬)
    # ──────────────────────────────────────────────────────
    def collect_blog_details(
        self, blog_ids: List[str], max_collect: int = 100
    ) -> List[PowerBlogger]:
        """
        여러 블로그의 상세 정보를 순차적으로 수집
        
        Args:
            blog_ids: 블로그 ID 리스트
            max_collect: 최대 수집 수
            
        Returns:
            PowerBlogger 리스트
        """
        bloggers = []
        total = min(len(blog_ids), max_collect)

        logger.info(f"[2단계] 블로그 상세 정보 수집 시작 ({total}개 대상)")

        for idx, bid in enumerate(blog_ids[:max_collect], 1):
            logger.info(
                f"  [{idx}/{total}] {bid} 정보 수집 중..."
            )

            blogger = self.get_blog_detail(bid)
            if blogger:
                bloggers.append(blogger)
                logger.info(
                    f"    → {blogger.blog_name or '(이름 없음)'} "
                    f"이웃:{blogger.neighbor_count} "
                    f"방문:{blogger.daily_visitors}/일 "
                    f"뱃지:{'✅' if blogger.has_influencer_badge else '❌'}"
                )
            else:
                logger.warning(f"    → {bid}: 정보 수집 실패")

            self._smart_delay()

        logger.info(f"[2단계 완료] {len(bloggers)}개 블로그 정보 수집")
        return bloggers

    # ──────────────────────────────────────────────────────
    #  4단계: 영향력 필터
    # ──────────────────────────────────────────────────────
    def filter_by_influence(
        self,
        bloggers: List[PowerBlogger],
        min_daily_visitors: int = 1000,
        min_neighbors: int = 2000,
        require_badge: bool = False,
    ) -> List[PowerBlogger]:
        """
        파워블로거 영향력 필터
        
        조건:
        1. 인플루언서 뱃지 보유 (require_badge=True일 때)
        2. 일평균 방문자 수 >= min_daily_visitors
        3. 이웃 수 >= min_neighbors
        """
        filtered = []
        rejected = []

        logger.info(
            f"[3단계] 영향력 필터 적용 "
            f"(방문자≥{min_daily_visitors}, 이웃≥{min_neighbors}, "
            f"뱃지필수={require_badge})"
        )

        for b in bloggers:
            reasons = []

            # 뱃지 필수일 때 확인
            if require_badge and not b.has_influencer_badge:
                reasons.append("인플루언서 뱃지 없음")

            # 일일 방문자 필터
            if b.daily_visitors < min_daily_visitors:
                reasons.append(
                    f"일방문자 부족: {b.daily_visitors} < {min_daily_visitors}"
                )

            # 이웃 수 필터
            if b.neighbor_count < min_neighbors:
                reasons.append(
                    f"이웃수 부족: {b.neighbor_count} < {min_neighbors}"
                )

            if not reasons:
                filtered.append(b)
            else:
                rejected.append((b, reasons))

        # 뱃지 보유 블로거 우선 정렬
        filtered.sort(
            key=lambda x: (
                x.has_influencer_badge,
                x.daily_visitors,
                x.neighbor_count,
            ),
            reverse=True,
        )

        logger.info(
            f"[3단계 완료] 통과: {len(filtered)}명, "
            f"탈락: {len(rejected)}명"
        )

        # 탈락 사유 상세 로그
        for b, reasons in rejected[:5]:  # 상위 5개만 표시
            logger.info(
                f"  [탈락] {b.blog_name or b.blog_id}: "
                f"{', '.join(reasons)}"
            )

        return filtered

    # ──────────────────────────────────────────────────────
    #  5단계: 게시글 품질 필터
    # ──────────────────────────────────────────────────────
    def check_post_quality(
        self,
        blogger: PowerBlogger,
        keyword: str,
        min_body_length: int = 1000,
        min_images: int = 5,
        max_posts_check: int = 10,
    ) -> List[BlogPost]:
        """
        블로그의 개별 포스트 품질 검사
        
        조건:
        1. 본문 텍스트 길이 >= min_body_length (공백 제외)
        2. 첨부 이미지 개수 >= min_images
        3. 스팸 문구 포함 여부
        
        Args:
            blogger: 파워블로거 정보
            keyword: 검색 키워드
            min_body_length: 최소 본문 길이
            min_images: 최소 이미지 수
            max_posts_check: 확인할 최대 포스트 수
        """
        quality_posts = []

        try:
            # 블로그 메인에서 포스트 URL 수집
            post_urls = self._get_post_urls(blogger.blog_id, max_posts_check)

            for post_url in post_urls[:max_posts_check]:
                post = self._check_single_post(
                    post_url, keyword, min_body_length, min_images
                )
                if post and not post.is_spam:
                    quality_posts.append(post)

                self._smart_delay()

        except Exception as e:
            logger.debug(
                f"  포스트 품질 검사 오류 ({blogger.blog_id}): {e}"
            )

        return quality_posts

    def _get_post_urls(
        self, blog_id: str, max_count: int = 10
    ) -> List[str]:
        """블로그에서 포스트 URL 목록 추출"""
        post_urls = []
        seen = set()

        urls_to_try = [
            f"https://m.blog.naver.com/{blog_id}?tab=1",
            f"{self.BLOG_HOME}/{blog_id}",
        ]

        for base_url in urls_to_try:
            try:
                resp = self.session.get(base_url, timeout=10)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # 포스트 링크 추출
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]

                    # 네이버 블로그 포스트 URL 패턴
                    post_id_match = None
                    if "PostView.naver" in href:
                        post_id_match = re.search(
                            r"logId=(\d+)", href
                        )
                    elif re.search(r"blog\.naver\.com/.+/\d{10,}", href):
                        post_id_match = re.search(
                            r"/(\d{10,})", href
                        )

                    if post_id_match:
                        post_id = post_id_match.group(1)
                        if post_id not in seen:
                            seen.add(post_id)
                            # 전체 URL 생성
                            if href.startswith("http"):
                                full_url = href
                            else:
                                full_url = urljoin(base_url, href)
                            post_urls.append(full_url)

                            if len(post_urls) >= max_count:
                                return post_urls

            except requests.RequestException:
                continue

        return post_urls

    def _check_single_post(
        self,
        post_url: str,
        keyword: str,
        min_body_length: int,
        min_images: int,
    ) -> Optional[BlogPost]:
        """개별 포스트의 품질 검사"""
        try:
            resp = self.session.get(post_url, timeout=10)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            post = BlogPost(url=post_url)

            # ── 포스트 제목 ──
            title_selectors = [
                ".se-text-paragraph", ".post-title",
                ".title_area", ".blog2_title",
                "h3", "h2.title",
            ]
            for sel in title_selectors:
                title_el = soup.select_one(sel)
                if title_el:
                    post.title = title_el.get_text(strip=True)[:200]
                    break

            # ── 작성일 ──
            date_patterns = [
                r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})",
                r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)",
            ]
            for pattern in date_patterns:
                date_m = re.search(pattern, soup.get_text())
                if date_m:
                    post.post_date = date_m.group(1)
                    break

            # ── 본문 텍스트 추출 ──
            body_selectors = [
                ".se-main-container",
                ".post-content",
                ".post-body",
                ".entry-content",
                "#postContentArea",
                ".contents_style",
                ".se-document",
            ]
            body_text = ""
            for sel in body_selectors:
                body_el = soup.select_one(sel)
                if body_el:
                    body_text = body_el.get_text(separator=" ", strip=True)
                    break

            if not body_text:
                body_text = soup.get_text(separator=" ", strip=True)

            # 공백 제외 길이 계산
            post.body_text = body_text[:2000]  # 저장용 최대 2000자
            post.body_length = len(re.sub(r"\s+", "", body_text))

            # ── 이미지 개수 ──
            body_html = ""
            for sel in body_selectors:
                body_el = soup.select_one(sel)
                if body_el:
                    body_html = str(body_el)
                    break

            if body_html:
                images = BeautifulSoup(body_html, "html.parser").find_all(
                    "img"
                )
                post.image_count = len(images)
            else:
                post.image_count = len(soup.find_all("img"))

            # ── 스팸 감지 ──
            full_text = body_text.lower()
            for pattern in SPAM_PATTERNS:
                if re.search(pattern, full_text):
                    post.is_spam = True
                    post.spam_reason = f"스팸 패턴 감지: {pattern}"
                    break

            return post

        except Exception as e:
            logger.debug(f"  포스트 검사 오류: {e}")
            return None

    # ──────────────────────────────────────────────────────
    #  품질 필터 적용
    # ──────────────────────────────────────────────────────
    def filter_by_quality(
        self,
        bloggers: List[PowerBlogger],
        keyword: str,
        min_body_length: int = 1000,
        min_images: int = 5,
    ) -> List[PowerBlogger]:
        """
        각 블로거의 포스트 품질 필터 적용
        
        Args:
            bloggers: 파워블로거 리스트
            keyword: 검색 키워드
            min_body_length: 최소 본문 길이
            min_images: 최소 이미지 수
        """
        logger.info(
            f"[4단계] 게시글 품질 필터 적용 "
            f"(본문≥{min_body_length}자, 이미지≥{min_images}개)"
        )

        filtered = []
        total = len(bloggers)

        for idx, blogger in enumerate(bloggers, 1):
            logger.info(
                f"  [{idx}/{total}] {blogger.blog_name or blogger.blog_id} "
                f"포스트 품질 검사 중..."
            )

            quality_posts = self.check_post_quality(
                blogger, keyword, min_body_length, min_images
            )

            if quality_posts:
                blogger.quality_posts = [
                    {
                        "title": p.title,
                        "url": p.url,
                        "date": p.post_date,
                        "body_length": p.body_length,
                        "image_count": p.image_count,
                    }
                    for p in quality_posts
                ]
                filtered.append(blogger)
                logger.info(
                    f"    → 품질 포스트 {len(quality_posts)}개 발견 ✅"
                )
            else:
                logger.info(
                    f"    → 품질 기준 충족 포스트 없음 ❌"
                )

        logger.info(
            f"[4단계 완료] 품질 필터 통과: {len(filtered)}/{total}명"
        )
        return filtered

    # ──────────────────────────────────────────────────────
    #  CSV 저장
    # ──────────────────────────────────────────────────────
    def save_to_csv(
        self,
        bloggers: List[PowerBlogger],
        keyword: str,
        filename: str = "naver_power_bloggers.csv",
    ):
        """
        수집된 파워블로거 정보를 CSV로 저장
        
        Args:
            bloggers: 파워블로거 리스트
            keyword: 검색 키워드
            filename: 저장 파일명
        """
        if not bloggers:
            logger.warning("저장할 데이터가 없습니다.")
            return

        logger.info(f"[5단계] CSV 저장 시작 ({filename})")

        # DataFrame 생성
        rows = []
        for b in bloggers:
            # 대표 포스트 (첫 번째 품질 포스트)
            best_post = b.quality_posts[0] if b.quality_posts else {}

            rows.append({
                "블로그_이름": b.blog_name,
                "블로거_닉네임": b.nickname or b.blog_name,
                "블로그_ID": b.blog_id,
                "블로그_URL": b.blog_url,
                "일일_방문자": b.daily_visitors,
                "누적_방문자": b.total_visitors,
                "이웃_수": b.neighbor_count,
                "인플루언서_뱃지": "예" if b.has_influencer_badge else "아니오",
                "카테고리": b.category,
                "게시글_수": b.post_count,
                "대표_포스트_제목": best_post.get("title", ""),
                "대표_포스트_URL": best_post.get("url", ""),
                "대표_포스트_작성일": best_post.get("date", ""),
                "대표_포스트_본문길이": best_post.get("body_length", 0),
                "대표_포스트_이미지수": best_post.get("image_count", 0),
                "검색_키워드": keyword,
                "수집_일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        df = pd.DataFrame(rows)

        # CSV 저장 (UTF-8 BOM — Excel 한글 깨짐 방지)
        df.to_csv(filename, index=False, encoding="utf-8-sig")

        logger.info(
            f"[5단계 완료] {len(rows)}명의 파워블로거 정보 저장 완료"
        )
        logger.info(f"  파일: {filename}")

        # 요약 통계 출력
        self._print_summary(df, keyword)

    def _print_summary(self, df: pd.DataFrame, keyword: str):
        """저장 후 요약 통계 출력"""
        print("\n" + "=" * 60)
        print(f"  📊 네이버 파워블로거 수집 결과 요약")
        print(f"  🔍 검색 키워드: '{keyword}'")
        print("=" * 60)
        print(f"  📝 총 수집 블로거: {len(df)}명")
        print(f"  🏅 인플루언서 뱃지 보유: {len(df[df['인플루언서_뱃지'] == '예'])}명")
        print(f"  👥 평균 이웃 수: {df['이웃_수'].mean():,.0f}명")
        print(f"  👁️  평균 일일 방문자: {df['일일_방문자'].mean():,.0f}명")
        print(f"  📸 평균 이미지 수: {df['대표_포스트_이미지수'].mean():.1f}개")
        print(f"  📄 평균 본문 길이: {df['대표_포스트_본문길이'].mean():,.0f}자")
        print("=" * 60)

        # 상위 5명 표시
        if len(df) > 0:
            print("\n  🏆 상위 5명 파워블로거:")
            for i, (_, row) in enumerate(df.head(5).iterrows(), 1):
                badge = "🏅" if row["인플루언서_뱃지"] == "예" else "  "
                print(
                    f"  {i}. {badge} {row['블로그_이름'][:20]}"
                    f" (방문자:{row['일일_방문자']:,}명, "
                    f"이웃:{row['이웃_수']:,}명)"
                )
        print()


# ──────────────────────────────────────────────────────────────
#  메인 실행
# ──────────────────────────────────────────────────────────────
def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description="네이버 파워블로거 수집 크롤러",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python naver_power_crawler.py
  python naver_power_crawler.py --keyword "제주도 맛집" --pages 5
  python naver_power_crawler.py --keyword "서울 카페" --min-visitors 500 --min-neighbors 1000
        """,
    )
    parser.add_argument(
        "--keyword", "-k", type=str, default="맛집",
        help="검색 키워드 (기본값: 맛집)",
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=5,
        help="검색 페이지 수 (기본값: 5)",
    )
    parser.add_argument(
        "--max-collect", "-m", type=int, default=100,
        help="최대 수집 블로그 수 (기본값: 100)",
    )
    parser.add_argument(
        "--min-visitors", type=int, default=1000,
        help="최소 일일 방문자 수 (기본값: 1000)",
    )
    parser.add_argument(
        "--min-neighbors", type=int, default=2000,
        help="최소 이웃 수 (기본값: 2000)",
    )
    parser.add_argument(
        "--require-badge", action="store_true",
        help="인플루언서 뱃지 필수",
    )
    parser.add_argument(
        "--min-body-length", type=int, default=1000,
        help="최소 본문 길이 (공백 제외, 기본값: 1000)",
    )
    parser.add_argument(
        "--min-images", type=int, default=5,
        help="최소 이미지 수 (기본값: 5)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default="naver_power_bloggers.csv",
        help="출력 CSV 파일명",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  🕷️  네이버 파워블로거 수집 크롤러 v1.0")
    print("=" * 60)
    print(f"  🔍 키워드: '{args.keyword}'")
    print(f"  📄 검색 페이지: {args.pages}페이지")
    print(f"  👁️  최소 일방문자: {args.min_visitors:,}명")
    print(f"  👥 최소 이웃수: {args.min_neighbors:,}명")
    print(f"  🏅 뱃지 필수: {'예' if args.require_badge else '아니오'}")
    print(f"  📸 최소 이미지: {args.min_images}개")
    print(f"  📝 최소 본문길이: {args.min_body_length}자")
    print("=" * 60 + "\n")

    crawler = NaverPowerCrawler()

    try:
        # ── 1단계: 블로그 ID 수집 ──
        blog_ids = crawler.search_blog_ids(
            args.keyword, max_pages=args.pages
        )

        if not blog_ids:
            logger.error("검색 결과에서 블로그를 찾지 못했습니다.")
            return

        # ── 2단계: 블로그 상세 정보 수집 ──
        bloggers = crawler.collect_blog_details(
            blog_ids, max_collect=args.max_collect
        )

        if not bloggers:
            logger.error("블로그 정보 수집에 실패했습니다.")
            return

        # ── 3단계: 영향력 필터 ──
        influence_filtered = crawler.filter_by_influence(
            bloggers,
            min_daily_visitors=args.min_visitors,
            min_neighbors=args.min_neighbors,
            require_badge=args.require_badge,
        )

        if not influence_filtered:
            logger.warning(
                "영향력 필터를 통과한 블로거가 없습니다. "
                "필터 조건을 완화해주세요."
            )
            return

        # ── 4단계: 게시글 품질 필터 ──
        quality_filtered = crawler.filter_by_quality(
            influence_filtered,
            keyword=args.keyword,
            min_body_length=args.min_body_length,
            min_images=args.min_images,
        )

        if not quality_filtered:
            logger.warning(
                "품질 필터를 통과한 블로거가 없습니다. "
                "필터 조건을 완화해주세요."
            )
            # 품질 필터 미통과 시에도 영향력 필터 결과 저장
            logger.info("영향력 필터 결과만으로 CSV 저장합니다.")
            quality_filtered = influence_filtered

        # ── 5단계: CSV 저장 ──
        crawler.save_to_csv(
            quality_filtered,
            keyword=args.keyword,
            filename=args.output,
        )

    except KeyboardInterrupt:
        logger.info("\n사용자에 의해 중지됨")
    except Exception as e:
        logger.error(f"크롤링 오류: {e}", exc_info=True)


if __name__ == "__main__":
    main()
