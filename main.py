"""
NAVER BLOG 관리 시스템 v3.4 — BlogGenius
파워블로거 수집 및 서로이웃 자동화 (원스톱)
- 탭2에서 아이디/비밀번호 입력 → 단일 버튼으로 로그인 → 이웃신청 → 공감 → 댓글까지 자동 진행
- 자격증명은 메모리에서만 사용하며 저장하지 않음
- 탭1: 수집 및 필터링 설정 / 탭2: 서로이웃 자동 신청
- Dark + Purple + Cyan 테마 (기존 디자인 유지)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import asyncio
import random
import os
from datetime import datetime, timedelta

from crawler.naver_crawler import NaverBlogCrawler, BloggerInfo
from crawler.automator import NaverAutomator

from core import history as work_history
from core import excel as excel_mod
from core import settings as settings_mod
from core import templates as templates_mod
from core import logs as logs_mod
from core import textfiles as textfiles_mod
from core import license as license_mod

# ─── 테마 설정 ───────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ─── 컬러 상수 (기존 디자인 유지 + 보라 강조) ─────────────
BG_DARK = "#0d1117"
BG_CARD = "#161b22"
BG_INPUT = "#21262d"
BG_TABLE_HEADER = "#1c2128"
BG_TABLE_ROW = "#0d1117"
PURPLE = "#8957e5"          # 보라 강조색
PURPLE_DARK = "#6e40c9"
PURPLE_HOVER = "#a371f7"
CYAN = "#39c5cf"            # 청록 상태 표시
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

# ─── 한글 선명 폰트 ───────────────────────────────────────
FONT_FAMILY = "맑은 고딕"   # Windows 기본 한글 폰트 (선명)
MONO_FAMILY = "Consolas"


def F(size, weight="normal"):
    """한글 최적화 폰트 헬퍼"""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


TAB_COLLECT = "  🔵  수집 및 필터링 설정  "
TAB_TEMPLATES = "  🟡  메시지·댓글 템플릿  "
TAB_WORK = "  🔵  서로이웃 자동 신청  "


class BlogGeniusApp(ctk.CTk):
    """네이버 블로그 수집/서로이웃 자동화 메인 윈도우"""

    def __init__(self):
        super().__init__()

        self.title("🚀 BlogGenius — 네이버 파워블로거 수집 및 서로이웃 자동화 v3.0")
        self.geometry("1280x820")
        self.minsize(1150, 760)
        self.configure(fg_color=BG_DARK)

        # ── 상태 변수 ──
        self.settings = settings_mod.load()
        self.bloggers = []            # 탭1 수집 결과
        self.selected_ids = set()     # 탭1 체크된 blog_id
        self.work_targets = []        # 탭2로 전송된 작업 대상
        self.work_selected_ids = set()
        self.work_status_map = {}     # blog_id -> 상태 텍스트
        self._tab2_row_map = {}
        self.is_searching = False
        self.is_running = False
        self.is_paused = False
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self._used_comments = set()
        self._used_messages = set()

        # ── [v3.4 신규] 라이센스 검증 (기능 전체 잠금용) ──
        self.license_authorized = False
        try:
            textfiles_mod.ensure_default_files(create_samples=True)
        except Exception:
            pass

        # 백엔드
        self.crawler = NaverBlogCrawler()
        self.crawler.set_log_callback(lambda m, l="info": self._ui_log(m, l))
        self.automator = NaverAutomator()
        self.automator.set_log_callback(lambda m, l="info": self._ui_log(m, l))

        # 로그인 상태: "out" | "checking" | "in"
        self.login_state = "out"

        self._build_ui()
        self._restore_settings_to_ui()
        self._set_login_indicator("out")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── [v3.4 신규] 시작 시 라이센스 인증 확인 (인증 전 전체 기능 제한) ──
        self.after(200, self._check_license_on_start)

        self._log("프로그램이 시작되었습니다.", "system")
        self._log("탭2에서 아이디/비밀번호 입력 후 [로그인 후 원스톱 작업 시작]을 누르면\n"
                  "로그인 → 이웃신청 → 공감 → 댓글까지 자동 진행됩니다 (자격증명은 저장하지 않음).", "info")

    # ══════════════════════════════════════════════════════
    #  UI 구성
    # ══════════════════════════════════════════════════════
    def _build_ui(self):
        self._build_header()
        self._build_tabview()
        self._build_work_status_bar()
        self._build_log_area()

        self.tabview.add(TAB_COLLECT)
        self.tabview.add(TAB_WORK)
        self.tabview.add(TAB_TEMPLATES)

        self._build_collect_tab(self.tabview.tab(TAB_COLLECT))
        self._build_templates_tab(self.tabview.tab(TAB_TEMPLATES))
        self._build_work_tab(self.tabview.tab(TAB_WORK))
        self.tabview.set(TAB_COLLECT)

    # ── 헤더 ──────────────────────────────────────────────
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, height=78)
        header.pack(fill="x", padx=12, pady=(10, 6))
        header.pack_propagate(False)

        # 타이틀
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="y", padx=16, pady=8)

        ctk.CTkLabel(
            title_frame, text="🚀 네이버 파워블로거 수집 및 서로이웃 자동화",
            font=F(20, "bold"), text_color=PURPLE_HOVER,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="대상을 수집·필터링하고, 확인한 작업만 보조합니다. 아이디/비밀번호는 저장하지 않습니다.",
            font=F(11), text_color=TEXT_GRAY,
        ).pack(anchor="w", pady=(1, 0))

        # 로그인 상태 표시만 (로그인 버튼은 탭2에 하나만 존재)
        login_frame = ctk.CTkFrame(header, fg_color="transparent")
        login_frame.pack(side="right", fill="y", padx=16, pady=8)

        self.login_status_label = ctk.CTkLabel(
            login_frame, text="🔴 로그아웃",
            font=F(15, "bold"), text_color=RED,
        )
        self.login_status_label.pack(anchor="e")

        login_btn_row = ctk.CTkFrame(login_frame, fg_color="transparent")
        login_btn_row.pack(anchor="e", pady=(4, 0))

        self.btn_logout = ctk.CTkButton(
            login_btn_row, text="로그아웃",
            font=F(11), fg_color=BG_INPUT, hover_color=RED,
            text_color=TEXT_GRAY, width=70, height=34, corner_radius=6,
            command=self._on_logout, state="disabled",
        )
        self.btn_logout.pack(side="left")

        self.btn_exit = ctk.CTkButton(
            login_btn_row, text="🔴 프로그램 종료",
            font=F(11, "bold"), fg_color="#3d1212", hover_color=RED,
            text_color=RED, width=110, height=34, corner_radius=6,
            command=self._on_exit_program,
        )
        self.btn_exit.pack(side="left", padx=(6, 0))

    # ── 탭 뷰 ─────────────────────────────────────────────
    def _build_tabview(self):
        self.tabview = ctk.CTkTabview(
            self, fg_color=BG_DARK,
            segmented_button_fg_color=BG_CARD,
            segmented_button_selected_color=PURPLE,
            segmented_button_selected_hover_color=PURPLE_HOVER,
            segmented_button_unselected_color=BG_CARD,
            segmented_button_unselected_hover_color="#1f242c",
            text_color=TEXT_WHITE, border_width=0,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(0, 6))

    # ── 작업 현황 바 (하단) ────────────────────────────────
    def _build_work_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, height=44)
        bar.pack(fill="x", padx=12, pady=(0, 6))
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="📊 작업 현황", font=F(12, "bold"),
                     text_color=TEXT_GRAY).pack(side="left", padx=(14, 10))

        self.stat_total = ctk.CTkLabel(bar, text="전체 0", font=F(13, "bold"), text_color=TEXT_WHITE)
        self.stat_total.pack(side="left", padx=8)
        self.stat_done = ctk.CTkLabel(bar, text="완료 0", font=F(13, "bold"), text_color=GREEN_LIGHT)
        self.stat_done.pack(side="left", padx=8)
        self.stat_doing = ctk.CTkLabel(bar, text="진행 0", font=F(13, "bold"), text_color=CYAN)
        self.stat_doing.pack(side="left", padx=8)
        self.stat_wait = ctk.CTkLabel(bar, text="대기 0", font=F(13, "bold"), text_color=YELLOW)
        self.stat_wait.pack(side="left", padx=8)
        self.stat_fail = ctk.CTkLabel(bar, text="실패 0", font=F(13, "bold"), text_color=RED)
        self.stat_fail.pack(side="left", padx=8)

        self.current_work_label = ctk.CTkLabel(bar, text="", font=F(12), text_color=CYAN)
        self.current_work_label.pack(side="left", padx=20)

        # 엑셀 열기
        ctk.CTkButton(
            bar, text="📊 엑셀 열기", font=F(11, "bold"), width=90, height=28,
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white",
            command=self._open_latest_excel,
        ).pack(side="right", padx=(0, 12))

        # 진행률 바
        self.work_progress = ctk.CTkProgressBar(
            bar, fg_color=BG_INPUT, progress_color=PURPLE, height=10, width=180,
        )
        self.work_progress.pack(side="right", padx=(0, 10))
        self.work_progress.set(0)

    # ── 로그 영역 (하단) ───────────────────────────────────
    def _build_log_area(self):
        log_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, height=170)
        log_frame.pack(fill="x", padx=12, pady=(0, 10))
        log_frame.pack_propagate(False)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=12, pady=(6, 0))

        ctk.CTkLabel(log_header, text="📜 실시간 작업 로그",
                     font=F(12, "bold"), text_color=TEXT_GRAY).pack(side="left")

        ctk.CTkButton(
            log_header, text="지우기", font=F(10),
            fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_GRAY,
            width=60, height=22, corner_radius=4,
            command=self._clear_log,
        ).pack(side="right")

        self.log_text = ctk.CTkTextbox(
            log_frame, fg_color=BG_TABLE_ROW, border_color=BORDER, border_width=1,
            text_color=GREEN_LIGHT, font=ctk.CTkFont(family=MONO_FAMILY, size=11),
            scrollbar_button_color=SCROLLBAR_BG, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.log_text.configure(state="disabled")

    def _log(self, message, level="info"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag_map = {
            "info": "[INFO]", "success": "[OK]", "warning": "[WARN]",
            "error": "[ERR]", "system": "[SYS]", "pause": "[PAUSE]",
        }
        prefix = tag_map.get(level, "[LOG]")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {prefix} {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        logs_mod.append(message, level, enabled=self.settings.get("save_logs", True))

    def _ui_log(self, message, level="info"):
        """스레드에서 호출되는 로그 → 메인 스레드로 전달"""
        try:
            self.after(0, self._log, message, level)
        except Exception:
            pass

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ── 테이블 공통 스타일 ────────────────────────────────
    def _setup_tree_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Treeview", background=BG_TABLE_ROW, foreground=TEXT_WHITE,
            fieldbackground=BG_TABLE_ROW, borderwidth=0, rowheight=34,
            font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Custom.Treeview.Heading", background=BG_TABLE_HEADER,
            foreground=TEXT_GRAY, borderwidth=0,
            font=(FONT_FAMILY, 10, "bold"), relief="flat",
        )
        style.map("Custom.Treeview",
                  background=[("selected", PURPLE_DARK)],
                  foreground=[("selected", "white")])
        style.configure("Custom.Vertical.TScrollbar",
                        background=SCROLLBAR_BG, troughcolor=BG_CARD,
                        borderwidth=0, arrowcolor=TEXT_DIM)

    # ══════════════════════════════════════════════════════
    #  탭 1: 수집 및 필터링 설정
    # ══════════════════════════════════════════════════════
    def _build_collect_tab(self, parent):
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self._setup_tree_style()

        # ── 왼쪽: 수집 및 필터링 설정 ──
        left = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8, width=430)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="수집 및 필터링 설정", font=F(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(left, text="조건을 모두 만족하는 블로그만 수집됩니다.",
                     font=F(11), text_color=TEXT_GRAY).pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkLabel(left, text="검색 키워드 (쉼표 구분)",
                     font=F(11), text_color=TEXT_GRAY).pack(anchor="w", padx=16)
        self.entry_keyword = ctk.CTkEntry(
            left, placeholder_text="예: 광주, IT, 테크, 맛집, 힐링", height=38,
            fg_color=BG_INPUT, border_color=PURPLE, border_width=2,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM, font=F(13),
        )
        self.entry_keyword.pack(fill="x", padx=16, pady=(4, 10))

        # ── 수집 조건 (2행 × 3열 배치 — 하단 버튼이 가려지지 않도록) ──
        ctk.CTkLabel(left, text="수집 조건", font=F(12, "bold"),
                     text_color=CYAN).pack(anchor="w", padx=16, pady=(2, 2))

        self.condition_entries = {}
        conditions = [
            ("개설 기준년도", "2003", "년 이후", "open_year"),
            ("최소 이웃 수", "500", "명 이상", "neighbors"),
            ("최소 누적 방문자 수", "5000", "명 이상", "visitors"),
            ("최소 일일 방문자 수", "100", "명 이상", "daily"),
            ("최소 게시글 수", "30", "개 이상", "posts"),
            ("목표 수집 블로그 수", "30", "개", "target"),
        ]
        # 이전 세션에 저장된 수집 조건을 최우선 사용 (재시작 시 마지막 입력값 표시)
        saved_conds = self.settings.get("conditions", {}) or {}

        # 조건 배치: 2행 × 3열
        for row_start in (0, 3):
            row = ctk.CTkFrame(left, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            for label, default, unit, key in conditions[row_start:row_start + 3]:
                cell = ctk.CTkFrame(row, fg_color="transparent")
                cell.pack(side="left", expand=True, fill="x", padx=3)

                ctk.CTkLabel(cell, text=label, font=F(10),
                             text_color=TEXT_GRAY, anchor="w").pack(anchor="w")

                inner = ctk.CTkFrame(cell, fg_color="transparent")
                inner.pack(anchor="w")
                entry = ctk.CTkEntry(
                    inner, width=62, height=28, fg_color=BG_INPUT,
                    border_color=BORDER, text_color=TEXT_WHITE,
                    justify="center", font=F(12, "bold"),
                )
                entry.insert(0, str(saved_conds.get(key, "")).strip() or default)
                entry.pack(side="left")
                ctk.CTkLabel(inner, text=unit, font=F(9),
                             text_color=TEXT_DIM).pack(side="left", padx=(3, 0))
                # 입력이 바뀔 때마다 즉시 저장 — 종료/재시작 관계없이 최근 값 유지
                entry.bind("<KeyRelease>", self._on_condition_changed)
                entry.bind("<FocusOut>", self._on_condition_changed)
                self.condition_entries[key] = entry

        # ── 버튼 ──
        self.btn_search = ctk.CTkButton(
            left, text="🟢  수집 시작", font=F(14, "bold"),
            fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
            height=44, corner_radius=6, command=self._on_start_search,
        )
        self.btn_search.pack(fill="x", padx=16, pady=(10, 4))

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 4))

        self.btn_search_stop = ctk.CTkButton(
            btn_row, text="🔴  수집 중지", font=F(13, "bold"),
            fg_color=BG_INPUT, hover_color=RED, text_color=TEXT_GRAY,
            height=38, corner_radius=6, state="disabled", command=self._on_stop_search,
        )
        self.btn_search_stop.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_transfer = ctk.CTkButton(
            btn_row, text="➡️  신청 탭으로 전송", font=F(13, "bold"),
            fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white",
            height=38, corner_radius=6, command=self._transfer_to_work,
        )
        self.btn_transfer.pack(side="left", expand=True, fill="x")

        # 브라우저 표시
        self.var_show_browser = ctk.BooleanVar(value=self.settings.get("show_browser", True))
        ctk.CTkCheckBox(
            left, text="브라우저 창 표시 (작업 화면을 실시간으로 확인)",
            variable=self.var_show_browser,
            font=F(11), text_color=TEXT_GRAY,
            fg_color=PURPLE, hover_color=PURPLE_HOVER, checkmark_color="white",
        ).pack(anchor="w", padx=16, pady=(6, 4))

        self.search_progress_label = ctk.CTkLabel(left, text="대기 중...",
                                                  font=F(11), text_color=TEXT_DIM)
        self.search_progress_label.pack(anchor="w", padx=16, pady=(0, 12))

        # ── 오른쪽: 합격 현황 + 명단 ──
        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew")

        # 상단 통계 카드
        stat_row = ctk.CTkFrame(right, fg_color="transparent")
        stat_row.pack(fill="x", padx=16, pady=(12, 4))

        left_stat = ctk.CTkFrame(stat_row, fg_color="transparent")
        left_stat.pack(side="left")
        ctk.CTkLabel(left_stat, text="합격 파워블로거", font=F(12),
                     text_color=TEXT_GRAY).pack(anchor="w")
        self.pass_count_label = ctk.CTkLabel(left_stat, text="0 명",
                                             font=F(28, "bold"), text_color=GREEN_LIGHT)
        self.pass_count_label.pack(anchor="w")

        right_stat = ctk.CTkFrame(stat_row, fg_color="transparent")
        right_stat.pack(side="right")
        ctk.CTkLabel(right_stat, text="실행 상태", font=F(12),
                     text_color=TEXT_GRAY).pack(anchor="e")
        self.run_state_label = ctk.CTkLabel(right_stat, text="IDLE",
                                            font=F(22, "bold"), text_color=YELLOW)
        self.run_state_label.pack(anchor="e")

        ctk.CTkFrame(right, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(6, 6))

        # 명단 헤더
        list_header = ctk.CTkFrame(right, fg_color="transparent")
        list_header.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(list_header, text="검증된 파워블로거 명단 (체크 후 신청 탭으로 이동)",
                     font=F(13, "bold"), text_color=PURPLE_HOVER).pack(side="left")

        self.selected_count_label = ctk.CTkLabel(
            list_header, text="선택 대상: 0명", font=F(13, "bold"), text_color=CYAN,
        )
        self.selected_count_label.pack(side="right")

        sel_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        sel_btn_row.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkButton(sel_btn_row, text="☑ 전체 선택", font=F(11), width=90, height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=lambda: self._select_all(True)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(sel_btn_row, text="☐ 전체 해제", font=F(11), width=90, height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=lambda: self._select_all(False)).pack(side="left")

        # 명단 테이블
        table_frame = ctk.CTkFrame(right, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        columns = ("sel", "no", "keyword", "blog_name", "blog_id",
                   "open_date", "neighbors", "recent")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                 style="Custom.Treeview", selectmode="none")
        col_config = [
            ("sel", "선택", 46),
            ("no", "#", 38),
            ("keyword", "키워드", 80),
            ("blog_name", "블로그명", 180),
            ("blog_id", "블로그 ID", 120),
            ("open_date", "개설일", 80),
            ("neighbors", "이웃수", 70),
            ("recent", "최근 게시글", 200),
        ]
        for col_id, heading, width in col_config:
            self.tree.heading(col_id, text=heading, anchor="center")
            self.tree.column(col_id, width=width, minwidth=44, anchor="center")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview,
                            style="Custom.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure("even", background=BG_TABLE_ROW)
        self.tree.tag_configure("odd", background="#11161d")

        self.tree.bind("<Button-1>", self._on_tree_click)
        self._insert_empty_result("수집 조건을 설정하고 [수집 시작]을 누르세요.")

    def _insert_empty_result(self, msg):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree.insert("", "end",
                         values=("", "", "", msg, "", "", "", ""), tags=("even",))

    # ── 수집 결과 테이블 ───────────────────────────────────
    def _populate_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.bloggers:
            self._insert_empty_result("조건에 맞는 블로그가 없습니다.")
            self.pass_count_label.configure(text="0 명")
            return

        for i, b in enumerate(self.bloggers):
            bid = b.get("blog_id", "")
            sel_text = "☑" if bid in self.selected_ids else "☐"
            open_year = b.get("blog_open_year", 0)
            # RSS 근사 개설연도는 '~년' 표기 (실제 개설일보다 최근일 수 있음)
            open_text = f"{open_year}년~" if b.get("blog_open_year_is_approx") else (
                f"{open_year}년" if open_year else "-")

            values = (
                sel_text, i + 1, b.get("keyword", "-"), b.get("blog_name", "-"),
                bid, open_text, b.get("neighbor_count", 0),
                (b.get("recent_title") or "")[:22],
            )
            self.tree.insert("", "end", values=values,
                             tags=("odd" if i % 2 else "even",))

        self.pass_count_label.configure(text=f"{len(self.bloggers)} 명")
        self._update_selected_count()

    def _update_selected_count(self):
        self.selected_count_label.configure(text=f"선택 대상: {len(self.selected_ids)}명")

    def _on_tree_click(self, event):
        """체크박스 칼럼 클릭으로 선택 토글 (탭1)"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        values = self.tree.item(item, "values")
        if len(values) < 5 or not values[4]:
            return
        bid = values[4]
        if bid in self.selected_ids:
            self.selected_ids.discard(bid)
            self.tree.set(item, column="sel", value="☐")
        else:
            self.selected_ids.add(bid)
            self.tree.set(item, column="sel", value="☑")
        self._update_selected_count()

    def _select_all(self, select: bool):
        if select:
            for b in self.bloggers:
                self.selected_ids.add(b.get("blog_id", ""))
        else:
            self.selected_ids.clear()
        self._populate_results()

    # ── 수집 실행 ─────────────────────────────────────────
    def _collect_conditions_safe(self):
        """수집 조건을 안전하게 int로 변환 (빈 값/오류는 0 = 조건 없음)"""
        conds = {}
        for key, entry in self.condition_entries.items():
            raw = entry.get().strip().replace(",", "")
            try:
                conds[key] = int(raw) if raw else 0
            except ValueError:
                conds[key] = 0
        return conds

    # ── 대기 단위(초/분/시간) 전환 ─────────────────────
    def _on_pause_unit_change(self):
        """대기 시간 단위가 바뀌면 안내 로그만 남기고, 저장 시 해석한다."""
        self._log(f"작업 간 대기 단위를 '{self.var_pause_unit.get()}'(으)로 설정했습니다.", "info")

    def _get_pause_delay_seconds(self) -> tuple:
        """작업 간 대기 시간을 초 단위로 계산 (단위: 초/분/시간 지원)"""
        try:
            lo = float(self.entry_pause_min.get() or 30)
            hi = float(self.entry_pause_max.get() or 90)
        except ValueError:
            lo, hi = 30.0, 90.0
        unit = self.var_pause_unit.get()
        if unit == "분":
            lo, hi = lo * 60, hi * 60
        elif unit == "시간":
            lo, hi = lo * 3600, hi * 3600
        lo = max(5.0, lo)
        hi = max(lo, hi)
        return lo, hi

    def _get_speed_factor(self) -> tuple:
        """작업 속도 배율 (0.2 ~ 3.0, 기본 0.5~1.0)"""
        try:
            lo = max(0.2, min(3.0, float(self.entry_speed_min.get() or 0.5)))
        except ValueError:
            lo = 0.5
        try:
            hi = max(0.2, min(3.0, float(self.entry_speed_max.get() or 1.0)))
        except ValueError:
            hi = 1.0
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi

    def _on_start_search(self):
        keyword = self.entry_keyword.get().strip()
        if not keyword:
            messagebox.showwarning("입력 필요", "검색 키워드를 입력하세요.")
            return
        if self.is_searching:
            messagebox.showinfo("알림", "이미 수집이 진행 중입니다.")
            return

        # ── [v3.4 신규] 라이센스 인증 확인 (만료/무효 시 사용 차단) ──
        if not self._ensure_licensed():
            self._log("라이센스 인증 실패 — 수집이 차단되었습니다.", "warning")
            return

        conds = self._collect_conditions_safe()
        target_count = conds.get("target") or 20

        self.is_searching = True
        self.btn_search.configure(state="disabled", text="수집 중...")
        self.btn_search_stop.configure(state="normal", text="🔴  수집 중지",
                                       fg_color=RED, text_color="white")
        self.run_state_label.configure(text="SEARCHING", text_color=CYAN)
        self.search_progress_label.configure(text=f"'{keyword}' 수집 중...")

        self._save_settings()
        self._log(f"═══ 수집 시작: 키워드='{keyword}', 목표={target_count}개 ═══", "system")
        self._log(f"조건: 개설>={conds['open_year']}년, 이웃>={conds['neighbors']}명, "
                  f"누적방문>={conds['visitors']}명, 일일방문>={conds['daily']}명, "
                  f"게시글>={conds['posts']}개", "info")

        thread = threading.Thread(target=self._search_worker,
                                  args=(keyword, conds, target_count), daemon=True)
        thread.start()

    def _on_stop_search(self):
        self.is_searching = False
        self.btn_search.configure(state="normal", text="🟢  수집 시작")
        self.btn_search_stop.configure(state="disabled", text="🔴  수집 중지",
                                       fg_color=BG_INPUT, text_color=TEXT_GRAY)
        self.run_state_label.configure(text="STOPPED", text_color=RED)
        self.search_progress_label.configure(text="수집이 중지되었습니다.")
        self._log("수집이 중지되었습니다.", "warning")

    def _search_worker(self, keyword_raw, conds, target_count):
        try:
            # ── 1단계: 키워드별 검색 (쉼표 구분 지원) ──
            keywords = [k.strip() for k in keyword_raw.split(",") if k.strip()] or [keyword_raw]
            all_ids = []
            kw_map = {}       # blog_id -> 매칭 키워드
            meta_all = {}     # blog_id -> {post_urls, post_titles}

            for kw in keywords:
                if not self.is_searching:
                    break
                self._ui_log(f"[1/4] 키워드 '{kw}' 검색 중...", "system")
                ids = self.crawler.search_blog_ids_http(kw, max_pages=3)
                for bid in ids:
                    if bid not in kw_map:
                        kw_map[bid] = kw
                # search_blog_ids_http가 내부 메타데이터를 리셋하므로 병합 보관
                meta_all.update(getattr(self.crawler, "_search_metadata", {}))
                all_ids.extend(ids)
                self._ui_log(f"  -> '{kw}' {len(ids)}건 수집", "info")

            # 중복 제거 (순서 유지)
            seen = set()
            blog_ids = []
            for bid in all_ids:
                if bid and bid not in seen:
                    seen.add(bid)
                    blog_ids.append(bid)

            self._ui_log(f"[1/4] 키워드 검색 완료: 총 {len(blog_ids)}개 블로그", "success")
            if not blog_ids or not self.is_searching:
                self.after(0, self._on_search_done, [], "결과 없음")
                return

            # ── 2단계: HTTP 병렬 사전 수집 ──
            self._ui_log(f"[2/4] 블로그 정보 병렬 수집 중... ({len(blog_ids)}개)", "info")
            prefiltered = self.crawler.http_prefilter_batch(
                blog_ids[:min(len(blog_ids), max(target_count * 8, 200))],
                keyword=keyword_raw,
                max_candidates=max(target_count * 3, 50),
                callback=lambda m, l="info": self._ui_log(m, l),
                stop_flag=lambda: not self.is_searching,
            )
            self._ui_log(f"[2/4] 정보 수집 완료: {len(prefiltered)}건", "success")

            if not prefiltered or not self.is_searching:
                self.after(0, self._on_search_done, [], "정보 수집 실패")
                return

            # 키워드/포스트 정보 결합
            for info in prefiltered:
                bid = info.get("blog_id", "")
                info["keyword"] = kw_map.get(bid, "")
                meta = meta_all.get(bid, {})
                info["post_urls"] = meta.get("post_urls", [])
                titles = meta.get("post_titles", [])
                info["recent_title"] = titles[0] if titles else ""

            # ── 3단계: 수집 조건 필터링 (확인된 값은 엄격, 미확인은 관대) ──
            # [v3.1.1 정책]
            #  - 데이터가 확인된 필드는 설정 조건보다 낮으면 무조건 제외 (엄격)
            #  - 데이터 자체가 확인되지 않은 필드(0)는 1차 필터에서 통과시키고
            #    관련도 점수에서 불이익을 준다 (완화 아님 — 완전 배제는 정보 부족 탓)
            #  - 예외: 개설년도 근사치(RSS)가 기준보다 오래됨이 '확인'되면 제외
            self._ui_log(f"[3/4] 수집 조건 필터링 중... ({len(prefiltered)}개)", "info")

            def apply_conds(c, strict_unknown=False):
                out = []
                for info in prefiltered:
                    if not self.is_searching:
                        break
                    y = info.get("blog_open_year", 0) or 0
                    n = info.get("neighbor_count", 0) or 0
                    v = info.get("visitor_count", 0) or 0
                    d = info.get("daily_visitor_count", 0) or 0
                    p = info.get("post_count", 0) or 0

                    # 개설년도: 근사치라도 확인됐으면 엄격 비교,
                    # strict 모드(재시도)에서는 미확인도 제외
                    if c["open_year"]:
                        if y and y < c["open_year"]:
                            continue
                        if strict_unknown and not y:
                            continue

                    # 이웃/방문자/일일/게시글: 확인된 값은 엄격 비교
                    # (미확인(0)은 1차 통과 — 점수에서 불이익)
                    if n and c["neighbors"] and n < c["neighbors"]:
                        continue
                    if v and c["visitors"] and v < c["visitors"]:
                        continue
                    if d and c["daily"] and d < c["daily"]:
                        continue
                    if p and c["posts"] and p < c["posts"]:
                        continue
                    out.append(info)
                return out

            working_conds = {k: conds[k] for k in ("open_year", "neighbors", "visitors", "daily", "posts")}
            passed = apply_conds(working_conds)
            self._ui_log(f"  -> 조건 통과: {len(passed)}건 "
                         "(확인된 조건 미달은 제외, 정보 미확인 블로그는 점수 불이익)", "info")

            # 1차 통과가 목표의 50% 미만이면 미확인 데이터를 엄격히 걸러 재시도
            if len(passed) < max(target_count // 2, 5):
                strict_passed = apply_conds(working_conds, strict_unknown=True)
                if strict_passed:
                    passed = strict_passed
                    self._ui_log(f"  ⚠️ 정보 미확인 블로그 재검증 → {len(passed)}건 (엄격 모드)", "warning")

            if len(passed) < target_count:
                self._ui_log(f"  ⚠️ 조건 통과 {len(passed)}건 < 목표 {target_count}개 — "
                             "조건을 완화하지 않고 찾은 만큼만 수집합니다.", "warning")

            if not passed or not self.is_searching:
                self.after(0, self._on_search_done, [], "조건 통과 없음")
                return

            # ── 4단계: 키워드 관련도 점수 → 정렬 → 목표 수 제한 ──
            self._ui_log(f"[4/4] 키워드 관련도 점수 계산 중... ({len(passed)}개)", "info")
            scored = []
            for info in passed:
                blogger = BloggerInfo(
                    blog_id=info.get("blog_id", ""),
                    blog_name=info.get("blog_name", ""),
                    category=info.get("category", ""),
                    description=info.get("description", ""),
                    post_titles=" ".join(info.get("post_titles", []) or []),
                    post_contents=info.get("post_contents", ""),
                    neighbor_count=info.get("neighbor_count", 0),
                    visitor_count=info.get("visitor_count", 0),
                    daily_visitor_count=info.get("daily_visitor_count", 0),
                    post_count=info.get("post_count", 0),
                    blog_open_year=info.get("blog_open_year", 0),
                    blog_url=f"https://blog.naver.com/{info.get('blog_id', '')}",
                )
                score = self.crawler._calc_relevance(keyword_raw, blogger)
                info["relevance_score"] = score if score > 0 else 10

                # 정보 미확인 필드 불이익 (확인된 블로그를 우선 정렬)
                unknown_penalty = 0
                if not info.get("blog_open_year"):
                    unknown_penalty += 5
                if not info.get("neighbor_count"):
                    unknown_penalty += 5
                if not info.get("visitor_count"):
                    unknown_penalty += 3
                if not info.get("post_count"):
                    unknown_penalty += 2
                info["relevance_score"] = max(0, info["relevance_score"] - unknown_penalty)
                scored.append(info)

            scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            results = scored[:target_count]

            self.after(0, self._on_search_done, results, "ok")

        except Exception as e:
            self._ui_log(f"수집 오류: {e}", "error")
            self.after(0, self._on_search_done, [], f"오류: {e}")

    def _on_search_done(self, results, reason):
        self.is_searching = False
        self.btn_search.configure(state="normal", text="🟢  수집 시작")
        self.btn_search_stop.configure(state="disabled", text="🔴  수집 중지",
                                       fg_color=BG_INPUT, text_color=TEXT_GRAY)
        self.run_state_label.configure(text="IDLE", text_color=YELLOW)

        if results:
            self.bloggers = results
            self.selected_ids = {b["blog_id"] for b in results}  # 기본 전체 선택
            self._populate_results()
            self.search_progress_label.configure(text=f"수집 완료: {len(results)}개 블로그")
            self._log(f"수집 완료: {len(results)}개 (전체 선택됨 — 원하는 대상만 체크 후 [신청 탭으로 전송])", "success")
        else:
            self.bloggers = []
            self.selected_ids.clear()
            self._populate_results()
            self.search_progress_label.configure(text=f"수집 완료 ({reason})")
            self._log(f"수집 완료: 결과 없음 ({reason})", "warning")

    # ── 탭2 전송 ──────────────────────────────────────────
    def _transfer_to_work(self):
        # ── [v3.4 신규] 라이센스 인증 확인 (만료/무효 시 사용 차단) ──
        if not self._ensure_licensed():
            self._log("라이센스 인증 실패 — 신청 탭 전송이 차단되었습니다.", "warning")
            return

        chosen = [b for b in self.bloggers if b.get("blog_id") in self.selected_ids]
        if not chosen:
            messagebox.showinfo("알림", "전송할 대상을 먼저 선택하세요.")
            return

        self.work_targets = chosen
        self.work_selected_ids = {b["blog_id"] for b in chosen}
        self.work_status_map = {}  # 상태 초기화
        self._populate_work_tree()

        self.tabview.set(TAB_WORK)
        self._log(f"서로이웃 자동 신청 탭으로 {len(chosen)}명 전송 완료.", "success")

    # ══════════════════════════════════════════════════════
    #  탭: 메시지·댓글 템플릿 (작업 전 미리 입력)
    # ══════════════════════════════════════════════════════
    def _build_templates_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="여기서 서로이웃 신청 메시지와 댓글을 미리 입력하세요. 저장한 내용은 "
                 "[서로이웃 자동 신청] 탭 입력창에도 그대로 사용되며, 발송 전 확인창에서 수정할 수도 있습니다.",
            font=F(12), text_color=CYAN, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))

        # ── 왼쪽: 서로이웃 신청 메시지 ──
        msg_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        msg_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))

        ctk.CTkLabel(msg_frame, text="✉️ 서로이웃 신청 메시지 (발송용)",
                     font=F(15, "bold"), text_color=TEXT_WHITE).pack(
            anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(msg_frame, text="대상마다 여러 개 중 랜덤으로 발송됩니다.",
                     font=F(10), text_color=TEXT_GRAY).pack(anchor="w", padx=16, pady=(0, 6))

        self.tpl_text_neighbor_msg = ctk.CTkTextbox(
            msg_frame, height=220, fg_color=BG_INPUT, border_color=BORDER,
            border_width=1, text_color=TEXT_WHITE, font=F(12),
            scrollbar_button_color=SCROLLBAR_BG,
        )
        self.tpl_text_neighbor_msg.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        saved_msgs = templates_mod.get_neighbor_messages()
        if saved_msgs:
            self.tpl_text_neighbor_msg.insert("1.0", saved_msgs[0])

        tpl_msg_btns = ctk.CTkFrame(msg_frame, fg_color="transparent")
        tpl_msg_btns.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(tpl_msg_btns, text="💾 메시지 저장", font=F(11), height=32,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=self._save_tpl_neighbor_msg).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_msg_btns, text="📋 저장 목록", font=F(11), height=32,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._show_neighbor_templates_from_tab).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_msg_btns, text="📥 불러오기", font=F(11), height=32,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._load_tpl_neighbor_msg_from_list).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_msg_btns, text="➡️ 신청 탭에 적용", font=F(11), height=32,
                      fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white",
                      command=self._apply_tpl_to_work).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_msg_btns, text="기본 메시지", font=F(11), height=32,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_GRAY,
                      command=self._load_tpl_default_msg).pack(side="right")

        # ── 오른쪽: 댓글 템플릿 ──
        cmt_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        cmt_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))

        ctk.CTkLabel(cmt_frame, text="💬 댓글 템플릿 (작성용)",
                     font=F(15, "bold"), text_color=TEXT_WHITE).pack(
            anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(cmt_frame, text="대상마다 여러 개 중 랜덤으로 작성됩니다.",
                     font=F(10), text_color=TEXT_GRAY).pack(anchor="w", padx=16, pady=(0, 6))

        self.tpl_text_comment = ctk.CTkTextbox(
            cmt_frame, height=220, fg_color=BG_INPUT, border_color=BORDER,
            border_width=1, text_color=TEXT_WHITE, font=F(12),
            scrollbar_button_color=SCROLLBAR_BG,
        )
        self.tpl_text_comment.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        saved_cmts = templates_mod.get_comments()
        if saved_cmts:
            self.tpl_text_comment.insert("1.0", saved_cmts[0])

        tpl_cmt_btns = ctk.CTkFrame(cmt_frame, fg_color="transparent")
        tpl_cmt_btns.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(tpl_cmt_btns, text="💾 댓글 저장", font=F(11), height=32,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=self._save_tpl_comment).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_cmt_btns, text="📋 저장 목록", font=F(11), height=32,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._show_comment_templates_from_tab).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tpl_cmt_btns, text="📥 불러오기", font=F(11), height=32,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._load_tpl_comment_from_list).pack(side="left")

    # ── 템플릿 탭 동작 ──
    def _save_tpl_neighbor_msg(self):
        msg = self.tpl_text_neighbor_msg.get("1.0", "end").strip()
        if not msg:
            messagebox.showwarning("입력 필요", "메시지를 입력하세요.")
            return
        templates_mod.add_neighbor_message(msg)
        # 신청 탭 입력창에도 즉시 반영 (수정 가능 상태 유지)
        self.text_neighbor_msg.delete("1.0", "end")
        self.text_neighbor_msg.insert("1.0", msg)
        self._log("신청 메시지가 템플릿에 저장되고 신청 탭에 적용되었습니다.", "success")

    def _save_tpl_comment(self):
        comment = self.tpl_text_comment.get("1.0", "end").strip()
        if not comment:
            messagebox.showwarning("입력 필요", "댓글을 입력하세요.")
            return
        templates_mod.add_comment(comment)
        self.text_comment.delete("1.0", "end")
        self.text_comment.insert("1.0", comment)
        self._log("댓글 템플릿이 저장되고 신청 탭에 적용되었습니다.", "success")

    def _show_neighbor_templates_from_tab(self):
        msgs = templates_mod.get_neighbor_messages()
        if not msgs:
            messagebox.showinfo("저장 목록", "저장된 메시지가 없습니다.")
            return

        def on_delete(idx):
            msgs.pop(idx)
            templates_mod.save_neighbor_messages(msgs)
            self._log("템플릿 메시지를 삭제했습니다.", "info")

        self._show_template_window("저장된 신청 메시지", msgs, delete_cb=on_delete)

    def _load_tpl_neighbor_msg_from_list(self):
        """저장 목록 창에서 항목을 선택해 메시지 입력창에 불러온다"""
        msgs = templates_mod.get_neighbor_messages()
        if not msgs:
            messagebox.showinfo("불러오기", "저장된 메시지가 없습니다.")
            return

        def on_delete(idx):
            msgs.pop(idx)
            templates_mod.save_neighbor_messages(msgs)

        picked = self._show_template_window("메시지 불러오기", msgs, delete_cb=on_delete,
                                            file_loader=templates_mod.read_template_file)
        if picked is not None:
            self.tpl_text_neighbor_msg.delete("1.0", "end")
            self.tpl_text_neighbor_msg.insert("1.0", picked)
            self._log("저장된 메시지를 템플릿 탭 입력창에 불러왔습니다.", "success")

    def _show_comment_templates_from_tab(self):
        comments = templates_mod.get_comments()
        if not comments:
            messagebox.showinfo("저장 목록", "저장된 댓글 템플릿이 없습니다.")
            return

        def on_delete(idx):
            comments.pop(idx)
            templates_mod.save_comments(comments)

        self._show_template_window("저장된 댓글 템플릿", comments, delete_cb=on_delete)

    def _load_tpl_comment_from_list(self):
        """저장 목록 창에서 항목을 선택해 댓글 입력창에 불러온다"""
        comments = templates_mod.get_comments()
        if not comments:
            messagebox.showinfo("불러오기", "저장된 댓글 템플릿이 없습니다.")
            return

        def on_delete(idx):
            comments.pop(idx)
            templates_mod.save_comments(comments)

        picked = self._show_template_window("댓글 불러오기", comments, delete_cb=on_delete,
                                            file_loader=templates_mod.read_template_file)
        if picked is not None:
            self.tpl_text_comment.delete("1.0", "end")
            self.tpl_text_comment.insert("1.0", picked)
            self._log("저장된 댓글 템플릿을 템플릿 탭 입력창에 불러왔습니다.", "success")

    def _apply_tpl_to_work(self):
        msg = self.tpl_text_neighbor_msg.get("1.0", "end").strip()
        cmt = self.tpl_text_comment.get("1.0", "end").strip()
        if msg:
            self.text_neighbor_msg.delete("1.0", "end")
            self.text_neighbor_msg.insert("1.0", msg)
        if cmt:
            self.text_comment.delete("1.0", "end")
            self.text_comment.insert("1.0", cmt)
        self._log("템플릿 탭의 메시지/댓글을 신청 탭 입력창에 적용했습니다.", "success")

    def _load_tpl_default_msg(self):
        defaults = templates_mod.DEFAULTS["neighbor_messages"]
        if defaults:
            self.tpl_text_neighbor_msg.delete("1.0", "end")
            self.tpl_text_neighbor_msg.insert("1.0", defaults[0])

    # ══════════════════════════════════════════════════════
    #  탭: 서로이웃 자동 신청
    # ══════════════════════════════════════════════════════
    def _build_work_tab(self, parent):
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # ── 왼쪽: 로그인 + 메시지 + 작업 옵션 (실행 버튼은 하단 고정 바) ──
        left = ctk.CTkScrollableFrame(parent, fg_color=BG_CARD, width=430,
                                      scrollbar_button_color=SCROLLBAR_BG)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        # ── 네이버 로그인 (탭2에 로그인 버튼은 이 하나뿐) ──
        ctk.CTkLabel(left, text="🔑 네이버 로그인 후 원스톱 작업", font=F(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(14, 2))

        login_row = ctk.CTkFrame(left, fg_color="transparent")
        login_row.pack(fill="x", padx=16, pady=(0, 4))

        self.login_status_label2 = ctk.CTkLabel(
            login_row, text="🔴 로그아웃", font=F(13, "bold"), text_color=RED,
        )
        self.login_status_label2.pack(side="left")

        # 아이디/비밀번호 입력 (메모리에서만 사용 — 저장하지 않음)
        # 주의: CTkEntry는 placeholder_text + show 조합 시 마스킹이 해제되는
        # 커스텀tkinter 동작이 있어, 비밀번호 필드에는 placeholder 대신 라벨을 사용한다.
        cred_row = ctk.CTkFrame(left, fg_color="transparent")
        cred_row.pack(fill="x", padx=16, pady=(2, 2))

        cred_id_cell = ctk.CTkFrame(cred_row, fg_color="transparent")
        cred_id_cell.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkLabel(cred_id_cell, text="네이버 아이디", font=F(10),
                     text_color=TEXT_GRAY, anchor="w").pack(anchor="w")
        self.entry_naver_id = ctk.CTkEntry(
            cred_id_cell, placeholder_text="아이디 입력", height=36,
            fg_color=BG_INPUT, border_color=PURPLE, border_width=2,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM, font=F(12),
        )
        self.entry_naver_id.pack(fill="x")

        cred_pw_cell = ctk.CTkFrame(cred_row, fg_color="transparent")
        cred_pw_cell.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(cred_pw_cell, text="비밀번호", font=F(10),
                     text_color=TEXT_GRAY, anchor="w").pack(anchor="w")
        self.entry_naver_pw = ctk.CTkEntry(
            cred_pw_cell, height=36, show="●",
            fg_color=BG_INPUT, border_color=PURPLE, border_width=2,
            text_color=TEXT_WHITE, font=F(12),
        )
        self.entry_naver_pw.pack(fill="x")

        # 단일 실행 버튼: 로그인 → 이웃신청 → 공감 → 댓글 원스톱
        self.btn_login_work = ctk.CTkButton(
            left, text="🚀  로그인 후 원스톱 작업 시작", font=F(14, "bold"),
            fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
            height=44, corner_radius=6, command=self._on_login_and_work,
        )
        self.btn_login_work.pack(fill="x", padx=16, pady=(6, 2))

        ctk.CTkLabel(left,
                     text="로그인 완료 즉시 서로이웃 신청 → 공감 → 댓글까지 자동 진행됩니다.\n"
                          "아이디/비밀번호는 프로그램에 저장되지 않습니다.",
                     font=F(10), text_color=CYAN, justify="left"
                     ).pack(anchor="w", padx=16, pady=(0, 8))

        # ── 서로이웃 신청 메시지 ──
        ctk.CTkLabel(left, text="✉️ 서로이웃 신청 메시지", font=F(14, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(8, 2))
        ctk.CTkLabel(left, text="여러 개를 저장하면 대상마다 랜덤으로 선택됩니다.",
                     font=F(10), text_color=TEXT_GRAY).pack(anchor="w", padx=16, pady=(0, 4))

        self.text_neighbor_msg = ctk.CTkTextbox(
            left, height=150, fg_color=BG_INPUT, border_color=BORDER,
            border_width=1, text_color=TEXT_WHITE, font=F(12),
            scrollbar_button_color=SCROLLBAR_BG,
        )
        self.text_neighbor_msg.pack(fill="x", padx=16, pady=(0, 4))
        default_msgs = templates_mod.get_neighbor_messages()
        if default_msgs:
            self.text_neighbor_msg.insert("1.0", default_msgs[0])

        msg_btn_row = ctk.CTkFrame(left, fg_color="transparent")
        msg_btn_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkButton(msg_btn_row, text="💾 메시지 저장", font=F(11), height=30,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=self._save_neighbor_template).pack(side="left", padx=(0, 5))
        ctk.CTkButton(msg_btn_row, text="📋 저장 목록", font=F(11), height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._show_neighbor_templates).pack(side="left", padx=(0, 5))
        ctk.CTkButton(msg_btn_row, text="👁 미리보기", font=F(11), height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._preview_neighbor_msg).pack(side="left")
        ctk.CTkButton(msg_btn_row, text="기본 메시지", font=F(11), height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_GRAY,
                      command=self._load_default_msg).pack(side="right")

        # ── 댓글 (옵션) ──
        ctk.CTkLabel(left, text="💬 댓글 (댓글 작업 선택 시 사용)", font=F(14, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(6, 2))

        self.text_comment = ctk.CTkTextbox(
            left, height=100, fg_color=BG_INPUT, border_color=BORDER,
            border_width=1, text_color=TEXT_WHITE, font=F(12),
            scrollbar_button_color=SCROLLBAR_BG,
        )
        self.text_comment.pack(fill="x", padx=16, pady=(0, 4))
        default_comments = templates_mod.get_comments()
        if default_comments:
            self.text_comment.insert("1.0", default_comments[0])

        c_btn_row = ctk.CTkFrame(left, fg_color="transparent")
        c_btn_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkButton(c_btn_row, text="💾 템플릿 저장", font=F(11), height=30,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=self._save_comment_template).pack(side="left", padx=(0, 5))
        ctk.CTkButton(c_btn_row, text="📋 템플릿 목록", font=F(11), height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=self._show_comment_templates).pack(side="left")

        # ── 작업 옵션 ──
        ctk.CTkLabel(left, text="⚙️ 작업 옵션", font=F(14, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(8, 2))

        self.opt_neighbor = ctk.BooleanVar(value=True)
        self.opt_like = ctk.BooleanVar(value=False)
        self.opt_comment = ctk.BooleanVar(value=False)

        opt_row = ctk.CTkFrame(left, fg_color="transparent")
        opt_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkCheckBox(opt_row, text="서로이웃 신청", variable=self.opt_neighbor,
                        font=F(12), fg_color=PURPLE, hover_color=PURPLE_HOVER,
                        checkmark_color="white").pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(opt_row, text="공감", variable=self.opt_like,
                        font=F(12), fg_color=PURPLE, hover_color=PURPLE_HOVER,
                        checkmark_color="white").pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(opt_row, text="댓글", variable=self.opt_comment,
                        font=F(12), fg_color=PURPLE, hover_color=PURPLE_HOVER,
                        checkmark_color="white").pack(side="left")

        self.var_confirm = ctk.BooleanVar(value=self.settings.get("confirm_before_work", True))
        ctk.CTkCheckBox(left, text="작업 전 확인창 표시 (권장)", variable=self.var_confirm,
                        font=F(11), fg_color=PURPLE, hover_color=PURPLE_HOVER,
                        checkmark_color="white").pack(anchor="w", padx=16, pady=(2, 4))

        # 대기 시간 + 작업 속도 설정
        delay_row = ctk.CTkFrame(left, fg_color="transparent")
        delay_row.pack(fill="x", padx=16, pady=(4, 2))

        ctk.CTkLabel(delay_row, text="작업 간 대기:", font=F(11),
                     text_color=TEXT_GRAY).pack(side="left")
        self.entry_pause_min = ctk.CTkEntry(delay_row, width=55, height=28,
                                            fg_color=BG_INPUT, border_color=BORDER,
                                            text_color=TEXT_WHITE, justify="center", font=F(11))
        self.entry_pause_min.insert(0, str(self.settings.get("pause_min", 30)))
        self.entry_pause_min.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(delay_row, text="~", font=F(11), text_color=TEXT_DIM).pack(side="left")
        self.entry_pause_max = ctk.CTkEntry(delay_row, width=55, height=28,
                                            fg_color=BG_INPUT, border_color=BORDER,
                                            text_color=TEXT_WHITE, justify="center", font=F(11))
        self.entry_pause_max.insert(0, str(self.settings.get("pause_max", 90)))
        self.entry_pause_max.pack(side="left", padx=(2, 4))
        ctk.CTkLabel(delay_row, text="(랜덤)", font=F(11), text_color=TEXT_DIM).pack(side="left")

        # 작업 속도: 타이핑/클릭 사이 기본 딜레이 배율 (0.5=빠름 ~ 2.0=느림)
        speed_row = ctk.CTkFrame(left, fg_color="transparent")
        speed_row.pack(fill="x", padx=16, pady=(2, 2))

        ctk.CTkLabel(speed_row, text="작업 속도:", font=F(11),
                     text_color=TEXT_GRAY).pack(side="left")
        self.entry_speed_min = ctk.CTkEntry(speed_row, width=50, height=28,
                                            fg_color=BG_INPUT, border_color=BORDER,
                                            text_color=TEXT_WHITE, justify="center", font=F(11))
        self.entry_speed_min.insert(0, str(self.settings.get("speed_min", 0.5)))
        self.entry_speed_min.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(speed_row, text="~", font=F(11), text_color=TEXT_DIM).pack(side="left")
        self.entry_speed_max = ctk.CTkEntry(speed_row, width=50, height=28,
                                            fg_color=BG_INPUT, border_color=BORDER,
                                            text_color=TEXT_WHITE, justify="center", font=F(11))
        self.entry_speed_max.insert(0, str(self.settings.get("speed_max", 1.0)))
        self.entry_speed_max.pack(side="left", padx=(2, 4))
        ctk.CTkLabel(speed_row, text="배 (1.0=사람 속도, 작을수록 빠름)", font=F(11),
                     text_color=TEXT_DIM).pack(side="left")

        unit_row = ctk.CTkFrame(left, fg_color="transparent")
        unit_row.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(unit_row, text="단위:", font=F(11),
                     text_color=TEXT_GRAY).pack(side="left")
        self.var_pause_unit = ctk.StringVar(value=self.settings.get("pause_unit", "초"))
        ctk.CTkRadioButton(unit_row, text="초 단위", variable=self.var_pause_unit,
                           value="초", font=F(11), fg_color=PURPLE,
                           hover_color=PURPLE_HOVER,
                           command=self._on_pause_unit_change).pack(side="left", padx=(6, 8))
        ctk.CTkRadioButton(unit_row, text="분 단위", variable=self.var_pause_unit,
                           value="분", font=F(11), fg_color=PURPLE,
                           hover_color=PURPLE_HOVER,
                           command=self._on_pause_unit_change).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(unit_row, text="시간 단위", variable=self.var_pause_unit,
                           value="시간", font=F(11), fg_color=PURPLE,
                           hover_color=PURPLE_HOVER,
                           command=self._on_pause_unit_change).pack(side="left")
        ctk.CTkLabel(unit_row, text="(선택 단위로 위 값이 해석됩니다: 초/분/시간)", font=F(10),
                     text_color=TEXT_DIM).pack(side="left", padx=(8, 0))

        # 실행 컨트롤(작업 시작/일시정지/재개/중지)은 탭 하단 고정 바로 이동 —
        # 스크롤과 무관하게 항상 보이도록 함

        # ── 오른쪽: 전송된 작업 대상 목록 ──
        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew")

        list_header = ctk.CTkFrame(right, fg_color="transparent")
        list_header.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(list_header, text="작업 대상 목록 (탭1에서 전송됨)",
                     font=F(14, "bold"), text_color=TEXT_WHITE).pack(side="left")

        self.work_count_label = ctk.CTkLabel(
            list_header, text="선택 대상: 0명", font=F(13, "bold"), text_color=CYAN,
        )
        self.work_count_label.pack(side="right")

        w_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        w_btn_row.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkButton(w_btn_row, text="☑ 전체 선택", font=F(11), width=90, height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=lambda: self._select_all_work(True)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(w_btn_row, text="☐ 전체 해제", font=F(11), width=90, height=30,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=lambda: self._select_all_work(False)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(w_btn_row, text="🚫 이전 처리 대상 제외", font=F(11), width=150, height=30,
                      fg_color=BG_INPUT, hover_color=RED, text_color=TEXT_GRAY,
                      command=self._exclude_processed).pack(side="right")

        # 작업 대상 테이블
        w_table_frame = ctk.CTkFrame(right, fg_color="transparent")
        w_table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        columns = ("sel", "no", "blog_name", "blog_id", "open_date",
                   "neighbors", "work_status")
        self.work_tree = ttk.Treeview(w_table_frame, columns=columns, show="headings",
                                      style="Custom.Treeview", selectmode="none")
        w_col_config = [
            ("sel", "선택", 46),
            ("no", "#", 38),
            ("blog_name", "블로그명", 200),
            ("blog_id", "블로그 ID", 130),
            ("open_date", "개설일", 80),
            ("neighbors", "이웃수", 70),
            ("work_status", "작업 상태", 170),
        ]
        for col_id, heading, width in w_col_config:
            self.work_tree.heading(col_id, text=heading, anchor="center")
            self.work_tree.column(col_id, width=width, minwidth=44, anchor="center")

        w_vsb = ttk.Scrollbar(w_table_frame, orient="vertical",
                              command=self.work_tree.yview, style="Custom.Vertical.TScrollbar")
        self.work_tree.configure(yscrollcommand=w_vsb.set)
        self.work_tree.grid(row=0, column=0, sticky="nsew")
        w_vsb.grid(row=0, column=1, sticky="ns")
        w_table_frame.grid_rowconfigure(0, weight=1)
        w_table_frame.grid_columnconfigure(0, weight=1)

        self.work_tree.tag_configure("even", background=BG_TABLE_ROW)
        self.work_tree.tag_configure("odd", background="#11161d")
        self.work_tree.tag_configure("done", foreground=GREEN_LIGHT)
        self.work_tree.tag_configure("fail", foreground=RED)
        self.work_tree.tag_configure("doing", foreground=CYAN)
        self.work_tree.tag_configure("skip", foreground=TEXT_DIM)

        self.work_tree.bind("<Button-1>", self._on_work_tree_click)
        self._insert_empty_work("탭1에서 대상을 전송하세요.")

        # ── 하단 고정 실행 컨트롤 바 (스크롤과 무관하게 항상 표시) ──
        work_ctrl_bar = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8, height=58)
        work_ctrl_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        work_ctrl_bar.pack_propagate(False)

        # 작업시작 버튼 없음 — [로그인 후 원스톱 작업 시작] 버튼 하나로 로그인과
        # 작업이 동시에 시작되며, 진행 중에는 일시정지/재개/중지만 사용한다.
        self.btn_pause = ctk.CTkButton(
            work_ctrl_bar, text="🟡 일시정지", font=F(12, "bold"),
            fg_color="#3d2e00", hover_color="#57420a", border_color=YELLOW, border_width=2,
            text_color=YELLOW, width=104, height=40, corner_radius=6,
            state="disabled", command=self._on_pause,
        )
        self.btn_pause.pack(side="left", padx=(14, 6), pady=9)

        self.btn_resume = ctk.CTkButton(
            work_ctrl_bar, text="🟢 재개", font=F(12, "bold"),
            fg_color="#0d2a14", hover_color="#145224", border_color=GREEN_LIGHT, border_width=2,
            text_color=GREEN_LIGHT, width=90, height=40, corner_radius=6,
            state="disabled", command=self._on_resume,
        )
        self.btn_resume.pack(side="left", padx=(0, 6), pady=9)

        self.btn_work_stop = ctk.CTkButton(
            work_ctrl_bar, text="🔴 중지", font=F(12, "bold"),
            fg_color="#3d1212", hover_color="#571c1c", border_color=RED, border_width=2,
            text_color=RED, width=90, height=40, corner_radius=6,
            state="disabled", command=self._on_work_stop,
        )
        self.btn_work_stop.pack(side="left", padx=(0, 6), pady=9)

        # ── 작업 간 대기시간 빠른 설정 (컨트롤 바 안 — [초]후 작업 / [분]후 작업) ──
        ctk.CTkLabel(work_ctrl_bar, text="⏳ 작업 간 대기:", font=F(11, "bold"),
                     text_color=TEXT_GRAY).pack(side="left", padx=(10, 4))

        ctk.CTkLabel(work_ctrl_bar, text="[초]", font=F(10),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, 2))
        self.entry_ctrl_pause_sec = ctk.CTkEntry(
            work_ctrl_bar, width=52, height=30, fg_color=BG_INPUT,
            border_color=BORDER, text_color=TEXT_WHITE, justify="center", font=F(11),
        )
        self.entry_ctrl_pause_sec.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(work_ctrl_bar, text="[분]", font=F(10),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, 2))
        self.entry_ctrl_pause_min = ctk.CTkEntry(
            work_ctrl_bar, width=52, height=30, fg_color=BG_INPUT,
            border_color=BORDER, text_color=TEXT_WHITE, justify="center", font=F(11),
        )
        self.entry_ctrl_pause_min.pack(side="left", padx=(0, 6))

        self.btn_ctrl_pause_save = ctk.CTkButton(
            work_ctrl_bar, text="💾 저장", font=F(11, "bold"), height=30,
            fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
            width=64, corner_radius=6, command=self._on_ctrl_pause_save,
        )
        self.btn_ctrl_pause_save.pack(side="left", padx=(0, 8))

        # 저장된 대기시간 값을 입력칸에 표시 (초 단위 기준 → [초] 칸에 표시)
        try:
            saved_unit = self.settings.get("pause_unit", "초")
            saved_lo = int(float(self.settings.get("pause_min", 30)))
            if saved_unit == "분":
                self.entry_ctrl_pause_min.insert(0, str(saved_lo))
            else:
                self.entry_ctrl_pause_sec.insert(0, str(saved_lo))
        except Exception:
            self.entry_ctrl_pause_sec.insert(0, "30")

        # 오류 일시정지 알림 (컨트롤 바 오른쪽에 표시)
        self.pause_notice_frame = ctk.CTkFrame(work_ctrl_bar, fg_color="#3d1d1d", corner_radius=6)
        self.pause_notice_label = ctk.CTkLabel(
            self.pause_notice_frame, text="", font=F(11, "bold"), text_color=RED,
            justify="left", wraplength=430,
        )
        self.pause_notice_label.pack(side="left", padx=(10, 8), pady=6)

        self.btn_recheck = ctk.CTkButton(
            self.pause_notice_frame, text="🔄 다시 확인 (인증 완료 후 클릭)",
            font=F(11, "bold"), fg_color=PURPLE, hover_color=PURPLE_HOVER,
            text_color="white", height=34, corner_radius=6, command=self._on_recheck_after_auth,
        )
        self.btn_recheck.pack(side="left", padx=(0, 10), pady=6)
        self.pause_notice_frame.pack_forget()

    def _insert_empty_work(self, msg):
        for item in self.work_tree.get_children():
            self.work_tree.delete(item)
        self.work_tree.insert("", "end", values=("", "", msg, "", "", "", ""),
                              tags=("even",))

    # ── 작업 대상 테이블 ──────────────────────────────────
    def _populate_work_tree(self):
        for item in self.work_tree.get_children():
            self.work_tree.delete(item)
        self._tab2_row_map = {}

        if not self.work_targets:
            self._insert_empty_work("탭1에서 대상을 전송하세요.")
            self.work_count_label.configure(text="선택 대상: 0명")
            return

        for i, t in enumerate(self.work_targets):
            bid = t.get("blog_id", "")
            sel_text = "☑" if bid in self.work_selected_ids else "☐"
            status = self.work_status_map.get(bid, "🟡 대기")
            tag = "even"
            if "완료" in status:
                tag = "done"
            elif "실패" in status:
                tag = "fail"
            elif "진행" in status:
                tag = "doing"

            open_year = t.get("blog_open_year", 0)
            open_text = f"{open_year}년" if open_year else "-"

            iid = self.work_tree.insert("", "end", values=(
                sel_text, i + 1, t.get("blog_name", "-"), bid,
                open_text, t.get("neighbor_count", 0), status,
            ), tags=(("odd" if i % 2 else "even"), tag))
            self._tab2_row_map[bid] = iid

        self._update_work_selected_count()

    def _update_work_selected_count(self):
        self.work_count_label.configure(text=f"선택 대상: {len(self.work_selected_ids)}명")

    def _on_work_tree_click(self, event):
        region = self.work_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        if self.work_tree.identify_column(event.x) != "#1":
            return
        item = self.work_tree.identify_row(event.y)
        if not item:
            return
        values = self.work_tree.item(item, "values")
        if len(values) < 4 or not values[3]:
            return
        bid = values[3]
        if bid in self.work_selected_ids:
            self.work_selected_ids.discard(bid)
            self.work_tree.set(item, column="sel", value="☐")
        else:
            self.work_selected_ids.add(bid)
            self.work_tree.set(item, column="sel", value="☑")
        self._update_work_selected_count()

    def _select_all_work(self, select: bool):
        if select:
            for t in self.work_targets:
                self.work_selected_ids.add(t.get("blog_id", ""))
        else:
            self.work_selected_ids.clear()
        self._populate_work_tree()

    def _exclude_processed(self):
        """이전에 성공 처리한 대상을 선택에서 제외 (중복 작업 방지)"""
        removed = 0
        for bid in list(self.work_selected_ids):
            last = work_history.get_blog_last_status(bid)
            if last and last["status"] == "success":
                self.work_selected_ids.discard(bid)
                removed += 1
        self._populate_work_tree()
        self._log(f"이전에 성공 처리한 {removed}명을 선택에서 제외했습니다.", "info")

    def _set_work_row_status(self, blog_id, status_text, tag):
        """작업 중 대상 행의 상태 갱신"""
        self.work_status_map[blog_id] = status_text
        iid = self._tab2_row_map.get(blog_id)
        if iid:
            try:
                self.work_tree.set(iid, column="work_status", value=status_text)
                base_tag = "odd" if int(self.work_tree.index(iid)) % 2 else "even"
                self.work_tree.item(iid, tags=(base_tag, tag))
            except Exception:
                pass

    def _get_work_targets(self):
        return [t for t in self.work_targets if t.get("blog_id") in self.work_selected_ids]

    # ── 메시지 템플릿 관련 ────────────────────────────────
    def _save_neighbor_template(self):
        msg = self.text_neighbor_msg.get("1.0", "end").strip()
        if not msg:
            messagebox.showwarning("입력 필요", "메시지를 입력하세요.")
            return
        templates_mod.add_neighbor_message(msg)
        self._log("신청 메시지가 템플릿에 저장되었습니다.", "success")
        messagebox.showinfo("저장 완료", "메시지가 저장되었습니다.\n여러 개를 저장하면 대상마다 랜덤으로 선택됩니다.")

    def _show_template_window(self, title, items, delete_cb=None, file_loader=None):
        """템플릿 목록 공통 창 (삭제 전용) — Returns: 선택된 항목 또는 None
        file_loader가 주어지면 [📁 파일 첨부] 버튼으로 메모장/엑셀 파일에서 불러올 수 있다."""
        result = {"selected": None}

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("560x420")
        win.configure(fg_color=BG_DARK)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text=title, font=F(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=16, pady=(14, 6))

        listbox = tk.Listbox(win, bg=BG_INPUT, fg=TEXT_WHITE, font=(FONT_FAMILY, 11),
                             selectbackground=PURPLE, height=12)
        listbox.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        for i, m in enumerate(items):
            listbox.insert("end", f"[{i+1}] {m[:60]}")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        def select_item():
            sel = listbox.curselection()
            if sel:
                result["selected"] = items[sel[0]]
                win.destroy()

        def delete_selected():
            sel = listbox.curselection()
            if sel:
                on_delete_idx = sel[0]
                if delete_cb:
                    delete_cb(on_delete_idx)
                listbox.delete(on_delete_idx)

        ctk.CTkButton(btn_row, text="선택", font=F(12), height=36,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=select_item).pack(side="left", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_row, text="삭제", font=F(12), height=36,
                      fg_color=RED, hover_color="#da3633", text_color="white",
                      command=delete_selected).pack(side="left", expand=True, padx=(0, 6))

        if file_loader:
            def attach_file():
                path = filedialog.askopenfilename(
                    title="템플릿 파일 선택",
                    filetypes=[
                        ("지원 파일 (메모장/엑셀)", "*.txt *.md *.log *.xlsx *.xlsm"),
                        ("메모장", "*.txt *.md *.log"),
                        ("엑셀", "*.xlsx *.xlsm"),
                        ("모든 파일", "*.*"),
                    ],
                )
                if not path:
                    return
                try:
                    text = file_loader(path)
                except Exception as e:
                    messagebox.showerror("파일 불러오기 실패", f"파일을 읽을 수 없습니다:\n{e}")
                    return
                if not text or not text.strip():
                    messagebox.showwarning("파일 비어 있음", "선택한 파일에 내용이 없습니다.")
                    return
                result["selected"] = text
                win.destroy()

            ctk.CTkButton(btn_row, text="📁 파일 첨부", font=F(12), height=36,
                          fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                          command=attach_file).pack(side="left", expand=True)

        win.delete_callback = delete_cb
        win.wait_window()
        return result["selected"]

    def _show_neighbor_templates(self):
        msgs = templates_mod.get_neighbor_messages()
        if not msgs:
            messagebox.showinfo("저장 목록", "저장된 메시지가 없습니다.")
            return

        def on_delete(idx):
            msgs.pop(idx)
            templates_mod.save_neighbor_messages(msgs)
            self._log("템플릿 메시지를 삭제했습니다.", "info")

        self._show_template_window("저장된 신청 메시지", msgs, delete_cb=on_delete)

    def _show_comment_templates(self):
        comments = templates_mod.get_comments()
        if not comments:
            messagebox.showinfo("저장 목록", "저장된 댓글 템플릿이 없습니다.")
            return

        def on_delete(idx):
            comments.pop(idx)
            templates_mod.save_comments(comments)

        self._show_template_window("저장된 댓글 템플릿", comments, delete_cb=on_delete)

    def _preview_neighbor_msg(self):
        msg = self.text_neighbor_msg.get("1.0", "end").strip()
        if not msg:
            messagebox.showinfo("미리보기", "입력된 메시지가 없습니다.")
            return
        win = ctk.CTkToplevel(self)
        win.title("메시지 미리보기")
        win.geometry("460x300")
        win.configure(fg_color=BG_DARK)
        win.transient(self)
        ctk.CTkLabel(win, text="📡 상대 블로그에 표시될 메시지", font=F(13, "bold"),
                     text_color=CYAN).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(win, text=msg, font=F(12), text_color=TEXT_WHITE,
                     justify="left", wraplength=400).pack(anchor="w", padx=16, pady=(0, 10))

    def _load_default_msg(self):
        defaults = templates_mod.DEFAULTS["neighbor_messages"]
        if defaults:
            self.text_neighbor_msg.delete("1.0", "end")
            self.text_neighbor_msg.insert("1.0", defaults[0])

    def _save_comment_template(self):
        comment = self.text_comment.get("1.0", "end").strip()
        if not comment:
            messagebox.showwarning("입력 필요", "댓글을 입력하세요.")
            return
        templates_mod.add_comment(comment)
        self._log("댓글 템플릿이 저장되었습니다.", "success")
        messagebox.showinfo("저장 완료", "댓글 템플릿이 저장되었습니다.")

    # ══════════════════════════════════════════════════════
    #  [v3.4 신규] 라이센스 키 인증 / 사용 기간 제어
    # ══════════════════════════════════════════════════════
    def _check_license_on_start(self):
        """프로그램 시작 시 저장된 라이센스 재확인.
        인증 성공 → 전체 기능 사용 가능
        만료/무효 → 인증창 열고, 취소 시 프로그램 종료"""
        state = license_mod.check_saved_license()
        if state == "ok":
            self.license_authorized = True
            expiry_txt = license_mod.get_expiry_text()
            self._log(f"🔑 라이센스 인증 완료 — 사용 기한: {expiry_txt} 까지", "success")
            return

        if state == "expired":
            self._log("라이센스 기간이 만료되었거나 유효하지 않은 키입니다. 키를 재발급 받아주세요.", "error")
        else:
            self._log("유효한 라이센스 키가 등록되지 않았습니다. 키를 입력해 인증하세요.", "info")
        self._show_license_dialog(on_cancel_exit=True)

    def _activate_license(self, key: str) -> bool:
        """입력된 키 검증 → 성공 시 license.json 기록. 실패 시 LicenseError 전파"""
        expiry = license_mod.validate_key(key)   # 실패 시 LicenseError 발생
        license_mod._write_state((key or "").strip().upper(), expiry, device_note="1")
        self.license_authorized = True
        self._log(f"🔑 라이센스 인증 성공 — 사용 기한: {license_mod.get_expiry_text()} 까지", "success")
        return True

    def _show_license_dialog(self, on_cancel_exit: bool = False):
        """라이센스 키 입력 인증창 (기존 디자인 톤앤매너 유지)"""
        self._log("🔑 라이센스 인증창을 엽니다.", "info")

        win = ctk.CTkToplevel(self)
        win.title("🔑 라이센스 인증")
        win.geometry("480x350")
        win.configure(fg_color=BG_DARK)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="🔑 라이센스 인증", font=F(19, "bold"),
                     text_color=PURPLE_HOVER).pack(anchor="w", padx=26, pady=(20, 4))
        ctk.CTkLabel(
            win,
            text="관리자가 발급한 라이센스 키를 입력하세요.\n"
                 "기한이 남아 있는 키만 사용할 수 있습니다.",
            font=F(12), text_color=TEXT_GRAY, justify="left",
        ).pack(anchor="w", padx=26, pady=(0, 10))

        entry_key = ctk.CTkEntry(
            win, placeholder_text="BLOGGENIUS-YYYYMMDDHHMM-XXXXXX", height=40,
            fg_color=BG_INPUT, border_color=PURPLE, border_width=2,
            text_color=TEXT_WHITE, placeholder_text_color=TEXT_DIM, font=F(12),
            width=360,
        )
        entry_key.pack(padx=26, pady=(4, 8))

        msg_label = ctk.CTkLabel(win, text="", font=F(12), text_color=RED,
                                 justify="left", wraplength=400)
        msg_label.pack(anchor="w", padx=26, pady=(0, 8))

        # 만료 상태 안내 문구 표시
        state = license_mod.check_saved_license()
        if state == "expired":
            msg_label.configure(
                text="⚠️ 라이센스 기간이 만료되었거나 유효하지 않은 키입니다.\n"
                     "   키를 재발급 받아주세요.", text_color=YELLOW)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=26, pady=(6, 18))

        def confirm():
            key = entry_key.get().strip()
            try:
                self._activate_license(key)
            except license_mod.LicenseError as e:
                msg_label.configure(
                    text=f"⚠️ 라이센스 기간이 만료되었거나 유효하지 않은 키입니다.\n"
                         f"   키를 재발급 받아주세요.\n({e})",
                    text_color=RED)
                return
            win.destroy()

        def cancel():
            win.destroy()
            if not self.license_authorized:
                if on_cancel_exit:
                    self._log("라이센스 인증 취소 — 프로그램을 종료합니다.", "warning")
                    self._on_exit_program()

        ctk.CTkButton(btn_row, text="✔ 인증 확인", font=F(13, "bold"), height=42,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=confirm).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(btn_row, text="취소", font=F(13, "bold"), height=42,
                      fg_color=BG_INPUT, hover_color=RED, text_color=TEXT_WHITE,
                      command=cancel).pack(side="left", expand=True, fill="x")

        win.wait_window()
        return self.license_authorized

    def _ensure_licensed(self) -> bool:
        """기능 실행 전 라이센스 상태 확인. 미인증/만료 시 인증창을 열고 차단한다."""
        state = license_mod.check_saved_license()
        if state == "ok":
            self.license_authorized = True
            return True

        self.license_authorized = False
        msg = ("라이센스 기간이 만료되었거나 유효하지 않은 키입니다.\n"
               "키를 재발급 받아주세요.")
        self._log(msg.replace("\n", " "), "error")
        messagebox.showwarning("라이센스 만료/무효", msg)
        self._show_license_dialog(on_cancel_exit=False)
        # 인증창에서 인증에 성공했으면 허용
        return self.license_authorized

    # ══════════════════════════════════════════════════════
    #  로그인 상태 표시/처리
    # ══════════════════════════════════════════════════════
    def _set_login_indicator(self, state: str):
        self.login_state = state
        if state == "in":
            text, color = "🟢 네이버 로그인 완료", GREEN_LIGHT
        elif state == "checking":
            text, color = "🟡 로그인 확인 중", YELLOW
        else:
            text, color = "🔴 로그아웃", RED

        self.login_status_label.configure(text=text, text_color=color)
        self.login_status_label2.configure(text=text, text_color=color)
        self.btn_logout.configure(state="normal" if state == "in" and not self.is_running else "disabled")

    # ══════════════════════════════════════════════════════
    #  원스톱 실행: 로그인 → 이웃신청 → 공감 → 댓글
    # ══════════════════════════════════════════════════════
    def _on_login_and_work(self):
        """단일 실행 버튼 — 로그인 완료 즉시 서로이웃 신청/공감/댓글까지 자동 진행"""
        if self.is_running:
            messagebox.showinfo("알림", "이미 작업이 진행 중입니다.")
            return

        # ── [v3.4 신규] 라이센스 인증 확인 (만료/무효 시 사용 차단) ──
        if not self._ensure_licensed():
            self._log("라이센스 인증 실패 — 원스톱 작업이 차단되었습니다.", "warning")
            return

        targets = self._get_work_targets()
        if not targets:
            messagebox.showwarning("대상 없음",
                                   "작업 대상이 없습니다.\n탭1에서 대상을 수집하고 [신청 탭으로 전송]하세요.")
            return

        msg_text = self.text_neighbor_msg.get("1.0", "end").strip()
        comment_text = self.text_comment.get("1.0", "end").strip()
        if not msg_text:
            messagebox.showwarning("메시지 필요", "서로이웃 신청 메시지를 입력하세요.")
            return

        # 로그인이 필요하면 아이디/비밀번호 확인 (저장하지 않고 메모리에서만 사용)
        naver_id = self.entry_naver_id.get().strip()
        naver_pw = self.entry_naver_pw.get()
        if self.login_state != "in" and (not naver_id or not naver_pw):
            messagebox.showwarning("입력 필요",
                                   "네이버 아이디와 비밀번호를 입력하세요.\n"
                                   "이미 로그인된 상태라면 입력 없이 바로 진행됩니다.")
            return

        # 대기시간 유효성
        try:
            pause_min = max(5, int(self.entry_pause_min.get() or 30))
            pause_max = max(pause_min, int(self.entry_pause_max.get() or 90))
        except ValueError:
            messagebox.showwarning("입력 오류", "대기 시간은 숫자로 입력하세요.")
            return

        self.settings["pause_min"] = pause_min
        self.settings["pause_max"] = pause_max
        self.settings["pause_unit"] = self.var_pause_unit.get()
        try:
            self.settings["speed_min"] = float(self.entry_speed_min.get() or 0.5)
            self.settings["speed_max"] = float(self.entry_speed_max.get() or 1.0)
        except ValueError:
            self.settings["speed_min"], self.settings["speed_max"] = 0.5, 1.0
        self.settings["confirm_before_work"] = self.var_confirm.get()
        settings_mod.save(self.settings)

        # 대기 시간/속도 저장
        self._pause_delay = self._get_pause_delay_seconds()
        self._speed_factor = self._get_speed_factor()
        self.automator.set_speed_factor(random.uniform(*self._speed_factor))
        self._log(f"작업 속도: {self._speed_factor[0]}~{self._speed_factor[1]}배, "
                  f"대기: {self._pause_delay[0]:.0f}~{self._pause_delay[1]:.0f}초", "info")

        # 환경설정: 작업 전 확인 여부 (확인창에서 메시지 수정 가능)
        if self.var_confirm.get():
            confirmed, msg_text = self._show_confirm_dialog(targets, msg_text)
            if not confirmed:
                self._log("사용자가 작업을 취소했습니다.", "warning")
                return
            msg_text = msg_text.strip()

        # 원스톱 시작
        self.is_running = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()
        self.btn_login_work.configure(state="disabled", text="⏳ 로그인 및 작업 진행 중...")
        self.btn_pause.configure(state="normal")
        self.btn_work_stop.configure(state="normal")
        self.btn_logout.configure(state="disabled")
        self._log(f"═══ 원스톱 작업 시작: {len(targets)}명 "
                  f"(1.서로이웃신청 메시지발송 → 2.공감(하트)클릭 → 3.댓글작성 고정 순서) ═══",
                  "system")

        self._work_thread = threading.Thread(
            target=self._work_worker,
            args=(targets, msg_text, comment_text, naver_id, naver_pw),
            daemon=True,
        )
        self._work_thread.start()

    def _on_logout(self):
        """로그아웃 — 세션 삭제 (비밀번호는 애초에 저장하지 않음)"""
        self._log("로그아웃: 브라우저 세션을 삭제합니다.", "info")
        threading.Thread(target=self._logout_worker, daemon=True).start()

    def _logout_worker(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.automator.logout())
        except Exception as e:
            self._ui_log(f"로그아웃 오류: {e}", "error")
        self.after(0, self._set_login_indicator, "out")
        self.after(0, lambda: self._log("로그아웃 완료.", "info"))

    def _show_confirm_dialog(self, targets, msg_text) -> tuple:
        """작업 전 최종 확인 화면 — 메시지를 직접 수정할 수 있음.
        Returns: (확인 여부, 수정된 메시지)"""
        confirmed = {"ok": False}
        edited_msg = {"text": msg_text}

        win = ctk.CTkToplevel(self)
        win.title("작업 전 최종 확인")
        win.geometry("520x560")
        win.configure(fg_color=BG_DARK)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="⚠️  작업 전 최종 확인", font=F(17, "bold"),
                     text_color=YELLOW).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(win, text=f"신청 예정 대상: 총 {len(targets)}명",
                     font=F(13, "bold"), text_color=TEXT_WHITE).pack(anchor="w", padx=20, pady=(6, 4))

        list_text = ctk.CTkTextbox(win, height=170, fg_color=BG_INPUT, border_color=BORDER,
                                   border_width=1, text_color=TEXT_WHITE, font=F(12))
        list_text.pack(fill="x", padx=20, pady=(0, 8))
        lines = [f"{i}. {t.get('blog_name', '-')} ({t.get('blog_id', '-')})"
                 for i, t in enumerate(targets, 1)]
        list_text.insert("1.0", "\n".join(lines))
        list_text.configure(state="disabled")

        ctk.CTkLabel(win, text="사용할 메시지 (✏️ 이 창에서 직접 수정할 수 있습니다):",
                     font=F(12), text_color=TEXT_GRAY).pack(anchor="w", padx=20)
        msg_box = ctk.CTkTextbox(win, height=100, fg_color=BG_INPUT, border_color=PURPLE,
                                 border_width=2, text_color=CYAN, font=F(11))
        msg_box.pack(fill="x", padx=20, pady=(4, 8))
        if msg_text:
            msg_box.insert("1.0", msg_text)

        opts = ["1. 서로이웃 신청 메시지 발송", "2. 공감(하트) 클릭", "3. 댓글 작성"]
        ctk.CTkLabel(win, text="수행 작업: " + " → ".join(opts),
                     font=F(12, "bold"), text_color=PURPLE_HOVER).pack(anchor="w", padx=20, pady=(0, 10))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(btn_row, text="취소", font=F(13, "bold"), height=42,
                      fg_color=BG_INPUT, hover_color=RED, text_color=TEXT_WHITE,
                      command=win.destroy).pack(side="left", expand=True, fill="x", padx=(0, 6))

        def confirm():
            confirmed["ok"] = True
            edited_msg["text"] = msg_box.get("1.0", "end").strip()
            win.destroy()

        ctk.CTkButton(btn_row, text="✔ 선택 대상 확인 후 신청", font=F(13, "bold"), height=42,
                      fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white",
                      command=confirm).pack(side="left", expand=True, fill="x")

        win.wait_window()
        return confirmed["ok"], edited_msg["text"]

    # ── 일시정지/재개/중지 ────────────────────────────────
    def _on_pause(self):
        self.is_paused = True
        self.pause_event.clear()
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="normal")
        self._log("🟡 작업 일시정지 — 현재 작업이 끝난 후 다음 대상으로 진행하지 않습니다.", "pause")

    def _on_resume(self):
        self.is_paused = False
        self.pause_event.set()
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")
        self._log("🟢 작업 재개", "success")

    def _on_work_stop(self):
        self.stop_event.set()
        self.pause_event.set()
        self._log("🔴 작업 중지 요청 — 현재 작업 완료 후 중지됩니다.", "warning")

    def _on_ctrl_pause_save(self):
        """컨트롤 바의 [초]후 작업 / [분]후 작업 입력값을 대기시간 설정에 저장.
        두 칸 중 값이 입력된 쪽을 우선 적용하고 (둘 다면 분 우선),
        왼쪽 패널의 대기시간/단위 라디오버튼에도 동기화한다."""
        sec_raw = self.entry_ctrl_pause_sec.get().strip()
        min_raw = self.entry_ctrl_pause_min.get().strip()

        try:
            if min_raw:  # 분 단위 우선
                val = max(1, int(min_raw))
                lo = hi = val * 60
                unit = "분"
                self.entry_pause_min.delete(0, "end")
                self.entry_pause_min.insert(0, str(val))
                self.entry_pause_max.delete(0, "end")
                self.entry_pause_max.insert(0, str(val))
            elif sec_raw:
                val = max(5, int(sec_raw))
                lo = hi = val
                unit = "초"
                self.entry_pause_min.delete(0, "end")
                self.entry_pause_min.insert(0, str(val))
                self.entry_pause_max.delete(0, "end")
                self.entry_pause_max.insert(0, str(val))
            else:
                messagebox.showwarning("입력 필요", "[초] 또는 [분] 칸에 대기 시간을 입력하세요.")
                return
        except ValueError:
            messagebox.showwarning("입력 오류", "대기 시간은 숫자로 입력하세요.")
            return

        self.var_pause_unit.set(unit)
        self.settings["pause_min"] = lo
        self.settings["pause_max"] = hi
        self.settings["pause_unit"] = unit
        settings_mod.save(self.settings)
        # 진행 중인 작업 루프에도 즉시 반영
        self._pause_delay = (float(lo), float(hi))
        self._log(f"⏳ 작업 간 대기시간 저장: {val}{unit} 후 다음 작업 진행", "success")

    def _show_pause_notice(self, reason):
        def _show():
            self.pause_notice_label.configure(text=f"작업이 일시정지되었습니다. 사유: {reason}")
            self.pause_notice_frame.pack(side="right", padx=(6, 12), pady=6)
        try:
            self.after(0, _show)
        except Exception:
            pass

    def _hide_pause_notice(self):
        try:
            self.pause_notice_frame.pack_forget()
        except Exception:
            pass

    def _on_recheck_after_auth(self):
        """사용자가 브라우저에서 인증을 완료한 후 다시 확인"""
        self._hide_pause_notice()
        self._log("로그인 상태를 다시 확인합니다...", "info")
        threading.Thread(target=self._recheck_worker, daemon=True).start()

    def _recheck_worker(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ok = loop.run_until_complete(self.automator._is_logged_in_now())
            self.after(0, self._on_recheck_result, ok)
        except Exception as e:
            self._ui_log(f"확인 오류: {e}", "error")
            self.after(0, self._on_recheck_result, False)

    def _on_recheck_result(self, ok):
        if ok:
            self.automator.is_logged_in = True
            self._set_login_indicator("in")
            self.pause_event.set()
            self.is_paused = False
            self.btn_pause.configure(state="normal")
            self.btn_resume.configure(state="disabled")
            self._log("🟢 로그인 확인 완료 — 작업을 재개합니다.", "success")
        else:
            self._set_login_indicator("out")
            self._show_pause_notice("아직 로그인되지 않았습니다. 브라우저에서 인증을 완료한 후 다시 확인하세요.")
            self._log("아직 로그인 상태가 아닙니다.", "warning")

    # ── 작업 워커 ─────────────────────────────────────────
    def _work_worker(self, targets, msg_text, comment_text, naver_id, naver_pw):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self._work_async(targets, msg_text, comment_text, naver_id, naver_pw))
        except Exception as e:
            self._ui_log(f"작업 오류: {e}", "error")
        finally:
            self.after(0, self._on_work_complete)

    async def _wait_if_paused(self):
        while self.is_paused and not self.stop_event.is_set():
            await asyncio.sleep(0.5)

    async def _work_async(self, targets, msg_text, comment_text, naver_id="", naver_pw=""):
        total = len(targets)
        done = 0
        fail = 0
        start_time = datetime.now()

        # ── 브라우저 시작 (실시간 화면 확인: 브라우저 창 표시 옵션) ──
        if not (self.automator.browser and self.automator.page):
            show = self.var_show_browser.get() if hasattr(self, "var_show_browser") else True
            self._ui_log("브라우저를 시작합니다...", "system")
            await self.automator.start_browser(headless=not show)
        await self.automator.bring_to_front()

        # ── 로그인: 세션 재사용 → 없으면 아이디/비밀번호를 사람처럼 타이핑해 로그인 ──
        # 로그인 완료 즉시 아래 루프에서 이웃신청 → 공감 → 댓글이 자동 진행된다.
        if not await self.automator._is_logged_in_now(verify=True):
            self.automator.is_logged_in = False
            self.after(0, self._set_login_indicator, "checking")

            if not naver_id or not naver_pw:
                self._ui_log("로그인이 필요하지만 아이디/비밀번호가 입력되지 않았습니다.", "error")
                self.after(0, self._set_login_indicator, "out")
                self.after(0, lambda: messagebox.showwarning(
                    "입력 필요", "네이버 아이디와 비밀번호를 입력한 후 다시 시작하세요."))
                return

            self._ui_log("네이버 로그인 페이지에서 아이디/비밀번호를 타이핑합니다...", "system")
            login_ok = await self.automator.login(naver_id, naver_pw)
            if not login_ok:
                self._ui_log("로그인에 실패해 작업을 중단합니다. (아이디/비밀번호 또는 2단계 인증 확인)", "error")
                self.after(0, self._set_login_indicator, "out")
                return
            self._ui_log("✅ 네이버 로그인 완료 — 곧바로 작업을 진행합니다.", "success")

        self.after(0, self._set_login_indicator, "in")
        self.automator.is_logged_in = True

        pause_lo, pause_hi = getattr(self, "_pause_delay", (30.0, 90.0))
        spd_lo, spd_hi = getattr(self, "_speed_factor", (0.5, 1.0))

        for idx, target in enumerate(targets):
            await self._wait_if_paused()
            if self.stop_event.is_set():
                self._ui_log("사용자가 작업을 중지했습니다.", "warning")
                break

            blog_id = target.get("blog_id", "")
            blog_name = target.get("blog_name", blog_id)
            post_url = (target.get("post_urls") or [""])[0] if target.get("post_urls") else ""

            # 중복 작업 방지
            last = work_history.get_blog_last_status(blog_id)
            if last and last["status"] == "success":
                self._ui_log(f"[{idx+1}/{total}] {blog_name}: 이전에 처리 완료 — 건너뜁니다 (중복 방지)", "info")
                done += 1
                self.after(0, self._set_work_row_status, blog_id,
                           "🟢 이전 완료 (건너뜀)", "skip")
                self.after(0, self._update_work_stats, idx + 1, done, 0, total - done - fail, fail)
                continue

            current = f"{blog_name} ({blog_id})"
            self.after(0, lambda c=current: self.current_work_label.configure(
                text=f"현재 작업: {c} 처리 중..."))
            self.after(0, self._set_work_row_status, blog_id, "🔵 진행 중...", "doing")
            self._ui_log(f"[{idx+1}/{total}] {current} 처리 시작", "system")

            ok = True
            err = ""

            # 하위 단계별 화면 표시 헬퍼 (브라우저 장면 + 앱 상태 동시 갱신)
            def _stage(text, row_status):
                self.after(0, lambda c=f"현재 작업: {current} — {text}":
                           self.current_work_label.configure(text=c))
                self.after(0, self._set_work_row_status, blog_id, row_status, "doing")

            try:
                # 게시글 열기 (브라우저에서 페이지 이동 장면이 보임)
                _stage("게시글 열기", "🔵 게시글 여는 중...")
                if not await self.automator.open_post(blog_id, post_url):
                    ok = False
                    err = "대상 블로그/게시글 접근 실패"
                else:
                    # 1) 서로이웃 신청 — 항상 1단계로 실행 (옵션 무관 고정)
                    if not self.stop_event.is_set():
                        # ── [v3.4 신규] 메모장 파일 연동: message.txt에서 줄 단위 랜덤 추출 ──
                        # 신청 요청 시점마다 파일을 새로 읽어 무작위 1개를 사용한다.
                        # (파일 없음/비어 있음/오류 시 None → 기존 입력창·템플릿 로직으로 폴백)
                        file_msg = textfiles_mod.pick_random("message", self._used_messages)
                        if file_msg:
                            message = file_msg
                            self._ui_log(f"  📝 message.txt 랜덤 추출: {message[:24]}...", "info")
                        else:
                            message = msg_text
                            if self._used_messages:
                                # 입력창에 여러 후보(빈 줄 구분) 또는 {A|B} 치환이 있으면
                                # 입력창 내용을 우선 랜덤 생성, 아니면 저장 템플릿 풀에서 선택
                                if templates_mod.split_candidates(msg_text) or ("{" in msg_text and "|" in msg_text):
                                    message = templates_mod.pick_from_text(msg_text, self._used_messages) or msg_text
                                else:
                                    message = templates_mod.pick_random("neighbor", self._used_messages) or msg_text
                        if message:
                            self._used_messages.add(message)
                        _stage("서로이웃 신청 중", "🔵 이웃신청 중...")
                        self._ui_log(f"  🤝 서로이웃 신청 진행 (메시지: {message[:20]}...) — 브라우저에서 신청 장면을 확인할 수 있습니다", "info")
                        neighbor_ok = await self.automator.write_comment(
                            blog_id=blog_id, comment="", my_blog_id="",
                            post_url="", neighbor_message=message,
                            stop_flag=lambda: self.stop_event.is_set(),
                            do_neighbor=True, do_like=False, do_comment=False,
                        )
                        if not neighbor_ok:
                            self._ui_log("  ⚠️ 서로이웃 신청 실패 (버튼 미발견 또는 이미 이웃) — 공감/댓글은 계속 진행합니다", "warning")

                        work_history.add_record(
                            work_history.WORK_NEIGHBOR, blog_id, blog_name,
                            message=message[:100],
                            result=work_history.RESULT_SUCCESS if neighbor_ok else work_history.RESULT_FAIL,
                            error="" if neighbor_ok else "신청 버튼 미발견/실패",
                        )
                        if self.settings.get("excel_auto_save", True):
                            self._record_to_excel(work_history.WORK_NEIGHBOR, blog_id, blog_name,
                                                  message, neighbor_ok)

                    # 2) 공감 — 항상 2단계로 실행 (옵션 무관 고정)
                    if not self.stop_event.is_set():
                        _stage("공감(하트) 클릭 중", "🔵 공감 진행 중...")
                        self._ui_log("  ❤️ 공감 처리 진행 — 브라우저에서 하트 클릭 장면을 확인할 수 있습니다", "info")
                        like_ok = await self.automator.do_like()
                        self._ui_log(f"  {'🟢 공감 완료' if like_ok else '🔴 공감 실패'}",
                                     "success" if like_ok else "warning")
                        work_history.add_record(
                            work_history.WORK_LIKE, blog_id, blog_name,
                            result=work_history.RESULT_SUCCESS if like_ok else work_history.RESULT_FAIL,
                            error="" if like_ok else "공감 버튼 미발견/실패",
                        )
                        if self.settings.get("excel_auto_save", True):
                            self._record_to_excel(work_history.WORK_LIKE, blog_id, blog_name, "", like_ok)

                    # 3) 댓글 — 항상 3단계로 실행 (옵션 무관 고정)
                    if not self.stop_event.is_set():
                        # ── [v3.4 신규] 메모장 파일 연동: comment.txt에서 줄 단위 랜덤 추출 ──
                        # 신청 요청 시점마다 파일을 새로 읽어 무작위 1개를 사용한다.
                        # (파일 없음/비어 있음/오류 시 None → 기존 입력창·템플릿 로직으로 폴백)
                        file_cmt = textfiles_mod.pick_random("comment", self._used_comments)
                        if file_cmt:
                            comment = file_cmt
                            self._ui_log(f"  📝 comment.txt 랜덤 추출: {comment[:24]}...", "info")
                        else:
                            comment = comment_text
                            if not comment or self._used_comments:
                                # 입력창에 여러 후보(빈 줄 구분) 또는 {A|B} 치환이 있으면
                                # 입력창 내용을 우선 랜덤 생성, 아니면 저장 템플릿 풀에서 선택
                                if templates_mod.split_candidates(comment_text) or ("{" in comment_text and "|" in comment_text):
                                    comment = templates_mod.pick_from_text(comment_text, self._used_comments) or comment_text
                                else:
                                    comment = templates_mod.pick_random("comment", self._used_comments) or comment_text
                        if comment:
                            self._used_comments.add(comment)
                        _stage("댓글 작성 중", "🔵 댓글 작성 중...")
                        self._ui_log(f"  💬 댓글 작성 진행: {comment[:20]}... — 브라우저에서 타이핑 장면을 확인할 수 있습니다", "info")
                        comment_ok = await self.automator.do_comment(comment)
                        self._ui_log(f"  {'🟢 댓글 등록 완료' if comment_ok else '🔴 댓글 등록 실패'}",
                                     "success" if comment_ok else "warning")
                        work_history.add_record(
                            work_history.WORK_COMMENT, blog_id, blog_name,
                            message=comment[:100],
                            result=work_history.RESULT_SUCCESS if comment_ok else work_history.RESULT_FAIL,
                            error="" if comment_ok else "댓글 입력창/등록 버튼 실패",
                        )
                        if self.settings.get("excel_auto_save", True):
                            self._record_to_excel(work_history.WORK_COMMENT, blog_id, blog_name, comment, comment_ok)

            except Exception as e:
                ok = False
                err = str(e)
                self._ui_log(f"  ❌ 처리 오류: {e}", "error")

            if not ok:
                fail += 1
                self._ui_log(f"[{idx+1}/{total}] {current} 실패: {err}", "error")
                self.after(0, self._set_work_row_status, blog_id, f"🔴 실패: {err[:20]}", "fail")
                # 오류 자동 일시정지
                if self.settings.get("pause_on_error", True):
                    self.is_paused = True
                    self.after(0, self._show_pause_notice, f"{current} 처리 실패: {err}")
                    self.after(0, lambda: self.btn_pause.configure(state="disabled"))
                    self.after(0, lambda: self.btn_resume.configure(state="normal"))
                    self._ui_log("🟡 오류 발생으로 작업이 일시정지되었습니다.", "pause")
                    while self.is_paused and not self.stop_event.is_set():
                        await asyncio.sleep(0.5)
                    self._hide_pause_notice()
            else:
                done += 1
                self.after(0, self._set_work_row_status, blog_id, "🟢 완료", "done")

            # 진행률 업데이트
            self.after(0, self.work_progress.set, (idx + 1) / total)
            self.after(0, self._update_work_stats, idx + 1, done, 0, total - done - fail, fail)

            # 작업 간 대기 (설정한 단위: 초/분/시간 반영)
            if idx < total - 1 and not self.stop_event.is_set():
                wait = random.uniform(pause_lo, pause_hi)
                if wait >= 3600:
                    unit_txt = f"{wait / 3600:.1f}시간"
                elif wait >= 120:
                    unit_txt = f"{wait / 60:.1f}분"
                else:
                    unit_txt = f"{wait:.0f}초"
                self._ui_log(f"  ⏳ 다음 대상까지 {unit_txt} 대기... (일시정지 가능)", "info")
                for _ in range(int(wait * 2)):
                    if self.stop_event.is_set():
                        break
                    await asyncio.sleep(0.5)

        elapsed = (datetime.now() - start_time).total_seconds()
        minutes = int(elapsed // 60)
        self._ui_log(f"═══ 작업 종료: 완료 {done} / 실패 {fail} / 전체 {total} (소요 {minutes}분) ═══", "system")

        # 작업 완료 후 브라우저 유지 여부
        if not self.settings.get("keep_browser_after_work", True):
            try:
                await self.automator.close()
            except Exception:
                pass

        self.after(0, self._show_work_complete, total, done, fail, minutes)

    def _record_to_excel(self, work_type, blog_id, blog_name, message, ok):
        try:
            record = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "work_type": work_type,
                "blog_id": blog_id,
                "blog_name": blog_name,
                "message": message or "",
                "result": work_history.RESULT_SUCCESS if ok else work_history.RESULT_FAIL,
                "error": "" if ok else "실패",
            }
            if self.settings.get("excel_dir", ""):
                excel_mod.EXCEL_DIR = self.settings["excel_dir"]
            excel_mod.append_record(record)
        except Exception as e:
            self._ui_log(f"엑셀 저장 실패: {e}", "warning")

    def _open_latest_excel(self):
        # ── [v3.4 신규] 라이센스 인증 확인 (만료/무효 시 사용 차단) ──
        if not self._ensure_licensed():
            return

        files = excel_mod.get_monthly_files()
        if not files:
            records = work_history.get_all_records()[:200]
            for r in reversed(records):
                excel_mod.append_record(r)
            files = excel_mod.get_monthly_files()
        if files:
            path = os.path.join(excel_mod.EXCEL_DIR, files[0])
            excel_mod.open_excel_file(path)
            self._log(f"엑셀 파일 열기: {path}", "info")
        else:
            messagebox.showinfo("엑셀", "저장된 엑셀 기록이 없습니다.")

    def _update_work_stats(self, total_idx=0, done=0, doing=0, wait=0, fail=0):
        self.stat_total.configure(text=f"전체 {total_idx + max(0, wait)}")
        self.stat_done.configure(text=f"완료 {done}")
        self.stat_doing.configure(text=f"진행 {doing if doing else (1 if self.is_running else 0)}")
        self.stat_wait.configure(text=f"대기 {max(0, wait)}")
        self.stat_fail.configure(text=f"실패 {fail}")

    def _show_work_complete(self, total, done, fail, minutes):
        """작업 완료 화면"""
        if self.stop_event.is_set():
            self._on_work_complete()
            return

        win = ctk.CTkToplevel(self)
        win.title("작업 완료")
        win.geometry("420x330")
        win.configure(fg_color=BG_DARK)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="✅ 작업 완료", font=F(20, "bold"),
                     text_color=GREEN_LIGHT).pack(anchor="w", padx=24, pady=(20, 8))

        summary = f"총 대상: {total}명\n완료: {done}명\n실패: {fail}명\n소요시간: {minutes}분"
        ctk.CTkLabel(win, text=summary, font=F(14), text_color=TEXT_WHITE,
                     justify="left").pack(anchor="w", padx=24, pady=(0, 14))

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(0, 20))

        def open_result():
            self.tabview.set(TAB_WORK)
            win.destroy()

        def open_excel():
            self._open_latest_excel()

        ctk.CTkButton(btn_frame, text="📋 작업 결과 보기", font=F(12, "bold"), height=38,
                      fg_color=PURPLE, hover_color=PURPLE_HOVER, text_color="white",
                      command=open_result).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(btn_frame, text="📗 엑셀 기록 열기", font=F(12, "bold"), height=38,
                      fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white",
                      command=open_excel).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(btn_frame, text="닫기", font=F(12), height=38,
                      fg_color=BG_INPUT, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
                      command=win.destroy).pack(fill="x")

        self._on_work_complete()

    def _on_work_complete(self):
        self.is_running = False
        self.is_paused = False
        self.current_work_label.configure(text="")
        self.btn_login_work.configure(state="normal", text="🚀  로그인 후 원스톱 작업 시작")
        self.btn_pause.configure(state="disabled", text="🟡 일시정지")
        self.btn_resume.configure(state="disabled")
        self.btn_work_stop.configure(state="disabled")
        self._hide_pause_notice()
        self._set_login_indicator(self.login_state)

    # ══════════════════════════════════════════════════════
    #  설정
    # ══════════════════════════════════════════════════════
    def _restore_settings_to_ui(self):
        self.entry_keyword.delete(0, "end")
        self.entry_keyword.insert(0, self.settings.get("keyword", ""))
        saved_conds = self.settings.get("conditions", {})
        for key, entry in self.condition_entries.items():
            if key in saved_conds and saved_conds[key]:
                entry.delete(0, "end")
                entry.insert(0, str(saved_conds[key]))

    def _save_settings(self):
        """수집 시작 시 자동 저장 (아이디/비밀번호는 저장하지 않음)"""
        self.settings.update({
            "keyword": self.entry_keyword.get().strip(),
            "conditions": {k: e.get().strip() for k, e in self.condition_entries.items()},
            "show_browser": self.var_show_browser.get(),
        })
        settings_mod.save(self.settings)

    def _on_condition_changed(self, event=None):
        """수집 조건 입력이 바뀔 때마다 즉시 저장 (재시작 후 마지막 입력값 유지)"""
        try:
            self.settings["conditions"] = {
                k: e.get().strip() for k, e in self.condition_entries.items()
            }
            self.settings["keyword"] = self.entry_keyword.get().strip()
            settings_mod.save(self.settings)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  종료
    # ══════════════════════════════════════════════════════
    def _on_exit_program(self):
        """프로그램 종료 버튼/X 버튼 — 브라우저 정리 후 확실하게 프로세스 종료.
        [원인] 기존에는 브라우저 close()가 무한 대기하거나 비(非)메인 스레드에서
        destroy()를 호출해 창이 닫히지 않는 문제가 있었다.
        [수정] 정리에 타임아웃을 두고, 창을 닫은 뒤 남은 스레드/서브프로세스까지
        os._exit()로 강제 종료한다."""
        if self.is_running:
            if not messagebox.askyesno("종료 확인", "작업이 진행 중입니다. 정말 종료하시겠습니까?"):
                return
        else:
            if not messagebox.askyesno("프로그램 종료", "프로그램을 종료하시겠습니까?"):
                return

        self._log("프로그램을 종료합니다... (브라우저 세션 저장 중)", "system")
        self.stop_event.set()
        self.pause_event.set()
        self.is_running = False

        # 브라우저/세션 정리는 백그라운드에서 최대 6초만 시도 (무한 대기 방지)
        cleanup_done = threading.Event()

        def cleanup():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    asyncio.wait_for(self.automator.close(), timeout=6))
            except Exception:
                pass
            finally:
                cleanup_done.set()

        threading.Thread(target=cleanup, daemon=True).start()

        # 창 닫기
        try:
            self.destroy()
        except Exception:
            pass

        # 세션 저장 여유 시간 (최대 3초) 후 확실한 프로세스 종료
        cleanup_done.wait(3.0)
        os._exit(0)

    def _on_close(self):
        """X 버튼으로도 동일하게 종료 (종료 안 되는 문제 수정)"""
        self._on_exit_program()


# ─── 엔트리 포인트 ────────────────────────────────────────
if __name__ == "__main__":
    app = BlogGeniusApp()
    app.mainloop()
