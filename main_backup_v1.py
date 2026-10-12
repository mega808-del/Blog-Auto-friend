"""
NAVER BLOG STEALTH AUTO SYSTEM v1.2
네이버 블로그에서 블로그 및 파워블로거를 자동으로 찾아주는 대시보드
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import csv
import os
import re
import asyncio
from datetime import datetime

from crawler.naver_crawler import NaverBlogCrawler, BloggerInfo
from crawler.automator import NaverAutomator

# ─── 테마 설정 ───────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ─── 컬러 상수 ───────────────────────────────────────────
BG_DARK = "#0d1117"
BG_CARD = "#161b22"
BG_INPUT = "#21262d"
BG_TABLE_HEADER = "#1c2128"
BG_TABLE_ROW = "#0d1117"
GREEN = "#2ea043"
GREEN_LIGHT = "#3fb950"
GREEN_HOVER = "#238636"
YELLOW = "#d29922"
RED = "#f85149"
BLUE = "#58a6ff"
TEXT_WHITE = "#e6edf3"
TEXT_GRAY = "#8b949e"
TEXT_DIM = "#484f58"
BORDER = "#30363d"
SCROLLBAR_BG = "#21262d"


# ─── 메인 애플리케이션 ────────────────────────────────────
class NaverBlogStealthSystem(ctk.CTk):
    """네이버 블로그 스텔스 자동화 시스템 메인 윈도우"""

    SETTINGS_FILE = "settings.json"

    def __init__(self):
        super().__init__()

        self.title("네이버 블로그(Stealth) 추천 시스템 자동화 v1.2")
        self.geometry("1050x680")
        self.minsize(950, 600)
        self.configure(fg_color=BG_DARK)

        # 상태 변수
        self.is_searching = False
        self.is_running_neighbor = False
        self.bloggers = []       # 탭1 검색 결과
        self.exec_bloggers = []  # 탭2 실행 대상
        self._exec_blogger_data = {}  # 블로그 ID → 전체 데이터 (포스트 URL 포함)
        self.search_result_reason = ""
        self.rejected_info = []
        self._used_comments = set()  # 랜덤 댓글 중복 방지용

        # 크롤러 & 자동화 인스턴스
        self.crawler = NaverBlogCrawler()
        self.crawler.set_log_callback(self._log_from_thread)  # 크롤러 → 탭1 검색 로그
        self.automator = NaverAutomator()
        self.automator.set_log_callback(self._log_exec_from_thread)  # 자동화 → 탭2 실행 로그
        self.automator.register_login_progress(self._on_login_stage_update)

        self._build_ui()
        self._load_settings()

    # ──────────────────────────────────────────────────────
    #  UI 구성
    # ──────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_header()

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=BG_DARK,
            segmented_button_fg_color=BG_CARD,
            segmented_button_selected_color=GREEN,
            segmented_button_selected_hover_color=GREEN_HOVER,
            segmented_button_unselected_color=BG_CARD,
            segmented_button_unselected_hover_color="#1f242c",
            text_color=TEXT_WHITE,
            border_width=0,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_search = self.tabview.add("  🔍  블로그 및 파워블로거 검색  ")
        self.tab_neighbor = self.tabview.add("  💬  댓글 자동 입력  ")

        self._build_search_tab(self.tab_search)
        self._build_neighbor_tab(self.tab_neighbor)
        self._build_statusbar()

        # ── 네이버 로그인 버튼 명령어 연결 (기존 _on_quick_login → _on_naver_login) ──
        # 이미 UI 빌드 시점에 self.btn_login.command = self._on_naver_login 로 설정되어 있음.
        # 여기서는 별도 작업 없이 유지하되, 버튼 텍스트/상태만 런타임에 변경됨.

    # ── 헤더 ──────────────────────────────────────────────
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG_DARK, height=70)
        header.pack(fill="x", padx=12, pady=(10, 0))

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="y")

        ctk.CTkLabel(
            title_frame,
            text="NAVER BLOG STEALTH AUTO SYSTEM",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=GREEN_LIGHT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="네이버 블로그에서 블로그 및 파워블로거를 자동으로 찾아주는 대시보드를 제공합니다.",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_GRAY,
        ).pack(anchor="w", pady=(2, 0))

        status_frame = ctk.CTkFrame(header, fg_color="transparent")
        status_frame.pack(side="right", fill="y")

        self.header_status = ctk.CTkLabel(
            status_frame,
            text="● READY",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GREEN,
        )
        self.header_status.pack(anchor="e", pady=(10, 0))

        self.header_time = ctk.CTkLabel(
            status_frame,
            text=datetime.now().strftime("%Y-%m-%d %H:%M"),
            font=ctk.CTkFont(size=10),
            text_color=TEXT_GRAY,
        )
        self.header_time.pack(anchor="e")

    # ── 상태바 ────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, height=28)
        bar.pack(fill="x", side="bottom", padx=0, pady=0)

        ctk.CTkLabel(
            bar,
            text="  v1.2  |  Python + CustomTkinter",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_DIM,
        ).pack(side="left", padx=10)

        self.statusbar_right = ctk.CTkLabel(
            bar,
            text="Ready  ",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_DIM,
        )
        self.statusbar_right.pack(side="right", padx=10)

    # ══════════════════════════════════════════════════════
    #  탭 1: 블로그 및 파워블로거 검색
    # ══════════════════════════════════════════════════════
    def _build_search_tab(self, parent):
        left = ctk.CTkFrame(parent, fg_color=BG_CARD, width=420, corner_radius=8)
        left.pack(side="left", fill="y", padx=(0, 8), pady=0)
        left.pack_propagate(False)
        self._build_filter_panel(left)

        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=0)
        self._build_result_panel(right)

        # ── 탭1 전용 검색 로그 ──
        log_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8, height=180)
        log_frame.pack(fill="x", padx=0, pady=(8, 0))
        log_frame.pack_propagate(False)

        ctk.CTkLabel(
            log_frame, text="🔍 검색 로그",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_GRAY,
        ).pack(anchor="w", padx=12, pady=(6, 2))

        self.search_log_text = ctk.CTkTextbox(
            log_frame, fg_color=BG_TABLE_ROW, border_color=BORDER,
            border_width=1, text_color=GREEN_LIGHT,
            font=ctk.CTkFont(family="Consolas", size=10),
            scrollbar_button_color=SCROLLBAR_BG, wrap="word",
        )
        self.search_log_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    # ── 좌측: 필터 패널 ───────────────────────────────────
    def _build_filter_panel(self, parent):
        ctk.CTkLabel(
            parent, text="블로그 수집 필터 설정",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            parent, text="검색 조건을 설정하고 검색 버튼을 클릭하세요.",
            font=ctk.CTkFont(size=10), text_color=TEXT_GRAY,
        ).pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=(0, 10)
        )

        # ── 키워드 검색 ──
        kw_frame = ctk.CTkFrame(parent, fg_color="transparent")
        kw_frame.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            kw_frame, text="검색 키워드",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        ).pack(anchor="w")

        search_row = ctk.CTkFrame(kw_frame, fg_color="transparent")
        search_row.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            search_row, text="🔍", font=ctk.CTkFont(size=13),
            text_color=TEXT_GRAY, width=24,
        ).pack(side="left")

        self.entry_keyword = ctk.CTkEntry(
            search_row,
            placeholder_text="키워드를 입력하세요 (예: 음식, 여행, 육아)",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM,
        )
        self.entry_keyword.pack(side="left", fill="x", expand=True)

        # ── 목표 수집 블로그 수 ──
        target_frame = ctk.CTkFrame(parent, fg_color="transparent")
        target_frame.pack(fill="x", padx=16, pady=(10, 2))

        ctk.CTkLabel(
            target_frame, text="목표 수집 블로그 수",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_WHITE, width=100, anchor="w",
        ).pack(side="left")

        self.entry_target_count = ctk.CTkEntry(
            target_frame, width=70, height=28,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=GREEN_LIGHT, justify="center",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.entry_target_count.insert(0, "20")
        self.entry_target_count.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(
            target_frame, text="개",
            font=ctk.CTkFont(size=10), text_color=TEXT_DIM,
            width=50, anchor="w",
        ).pack(side="left")

        # ── 필터 조건 (5개 ALL-TRUE) ──
        ctk.CTkLabel(
            parent, text="필터 조건 (모든 조건을 통과해야 수집됩니다)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(10, 6))

        # (라벨, 기본값, 단위, 키)
        filters = [
            ("운영 기간",     "3",    "년 이상",   "min_operating_years"),
            ("최소 이웃 수",   "50",   "명 이상",   "min_neighbors"),
            ("최소 누적방문자", "1000", "명 이상",   "min_visitors"),
            ("최소 일일방문자", "10",   "명 이상",   "min_daily_visitors"),
            ("최소 게시글 수",  "30",   "개 이상",   "min_posts"),
        ]

        self.filter_entries = {}
        for label, default, unit, key in filters:
            row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
            row.pack(fill="x", padx=16, pady=2)

            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=11),
                text_color=TEXT_GRAY, width=100, anchor="w",
            ).pack(side="left")

            entry = ctk.CTkEntry(
                row, width=70, height=28,
                fg_color=BG_INPUT, border_color=BORDER,
                text_color=TEXT_WHITE, justify="center",
            )
            entry.insert(0, default)
            entry.pack(side="left", padx=(0, 4))
            self.filter_entries[key] = entry

            ctk.CTkLabel(
                row, text=unit, font=ctk.CTkFont(size=10),
                text_color=TEXT_DIM, width=60, anchor="w",
            ).pack(side="left")

        # ── 버튼 영역 ──
        ctk.CTkFrame(parent, fg_color="transparent", height=1).pack(
            fill="x", padx=16, pady=(12, 8)
        )

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 6))

        self.btn_search = ctk.CTkButton(
            btn_frame, text="🟢  시작 검색",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER,
            text_color="white", height=40, corner_radius=6,
            command=self._on_start_search,
        )
        self.btn_search.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_search_stop = ctk.CTkButton(
            btn_frame, text="🔴  중지",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=RED, hover_color="#da3633",
            text_color="white", height=40, corner_radius=6,
            state="disabled", command=self._on_stop_search,
        )
        self.btn_search_stop.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # 브라우저 창 표시
        browser_row = ctk.CTkFrame(parent, fg_color="transparent")
        browser_row.pack(fill="x", padx=16, pady=(0, 4))

        self.show_browser_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            browser_row, text="브라우저 창 표시",
            variable=self.show_browser_var,
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
            fg_color=GREEN, hover_color=GREEN_HOVER,
            checkmark_color="white",
        ).pack(side="left")

        # 정렬 방식
        sort_row = ctk.CTkFrame(parent, fg_color="transparent")
        sort_row.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(
            sort_row, text="정렬 방식",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        ).pack(side="left")

        self.sort_menu = ctk.CTkOptionMenu(
            sort_row,
            values=["일치도순", "최신순", "이웃수순", "방문자순", "포스팅수순"],
            fg_color=BG_INPUT, button_color=BORDER,
            button_hover_color=GREEN_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=GREEN_HOVER,
            text_color=TEXT_WHITE, width=120, height=30,
        )
        self.sort_menu.pack(side="right")

        # 진행 현황
        ctk.CTkFrame(parent, fg_color="transparent", height=1).pack(
            fill="x", padx=16, pady=(8, 4)
        )

        self.progress_label = ctk.CTkLabel(
            parent, text="검색 대기 중...",
            font=ctk.CTkFont(size=10), text_color=TEXT_DIM,
        )
        self.progress_label.pack(anchor="w", padx=16, pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(
            parent, fg_color=BG_INPUT, progress_color=GREEN, height=4,
        )
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 16))
        self.progress_bar.set(0)

    # ── 우측: 결과 패널 ───────────────────────────────────
    def _build_result_panel(self, parent):
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.pack(fill="x", padx=16, pady=(16, 8))

        left_stats = ctk.CTkFrame(stats_frame, fg_color="transparent")
        left_stats.pack(side="left")

        ctk.CTkLabel(
            left_stats, text="수집한 블로그",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        ).pack(anchor="w")

        self.count_label = ctk.CTkLabel(
            left_stats, text="0 명",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=GREEN_LIGHT,
        )
        self.count_label.pack(anchor="w")

        right_stats = ctk.CTkFrame(stats_frame, fg_color="transparent")
        right_stats.pack(side="right")

        ctk.CTkLabel(
            right_stats, text="현재 상태",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        ).pack(anchor="e")

        self.status_label = ctk.CTkLabel(
            right_stats, text="IDLE",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=YELLOW,
        )
        self.status_label.pack(anchor="e")

        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=(8, 8)
        )

        # ── 결과 테이블 ──
        table_frame = ctk.CTkFrame(parent, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Treeview",
            background=BG_TABLE_ROW, foreground=TEXT_WHITE,
            fieldbackground=BG_TABLE_ROW, borderwidth=0,
            rowheight=32, font=("Consolas", 10),
        )
        style.configure(
            "Custom.Treeview.Heading",
            background=BG_TABLE_HEADER, foreground=TEXT_GRAY,
            borderwidth=0, font=("Consolas", 10, "bold"), relief="flat",
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", GREEN_HOVER)],
            foreground=[("selected", "white")],
        )
        style.configure(
            "Custom.Vertical.TScrollbar",
            background=SCROLLBAR_BG, troughcolor=BG_CARD,
            borderwidth=0, arrowcolor=TEXT_DIM,
        )

        columns = (
            "no", "score", "category", "blog_name",
            "neighbors", "posts", "visitors", "rejection",
        )
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Custom.Treeview", selectmode="browse",
        )

        col_config = [
            ("no",       "#",       40),
            ("score",    "일치도",   60),
            ("category", "카테고리",  80),
            ("blog_name","블로그명",  220),
            ("neighbors","이웃수",    80),
            ("posts",    "포스트",    70),
            ("visitors", "방문자",    80),
            ("rejection","상세/탈락사유", 380),
        ]
        for col_id, heading, width in col_config:
            self.tree.heading(col_id, text=heading, anchor="center")
            self.tree.column(col_id, width=width, minwidth=50, anchor="center")

        # 세로 스크롤바
        v_scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical",
            command=self.tree.yview, style="Custom.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=v_scrollbar.set)

        # 가로 스크롤바
        h_scrollbar = ttk.Scrollbar(
            table_frame, orient="horizontal",
            command=self.tree.xview, style="Custom.Vertical.TScrollbar",
        )
        self.tree.configure(xscrollcommand=h_scrollbar.set)

        # 배치: 테이블 + 세로스크롤 + 가로스크롤
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self._insert_empty_message()

        # 우클릭 메뉴
        self.tree_menu = tk.Menu(
            self, tearoff=0, bg=BG_CARD, fg=TEXT_WHITE,
            activebackground=GREEN_HOVER, activeforeground="white",
        )
        self.tree_menu.add_command(label="블로그 열기", command=self._open_blog)
        self.tree_menu.add_command(
            label="이웃 신청 대상에 추가", command=self._add_to_neighbor_list
        )
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label="목록에서 제거", command=self._remove_selected)
        self.tree.bind("<Button-3>", self._show_context_menu)

    def _insert_empty_message(self):
        self.tree.insert(
            "", "end",
            values=("", "", "", "검색 결과가 없습니다.", "", "", "", ""),
            tags=("empty",),
        )
        self.tree.tag_configure("empty", foreground=TEXT_DIM)

    # ── 테이블 업데이트 ────────────────────────────────────
    def _populate_table(self, bloggers):
        """블로거 목록으로 테이블 채우기 — 필터 통과 블로거만 표시"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not bloggers:
            self._insert_empty_message()
            return

        for i, b in enumerate(bloggers, 1):
            score = b.get("relevance_score", 0)
            # 블로그명 + ID를 한 칼럼에 표시 (글자 잘림 방지)
            display_name = b.get("blog_name", "-")
            blog_id = b.get("blog_id", "-")
            name_with_id = f"{display_name} ({blog_id})"

            self.tree.insert(
                "", "end",
                values=(
                    i,
                    f"{score}%",
                    b.get("category", "-"),
                    name_with_id,
                    b.get("neighbor_count", 0),
                    b.get("post_count", 0),
                    b.get("visitor_count", 0),
                    "",
                ),
                tags=(
                    ("high",) if score >= 50
                    else (("mid",) if score >= 20 else ("low",))
                ),
            )

        self.tree.tag_configure("high", background="#0d2818")
        self.tree.tag_configure("mid", background=BG_TABLE_ROW)
        self.tree.tag_configure("low", background="#1a1018")

    def _populate_empty_table(self, main_msg, sub_msg):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.tree.insert(
            "", "end",
            values=("", "", "", main_msg, "", "", "", ""),
            tags=("msg_main",),
        )
        if sub_msg:
            self.tree.insert(
                "", "end",
                values=("", "", "", sub_msg, "", "", "", ""),
                tags=("msg_sub",),
            )

        self.tree.tag_configure("msg_main", foreground=YELLOW)
        self.tree.tag_configure("msg_sub", foreground=TEXT_DIM)

    def _populate_rejected_table(self, rejected_list):
        """탈락 블로거와 사유를 테이블에 표시"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not rejected_list:
            self._populate_empty_table("조건에 맞는 블로그가 없습니다", "")
            return

        self.tree.insert(
            "", "end",
            values=("", "", "카테고리", "블로그명", "", "", "", "탈락 사유"),
            tags=("header",),
        )
        self.tree.tag_configure("header", foreground=TEXT_GRAY)

        for i, r in enumerate(rejected_list, 1):
            reasons_text = " | ".join(r["reasons"])
            name_with_id = f"{r['blog_name']} ({r['blog_id']})"
            self.tree.insert(
                "", "end",
                values=(
                    i, "", "", name_with_id,
                    "", "", "", reasons_text,
                ),
                tags=("rejected",),
            )

        self.tree.tag_configure("rejected", foreground=RED)

    # ── 우클릭 메뉴 ────────────────────────────────────────
    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.tree_menu.post(event.x_root, event.y_root)

    def _extract_blog_id_from_row(self, values):
        """테이블 행 값에서 블로그 ID 추출 (블로그명 칼럼에서 'name (id)' 형태 파싱)"""
        if len(values) < 4:
            return ""
        name_cell = str(values[3])
        # "블로그명 (blogid)" 형태에서 ID 추출
        m = re.search(r"\(([^)]+)\)\s*$", name_cell)
        if m:
            return m.group(1)
        return ""

    def _open_blog(self):
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            blog_id = self._extract_blog_id_from_row(values)
            if blog_id and blog_id not in ("", "검색 결과가 없습니다.", "블로그 ID"):
                import webbrowser
                webbrowser.open(f"https://blog.naver.com/{blog_id}")

    def _add_to_neighbor_list(self):
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            blog_id = self._extract_blog_id_from_row(values)
            if blog_id:
                messagebox.showinfo(
                    "추가됨",
                    f"블로그 {blog_id}이(가) 이웃 신청 대상에 추가되었습니다.",
                )

    def _remove_selected(self):
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0])

    # ══════════════════════════════════════════════════════
    #  탭 2: 댓글 자동 입력
    # ══════════════════════════════════════════════════════
    def _build_neighbor_tab(self, parent):
        left = ctk.CTkFrame(parent, fg_color=BG_CARD, width=420, corner_radius=8)
        left.pack(side="left", fill="y", padx=(0, 8), pady=0)
        left.pack_propagate(False)
        self._build_neighbor_config(left)

        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=0)

        # ── 탭2 실행 대상 테이블 ──
        table_frame = ctk.CTkFrame(right, fg_color="transparent")
        table_frame.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            table_frame, text="실행 대상 블로그 (탭1 검색 결과에서 자동 이관)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_GRAY,
        ).pack(anchor="w")

        exec_table_frame = ctk.CTkFrame(right, fg_color="transparent", height=150)
        exec_table_frame.pack(fill="x", padx=16, pady=(0, 8))
        exec_table_frame.pack_propagate(False)

        exec_columns = (
            "no", "score", "category", "blog_name",
            "neighbors", "posts", "visitors", "status",
        )
        self.exec_tree = ttk.Treeview(
            exec_table_frame, columns=exec_columns, show="headings",
            style="Custom.Treeview", selectmode="browse", height=5,
        )
        exec_col_config = [
            ("no",       "#",       35),
            ("score",    "일치도",   50),
            ("category", "카테고리",  65),
            ("blog_name","블로그명",  180),
            ("neighbors","이웃수",    65),
            ("posts",    "포스트",    55),
            ("visitors", "방문자",    65),
            ("status",   "상태",     80),
        ]
        for col_id, heading, width in exec_col_config:
            self.exec_tree.heading(col_id, text=heading, anchor="center")
            self.exec_tree.column(col_id, width=width, minwidth=40, anchor="center")

        exec_scrollbar = ttk.Scrollbar(
            exec_table_frame, orient="vertical",
            command=self.exec_tree.yview, style="Custom.Vertical.TScrollbar",
        )
        self.exec_tree.configure(yscrollcommand=exec_scrollbar.set)
        self.exec_tree.pack(side="left", fill="both", expand=True)
        exec_scrollbar.pack(side="right", fill="y")

        self.exec_tree.insert(
            "", "end",
            values=("", "", "", "탭 1에서 검색 후 자동으로 이관됩니다", "", "", "", ""),
            tags=("empty",),
        )
        self.exec_tree.tag_configure("empty", foreground=TEXT_DIM)

        ctk.CTkFrame(right, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=(4, 4)
        )

        # ── 탭2 전용 실행 로그 ──
        self._build_neighbor_log(right)

    def _build_neighbor_config(self, parent):
        ctk.CTkLabel(
            parent, text="댓글 자동 입력 설정",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            parent, text="수집된 블로거 대상으로 댓글을 자동으로 입력합니다.",
            font=ctk.CTkFont(size=10), text_color=TEXT_GRAY,
        ).pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=(0, 10)
        )

        # ── 네이버 계정 ──
        ctk.CTkLabel(
            parent, text="네이버 계정",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        # 로그인 전: 아이디/비밀번호 입력 프레임
        self.login_input_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.login_input_frame.pack(fill="x", padx=0, pady=0)

        self.entry_naver_id = ctk.CTkEntry(
            self.login_input_frame, placeholder_text="네이버 아이디",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM,
        )
        self.entry_naver_id.pack(fill="x", padx=16, pady=(0, 4))

        pw_frame = ctk.CTkFrame(self.login_input_frame, fg_color="transparent")
        pw_frame.pack(fill="x", padx=16, pady=(0, 4))

        self.entry_naver_pw = ctk.CTkEntry(
            pw_frame, placeholder_text="네이버 비밀번호", show="●",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM,
        )
        self.entry_naver_pw.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_login = ctk.CTkButton(
            pw_frame, text="🔑 로그인",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1a73e8", hover_color="#1557b0",
            text_color="white", width=90, height=34, corner_radius=6,
            command=self._on_naver_login,
        )
        self.btn_login.pack(side="right")

        # 로그인 버튼 클릭 시 브라우저 뷰를 먼저 탭2에 띄우고
        # 네이버 로그인 화면(https://nid.naver.com/nidlogin.login)이
        # 가장 먼저 열리도록 UI 상태만 미리 준비한다.
        # 실제 브라우저 이동/타이핑은 _on_naver_login에서 시작한다.
        self.btn_login.bind("<ButtonPress-1>", self._on_login_button_press)

        # 로그인 후: 완료 상태 프레임 (기본 숨김)
        self.logged_in_frame = ctk.CTkFrame(parent, fg_color="transparent")

        self.logged_in_label = ctk.CTkLabel(
            self.logged_in_frame, text="✅ 네이버 로그인 완료",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=GREEN_LIGHT,
        )
        self.logged_in_label.pack(anchor="w", padx=16, pady=(4, 2))

        logout_row = ctk.CTkFrame(self.logged_in_frame, fg_color="transparent")
        logout_row.pack(fill="x", padx=16, pady=(0, 4))

        self.logged_in_id_label = ctk.CTkLabel(
            logout_row, text="",
            font=ctk.CTkFont(size=10), text_color=TEXT_GRAY,
        )
        self.logged_in_id_label.pack(side="left")

        self.btn_logout = ctk.CTkButton(
            logout_row, text="로그아웃",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=RED, hover_color="#da3633",
            text_color="white", width=70, height=26, corner_radius=4,
            command=self._on_logout,
        )
        self.btn_logout.pack(side="right")

        # ── 내 블로그 주소 ──
        ctk.CTkLabel(
            parent, text="내 블로그 주소 (댓글이 달릴 내 블로그)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        blog_frame = ctk.CTkFrame(parent, fg_color="transparent")
        blog_frame.pack(fill="x", padx=16, pady=(0, 4))

        self.entry_my_blog_url = ctk.CTkEntry(
            blog_frame,
            placeholder_text="blog.naver.com/내블로그ID",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM,
        )
        self.entry_my_blog_url.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_save_blog = ctk.CTkButton(
            blog_frame, text="💾 저장",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER,
            text_color="white", width=70, height=34, corner_radius=6,
            command=self._on_save_blog_url,
        )
        self.btn_save_blog.pack(side="right")

        # 저장된 블로그 주소 표시 (주황색)
        self.saved_blog_label = ctk.CTkLabel(
            parent, text="",
            font=ctk.CTkFont(size=10), text_color=YELLOW,
        )
        self.saved_blog_label.pack(anchor="w", padx=16, pady=(0, 4))

        # ── 댓글 템플릿 ──
        ctk.CTkLabel(
            parent, text="댓글 템플릿",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        # 랜덤 댓글 사용 여부
        self.use_random_comments_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            parent, text="comments.json에서 랜덤 댓글 사용",
            variable=self.use_random_comments_var,
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
            fg_color=GREEN, hover_color=GREEN_HOVER,
            checkmark_color="white",
        ).pack(anchor="w", padx=16, pady=(4, 4))

        ctk.CTkLabel(
            parent, text="수동 댓글 (랜덤 비활성 시 사용)",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        self.text_comment = ctk.CTkTextbox(
            parent, height=80,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, font=ctk.CTkFont(size=11),
            scrollbar_button_color=SCROLLBAR_BG,
        )
        self.text_comment.pack(fill="x", padx=16, pady=(0, 4))
        self.text_comment.insert(
            "1.0",
            "안녕하세요! 포스트 잘 보고 왔어요~\n"
            "서로 이웃 맺고 소통하면 좋겠습니다!\n"
            "이웃 신청 드립니다 😊",
        )

        # ── 실행 설정 ──
        ctk.CTkLabel(
            parent, text="실행 설정",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(6, 2))

        # ── 대기 시간 / 일일 제한 ──
        delay_row = ctk.CTkFrame(parent, fg_color="transparent")
        delay_row.pack(fill="x", padx=16, pady=1)

        ctk.CTkLabel(
            delay_row, text="요청 간 대기 시간",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
            width=120, anchor="w",
        ).pack(side="left")

        self.entry_delay = ctk.CTkEntry(
            delay_row, width=60, height=28,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, justify="center",
        )
        self.entry_delay.insert(0, "60")
        self.entry_delay.pack(side="left")

        ctk.CTkLabel(
            delay_row, text="초", font=ctk.CTkFont(size=10), text_color=TEXT_DIM,
        ).pack(side="left", padx=4)

        limit_row = ctk.CTkFrame(parent, fg_color="transparent")
        limit_row.pack(fill="x", padx=16, pady=1)

        ctk.CTkLabel(
            limit_row, text="일일 최대 입력 수",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
            width=120, anchor="w",
        ).pack(side="left")

        self.entry_daily_limit = ctk.CTkEntry(
            limit_row, width=60, height=28,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_WHITE, justify="center",
        )
        self.entry_daily_limit.insert(0, "30")
        self.entry_daily_limit.pack(side="left")

        ctk.CTkLabel(
            limit_row, text="건", font=ctk.CTkFont(size=10), text_color=TEXT_DIM,
        ).pack(side="left", padx=4)

        # 실행 설정 저장 버튼 (일일 최대 입력 수 행 오른쪽)
        self.btn_save_exec_settings = ctk.CTkButton(
            limit_row, text="💾 저장",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER,
            text_color="white", width=60, height=26, corner_radius=4,
            command=self._on_save_exec_settings,
        )
        self.btn_save_exec_settings.pack(side="right")

        self.exec_settings_saved_label = ctk.CTkLabel(
            limit_row, text="",
            font=ctk.CTkFont(size=9), text_color=GREEN_LIGHT,
        )
        self.exec_settings_saved_label.pack(side="right", padx=(0, 6))

        # ── 브라우저 로그인 창 ──
        # 탭2 하단 영역: 네이버 로그인 장면을 실시간으로 보여주는 창
        # (기존 로그인 입력 UI/댓글 UI 디자인은 절대 변경하지 않음)
        self.browser_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        self.browser_frame.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        self.browser_frame.pack_propagate(False)

        # 브라우저 창은 처음에는 숨겨두고, 로그인 버튼 누를 때만 탭2에서 보이도록 함
        self.browser_frame.pack_forget()
        self._browser_visible = False
        self._browser_frame_initially_visible = False

        self.browser_title = ctk.CTkLabel(
            self.browser_frame, text="🔒 네이버 로그인 화면 (실시간)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_GRAY,
        )
        self.browser_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.browser_container = ctk.CTkFrame(self.browser_frame, fg_color=BG_TABLE_ROW, corner_radius=6)
        self.browser_container.pack(fill="both", expand=True, padx=12, pady=(2, 6))

        # 브라우저 창 헤더 (이동/새로고침/크기조절 모방)
        self.browser_header = ctk.CTkFrame(self.browser_container, fg_color=BG_CARD, corner_radius=6)
        self.browser_header.pack(fill="x", padx=0, pady=0)

        self.browser_url_label = ctk.CTkLabel(
            self.browser_header, text="🔒 nid.naver.com/nidlogin.login",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=TEXT_GRAY,
        )
        self.browser_url_label.pack(side="left", padx=(8, 0))

        self.browser_window_label = ctk.CTkLabel(
            self.browser_header,
            text="◧  네이버 로그인",
            font=ctk.CTkFont(size=9), text_color=TEXT_GRAY,
        )
        self.browser_window_label.pack(side="right", padx=(0, 8))

        # ── 브라우저 상태 라벨 (브라우저 뷰 아래에 표시) ──
        self.browser_status = ctk.CTkLabel(
            self.browser_frame, text="브라우저 창을 열려면 위 아이디/비밀번호를 입력하고 [🔑 로그인]을 누르세요.",
            font=ctk.CTkFont(size=9), text_color=TEXT_DIM,
        )
        self.browser_status.pack(anchor="w", padx=12, pady=(0, 8))

        # ── 진행 현황 ──
        ctk.CTkLabel(
            parent, text="진행 현황",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_WHITE,
        ).pack(anchor="w", padx=16, pady=(8, 2))

        self.neighbor_progress_label = ctk.CTkLabel(
            parent, text="0 / 0 완료",
            font=ctk.CTkFont(size=11), text_color=TEXT_GRAY,
        )
        self.neighbor_progress_label.pack(anchor="w", padx=16)

        self.neighbor_progress_bar = ctk.CTkProgressBar(
            parent, fg_color=BG_INPUT, progress_color=GREEN, height=4,
        )
        self.neighbor_progress_bar.pack(fill="x", padx=16, pady=(2, 8))
        self.neighbor_progress_bar.set(0)

    def _on_login_button_press(self, event):
        """로그인 버튼 클릭 시 브라우저 뷰가 먼저 탭2에 보이도록 예약한다.
        실제 브라우저 열기/이동은 _on_naver_login에서 처리하므로,
        여기서는 버튼 누르는 순간 탭2의 브라우저 뷰가 표시되도록만 한다.
        """
        try:
            if not self._browser_visible:
                self._show_browser_frame()
        except Exception:
            pass

    def _build_neighbor_log(self, parent):
        # 실행 로그 제목 + 중지 버튼 (한 줄)
        log_header = ctk.CTkFrame(parent, fg_color="transparent")
        log_header.pack(fill="x", padx=16, pady=(8, 2))

        ctk.CTkLabel(
            log_header, text="실행 로그",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_WHITE,
        ).pack(side="left")

        self.btn_neighbor_stop = ctk.CTkButton(
            log_header, text="🔴  중지",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=RED, hover_color="#da3633",
            text_color="white", width=70, height=28, corner_radius=6,
            state="disabled", command=self._on_stop_neighbor,
        )
        self.btn_neighbor_stop.pack(side="right")

        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=(0, 4)
        )

        self.log_text = ctk.CTkTextbox(
            parent, fg_color=BG_TABLE_ROW, border_color=BORDER,
            border_width=1, text_color=GREEN_LIGHT,
            font=ctk.CTkFont(family="Consolas", size=11),
            scrollbar_button_color=SCROLLBAR_BG, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._log_exec("[SYSTEM] 프로그램이 시작되었습니다.")
        self._log_exec("[SYSTEM] 탭 1에서 블로거를 검색한 후, 이 탭에서 작업하세요.")
        self._log_exec("[SYSTEM] 네이버 로그인 → 블로그 주소 저장 → 로그인 시 댓글 자동 입력이 시작됩니다.")
        self._log_exec("[SYSTEM] 안전: 일일 30건, 요청 간 60초 대기가 설정되었습니다.")

        # 초기 브라우저 뷰 상태: 숨은 상태로 시작하되, 로그인 누르면 브라우저 등장하도록 준비
        self._update_browser_ui_login_page()

    def _log(self, message, level="info"):
        """탭1 검색 로그에 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag_map = {
            "info": "[INFO]", "success": "[OK]", "warning": "[WARN]",
            "error": "[ERR]", "system": "[SYS]",
        }
        prefix = tag_map.get(level, "[LOG]")

        self.search_log_text.configure(state="normal")
        self.search_log_text.insert("end", f"[{timestamp}] {prefix} {message}\n")
        self.search_log_text.see("end")
        self.search_log_text.configure(state="disabled")

    def _log_exec(self, message, level="info"):
        """탭2 실행 로그에 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag_map = {
            "info": "[INFO]", "success": "[OK]", "warning": "[WARN]",
            "error": "[ERR]", "system": "[SYS]",
        }
        prefix = tag_map.get(level, "[LOG]")

        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {prefix} {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ══════════════════════════════════════════════════════
    #  설정 저장/로드
    # ══════════════════════════════════════════════════════
    def _save_settings(self, keyword, filters, target_count):
        settings = {
            "keyword": keyword,
            "filters": filters,
            "target_count": target_count,
            "my_blog_url": self.entry_my_blog_url.get().strip(),
            "naver_id": self.entry_naver_id.get().strip(),
            "delay": self.entry_delay.get().strip(),
            "daily_limit": self.entry_daily_limit.get().strip(),
        }
        try:
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"설정 저장 실패: {e}", "error")

    def _load_settings(self):
        if not os.path.exists(self.SETTINGS_FILE):
            return
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)

            keyword = settings.get("keyword", "")
            if keyword:
                self.entry_keyword.delete(0, "end")
                self.entry_keyword.insert(0, keyword)

            filters = settings.get("filters", {})
            for key, entry in self.filter_entries.items():
                if key in filters:
                    entry.delete(0, "end")
                    entry.insert(0, str(filters[key]))

            target = settings.get("target_count", 20)
            self.entry_target_count.delete(0, "end")
            self.entry_target_count.insert(0, str(target))

            # 내 블로그 주소 복원 (오염된 주소 자동 정규화)
            my_blog = settings.get("my_blog_url", "")
            if my_blog:
                normalized_blog = f"blog.naver.com/{self._extract_blog_id_from_url(my_blog)}"
                if normalized_blog != my_blog and self._extract_blog_id_from_url(my_blog):
                    self._log(f"내 블로그 주소 정규화: {my_blog} → {normalized_blog}", "info")
                    settings["my_blog_url"] = normalized_blog
                    try:
                        with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                            json.dump(settings, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                self.entry_my_blog_url.delete(0, "end")
                self.entry_my_blog_url.insert(0, normalized_blog)

            # 네이버 아이디 복원 (비밀번호는 저장하지 않음)
            naver_id = settings.get("naver_id", "")
            if naver_id:
                self.entry_naver_id.delete(0, "end")
                self.entry_naver_id.insert(0, naver_id)

            # 요청 간 대기 시간 복원
            delay = settings.get("delay", "")
            if delay:
                self.entry_delay.delete(0, "end")
                self.entry_delay.insert(0, str(delay))

            # 일일 최대 입력수 복원
            daily_limit = settings.get("daily_limit", "")
            if daily_limit:
                self.entry_daily_limit.delete(0, "end")
                self.entry_daily_limit.insert(0, str(daily_limit))

            self._log("이전 설정을 불러왔습니다.", "info")
        except Exception as e:
            self._log(f"설정 로드 실패: {e}", "error")

    # ── 입력값 안전 파싱 헬퍼 ──────────────────────────────
    @staticmethod
    def _extract_blog_id_from_url(url: str) -> str:
        """블로그 URL/문자열에서 블로그 ID만 추출 (m.blog.naver.com 등 오타입 정규화 포함)"""
        if not url:
            return ""
        s = str(url).strip().replace("https://", "").replace("http://", "").strip("/")
        s = s.replace("m.blog.naver.com", "").replace("blog.naver.com", "")
        s = s.strip("/").strip()
        if "/" in s:
            s = s.split("/")[0]
        return s.strip()

    def _collect_filters_safe(self):
        """필터 입력값을 안전하게 int로 수집 (숫자 아닌 값은 0 처리)"""
        filters = {}
        for k, e in self.filter_entries.items():
            try:
                filters[k] = int(e.get() or 0)
            except ValueError:
                filters[k] = 0
        return filters

    def _get_target_count_safe(self, default=20):
        """목표 수집 수를 안전하게 int로 변환"""
        try:
            return int(self.entry_target_count.get() or default)
        except ValueError:
            return default

    # ══════════════════════════════════════════════════════
    #  이벤트 핸들러
    # ══════════════════════════════════════════════════════
    def _on_start_search(self):
        keyword = self.entry_keyword.get().strip()
        if not keyword:
            messagebox.showwarning("입력 필요", "검색 키워드를 입력하세요.")
            return

        if self.is_searching:
            messagebox.showinfo("알림", "이미 검색 중입니다.")
            return

        self.is_searching = True
        self.btn_search.configure(state="disabled", text="검색 중...")
        self.btn_search_stop.configure(state="normal")
        self.status_label.configure(text="SEARCHING", text_color=BLUE)
        self.header_status.configure(text="● SEARCHING", text_color=BLUE)
        self.progress_label.configure(text=f"'{keyword}' 검색 중...")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 기존 데이터 초기화 (새 검색 시 이전 결과 완전 삭제)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1) 탭1 결과 테이블 초기화
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._insert_empty_message()

        # 2) 탭2 실행 대상 테이블 초기화
        for item in self.exec_tree.get_children():
            self.exec_tree.delete(item)
        self.exec_tree.insert(
            "", "end",
            values=("", "", "", "탭 1에서 검색 후 자동으로 이관됩니다", "", "", "", ""),
            tags=("empty",),
        )
        self.exec_tree.tag_configure("empty", foreground=TEXT_DIM)

        # 3) 카운트 라벨 초기화
        self.count_label.configure(text="0 명")

        # 4) 진행률 초기화
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"'{keyword}' 검색 초기화 완료, 검색 시작...")

        # 5) 상태 변수 초기화
        self.bloggers = []
        self.exec_bloggers = []
        self.rejected_info = []
        self.search_result_reason = ""

        # 6) 검색 로그 초기화 (새 검색 시작 표시)
        self.search_log_text.configure(state="normal")
        self.search_log_text.delete("1.0", "end")
        self.search_log_text.configure(state="disabled")
        self._log("═══════════════════════════════════════", "system")
        self._log(f"새 검색 시작: 키워드='{keyword}'", "system")
        self._log("═══════════════════════════════════════", "system")

        # 필터 값 수집
        filters = {}
        for key, entry in self.filter_entries.items():
            try:
                filters[key] = int(entry.get())
            except ValueError:
                filters[key] = 0

        # 목표 수집 수
        try:
            target_count = int(self.entry_target_count.get())
        except ValueError:
            target_count = 20

        # 설정 저장
        self._save_settings(keyword, filters, target_count)

        self._log(
            f"검색 시작: 키워드='{keyword}', 목표={target_count}개, 필터={filters}",
            "system",
        )

        thread = threading.Thread(
            target=self._search_worker,
            args=(keyword, filters, target_count),
            daemon=True,
        )
        thread.start()

    def _log_from_thread(self, message, level="info"):
        self.after(0, self._log, message, level)

    def _log_exec_from_thread(self, message, level="info"):
        self.after(0, self._log_exec, message, level)

    def _on_stop_search(self):
        """검색 중지"""
        self.is_searching = False
        self.btn_search.configure(state="normal", text="🟢  시작 검색")
        self.btn_search_stop.configure(state="disabled")
        self.status_label.configure(text="STOPPED", text_color=RED)
        self.header_status.configure(text="● STOPPED", text_color=RED)
        self._log("검색이 중지되었습니다.", "warning")

    def _search_worker(self, keyword, filters, target_count):
        """백그라운드 검색 워커 — 고속: HTTP 병렬 필터링"""
        import time as _time
        t_start = _time.time()
        try:
            self.after(0, self._log, f"네이버 블로그 고속 검색 시작: '{keyword}'", "system")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 1단계: HTTP로 네이버 검색에서 블로그 ID 수집
            #         (Playwright 없이 requests로만 수행 → 1초 이내)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self.after(
                0, self._log,
                "[1/5] HTTP 검색으로 블로그 ID 수집 중...", "info",
            )

            blog_ids = self.crawler.search_blog_ids_http(keyword, max_pages=10)

            self.after(
                0, self._log,
                f"  -> 검색 결과 {len(blog_ids)}건 수집 완료",
                "success",
            )

            if not blog_ids:
                self.after(0, self._log, "검색 결과에서 블로그를 찾지 못했습니다.", "warning")
                self.search_result_reason = "no_search"
                self.after(0, self._on_search_complete)
                return

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 2단계: HTTP 경량 사전 필터링 (브라우저 없음)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self.after(
                0, self._log,
                f"[2/5] HTTP 병렬 사전 필터링 중... ({len(blog_ids)}개 대상, 10개 동시요청)",
                "info",
            )

            prefilter_limit = min(len(blog_ids), max(target_count * 8, 200))
            prefilter_ids = blog_ids[:prefilter_limit]

            def http_log(msg, level="info"):
                self.after(0, self._log, msg, level)

            prefiltered = self.crawler.http_prefilter_batch(
                prefilter_ids,
                keyword=keyword,
                max_candidates=max(target_count * 3, 50),
                callback=http_log,
                stop_flag=lambda: not self.is_searching,
            )

            self.after(
                0, self._log,
                f"  -> HTTP 사전 필터 통과: {len(prefiltered)}건",
                "success",
            )

            if not prefiltered:
                self.after(0, self._log, "사전 필터를 통과한 블로그가 없습니다.", "warning")
                self.search_result_reason = "no_prefilter"
                self.after(0, self._on_search_complete)
                return

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 3단계: HTTP 데이터로 BloggerInfo 생성 + 점수 계산
            #         (브라우저 상세 수집 단계 완전 제거 → 속도 10배 향상)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self.after(
                0, self._log,
                f"[3/5] 키워드 점수 계산 중... ({len(prefiltered)}개)",
                "info",
            )

            from crawler.naver_crawler import BloggerInfo
            bloggers_detail = []
            for info in prefiltered:
                bid = info["blog_id"]
                blogger = BloggerInfo(
                    blog_id=bid,
                    blog_name=info.get("blog_name", ""),
                    category=info.get("category", ""),
                    description=info.get("description", ""),
                    post_titles=" ".join(info.get("post_titles", [])),
                    post_contents=info.get("post_contents", ""),
                    neighbor_count=info.get("neighbor_count", 0),
                    visitor_count=info.get("visitor_count", 0),
                    daily_visitor_count=info.get("daily_visitor_count", 0),
                    post_count=info.get("post_count", 0),
                    blog_open_year=info.get("blog_open_year", 0),
                    blog_url=f"https://blog.naver.com/{bid}",
                )
                score = self.crawler._calc_relevance(keyword, blogger)
                # 네이버 검색 결과에서 나온 블로그는 기본 점수 부여
                # (HTTP 응답에 키워드가 없어도 검색으로 관련성 확인됨)
                if score == 0:
                    score = 10
                blogger.relevance_score = score
                bloggers_detail.append(blogger)

            self.after(
                0, self._log,
                f"  -> 점수 계산 완료: {len(bloggers_detail)}건",
                "success",
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 4단계: 자동 필터 조정 + 하드 필터 ALL-TRUE
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self.after(
                0, self._log,
                "[4/5] 필터 조건 자동 분석 + 적용 중...", "info",
            )

            # 수집된 데이터 분석하여 필터 자동 조정
            auto_filters = self._auto_adjust_filters(
                bloggers_detail, filters, target_count
            )

            self.after(
                0, self._log,
                f"  자동 필터: 운영={auto_filters['min_operating_years']}년 "
                f"이웃={auto_filters['min_neighbors']}명 "
                f"방문={auto_filters['min_visitors']}명 "
                f"일일={auto_filters['min_daily_visitors']}명 "
                f"게시={auto_filters['min_posts']}개",
                "info",
            )

            filtered, rejected = self.crawler.filter_bloggers(
                bloggers_detail,
                keyword=keyword,
                min_operating_years=auto_filters["min_operating_years"],
                min_neighbors=auto_filters["min_neighbors"],
                min_visitors=auto_filters["min_visitors"],
                min_daily_visitors=auto_filters["min_daily_visitors"],
                min_posts=auto_filters["min_posts"],
            )

            self.after(
                0, self._log,
                f"  -> 통과: {len(filtered)}건, 탈락: {len(rejected)}건",
                "info",
            )

            # 탈락 사유 상세 로그
            for r in rejected:
                self.after(
                    0, self._log,
                    f"  [탈락] {r['blog_name']}({r['blog_id']}): "
                    f"{', '.join(r['reasons'])}",
                    "warning",
                )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5단계: 키워드 검증 — 각 블로그에서 5개 이상 포스트에 키워드 확인
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if filtered:
                self.after(
                    0, self._log,
                    f"[5/5] 키워드 검증 중... ({len(filtered)}개 블로그, 블로그명/카테고리/설명/포스트 종합 확인)",
                    "info",
                )

                verified, kw_rejected = self.crawler.verify_keyword_batch(
                    filtered,
                    keyword=keyword,
                    min_matches=1,
                    callback=lambda msg, lvl: self.after(0, self._log, msg, lvl),
                    stop_flag=lambda: not self.is_searching,
                    max_workers=5,
                )

                # 키워드 검증 탈락자를 rejected 목록에 추가
                rejected.extend(kw_rejected)
                filtered = verified

                self.after(
                    0, self._log,
                    f"  -> 키워드 검증 통과: {len(filtered)}건, 탈락: {len(kw_rejected)}건",
                    "success" if filtered else "warning",
                )

                # 키워드 검증 탈락 사유 로그
                for r in kw_rejected:
                    self.after(
                        0, self._log,
                        f"  [키워드탈락] {r['blog_name']}({r['blog_id']}): "
                        f"{', '.join(r['reasons'])}",
                        "warning",
                    )

            # 목표 수집 수만큼만 제한
            if len(filtered) > target_count:
                filtered = filtered[:target_count]

            # 결과 저장
            if filtered:
                self.bloggers = [b.to_dict() for b in filtered]
                self.search_result_reason = "ok"
                self.rejected_info = rejected
                # 블로그별 포스트 URL 저장 (댓글 작성 시 사용)
                self._exec_blogger_data = {}
                search_meta = getattr(self.crawler, '_search_metadata', {})
                for b in filtered:
                    meta = search_meta.get(b.blog_id, {})
                    post_urls = meta.get('post_urls', [])
                    self._exec_blogger_data[b.blog_id] = {
                        'post_urls': post_urls,
                        'post_titles': meta.get('post_titles', []),
                    }
            else:
                self.bloggers = []
                self._exec_blogger_data = {}
                self.search_result_reason = "no_filter_match"
                self.rejected_info = rejected

            elapsed = _time.time() - t_start
            self.after(
                0, self._log,
                f"검색 완료! 총 소요 시간: {elapsed:.1f}초 (수집: {len(blog_ids)}개"
                f" → 사전필터: {len(prefiltered)}개 → 최종: {len(filtered)}개)",
                "success",
            )

            # ── 브라우저 창으로 결과 확인 (선택 시) ──
            # filtered(통과) 또는 bloggers_detail(수집 전체)를 브라우저에서 표시
            browser_targets = filtered[:target_count] if filtered else bloggers_detail[:min(5, target_count)]
            if self.show_browser_var.get() and browser_targets:
                self.after(
                    0, self._log,
                    f"브라우저에서 수집 결과 확인 중... ({len(browser_targets)}개 표시)",
                    "info",
                )
                try:
                    loop2 = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop2)

                    async def open_browser_preview():
                        from playwright.async_api import async_playwright

                        pw = None
                        browser = None
                        try:
                            pw = await async_playwright().start()
                            browser = await pw.chromium.launch(
                                headless=False,
                                args=[
                                    "--disable-blink-features=AutomationControlled",
                                    "--no-sandbox",
                                ],
                            )
                            # 모바일 뷰포트
                            context = await browser.new_context(
                                user_agent=(
                                    "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/131.0.0.0 Mobile Safari/537.36"
                                ),
                                viewport={"width": 412, "height": 915},
                                locale="ko-KR",
                                is_mobile=True,
                                has_touch=True,
                            )
                            await context.add_init_script(
                                "Object.defineProperty(navigator, 'webdriver', "
                                "{get: () => undefined});"
                            )
                            page = await context.new_page()

                            self.after(
                                0, self._log,
                                f"  브라우저 시작 완료 (모바일 뷰)",
                                "success",
                            )

                            # 상위 블로그 순차 열기
                            for idx, b in enumerate(browser_targets[:5]):
                                bid = b.blog_id
                                url = f"https://blog.naver.com/{bid}"
                                self.after(
                                    0, self._log,
                                    f"  [{idx+1}/{min(5, len(browser_targets))}] "
                                    f"{b.blog_name}({bid}) 열기...",
                                    "info",
                                )
                                try:
                                    await page.goto(url, wait_until="domcontentloaded")
                                    await asyncio.sleep(3)
                                except Exception as e:
                                    self.after(
                                        0, self._log,
                                        f"    페이지 로드 실패: {e}",
                                        "warning",
                                    )

                            self.after(
                                0, self._log,
                                "브라우저에서 결과를 확인하세요."
                                " (확인 후 브라우저를 닫으면 검색이 완료됩니다)",
                                "success",
                            )

                            # 브라우저가 닫힐 때까지 대기
                            try:
                                await browser.wait_for_event("close", timeout=300000)
                            except Exception:
                                pass

                        except Exception as e:
                            self.after(
                                0, self._log,
                                f"브라우저 프리뷰 오류: {e}",
                                "error",
                            )
                        finally:
                            if browser:
                                try:
                                    await browser.close()
                                except Exception:
                                    pass
                            if pw:
                                try:
                                    await pw.stop()
                                except Exception:
                                    pass

                    loop2.run_until_complete(open_browser_preview())
                    loop2.close()

                except Exception as e:
                    self.after(
                        0, self._log,
                        f"브라우저 시작 실패: {e}",
                        "error",
                    )

            self.after(0, self._on_search_complete)

        except Exception as e:
            self.after(0, lambda e=e: self._log(f"검색 오류: {e}", "error"))
            self.after(0, self._on_search_error)

    def _on_search_complete(self):
        self.is_searching = False
        self.btn_search.configure(state="normal", text="🟢  시작 검색")
        self.btn_search_stop.configure(state="disabled")
        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)
        self.progress_bar.set(1.0)

        count = len(self.bloggers)

        if count == 0 and self.search_result_reason == "no_search":
            msg = "검색 결과에서 블로그를 찾지 못했습니다"
            self.count_label.configure(text="0 명")
            self.progress_label.configure(text=msg)
            self._log(
                msg + ". 다른 키워드로 다시 시도해주세요.", "warning"
            )
            self._populate_empty_table(
                "검색 결과에서 블로그를 찾지 못했습니다",
                "다른 키워드로 다시 검색해주세요",
            )

        elif count == 0 and self.search_result_reason == "no_filter_match":
            msg = "조건에 맞는 블로그가 없습니다"
            self.count_label.configure(text="0 명")
            self.progress_label.configure(text=msg)
            self._log(
                msg + ". 필터 조건을 완화해주세요.", "warning"
            )
            self._populate_rejected_table(self.rejected_info)

        elif count > 0:
            self.count_label.configure(text=f"{count} 명")
            self.progress_label.configure(
                text=f"검색 완료: {count}개 블로그 수집 (조건 충족)"
            )
            self._populate_table(self.bloggers)
            self._log(
                f"검색 완료: {count}개 블로그 수집 (조건 충족)", "success"
            )
            # 탭2 실행 테이블로 데이터 자동 이관
            self._transfer_to_exec_tab(self.bloggers)
            self._log(
                f"탭 2 실행 대상에 {count}개 블로그 이관 완료",
                "success",
            )

        else:
            self.count_label.configure(text="0 명")
            self.progress_label.configure(text="검색 완료")
            self._populate_empty_table("수집된 블로그가 없습니다", "")

    def _auto_adjust_filters(self, bloggers, user_filters, target_count):
        """
        수집된 블로그 데이터를 분석하여 필터 조건을 자동 조정.
        사용자가 설정한 필터를 기반으로 하되, 실제 데이터 분포에 맞게 완화.
        """
        if not bloggers:
            return user_filters

        # 데이터 분포 분석
        neighbors = [b.neighbor_count for b in bloggers]
        visitors = [b.visitor_count for b in bloggers]
        daily_visitors = [b.daily_visitor_count for b in bloggers]
        posts = [b.post_count for b in bloggers]

        # 정렬
        neighbors.sort()
        visitors.sort()
        daily_visitors.sort()
        posts.sort()

        n = len(bloggers)

        # 목표 수집 수 대비 통과율 계산
        def calc_pass_rate(min_val, data):
            return sum(1 for v in data if v >= min_val) / len(data) if data else 0

        result = dict(user_filters)

        # ── 이웃 수 자동 조정 ──
        user_min = user_filters.get("min_neighbors", 0)
        if user_min > 0:
            pass_rate = calc_pass_rate(user_min, neighbors)
            if pass_rate < 0.3:  # 30% 미만 통과 시 자동 완화
                # 상위 50% 지점으로 완화
                auto_val = neighbors[n // 2] if n > 0 else 0
                result["min_neighbors"] = max(0, min(auto_val, user_min))
                self.after(
                    0, self._log,
                    f"  이웃수 자동조정: {user_min} → {result['min_neighbors']} "
                    f"(통과율 {pass_rate*100:.0f}%→개선)",
                    "info",
                )

        # ── 방문자 수 자동 조정 ──
        user_min = user_filters.get("min_visitors", 0)
        if user_min > 0:
            pass_rate = calc_pass_rate(user_min, visitors)
            if pass_rate < 0.3:
                auto_val = visitors[n // 2] if n > 0 else 0
                result["min_visitors"] = max(0, min(auto_val, user_min))
                self.after(
                    0, self._log,
                    f"  방문자수 자동조정: {user_min} → {result['min_visitors']} "
                    f"(통과율 {pass_rate*100:.0f}%→개선)",
                    "info",
                )

        # ── 일일 방문자 자동 조정 ──
        user_min = user_filters.get("min_daily_visitors", 0)
        if user_min > 0:
            pass_rate = calc_pass_rate(user_min, daily_visitors)
            if pass_rate < 0.3:
                auto_val = daily_visitors[n // 2] if n > 0 else 0
                result["min_daily_visitors"] = max(0, min(auto_val, user_min))
                self.after(
                    0, self._log,
                    f"  일일방문자 자동조정: {user_min} → {result['min_daily_visitors']} "
                    f"(통과율 {pass_rate*100:.0f}%→개선)",
                    "info",
                )

        # ── 게시글 수 자동 조정 ──
        user_min = user_filters.get("min_posts", 0)
        if user_min > 0:
            pass_rate = calc_pass_rate(user_min, posts)
            if pass_rate < 0.3:
                auto_val = posts[n // 2] if n > 0 else 0
                result["min_posts"] = max(0, min(auto_val, user_min))
                self.after(
                    0, self._log,
                    f"  게시글수 자동조정: {user_min} → {result['min_posts']} "
                    f"(통과율 {pass_rate*100:.0f}%→개선)",
                    "info",
                )

        # ── 목표 수 미달 시 추가 완화 ──
        # 현재 필터로 목표 수의 50%도 못 채우면 한번 더 완화
        temp_filtered, _ = self.crawler.filter_bloggers(
            bloggers, keyword="",
            min_operating_years=result["min_operating_years"],
            min_neighbors=result["min_neighbors"],
            min_visitors=result["min_visitors"],
            min_daily_visitors=result["min_daily_visitors"],
            min_posts=result["min_posts"],
        )
        if len(temp_filtered) < target_count * 0.5:
            self.after(
                0, self._log,
                f"  목표({target_count}개) 대비 부족 ({len(temp_filtered)}개) → 필터 추가 완화",
                "warning",
            )
            # 상위 30% 지점으로 추가 완화
            result["min_neighbors"] = max(0, neighbors[n * 3 // 10] if n > 0 else 0)
            result["min_visitors"] = max(0, visitors[n * 3 // 10] if n > 0 else 0)
            result["min_daily_visitors"] = max(0, daily_visitors[n * 3 // 10] if n > 0 else 0)
            result["min_posts"] = max(0, posts[n * 3 // 10] if n > 0 else 0)

        return result

    def _transfer_to_exec_tab(self, bloggers):
        """검색 결과를 탭2 실행 테이블로 이관"""
        # 기존 실행 테이블 비우기
        for item in self.exec_tree.get_children():
            self.exec_tree.delete(item)

        if not bloggers:
            self.exec_tree.insert(
                "", "end",
                values=("", "", "", "조건에 맞는 블로그가 없습니다", "", "", "", ""),
                tags=("empty",),
            )
            self.exec_tree.tag_configure("empty", foreground=TEXT_DIM)
            return

        for i, b in enumerate(bloggers, 1):
            score = b.get("relevance_score", 0)
            display_name = b.get("blog_name", "-")
            blog_id = b.get("blog_id", "-")
            name_with_id = f"{display_name} ({blog_id})"

            self.exec_tree.insert(
                "", "end",
                values=(
                    i,
                    f"{score}%",
                    b.get("category", "-"),
                    name_with_id,
                    b.get("neighbor_count", 0),
                    b.get("post_count", 0),
                    b.get("visitor_count", 0),
                    "대기",
                ),
                tags=(
                    ("high",) if score >= 50
                    else (("mid",) if score >= 20 else ("low",))
                ),
            )

    def _on_search_error(self):
        self.is_searching = False
        self.btn_search.configure(state="normal", text="🟢  시작 검색")
        self.btn_search_stop.configure(state="disabled")
        self.status_label.configure(text="ERROR", text_color=RED)
        self.header_status.configure(text="● ERROR", text_color=RED)
        self.progress_label.configure(text="검색 중 오류 발생")

    def _on_naver_login(self):
        """네이버 로그인 시작 — 브라우저에서 네이버 로그인 화면을 실시간으로 보여주며 2FA까지 사람이 보채도록 유도."""
        naver_id = self.entry_naver_id.get().strip()
        naver_pw = self.entry_naver_pw.get().strip()

        if not naver_id or not naver_pw:
            messagebox.showwarning(
                "입력 필요", "네이버 아이디와 비밀번호를 입력하세요."
            )
            return

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1) 백엔드 사전 검증(headless 로그인) 완전 제거!
        #    실제 브라우저 1개에서만 로그인 진행 → 2FA 1회만 발송
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 저장된 세션 확인 (표시용)
        has_session = self.automator._has_saved_session()

        if has_session:
            self._log_exec("저장된 세션 감지됨. 브라우저에서 자동으로 로그인 상태가 복원됩니다.", "info")
            self._log_exec("(세션이 유효하면 비밀번호 입력 없이 로그인됩니다)", "info")
        else:
            self._log_exec(f"네이버 로그인 준비: {naver_id}", "system")
            self._log_exec("브라우저 로그인 창이 표시됩니다. 직접 ID/PW를 입력하고 로그인하세요.", "info")

        # 로그인 버튼 비활성화 (중복 클릭 방지)
        self.btn_login.configure(state="disabled", text="⏳ 로그인 중...")

        # ── 로그인 작업 시작 (별도 스레드, UI 블로킹 방지) ──
        # 로그인 누르면 바로 브라우저 창을 탭2에서 보이게 함
        self.after(0, self._show_browser_frame)

        thread = threading.Thread(
            target=self._naver_login_worker,
            args=(naver_id, naver_pw, has_session),
            daemon=True,
        )
        thread.start()

    def _on_login_complete(self, success):
        """로그인 완료 콜백 (레거시 — 더 이상 사용하지 않음)"""
        self.is_running_neighbor = False
        self.btn_login.configure(state="normal", text="🔑 로그인")

        if success:
            self.login_input_frame.pack_forget()
            naver_id = self.entry_naver_id.get().strip()
            self.logged_in_id_label.configure(text=f"ID: {naver_id}")
            self.logged_in_frame.pack(fill="x", padx=0, pady=(0, 4))
            self.status_label.configure(text="IDLE", text_color=YELLOW)
            self.header_status.configure(text="● READY", text_color=GREEN)
            self._log_exec("네이버 로그인 성공!", "success")
        else:
            self.login_input_frame.pack(fill="x", padx=0, pady=(0, 4))
            self.status_label.configure(text="IDLE", text_color=YELLOW)
            self.header_status.configure(text="● READY", text_color=GREEN)
            self._log_exec("로그인 실패. 아이디/비밀번호를 확인하세요.", "warning")

    def _on_logout(self):
        """로그아웃 — 입력 화면으로 복원"""
        # 로그인 완료 프레임 숨기고 입력 프레임 표시
        self.logged_in_frame.pack_forget()
        self.entry_naver_id.delete(0, "end")
        self.entry_naver_pw.delete(0, "end")
        self.login_input_frame.pack(fill="x", padx=0, pady=0)

        # 브라우저 로그인 창 초기화 표시로 되돌리기
        self.browser_status.configure(
            text="브라우저 창을 열려면 위 아이디/비밀번호를 입력하고 [🔑 로그인]을 누르세요."
        )

        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)
        self._log_exec("로그아웃되었습니다. 다시 로그인하세요.", "info")

    def _on_save_blog_url(self):
        """내 블로그 주소 저장"""
        blog_url = self.entry_my_blog_url.get().strip()
        if not blog_url:
            messagebox.showwarning("입력 필요", "내 블로그 주소를 입력하세요.")
            return

        # URL 정리 — m.blog.naver.com 등 잘못 입력된 주소도 정규화
        blog_id = self._extract_blog_id_from_url(blog_url)
        if not blog_id:
            messagebox.showwarning(
                "입력 오류",
                "올바른 블로그 주소를 입력하세요.\n(예: blog.naver.com/myblogid)",
            )
            return
        clean_url = f"blog.naver.com/{blog_id}"

        # 입력 필드 업데이트
        self.entry_my_blog_url.delete(0, "end")
        self.entry_my_blog_url.insert(0, clean_url)

        # 설정에 저장
        self._save_settings(
            self.entry_keyword.get().strip(),
            self._collect_filters_safe(),
            self._get_target_count_safe(),
        )

        self._log_exec(f"내 블로그 주소 저장: {clean_url}", "success")

        # 주황색으로 저장된 블로그 주소 표시
        self.saved_blog_label.configure(text=f"📌 저장됨: {clean_url}")

        messagebox.showinfo(
            "저장 완료",
            f"내 블로그 주소가 저장되었습니다.\n{clean_url}"
        )

    def _on_save_exec_settings(self):
        """실행 설정(요청간 대기시간, 일일 최대 입력수) 저장"""
        try:
            delay_val = int(self.entry_delay.get())
            daily_limit_val = int(self.entry_daily_limit.get())
        except ValueError:
            messagebox.showwarning("입력 오류", "대기시간과 일일 입력수는 숫자로 입력하세요.")
            return

        if delay_val < 5:
            messagebox.showwarning("입력 오류", "대기시간은 최소 5초 이상이어야 합니다.")
            return
        if daily_limit_val < 1:
            messagebox.showwarning("입력 오류", "일일 최대 입력수는 1 이상이어야 합니다.")
            return

        # 설정 저장
        self._save_settings(
            self.entry_keyword.get().strip(),
            self._collect_filters_safe(),
            self._get_target_count_safe(),
        )

        self.exec_settings_saved_label.configure(text=f"✅ 저장 완료 (대기 {delay_val}초 / 일일 {daily_limit_val}건)")
        self._log_exec(
            f"실행 설정 저장: 대기시간={delay_val}초, 일일최대={daily_limit_val}건",
            "success",
        )
        self._log(
            f"실행 설정 저장: 대기시간={delay_val}초, 일일최대={daily_limit_val}건",
            "success",
        )

        messagebox.showinfo(
            "저장 완료",
            f"실행 설정이 저장되었습니다.\n"
            f"요청간 대기시간: {delay_val}초\n"
            f"일일 최대 입력수: {daily_limit_val}건"
        )

    # ── 네이버 로그인 워크 (별도 스레드) ──────────────────────
    def _naver_login_worker(self, naver_id: str, naver_pw: str, has_session: bool):
        """네이버 로그인 전용 워커 — 브라우저 열기, 네이버 로그인 화면 실시간 표시, 2FA 대기까지 사람이 보채도록 진행."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._naver_login_async(naver_id, naver_pw, has_session))
        except Exception as e:
            self.after(0, self._log_exec, f"로그인 오류: {e}", "error")
            self.after(0, self._on_login_failed)

    async def _naver_login_async(self, naver_id: str, naver_pw: str, has_session: bool):
        """네이버 로그인 비동기 워크 — 로그인 성공/실패는 콜백으로 알림."""
        try:
            # 이미 브라우저가 떠 있으면 새로 로그인용으로 다시 열지 않음
            show_browser = self.show_browser_var.get()

            # 기존 브라우저 정리 (이벤트 루프 충돌 방지)
            if self.automator.browser:
                self.after(0, self._log_exec, "기존 브라우저를 정리합니다...", "info")
                try:
                    await self.automator.close()
                except Exception:
                    pass
                self.automator.browser = None
                self.automator.page = None
                self.automator.is_logged_in = False

            # 브라우저 시작 (헤드리스이면 뒤쪽에서 돌아가지만, 안티패턴 방지를 위해 show_browser 따르되
            # 로그인 장면은 항상 보이도록 헤드리스=false로 강제함)
            self.after(0, self._log_exec, "브라우저를 시작합니다...", "system")
            await self.automator.start_browser(headless=False)

            # 브라우저 창을 화면 앞으로 가져오기 — 로그인 장면을 바로 볼 수 있게 함
            self.after(0, self._log_exec, "브라우저 창을 화면 앞으로 가져옵니다...", "info")
            await self.automator.bring_to_front()
            await asyncio.sleep(1)

            # ── 브라우저 UI 업데이트: 네이버 로그인 화면임을 표시 ──
            self.after(0, self._update_browser_ui_login_page)

            # ── 네이버 로그인 페이지로 이동 ──
            # ※ 저장된 세션이 있어도 로그인 화면을 "먼저" 보여준다.
            #   (과거에는 m.naver.com → mail.naver.com으로 세션 검증을 우회했는데,
            #    이때 로그인 안 된 다른 페이지가 먼저 떠서 "로그인 안 한 창이 뜨는"
            #    현상처럼 보였다. 세션은 로그인 화면에서 URL로만 가볍게 확인한다.)
            self.after(0, self._log_exec, "네이버 로그인 페이지로 이동합니다...", "system")
            await self.automator.page.goto(self.automator.NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            # 창 위치 조정: 로그인 폼이 화면 중앙에 오도록 뷰포트를 가운데로
            await self.automator.bring_to_front()
            await asyncio.sleep(0.5)

            # ── 세션 가벼운 확인: 로그인 화면에서 벗어났다면 이미 로그인된 것 ──
            # (페이지 우회 없이 현재 URL만 확인 → 화면 흐름이 끊기지 않음)
            if has_session:
                self.after(0, self._log_exec, "저장된 세션 확인 중... (로그인 화면 유지)", "info")
                try:
                    current_url = self.automator.page.url
                    page_text = await self.automator.page.evaluate("() => document.body.innerText")
                    is_logged = (
                        "nid.naver.com" not in current_url
                        and "login" not in current_url
                        and "로그인" not in page_text[:200]
                    )
                    if is_logged:
                        self.after(0, self._log_exec, "✅ 저장된 세션으로 자동 로그인 성공!", "success")
                        self.after(0, self._on_login_success, naver_id)
                        return
                    self.after(0, self._log_exec, "세션이 만료됨. 화면에서 아이디/비밀번호를 입력합니다.", "warning")
                except Exception as e:
                    self.after(0, self._log_exec, f"세션 확인 실패, 새 로그인으로 진행: {e}", "warning")

            # ── 아이디/비밀번호 입력: 타자 치듯 화면에 보이게 ──
            # 로그인 창이 실제로 포커스를 갖도록 반복 bring_to_front + 창 포커스
            for _ in range(6):
                await self.automator.bring_to_front()
                try:
                    await self.automator.page.evaluate("() => { window.focus(); document.body.focus?.(); }")
                except Exception:
                    pass
                await asyncio.sleep(0.2)

            self.after(0, self._log_exec, "아이디와 비밀번호를 브라우저 창에 자동으로 입력합니다...", "info")
            await self.automator.bring_to_front()
            await asyncio.sleep(0.5)

            # 현재 페이지 URL 확인 — 로그인 페이지가 실제로 열렸는지 검증
            try:
                current_url = self.automator.page.url
                self.after(0, self._log_exec, f"  📍 현재 페이지: {current_url}", "info")
            except Exception as e:
                self.after(0, self._log_exec, f"  ⚠️ 페이지 URL 확인 실패: {e}", "warning")

            id_input = await self.automator.page.query_selector('input[name="id"]')
            if not id_input:
                # 아이디 입력창을 못 찾으면 120초 대기 없이 즉시 실패 처리
                self.after(0, self._log_exec, "❌ 아이디 입력창을 찾지 못했습니다. 로그인 페이지 로드를 확인하세요.", "error")
                self.after(0, self._on_login_failed)
                return
            if id_input:
                self.after(0, self._log_exec, "✅ 아이디 입력창 발견 — 커서 이동 및 포커스 중...", "info")
                await self.automator.bring_to_front()
                await asyncio.sleep(0.3)
                try:
                    await self.automator.page.evaluate("() => { document.activeElement?.blur?.(); }")
                except Exception:
                    pass
                # 사람처럼 커서를 입력창으로 이동시킨 뒤 클릭 (화면에 보임)
                await self.automator.human_move_and_click(id_input)
                await asyncio.sleep(0.3)
                try:
                    await self.automator.page.evaluate("() => { const e = document.querySelector('input[name=\"id\"]'); if(e){ e.focus(); } }")
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                await id_input.fill("")
                await self.automator._type_like_human(id_input, naver_id)
            await asyncio.sleep(0.5)

            pw_input = await self.automator.page.query_selector('input[name="pw"]')
            if not pw_input:
                self.after(0, self._log_exec, "❌ 비밀번호 입력창을 찾지 못했습니다.", "error")
                self.after(0, self._on_login_failed)
                return
            if pw_input:
                self.after(0, self._log_exec, "✅ 비밀번호 입력창 발견 — 커서 이동 및 포커스 중...", "info")
                await self.automator.bring_to_front()
                await asyncio.sleep(0.3)
                try:
                    await self.automator.page.evaluate("() => { const e = document.querySelector('input[name=\"pw\"]'); if(e){ e.focus(); } }")
                except Exception:
                    pass
                # 사람처럼 커서를 비밀번호 입력창으로 이동시킨 뒤 클릭 (화면에 보임)
                await self.automator.human_move_and_click(pw_input)
                await asyncio.sleep(0.3)
                try:
                    await self.automator.page.evaluate("() => { const e = document.querySelector('input[name=\"pw\"]'); if(e){ e.focus(); } }")
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                await pw_input.fill("")
                await self.automator._type_like_human(pw_input, naver_pw)
            await asyncio.sleep(0.5)

            self.after(0, self._log_exec, "아이디/비밀번호 입력 완료. 로그인 버튼을 누릅니다...", "info")
            await self.automator.bring_to_front()
            await asyncio.sleep(1)

            # 로그인 버튼 찾기
            login_selectors = [
                '#loginBtn_column',
                '#loginBtn_row',
                'button[type="submit"]',
                '.btn_login',
                'button.btn_done',
            ]
            login_btn = None
            for sel in login_selectors:
                login_btn = await self.automator.page.query_selector(sel)
                if login_btn:
                    self.after(0, self._log_exec, f"로그인 버튼 발견: {sel}", "info")
                    break
            if login_btn:
                self.after(0, self._log_exec, "✅ 로그인 버튼 발견 — 커서 이동 후 클릭...", "info")
                # 사람처럼 커서를 로그인 버튼으로 이동시킨 뒤 클릭 (화면에 보임)
                await self.automator.human_move_and_click(login_btn, scroll_first=True)
                self.after(0, self._log_exec, "✅ 로그인 버튼 클릭 완료", "success")

            # ── 로그인 후: 페이지 변경을 "한 번만" 관찰 (2FA 중복 방지) ──
            # 절대 evaluate/fetch 등으로 페이지를 건드리지 않음!
            self.after(0, self._log_exec, "페이지 전환 대기 중... (페이지 조작 없음)", "info")

            # 10초 동안 URL 변경만 관찰
            logged_in = False
            for i in range(10):
                await asyncio.sleep(1)
                url = self.automator.page.url
                if "nid.naver.com" not in url or "login" not in url:
                    logged_in = True
                    self.after(0, self._log_exec, f"✅ URL 변경 감지: {url[:60]}", "success")
                    break

            if logged_in:
                self.after(0, self._log_exec, "✅ 네이버 로그인 성공!", "success")
                # ★ 세션 저장 후 브라우저 정리 (세션 없이 닫으면 댓글 작업 시
                #   만료된 옛 세션으로 재로그인 실패하는 버그 방지)
                try:
                    await self.automator._save_session()
                    await self.automator.close()
                except Exception:
                    pass
                self.automator.browser = None
                self.automator.page = None
                self.automator.is_logged_in = True
                self.after(0, self._on_login_success, naver_id)
                return

            # URL 변경 없음 → 2FA 또는 에러 → 사람에게 맡김
            self.after(0, self._log_exec, "2FA 또는 추가 인증 대기 중... 브라우저에서 인증을 완료하세요.", "info")
            await self.automator.bring_to_front()

            # 최대 120초 동안 URL 변경만 관찰
            two_fa_done = False
            for i in range(120):
                await asyncio.sleep(1)
                url = self.automator.page.url
                if "nid.naver.com" not in url or "login" not in url:
                    two_fa_done = True
                    self.after(0, self._log_exec, f"✅ 로그인 성공! (URL: {url[:60]})", "success")
                    break
                if i > 0 and i % 10 == 0:
                    self.after(0, self._log_exec,
                        f"⏳ 로그인 대기 중... ({i}초) 현재 URL: {url[:60]}", "info")
                    # 브라우저 뷰 URL 업데이트
                    self.after(0, lambda u=url: self.browser_url_label.configure(text=f"🔒 {u}"))

            if not two_fa_done:
                self.after(0, self._log_exec, "❌ 로그인 시간 초과 (120초)", "error")
                self.after(0, self._on_login_failed)
                return

            # 로그인 성공: 이 브라우저(이벤트 루프)에서 세션 저장 후 정리.
            # ※ 다른 스레드(다른 asyncio 루프)에서 이 브라우저를 재사용하면
            #   Playwright 크로스루프 오류로 "브라우저가 닫혔다" 오류가 나므로,
            #   댓글 작업 시에는 항상 새 브라우저를 열도록 한다.
            await self.automator._save_session()
            await self.automator.close()
            self.automator.browser = None
            self.automator.page = None
            self.automator.is_logged_in = True  # 댓글 작업 시작 시 자동 로그인 판정용
            self.after(0, self._log_exec, "로그인 완료 — 세션 저장됨. 댓글 작업 시 자동 로그인됩니다.", "success")
            # ★ 2FA 성공 경로에서도 로그인 성공 콜백을 반드시 호출해야
            #   UI가 "⏳ 로그인 중..."에 멈추지 않고 댓글 작업으로 넘어간다.
            self.after(0, self._on_login_success, naver_id)

        except Exception as e:
            self.after(0, self._log_exec, f"로그인 오류: {e}", "error")
            self.after(0, self._on_login_failed)

    def _update_browser_ui_login_page(self):
        """브라우저 뷰의 헤더를 네이버 로그인 페이지로 표시."""
        self.browser_url_label.configure(
            text="🔒 nid.naver.com/nidlogin.login"
        )
        self.browser_window_label.configure(text="◧  네이버 로그인")
        self.browser_status.configure(
            text="네이버 로그인 화면이 브라우저에 표시됩니다. 직접 아이디/비밀번호를 입력하고 로그인 버튼을 누르세요.",
            text_color=TEXT_GRAY,
        )

    # ── 로그인 단계별 실시간 브라우저 뷰 업데이트 (자동 입력 진행상황 표시) ──
    def _on_login_stage_update(self, stage: str, detail: str):
        """
        automator에서 로그인 입력 진행 상황을 받을 때마다
        탭2의 브라우저 뷰 하단의 상태 텍스트와 입력 마스크를 갱신.
        화면이 '사람 손이 키보드 치듯' 흘러가는 것을 시각적으로 보여주기 위함.
        """
        if not getattr(self, "_browser_visible", False) and not getattr(
            self, "_browser_frame_initially_visible", False
        ):
            return

        if stage == "id_focus":
            self.browser_status.configure(
                text="커서가 아이디 입력창에 들어왔습니다. (자동 입력이 시작됩니다)",
                text_color=TEXT_GRAY,
            )
            self.browser_url_label.configure(
                text="🔒 nid.naver.com/nidlogin.login  [아이디 입력 중]"
            )

        elif stage == "id_input":
            self.browser_status.configure(
                text=f"아이디 입력 진행 중: {detail}",
                text_color=TEXT_GRAY,
            )

        elif stage == "pw_focus":
            self.browser_status.configure(
                text="커서가 비밀번호 입력창으로 이동했습니다. (자동 입력이 시작됩니다)",
                text_color=TEXT_GRAY,
            )
            self.browser_url_label.configure(
                text="🔒 nid.naver.com/nidlogin.login  [비밀번호 입력 중]"
            )

        elif stage == "pw_input":
            self.browser_status.configure(
                text=f"비밀번호 입력 진행 중: {detail} (마스킹 표시)",
                text_color=TEXT_GRAY,
            )

        elif stage == "typing_start":
            self.browser_status.configure(
                text=f"타자 시뮬레이션 시작: '{detail}'자 입력 중입니다...",
                text_color=TEXT_GRAY,
            )

        elif stage == "typing_progress":
            self.browser_status.configure(
                text=f"입력 진행 중: {detail} (실시간)",
                text_color=TEXT_GRAY,
            )

        elif stage == "typing_done":
            self.browser_status.configure(
                text="입력 완료. 로그인 버튼 클릭을 준비합니다.",
                text_color=TEXT_GRAY,
            )

        elif stage == "ready_to_login":
            self.browser_status.configure(
                text="아이디/비밀번호 입력 완료. 로그인 버튼을 누르는 중입니다...",
                text_color=TEXT_GRAY,
            )

        elif stage == "login_clicked":
            self.browser_status.configure(
                text="로그인 버튼 클릭 완료. 페이지 전환 대기 중 (페이지 조작 없음)...",
                text_color=TEXT_GRAY,
            )
            self.browser_url_label.configure(
                text="🔒 nid.naver.com/nidlogin.login → 전환 대기 중"
            )


    # ── 로그인 완료/실패 콜백 ──────────────────────
    def _on_login_success(self, naver_id: str):
        """네이버 로그인 성공 시 UI 복원 + 댓글 작업 바로 시작."""
        # ★★★ automator 상태도 반드시 동기화 ★★★
        self.automator.is_logged_in = True

        self.btn_login.configure(state="normal", text="🔑 로그인")

        # 로그인 완료 프레임 표시 (입력 프레임 숨김)
        self.login_input_frame.pack_forget()
        self.logged_in_id_label.configure(text=f"ID: {naver_id}")
        self.logged_in_frame.pack(fill="x", padx=0, pady=(0, 4))

        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)
        self._log_exec("네이버 로그인 성공! 이제 댓글 자동 입력을 시작할 수 있습니다.", "success")

        # 브라우저 프레임 숨기기 (로그인 창은 이제 불필요)
        if getattr(self, '_browser_visible', False):
            self.browser_frame.pack_forget()
            self._browser_visible = False
            self.browser_status.configure(text="로그인 완료. 댓글 작업을 시작합니다.")

        # 바로 댓글 작업 시작
        self.after(10, self._update_browser_ui_logged_in)

    def _on_login_failed(self):
        """네이버 로그인 실패 시 UI 복원."""
        self.btn_login.configure(state="normal", text="🔑 로그인")
        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)
        self._log_exec("로그인 실패. 아이디/비밀번호를 확인하세요.", "warning")

        # 브라우저 창은 탭2 안에 그대로 두고, 상태만 변경
        self.after(0, self._show_browser_frame)
        self.after(10, self._update_browser_ui_login_page)

    def _show_browser_frame(self):
        """브라우저 로그인 창을 탭2에서 보이게 표시."""
        if not getattr(self, '_browser_visible', False) and not getattr(self, '_browser_frame_initially_visible', False):
            self.browser_frame.pack(fill="both", expand=True, padx=16, pady=(10, 8))
            self._browser_visible = True
            self._browser_frame_initially_visible = True
            # 탭2 목록에서 실제로 보이도록 바로 레이아웃 갱신
            try:
                self.tab_neighbor.update_idletasks()
            except Exception:
                pass
            try:
                self.tab_neighbor.update()
            except Exception:
                pass
            try:
                self.update_idletasks()
            except Exception:
                pass
            try:
                self.update()
            except Exception:
                pass
            try:
                self.browser_frame.update_idletasks()
            except Exception:
                pass
            try:
                self.browser_frame.update()
            except Exception:
                pass
            try:
                self.browser_frame.lift()
            except Exception:
                pass
        else:
            # 이미 보이는 상태라도 최앞면으로
            try:
                self.browser_frame.lift()
            except Exception:
                pass

    def _complete_browser_show(self):
        try:
            self.update_idletasks()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
        try:
            self.browser_frame.update_idletasks()
        except Exception:
            pass
        try:
            self.browser_frame.update()
        except Exception:
            pass
        try:
            self.browser_frame.lift()
        except Exception:
            pass
        try:
            self.update_idletasks()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
        try:
            self.browser_frame.update_idletasks()
        except Exception:
            pass
        try:
            self.browser_frame.update()
        except Exception:
            pass
        try:
            self.browser_frame.lift()
        except Exception:
            pass

    def _update_browser_ui_logged_in(self):
        """브라우저 뷰를 로그인 완료 상태로 표시."""
        # 브라우저 프레임 숨기기 (댓글 작업 시작)
        if getattr(self, '_browser_visible', False):
            self.browser_frame.pack_forget()
            self._browser_visible = False
            self.browser_status.configure(text="로그인 완료. 댓글 작업을 시작합니다.")

        naver_id = self.entry_naver_id.get().strip()
        naver_pw = self.entry_naver_pw.get().strip()
        my_blog_url = self.entry_my_blog_url.get().strip()

        # 세션 복원 시에는 ID/PW가 비어있을 수 있음 — 이 경우 무시하고 진행

        # 블로그 ID 추출 (URL에서 — m.blog.naver.com 등 오타입 정규화 포함)
        my_blog_id = self._extract_blog_id_from_url(my_blog_url)
        if not my_blog_id:
            messagebox.showwarning(
                "입력 오류",
                "올바른 블로그 주소를 입력하세요.\n"
                "(예: blog.naver.com/myblogid)",
            )
            return
        self._log_exec(f"내 블로그 ID: {my_blog_id}", "info")

        # 탭2 테이블에서 대상 블로그 수집
        self.exec_bloggers = self._get_exec_targets()
        if not self.exec_bloggers:
            messagebox.showwarning(
                "대상 없음", "실행할 블로그가 없습니다.\n탭 1에서 먼저 검색하세요."
            )
            return

        self.is_running_neighbor = True
        self.btn_neighbor_stop.configure(state="normal")
        self.status_label.configure(text="RUNNING", text_color=GREEN_LIGHT)
        self.header_status.configure(text="● RUNNING", text_color=GREEN_LIGHT)

        self._log_exec(f"댓글 자동 입력 시작: {len(self.exec_bloggers)}개 대상", "system")

        # 랜덤 댓글 로드
        use_random = self.use_random_comments_var.get()
        random_comments = []
        if use_random:
            try:
                comments_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comments.json")
                with open(comments_path, "r", encoding="utf-8") as f:
                    random_comments = json.load(f)
                self._log_exec(f"comments.json에서 {len(random_comments)}개 댓글 로드 완료", "success")
            except Exception as e:
                self._log_exec(f"comments.json 로드 실패: {e}. 수동 댓글을 사용합니다.", "warning")
                use_random = False

        # 랜덤 서로이웃신청 메시지 로드
        neighbor_messages = []
        try:
            msgs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neighbor_messages.json")
            with open(msgs_path, "r", encoding="utf-8") as f:
                neighbor_messages = json.load(f)
            self._log_exec(f"neighbor_messages.json에서 {len(neighbor_messages)}개 신청 메시지 로드 완료", "success")
        except Exception as e:
            self._log_exec(f"neighbor_messages.json 로드 실패: {e}. 메시지 없이 신청합니다.", "warning")

        comment = self.text_comment.get("1.0", "end").strip()
        try:
            delay = int(self.entry_delay.get())
        except ValueError:
            delay = 60
        try:
            daily_limit = int(self.entry_daily_limit.get())
        except ValueError:
            daily_limit = 30

        thread = threading.Thread(
            target=self._neighbor_worker,
            args=(naver_id, naver_pw, comment, delay, daily_limit, use_random, random_comments, my_blog_id, neighbor_messages),
            daemon=True,
        )
        thread.start()

    def _get_exec_targets(self):
        """탭2 테이블에서 실행 대상 블로그 목록 반환"""
        targets = []
        for item in self.exec_tree.get_children():
            values = self.exec_tree.item(item, "values")
            if len(values) >= 8 and values[3] and values[3] not in ("", "수집된 블로그가 없습니다.", "탭 1에서 검색 후 자동으로 이관됩니다"):
                # "블로그명 (blogid)" 형태에서 ID 추출
                name_cell = str(values[3])
                m = re.search(r"\(([^)]+)\)\s*$", name_cell)
                blog_id = m.group(1) if m else name_cell
                blog_name = name_cell.split(" (")[0] if " (" in name_cell else name_cell
                targets.append({
                    "blog_id": blog_id,
                    "blog_name": blog_name,
                    "neighbor_count": values[4],
                    "post_count": values[5],
                    "visitor_count": values[6],
                })
        return targets

    def _on_stop_neighbor(self):
        self.is_running_neighbor = False
        self.btn_neighbor_stop.configure(state="disabled")
        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)
        self._log_exec("댓글 자동 입력이 중지되었습니다.", "warning")

    def _neighbor_worker(self, naver_id, naver_pw, comment, delay, daily_limit, use_random=False, random_comments=None, my_blog_id="", neighbor_messages=None):
        """백그라운드 댓글 자동 입력 워커"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self._neighbor_async(naver_id, naver_pw, comment, delay, daily_limit, use_random, random_comments, my_blog_id, neighbor_messages)
            )
        except Exception as e:
            self.after(0, self._log_exec, f"댓글 자동 입력 오류: {e}", "error")
            self.after(0, self._on_neighbor_complete)

    COMMENT_HISTORY_FILE = "comment_history.json"

    def _save_comment_history(self, records):
        """댓글 작성/검증 기록을 JSON 파일로 저장 (세션 누적)"""
        try:
            # 기존 기록 로드 (세션 간 누적)
            existing = []
            if os.path.exists(self.COMMENT_HISTORY_FILE):
                with open(self.COMMENT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            existing.extend(records)

            with open(self.COMMENT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            self._log(
                f"히스토리 저장 완료: {len(records)}건 추가 (총 {len(existing)}건)",
                "success",
            )
        except Exception as e:
            self._log(f"히스토리 저장 실패: {e}", "error")

    async def _neighbor_async(self, naver_id, naver_pw, comment, delay, daily_limit, use_random=False, random_comments=None, my_blog_id="", neighbor_messages=None):
        total = len(self.exec_bloggers)
        completed = 0
        session_records = []  # 이번 세션 기록 누적

        try:
            # ── 새 브라우저에서 로그인 + 댓글 작성 (같은 이벤트 루프) ──
            # 주의: 로그인 전용 워크에서 이미 브라우저가 떠 있을 수 있으므로,
            # 여기서는 브라우저가 없으면 새로 만들고, 있으면 재사용한다.
            # 이미 로그인이 완료된 브라우저라면 재로그인은 하지 않는다.
            show_browser = self.show_browser_var.get()

            if self.automator.browser:
                # ※ 로그인 스레드(다른 asyncio 루프)에서 만든 브라우저는 여기서
                #   재사용할 수 없다 (Playwright 크로스루프 오류로 "브라우저 닫힘" 발생).
                #   이 루프에서 정리하고 세션으로 재로그인한다.
                self.after(0, self._log_exec, "이전 스레드의 브라우저를 정리합니다 (크로스루프 오류 방지)...", "info")
                try:
                    await self.automator.close()
                except Exception:
                    pass
                self.automator.browser = None
                self.automator.page = None
                self.automator.is_logged_in = False

            # 저장된 세션이 있으면 브라우저만 열면 자동 로그인됨 (2FA 재발송 없음)
            has_session = self.automator._has_saved_session()
            self.after(0, self._log_exec, "브라우저 시작 중... (로그인 + 댓글 작업용)", "system")
            await self.automator.start_browser(headless=False)
            await self.automator.bring_to_front()
            await asyncio.sleep(1)

            if has_session:
                self.after(0, self._log_exec, "저장된 세션으로 자동 로그인을 시도합니다...", "info")
                login_ok = await self.automator.login_with_saved_session()
                if not login_ok:
                    # 세션 만료 → 아이디/비밀번호로 재로그인 폴백
                    # (브라우저는 그대로 재사용, 새로 열지 않음)
                    self.after(0, self._log_exec,
                        "세션이 만료되어 아이디/비밀번호로 재로그인합니다...", "warning")
                    if naver_id and naver_pw:
                        self.automator.is_logged_in = False
                        login_ok = await self.automator.login(naver_id, naver_pw)
                    else:
                        self.after(0, self._log_exec,
                            "저장된 아이디/비밀번호가 없어 재로그인할 수 없습니다.", "error")
            else:
                self.after(0, self._log_exec, "네이버 로그인 중...", "system")
                login_ok = await self.automator.login(naver_id, naver_pw)
            if not login_ok:
                self.after(
                    0, self._log_exec,
                    "로그인 실패! 아이디/비밀번호를 확인하세요.",
                    "error",
                )
                return

            # 로그인 성공 후 브라우저 창을 앞으로 가져오기
            await self.automator.bring_to_front()
            self.after(0, self._log_exec, "브라우저 창이 화면에 표시됩니다. 댓글 작성을 시작합니다.", "info")
            await asyncio.sleep(2)

            for idx, blogger in enumerate(self.exec_bloggers):
                if not self.is_running_neighbor:
                    break

                if completed >= daily_limit:
                    self.after(
                        0, self._log_exec,
                        f"일일 제한({daily_limit}건) 도달. 중지합니다.", "warning",
                    )
                    break

                blog_id = blogger.get("blog_id", "")
                blog_name = blogger.get("blog_name", blog_id)

                # 검색 결과에서 수집한 포스트 URL 가져오기
                exec_data = self._exec_blogger_data.get(blog_id, {})
                post_urls = exec_data.get('post_urls', [])
                post_url = post_urls[0] if post_urls else ""
                if post_url:
                    self.after(
                        0, self._log_exec,
                        f"  -> 수집된 포스트 URL 사용: {post_url[:60]}...",
                        "info",
                    )

                self.after(
                    0, self._log_exec,
                    f"[{idx+1}/{total}] 댓글 작성 시도: {blog_name}({blog_id})",
                    "info",
                )

                progress = (idx + 1) / total
                self.after(0, self.neighbor_progress_bar.set, progress)
                self.after(
                    0, self.neighbor_progress_label.configure,
                    {"text": f"{idx+1} / {total} 완료"},
                )

                # 랜덤 댓글 선택 (중복 방지)
                actual_comment = comment
                if use_random and random_comments:
                    import random as _random
                    # 사용하지 않은 댓글만 남김
                    available = [
                        c for c in random_comments
                        if c not in self._used_comments
                    ]
                    # 모든 댓글을 사용했으면 초기화
                    if not available:
                        self._used_comments.clear()
                        available = list(random_comments)
                        self.after(
                            0, self._log_exec,
                            "  -> 모든 댓글 사용 완료, 목록 초기화",
                            "info",
                        )
                    actual_comment = _random.choice(available)
                    self._used_comments.add(actual_comment)
                    self.after(
                        0, self._log_exec,
                        f"  -> 랜덤 댓글 선택 ({len(random_comments) - len(self._used_comments)}개 남음): {actual_comment[:30]}...",
                        "info",
                    )

                try:
                    # 브라우저 창을 앞으로 가져와서 댓글 작성을 볼 수 있도록
                    await self.automator.bring_to_front()
                    await asyncio.sleep(1)

                    self.after(
                        0, self._log_exec,
                        f"  🔄 [{idx+1}/{total}] 브라우저에서 댓글 작성 진행 중...",
                        "info",
                    )

                    # 랜덤 서로이웃신청 메시지 선택
                    actual_neighbor_msg = ""
                    if neighbor_messages:
                        import random as _rnd
                        actual_neighbor_msg = _rnd.choice(neighbor_messages)
                        self.after(
                            0, self._log_exec,
                            f"  -> 랜덤 신청 메시지: '{actual_neighbor_msg[:40]}...'",
                            "info",
                        )

                    comment_ok = await self.automator.write_comment(
                        blog_id, actual_comment, my_blog_id=my_blog_id,
                        post_url=post_url,
                        neighbor_message=actual_neighbor_msg,
                        stop_flag=lambda: not self.is_running_neighbor
                    )
                    # 기록 초기화
                    record = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "blog_id": blog_id,
                        "blog_name": blog_name,
                        "comment": actual_comment,
                        "write_success": comment_ok,
                        "verify_found": False,
                        "verify_message": "작성 실패",
                    }

                    if comment_ok:
                        completed += 1
                        self.after(
                            0, self._log_exec,
                            f"  -> 댓글 작성 성공 ({completed}건 완료)",
                            "success",
                        )

                        # 댓글 작성 결과를 브라우저에서 확인할 수 있도록 대기
                        if show_browser:
                            self.after(
                                0, self._log_exec,
                                "  -> 5초간 댓글 작성 결과를 확인하세요...",
                                "info",
                            )
                            await asyncio.sleep(5)

                        # ── 댓글 검증: 실제 게시글 페이지에서 내 댓글 확인 ──
                        await asyncio.sleep(3)  # 댓글 반영 대기
                        try:
                            verify = await self.automator.verify_comment(
                                blog_id, actual_comment, post_url=post_url
                            )
                            record["verify_found"] = verify.get("found", False)
                            record["verify_message"] = verify.get("message", "")

                            if verify["found"]:
                                self.after(
                                    0, self._log_exec,
                                    f"  -> ✅ 검증 완료: 댓글이 정상적으로 작성됐습니다 ({verify['message']})",
                                    "success",
                                )
                            elif verify["verified"]:
                                self.after(
                                    0, self._log_exec,
                                    f"  -> ⚠️ 검증: 댓글 영역은 확인 (텍스트 매칭 미확인) - {verify['message']}",
                                    "info",
                                )
                            else:
                                self.after(
                                    0, self._log_exec,
                                    f"  -> ❓ 검증 불가: {verify['message']} - comment_history.json에서 확인하세요",
                                    "warning",
                                )
                        except Exception as ve:
                            record["verify_message"] = f"검증 오류: {ve}"
                            self.after(
                                0, self._log_exec,
                                f"  -> 검증 오류: {ve}", "warning",
                            )
                    else:
                        self.after(
                            0, self._log_exec,
                            f"  -> 댓글 작성 실패 (스킵)", "warning",
                        )

                    session_records.append(record)
                except Exception as e:
                    self.after(
                        0, self._log_exec,
                        f"  -> 오류: {e} (스킵)", "error",
                    )

                # 대기
                if idx < total - 1 and self.is_running_neighbor:
                    import random
                    jitter = random.randint(-10, 10)
                    wait = max(10, delay + jitter)
                    self.after(
                        0, self._log_exec,
                        f"  -> {wait}초 대기 중... 다음 블로그를 준비합니다.", "info",
                    )
                    # 대기 중에도 브라우저 창이 보이도록
                    await self.automator.bring_to_front()
                    await asyncio.sleep(wait)

        finally:
            # browser가 있으면 세션 보존 후 종료
            if self.automator.browser:
                try:
                    await self.automator._save_session()
                except Exception:
                    pass
                try:
                    await self.automator.close()
                except Exception:
                    pass
                self.automator.browser = None
                self.automator.page = None
                self.automator.is_logged_in = False

            # 브라우저 창 표시 모드였으면 메인 창 복원
            if show_browser:
                self.after(0, self.deiconify)
                self.after(0, self._log_exec, "메인 창을 복원합니다.", "info")

        # ── 세션 결과 저장 ──
        if session_records:
            self.after(0, self._save_comment_history, session_records)

        self.after(
            0, self._log_exec,
            f"댓글 자동 입력 완료: {completed}/{total}건 성공", "success",
        )
        self.after(0, self._on_neighbor_complete)

    def _on_neighbor_complete(self):
        self.is_running_neighbor = False
        self.btn_neighbor_stop.configure(state="disabled")
        self.status_label.configure(text="IDLE", text_color=YELLOW)
        self.header_status.configure(text="● READY", text_color=GREEN)


# ─── 엔트리 포인트 ────────────────────────────────────────
if __name__ == "__main__":
    app = NaverBlogStealthSystem()
    app.mainloop()
