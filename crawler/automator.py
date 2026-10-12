"""
네이버 블로그 자동화 모듈 (Playwright 기반)
- 모바일 스텔스 UA (스마트폰에서 접속한 것처럼)
- 타자를 손으로 직접 치듯 문자별 입력 (랜덤 딜레이)
- 네이버 로그인 / 댓글 자동 작성 / 이웃 신청
"""

import asyncio
import json
import os
import random
from typing import Optional, Callable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


# ── 모바일 스텔스 User-Agent ─────────────────────────────
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)


class NaverAutomator:
    """Playwright 기반 네이버 블로그 자동화 (모바일 스텔스 + 타자 시뮬레이션)"""

    NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
    BLOG_HOME = "https://blog.naver.com"
    BLOG_MOBILE_HOME = "https://m.blog.naver.com"

    # 세션 저장 경로
    SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "browser_session")
    SESSION_FILE = os.path.join(SESSION_DIR, "session_state.json")

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        self.log_callback: Optional[Callable] = None
        # 작업 속도 배율 (UI에서 설정, 1.0=사람 속도)
        self.speed_factor: float = 1.0
        # 로그인 화면 실시간 진행 공유용 큐 (main.py가 브라우저 뷰에 표시)
        self.login_progress_callbacks: list = []

    def set_log_callback(self, callback: Callable):
        self.log_callback = callback

    def _log(self, message: str, level: str = "info"):
        if self.log_callback:
            self.log_callback(message, level)

    def register_login_progress(self, cb: Callable):
        """로그인 입력 진행 상황을 main.py 브라우저 뷰에 전달할 콜백 등록"""
        self.login_progress_callbacks.append(cb)

    def _emit_login_progress(self, stage: str, detail: str):
        for cb in self.login_progress_callbacks:
            try:
                cb(stage, detail)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────
    #  브라우저 시작 (모바일 스텔스)
    # ──────────────────────────────────────────────────────
    # ── 세션 저장/로드 ────────────────────────────────
    async def _save_session(self):
        """현재 브라우저 세션(쿠키+localStorage)을 파일로 저장"""
        if not self.context:
            return
        try:
            os.makedirs(self.SESSION_DIR, exist_ok=True)
            storage = await self.context.storage_state()
            with open(self.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(storage, f, ensure_ascii=False, indent=2)
            self._log("세션 저장 완료 (자동 로그인 가능)", "success")
        except Exception as e:
            self._log(f"세션 저장 실패: {e}", "warning")

    def _has_saved_session(self) -> bool:
        """저장된 세션이 있는지 확인"""
        return os.path.exists(self.SESSION_FILE)

    async def start_browser(self, headless: bool = False, mobile: bool = True):
        """브라우저 시작 — 세션 복원 또는 새 브라우저"""
        mode = "모바일 스텔스" if mobile else "데스크톱"
        self._log(f"브라우저 시작 중... ({mode})", "system")

        self.playwright = await async_playwright().start()
        launch_kwargs = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if headless:
            # 기본 headless shell은 일부 Windows 환경에서 ICU 데이터 오류로 실행되지 않음.
            # 전체 Chromium 기반 신형 headless를 사용해 안정성 확보.
            launch_kwargs["channel"] = "chromium"
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        viewport = {"width": 412, "height": 915} if mobile else {"width": 1280, "height": 800}
        user_agent = MOBILE_UA if mobile else (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        # 세션 복원 또는 새 컨텍스트 생성
        if self._has_saved_session():
            try:
                self._log("저장된 세션 복원 중...", "info")
                self.context = await self.browser.new_context(
                    storage_state=self.SESSION_FILE,
                    user_agent=user_agent,
                    viewport=viewport,
                    locale="ko-KR",
                    is_mobile=mobile,
                    has_touch=mobile,
                )
                self._log("세션 복원 완료!", "success")
            except Exception as e:
                self._log(f"세션 복원 실패, 새 브라우저 생성: {e}", "warning")
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    viewport=viewport,
                    locale="ko-KR",
                    is_mobile=mobile,
                    has_touch=mobile,
                )
        else:
            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                locale="ko-KR",
                is_mobile=mobile,
                has_touch=mobile,
            )

        # 자동화 감지 우회 — WebGL, plugin, permissions 등 강화
        await self.context.add_init_script("""
            // webdriver 제거
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // plugin 개수 실제 기기처럼
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const p = [
                        {0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null}, length: 1},
                        {0: {type: 'application/pdf', suffixes: 'pdf', description: 'PDF', enabledPlugin: null}, length: 1}
                    ];
                    return Object.freeze(p);
                }
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en']});
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
            // Permissions API 감지 우회
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : origQuery(parameters);
            // WebGL renderer 자연스러운 값
            const origGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (Android)';
                if (param === 37446) return 'ANGLE (Android, AMD Radeon(TM) RX Vega M GC, OpenGL 3.2)';
                return origGetParameter.call(this, param);
            };
            // Playwright 흔적 제거
            delete navigator.__playwright;
            delete navigator.webdriver;
        """)

        self.page = await self.context.new_page()
        if not headless:
            try:
                await self.page.set_viewport_size({"width": 420, "height": 880})
            except Exception:
                pass
            # 윈도우가 실제로 사용자에게 보이도록 최상단에 띄우고 포커스 확보
            for _ in range(8):
                try:
                    await self.page.bring_to_front()
                except Exception:
                    pass
                await asyncio.sleep(0.15)
            try:
                await self.page.evaluate("() => window.focus()")
            except Exception:
                pass
            # 헤드리스처럼 보이지 않도록 초기화 후 잠시 대기
            await asyncio.sleep(1.0)
        else:
            # headless 모드에서도 페이지 생성 직후 포커스 상태를 미리 확보
            try:
                await self.page.bring_to_front()
            except Exception:
                pass
        self._log(f"브라우저 시작 완료 ({mode})", "success")

    # ──────────────────────────────────────────────────────
    #  작업 속도 배율 (UI에서 설정 — 1.0=사람 속도, 작을수록 빠름)
    # ──────────────────────────────────────────────────────
    def set_speed_factor(self, factor: float):
        """타이핑/마우스 이동/대기 딜레이 배율 (0.2~3.0)"""
        self.speed_factor = max(0.2, min(3.0, float(factor)))
        self._log(f"작업 속도 배율: {self.speed_factor}배", "info")

    def _sd(self, seconds: float) -> float:
        """속도 배율이 적용된 딜레이 반환 (speed delay)"""
        return max(0.01, seconds * getattr(self, "speed_factor", 1.0))

    # ──────────────────────────────────────────────────────
    #  사람처럼 커서 이동 후 클릭 (브라우저에 실시간 표시)
    # ──────────────────────────────────────────────────────
    async def human_move_and_click(self, element, scroll_first: bool = False):
        """
        사람이 마우스를 움직이듯 커서를 요소로 이동시킨 뒤 클릭한다.
        - (옵션) 요소를 화면에 스크롤
        - 요소 중심까지 여러 단계로 나눠 커서 이동 (가속/감속 느낌)
        - 클릭 전 잠깐 멈춤 → 클릭
        브라우저 화면에서 커서가 실제로 움직이는 것이 보인다.
        """
        try:
            if scroll_first:
                try:
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(self._sd(0.8))
                except Exception:
                    pass

            box = await element.bounding_box()
            if not box:
                # 좌표를 못 구하면 일반 클릭으로 폴백
                await element.click()
                return

            target_x = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)

            # 현재 마우스 위치에서 대상까지 4~7단계로 이동 (사람 손떨림 느낌)
            try:
                cur = await self.page.evaluate("() => ({x: window.mouseX || 0, y: window.mouseY || 0})")
            except Exception:
                cur = {"x": 0, "y": 0}

            steps = random.randint(4, 7)
            for i in range(1, steps + 1):
                ratio = i / steps
                # ease-out (처음 빠르고 끝에서 느려짐)
                eased = 1 - (1 - ratio) ** 2
                nx = cur["x"] + (target_x - cur["x"]) * eased
                ny = cur["y"] + (target_y - cur["y"]) * eased
                try:
                    await self.page.mouse.move(nx, ny)
                except Exception:
                    pass
                await asyncio.sleep(self._sd(random.uniform(0.04, 0.12)))

            # 대상 위에서 잠깐 멈췄다가 클릭 (사람이 조준하는 느낌)
            await asyncio.sleep(self._sd(random.uniform(0.15, 0.35)))
            try:
                await self.page.mouse.move(target_x, target_y)
                await asyncio.sleep(self._sd(random.uniform(0.05, 0.15)))
                await self.page.mouse.click(target_x, target_y)
            except Exception:
                await element.click()

        except Exception:
            # 어떤 이유로든 실패하면 기본 클릭으로 폴백 (동작 보장)
            try:
                await element.click()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────
    #  OS 창 자체를 전면으로 가져오기 (Windows 전용)
    # ──────────────────────────────────────────────────────
    def _activate_os_window(self):
        """
        page.bring_to_front()는 브라우저 내부의 '탭'만 전면화할 뿐
        OS 윈도우를 활성화하지 않는다. Windows API로 Chromium 창을
        실제 화면 최전면으로 가져와 로그인 타이핑·이웃신청·공감·댓글 작성
        장면을 사용자가 실시간으로 볼 수 있게 한다.
        """
        try:
            import sys
            if sys.platform != "win32":
                return
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )
            user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]

            best_hwnd = 0
            best_len = 0

            def _enum_cb(hwnd, lparam):
                nonlocal best_hwnd, best_len
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    # Playwright Chromium 창 제목은 "... - Chromium" 형태
                    if "Chromium" in title and length > best_len:
                        best_hwnd = hwnd
                        best_len = length
                except Exception:
                    pass
                return True

            try:
                user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
            except Exception:
                pass

            hwnd = best_hwnd or user32.GetForegroundWindow()
            if not hwnd:
                return

            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            # 최소화 상태면 복원
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # 최상위로 잠깐 올렸다가 해제 → 다른 창 위에 확실히 보이게
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    async def bring_to_front(self):
        """브라우저 창을 화면 가장 앞으로 가져오기 (OS 창 활성화 포함)"""
        if self.page:
            try:
                await self.page.bring_to_front()
            except Exception:
                pass
            # 추가: 윈도우 포커스 확보
            try:
                await self.page.evaluate("() => window.focus()")
            except Exception:
                pass
            # OS 윈도우 자체를 전면으로 (작업 화면 실시간 표시)
            self._activate_os_window()
            # 마우스 이동 없이 브라우저 창만 확실하게 전면에 띄우도록 반복 시도
            for _ in range(5):
                try:
                    await self.page.bring_to_front()
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            self._activate_os_window()

    # ──────────────────────────────────────────────────────
    #  현재 브라우저 페이지가 네이버 로그인 상태인지 확인
    # ──────────────────────────────────────────────────────
    async def _check_logged_in_state(self) -> bool:
        """현재 브라우저 페이지가 네이버 로그인 상태인지 확인."""
        self._log("  🔍 [_check_logged_in_state] 진입: is_logged_in={}, page={}, browser={}".format(
            self.is_logged_in, self.page is not None, self.browser is not None), "info")

        # is_logged_in=True이면 무조건 True 반환 (불필요한 페이지 이동 방지)
        if self.is_logged_in:
            self._log("  🔍 [_check_logged_in_state] is_logged_in=True → 즉시 True 반환", "info")
            return True

        if not self.page:
            self._log("  ⚠️ [_check_logged_in_state] page 없음 → False 반환", "warning")
            return False

        login_indicators = ["로그인", "로그인이 필요합니다", "마이페이지", "회원가입"]
        try:
            # 1단계: m.naver.com에서 기본 상태 확인
            await self.page.goto("https://m.naver.com", wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(2)
            current_url = self.page.url
            page_text = await self.page.evaluate("() => document.body.innerText")
            has_login_hint = any(ind in page_text for ind in login_indicators)
            self._log("  🔍 m.naver.com: url={} hint={}".format(
                current_url[:60], has_login_hint), "info")

            # 2단계: 로그인 필수 페이지(mail.naver.com)에서 실제 검증
            mail_logged_in = False
            try:
                await self.page.goto("https://mail.naver.com/", wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(2)
                mail_url = self.page.url
                mail_text = await self.page.evaluate("() => document.body.innerText")
                mail_login_ind = "nid.naver.com" in mail_url or any(ind in mail_text for ind in login_indicators)
                mail_form = await self.page.query_selector('input[name="id"]')
                mail_logged_in = not (mail_login_ind or mail_form is not None)
                self._log("  🔍 mail.naver.com: logged_in={}, url={}".format(mail_logged_in, mail_url[:60]), "info")
                if mail_logged_in:
                    await self.page.goto("https://m.naver.com", wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(1)
            except Exception as e:
                self._log("  ⚠️ 메일 검증 예외: {}".format(e), "warning")

            is_not_login = mail_logged_in
            self._log("  🔍 [_check_logged_in_state] 최종: is_not_login={}, mail={}".format(is_not_login, mail_logged_in), "info")
            return is_not_login
        except Exception as e:
            self._log("  ⚠️ [_check_logged_in_state] 예외: {}".format(e), "warning")
            return False

    # ──────────────────────────────────────────────────────
    #  타자를 손으로 직접 치듯 입력
    # ──────────────────────────────────────────────────────
    async def _type_like_human(self, element, text, frame=None):
        """한 글자씩 천천히 입력 — 브라우저 화면에서 실제로 타이핑되는 모습 확인 + 상세 로그"""
        await self.bring_to_front()
        await asyncio.sleep(0.15)



        self._log(f"  타이핑 시작 ({len(text)}자)...", "info")
        self._emit_login_progress("typing_start", str(len(text)))

        # 요소 클릭 → 포커스 → 기존 텍스트 클리어
        try:
            await element.click()
            await asyncio.sleep(0.25)
        except Exception:
            pass
        try:
            await element.focus()
        except Exception:
            pass
        await asyncio.sleep(0.15)

        # 기존 텍스트를 지운다 (이미 들어 있던 값이 있으면)
        try:
            await element.fill("")
        except Exception:
            try:
                await element.evaluate("el => el.value = ''")
            except Exception:
                pass
        await asyncio.sleep(0.12)

        # 클릭 후 포커스가 확실히 들어갔는지 한 번 더 앞으로 가져옴
        await self.bring_to_front()
        await asyncio.sleep(0.15)

        # 입력할 텍스트의 길이
        total = len(text)

        # 사용할 키보드 API 결정 (iframe이면 frame.keyboard, 아니면 page.keyboard)
        keyboard = None
        if frame and hasattr(frame, 'keyboard'):
            keyboard = frame.keyboard
        elif self.page:
            keyboard = self.page.keyboard

        # 타이핑 시작 시점을 로그/진행 표시에 반영
        start_idx = 0

        for i, char in enumerate(text):
            if not self.page:
                break

            # 문장 부호에서 약간 더 오래 쉼
            if char in ('.', '!', '?', ',', '~'):
                delay = random.uniform(0.18, 0.40)
            elif char in (' '):
                delay = random.uniform(0.10, 0.25)
            else:
                delay = random.uniform(0.06, 0.20)

            # 가끔 생각하는 시간 (5% 확률)
            if random.random() < 0.05:
                delay += random.uniform(0.3, 0.9)

            await asyncio.sleep(delay)

            if not self.page:
                break

            # 타이핑 진행 중 몇 글자마다 창을 앞으로 가져와서
            # 입력 중인 화면이 계속 전면에 보이도록 유지
            if (i - start_idx + 1) % 3 == 0 or i == 0:
                try:
                    await self.bring_to_front()
                except Exception:
                    pass
                await asyncio.sleep(0.05)

            # Playwright element.type(): 실제 키 이벤트를 발생시켜 화면에 한 글자씩 표시됨
            # (insert_text는 이벤트 없이 텍스트만 삽입하여 일부 화면에서 안 보일 수 있음)
            typed = False
            try:
                await element.type(char, delay=0)
                typed = True
            except Exception:
                pass

            if not typed and keyboard:
                try:
                    await keyboard.insert_text(char)
                    typed = True
                except Exception:
                    pass

            if not typed:
                # fallback: 요소 직접 입력
                try:
                    await element.press(char)
                except Exception:
                    await self._type_unicode_char(element, char)

            # 진행 상황 공유 (한글이므로 마스킹된 길이만 전달)
            # 5자마다 실제 입력 중인 글자도 로그로 출력 (디버그 확인용)
            if (i + 1) % 5 == 0 or i == len(text) - 1:
                current_val = text[:i+1]
                self._log(
                    f"  🔤 아이디 입력 중: '{current_val}' ({i+1}/{len(text)}자)",
                    "info",
                )
            self._emit_login_progress(
                "typing_progress",
                "●" * min(8, (i + 1)),
            )

        # 타이핑 완료 후 잠시 대기
        await asyncio.sleep(0.3)
        self._log(f"  타이핑 완료", "success")
        self._emit_login_progress("typing_done", "완료")

    async def _type_on_page(self, text: str, frame=None, element=None):
        """
        한 글자씩 입력 — 브라우저 화면에서 실시간으로 타이핑 장면을 볼 수 있음.
        element: 실제 textarea 요소 (iframe 내부 textarea도 element.type()으로 입력 가능)
        frame: 댓글 입력이 있는 프레임
        
        핵심: element.type(char)은 메인 페이지/iframe 모두에서 작동하여
        브라우저 화면에 한 글자씩 타이핑되는 것이 실제로 보임.
        """
        total = len(text)
        use_element = element is not None

        if use_element:
            self._log(f"  ⌨️  element.type() 사용 (메인/iframe 모두 작동)", "info")
        else:
            self._log(f"  ⌨️  page.keyboard 사용", "info")

        for i, char in enumerate(text):
            if not self.page:
                break

            # 문장 부호에서 더 오래 쉼 (생각하는 시간)
            if char in ('.', '!', '?'):
                delay = random.uniform(0.30, 0.60)
            elif char in (',', '~'):
                delay = random.uniform(0.20, 0.45)
            elif char == ' ':
                delay = random.uniform(0.15, 0.35)
            else:
                # 한글/영문 글자: 150~300ms (사용자가 한 글자씩 입력되는 것을 볼 수 있도록)
                delay = random.uniform(0.15, 0.30)

            # 가끔 더 긴 딜레이 (생각하는 시간, 10% 확률)
            if random.random() < 0.10:
                pause = self._sd(random.uniform(0.5, 1.2))
                self._log(f"  💭  생각 중... ({pause:.1f}초)", "info")
                await asyncio.sleep(pause)

            await asyncio.sleep(self._sd(delay))

            # 주기적으로 화면을 전면으로 가져와 실시간 타이핑 장면이 보이게 유지
            if (i + 1) % 5 == 0 or i == 0:
                try:
                    await self.bring_to_front()
                except Exception:
                    pass

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 실제 타이핑 — 브라우저 화면에 한 글자씩 보이게 입력
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            typed = False

            # 1순위: element.type(char) — 메인/iframe 모두 작동!
            # Playwright elementHandle.type()은 해당 요소에 직접 키보드 이벤트를 보냄
            # iframe 내부 textarea에서도 정상 작동
            if use_element:
                try:
                    await element.type(char, delay=0)
                    typed = True
                except Exception:
                    pass

            # 2순위: page.keyboard.insert_text(char) — 메인 페이지용
            if not typed and self.page:
                try:
                    await self.page.keyboard.insert_text(char)
                    typed = True
                except Exception:
                    pass

            # 3순위: element.type(char) 재시도 (포커스 확인 후)
            if not typed and use_element:
                try:
                    await element.click()
                    await asyncio.sleep(0.1)
                    await element.type(char, delay=0)
                    typed = True
                except Exception:
                    pass

            # 4순위 (최후수단): JavaScript InputEvent
            if not typed:
                try:
                    if frame:
                        await frame.evaluate(
                            """(ch) => {
                                const el = document.activeElement;
                                if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                                    const s = el.selectionStart || el.value.length;
                                    const e = el.selectionEnd || el.value.length;
                                    el.value = el.value.substring(0, s) + ch + el.value.substring(e);
                                    el.selectionStart = el.selectionEnd = s + ch.length;
                                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: ch}));
                                } else {
                                    document.execCommand('insertText', false, ch);
                                }
                            }""",
                            char,
                        )
                    else:
                        await self.page.evaluate(
                            """(ch) => {
                                const el = document.activeElement;
                                if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                                    const s = el.selectionStart || el.value.length;
                                    const e = el.selectionEnd || el.value.length;
                                    el.value = el.value.substring(0, s) + ch + el.value.substring(e);
                                    el.selectionStart = el.selectionEnd = s + ch.length;
                                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: ch}));
                                } else {
                                    document.execCommand('insertText', false, ch);
                                }
                            }""",
                            char,
                        )
                except Exception:
                    pass

            # 한 글자 입력 완료 로그 (입력되는 장면이 브라우저에 보임)
            # 3자마다 + 마지막 글자에 진행 상황 출력
            if (i + 1) % 3 == 0 or i == 0:
                progress_pct = int((i + 1) / total * 100)
                typed_so_far = text[:i+1]
                self._log(f"  ⌨️  [{i+1}/{total}자] '{typed_so_far}' ({progress_pct}%)", "info")

        # 타이핑 완료
        await asyncio.sleep(0.5)

    async def _type_unicode_char(self, element, char: str):
        """
        유니코드 문자(한글 등)를 화면에 보이게 입력.
        Playwright keyboard API를 우선 사용하여 브라우저 화면에서
        글자가 하나씩 타이핑되는 것을 시각적으로 볼 수 있음.
        """
        # 1순위: Playwright keyboard API (가장 확실하게 화면에 표시)
        try:
            await self.page.keyboard.insert_text(char)
            return
        except Exception:
            pass

        # 2순위: JavaScript InputEvent로 화면에 표시
        try:
            await element.evaluate(
                "(el, ch) => { "
                "  el.focus(); "
                "  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') { "
                "    const start = el.selectionStart || el.value.length; "
                "    const end = el.selectionEnd || el.value.length; "
                "    el.value = el.value.substring(0, start) + ch + el.value.substring(end); "
                "    el.selectionStart = el.selectionEnd = start + ch.length; "
                "    el.dispatchEvent(new InputEvent('input', { "
                "      bubbles: true, cancelable: true, inputType: 'insertText', data: ch "
                "    })); "
                "  } else { "
                "    document.execCommand('insertText', false, ch); "
                "  } "
                "}",
                char,
            )
        except Exception:
            # 3순위: fallback
            try:
                await element.evaluate(
                    "(el, ch) => { el.value += ch; "
                    "el.dispatchEvent(new Event('input', {bubbles: true})); }",
                    char,
                )
            except Exception:
                pass

    async def _type_in_field(self, selector: str, text: str) -> bool:
        """특정 입력 필드에 타자 치듯 입력"""
        if not self.page:
            return False

        try:
            element = await self.page.wait_for_selector(selector, timeout=5000)
            if element:
                await element.click()
                await asyncio.sleep(0.3)

                # 기존 텍스트 삭제
                await element.press("Control+a")
                await element.press("Backspace")
                await asyncio.sleep(0.2)

                # 타자 치듯 입력 (화면에 실시간으로 보이도록 bring_to_front 포함해 진행)
                await self.bring_to_front()
                await asyncio.sleep(0.12)
                await self._type_like_human(element, text)
                return True
        except Exception as e:
            self._log(f"  필드 입력 실패 ({selector}): {e}", "error")

        return False

    # ──────────────────────────────────────────────────────
    #  viewport 내 위치 확인
    # ──────────────────────────────────────────────────────
    async def _check_in_viewport(self, element, frame=None) -> bool:
        """
        요소가 현재 viewport(화면) 안에 있는지 확인.
        Playwright elementHandle.evaluate로 getBoundingClientRect를 사용.
        """
        try:
            in_view = await element.evaluate("""(el) => {
                const rect = el.getBoundingClientRect();
                const viewH = window.innerHeight || document.documentElement.clientHeight;
                const viewW = window.innerWidth || document.documentElement.clientWidth;
                // 요소가 viewport 안에 최소 1px 이상 노출되어 있는지
                return (
                    rect.bottom > 0 &&
                    rect.top < viewH &&
                    rect.right > 0 &&
                    rect.left < viewW
                );
            }""")
            return bool(in_view)
        except Exception:
            return True  # 확인 실패 시 일단 진행

    # ──────────────────────────────────────────────────────
    #  요소를 화면 중앙으로 부드럽게 스크롤 (iframe 지원)
    # ──────────────────────────────────────────────────────
    async def _scroll_to_element_center(self, element, frame=None) -> bool:
        """요소를 화면 중앙으로 부드럽게 스크롤한다 (작업 장면이 화면에 보이도록).
        - 요소가 속한 프레임 컨텍스트에서 smooth 스크롤 실행
        - viewport 확인 실패 시 CDP scrollIntoViewIfNeeded로 폴백
        성공: True / 완전 실패: False (호출부는 계속 진행 가능)
        """
        if element is None:
            return False
        # 1) 요소의 프레임 기준 부드러운 스크롤 (화면 중앙 정렬)
        try:
            await element.evaluate(
                """(el) => {
                    const r = el.getBoundingClientRect();
                    const doc = document.scrollingElement || document.documentElement;
                    const cur = window.scrollY || doc.scrollTop || 0;
                    const y = r.top + cur - (window.innerHeight / 2) + (r.height / 2);
                    const maxTop = Math.max(0, doc.scrollHeight - window.innerHeight);
                    window.scrollTo({ top: Math.max(0, Math.min(y, maxTop)), behavior: 'smooth' });
                }"""
            )
            await asyncio.sleep(1.2)
        except Exception:
            pass
        # 2) viewport 안에 들어왔는지 확인
        try:
            if await self._check_in_viewport(element):
                return True
        except Exception:
            pass
        # 3) 폴백: CDP scrollIntoViewIfNeeded (내부 스크롤 컨테이너까지 처리)
        try:
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(0.8)
            return True
        except Exception:
            return False

    # ──────────────────────────────────────────────────────
    #  네이버 로그인
    # ──────────────────────────────────────────────────────
    async def login(self, naver_id: str, naver_pw: str) -> bool:
        if not self.page:
            self._log("브라우저가 시작되지 않았습니다.", "error")
            return False

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1) 무조건 네이버 로그인 페이지를 가장 먼저 연다.
        #    아이디/비밀번호를 치기 전에 브라우저에 로그인 화면이
        #    보이는 상태에서 시작하도록 한다.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self._log("네이버 로그인 페이지로 이동 중...", "system")
        self._emit_login_progress("open_login_page", "")
        try:
            await self.page.goto(self.NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.2)
        except Exception as e:
            self._log(f"네이버 로그인 페이지 이동 중 오류: {e}", "warning")

        # 브라우저 창을 가장 앞으로 가져와서 사용자가 화면을 볼 수 있게 함
        await self.bring_to_front()
        await asyncio.sleep(0.4)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 세션이 있어도 로그인 화면이 보이는 상태로 시작했으면,
        # 이미 로그인된 페이지인지 한 번만 확인한다.
        # (로그인 페이지를 먼저 열었으므로 2FA 재발송 방지가 우선)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if self._has_saved_session():
            self._log("저장된 세션 확인 중...", "info")
            try:
                current_url = self.page.url
                page_text = await self.page.evaluate("() => document.body.innerText")
                is_logged = (
                    "nid.naver.com" not in current_url
                    and "login" not in current_url
                    and "로그인" not in page_text[:200]
                )
                if is_logged:
                    self.is_logged_in = True
                    self._log("✅ 저장된 세션으로 자동 로그인 확인! (2FA 불필요)", "success")
                    await self.bring_to_front()
                    return True
                else:
                    self._log("세션이 유효하지 않습니다. 로그인 화면을 다시 표시합니다.", "warning")
            except Exception as e:
                self._log(f"세션 확인 중 오류, 로그인 화면으로 진행합니다: {e}", "warning")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2) 로그인 화면에 아이디/비밀번호를 타자로 치듯 입력
        #    - 입력되는 화면이 실시간으로 보이도록 포커스를 확실히 줌
        #    - fill()로 한 번에 넣지 않고 한 글자씩 입력
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self._log("네이버 로그인 화면 표시 완료. 아이디/비밀번호를 타이핑합니다.", "info")

        # 아이디 입력
        self._emit_login_progress("id_focus", "")
        id_input = None
        for _ in range(3):
            id_input = await self.page.query_selector('input[name="id"]')
            if id_input:
                break
            await asyncio.sleep(0.3)

        if id_input:
            await id_input.click()
            await asyncio.sleep(0.3)
            try:
                await id_input.focus()
            except Exception:
                pass
            await asyncio.sleep(0.15)
            # 기존 텍스트가 있으면 지움
            try:
                await id_input.fill("")
            except Exception:
                pass
            await asyncio.sleep(0.12)
            self._emit_login_progress("id_input", naver_id)
            await self.bring_to_front()
            await asyncio.sleep(0.1)
            self._log(f"  🔤 아이디 입력 시작: '{naver_id}' ({len(naver_id)}자)", "info")
            await self._type_like_human(id_input, naver_id)
            self._log(f"  🔤 아이디 입력 완료: '{naver_id}'", "success")
        else:
            self._log("  ⚠️ 아이디 입력창을 찾지 못했습니다.", "warning")

            await asyncio.sleep(0.4)

            # 비밀번호 입력
        self._emit_login_progress("pw_focus", "")
        pw_input = None
        for _ in range(3):
            pw_input = await self.page.query_selector('input[name="pw"]')
            if pw_input:
                break
            await asyncio.sleep(0.3)

        if pw_input:
            await pw_input.click()
            await asyncio.sleep(0.3)
            try:
                await pw_input.focus()
            except Exception:
                pass
            await asyncio.sleep(0.15)
            try:
                await pw_input.fill("")
            except Exception:
                pass
            await asyncio.sleep(0.12)
            self._emit_login_progress("pw_input", "●" * min(8, len(naver_pw)))
            await self.bring_to_front()
            await asyncio.sleep(0.1)
            self._log("  🔤 비밀번호 입력 시작...", "info")
            await self._type_like_human(pw_input, naver_pw)
            self._log("  🔤 비밀번호 입력 완료", "success")
        else:
            self._log("  ⚠️ 비밀번호 입력창을 찾지 못했습니다.", "warning")

        await asyncio.sleep(0.5)

        self._log("  아이디/비밀번호 입력 완료. 로그인 버튼을 누릅니다...", "info")
        self._emit_login_progress("ready_to_login", "")
        await self.bring_to_front()
        await asyncio.sleep(0.8)

        # 로그인 버튼 클릭
        login_selectors = [
            '#loginBtn_column',
            '#loginBtn_row',
            'button[type="submit"]',
            '.btn_login',
            'button.btn_done',
        ]
        login_btn = None
        for sel in login_selectors:
            login_btn = await self.page.query_selector(sel)
            if login_btn:
                self._log(f"  로그인 버튼 발견 ({sel})", "info")
                break
        if login_btn:
            await login_btn.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)
            await self.bring_to_front()
            await asyncio.sleep(0.3)
            await login_btn.click()
            self._log("  ✅ 로그인 버튼 클릭 완료", "success")
            self._emit_login_progress("login_clicked", "")
        else:
            self._log("  ⚠️ 로그인 버튼을 찾지 못했습니다.", "warning")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3) 로그인 후: 페이지 변경을 한 번만 관찰 (2FA 중복 방지)
        #    절대 evaluate/fetch 등으로 페이지를 건드리지 않음!
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self._log("  ⏳ 페이지 전환 대기 중... (페이지 조작 없음)", "info")

        # 10초 동안 URL 변경만 관찰
        logged_in = False
        for i in range(10):
            await asyncio.sleep(1)
            url = self.page.url
            if "nid.naver.com" not in url or "login" not in url:
                logged_in = True
                self._log(f"  ✅ URL 변경 감지: {url[:60]}", "success")
                break

        if logged_in:
            self.is_logged_in = True
            self._log("네이버 로그인 성공!", "success")
            await self.bring_to_front()
            await self._save_session()
            return True

        # URL 변경 없음 → 2FA 또는 에러
        self._log("  ⏳ 2FA 또는 추가 인증 대기 중...", "info")
        await self.bring_to_front()

        # 최대 120초 동안 URL 변경만 관찰
        for i in range(120):
            await asyncio.sleep(1)
            url = self.page.url
            if "nid.naver.com" not in url or "login" not in url:
                self.is_logged_in = True
                self._log(f"  ✅ 로그인 성공! (URL: {url[:60]})", "success")
                await self._save_session()
                return True
            if i > 0 and i % 30 == 0:
                self._log(f"  ⏳ 로그인 대기 중... ({i}초 경과) - 브라우저에서 인증을 완료하세요", "info")
                self._log("  ⏳ (2FA 코드는 이미 1회 발송됨. 재발송 버튼을 누르지 마세요)", "warning")

        self._log("  ❌ 로그인 시간 초과 (120초)", "error")
        return False

    # ──────────────────────────────────────────────────────
    #  세션 기반 자동 로그인 (브라우저 새로 열었을 때)
    # ──────────────────────────────────────────────────────
    async def login_with_saved_session(self) -> bool:
        """저장된 세션(쿠키)으로 로그인 상태인지 확인하고, 로그인 페이지가
        뜨지 않으면 성공 처리한다. 화면 흐름을 끊지 않기 위해 페이지 우회 없이
        네이버 메인에서 로그인 여부만 가볍게 확인한다."""
        if not self.page:
            self._log("브라우저가 시작되지 않았습니다.", "error")
            return False

        try:
            self._log("저장된 세션으로 로그인 확인 중...", "info")
            await self.page.goto("https://m.naver.com", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            url = self.page.url
            page_text = await self.page.evaluate("() => document.body.innerText")

            # 로그인 페이지로 리다이렉트됐거나 로그인 안내 문구가 있으면 세션 만료
            login_indicators = ["로그인", "로그인이 필요합니다", "회원가입"]
            is_logged = (
                "nid.naver.com" not in url
                and "login" not in url.lower()
                and not any(ind in page_text[:300] for ind in login_indicators)
            )

            if is_logged:
                self.is_logged_in = True
                self._log("✅ 저장된 세션으로 자동 로그인 성공! (2FA 불필요)", "success")
                await self.bring_to_front()
                return True

            self._log("세션이 만료되어 재로그인이 필요합니다.", "warning")
            return False
        except Exception as e:
            self._log(f"세션 확인 중 오류: {e}", "warning")
            return False

    # ──────────────────────────────────────────────────────
    #  댓글 검증 — 블로그에 다시 접속해서 내 댓글 확인
    # ──────────────────────────────────────────────────────
    async def verify_comment(self, blog_id: str, comment_text: str = "", post_url: str = "") -> dict:
        """
        작성한 댓글이 실제로 상대 블로그에 올라갔는지 검증.
        실제 게시글 페이지(댓글이 달린 위치)를 우선 확인하고,
        실패 시 블로그 메인(모바일/PC)을 순차 확인한다.
        Returns: {"verified": bool, "found": bool, "comment_count": int, "message": str}
        """
        result = {"verified": False, "found": False, "comment_count": 0, "message": ""}

        if not self.page:
            result["message"] = "브라우저 미시작"
            return result

        # ── 확인 대상 URL 후보 ──
        # 1순위: 실제 댓글이 달린 게시글 페이지 (모바일/PC 둘 다)
        urls_to_try = []
        if post_url:
            urls_to_try.append(self._to_mobile_url(post_url))
            urls_to_try.append(post_url)
        # 2순위 폴백: 블로그 메인
        urls_to_try.append(f"{self.BLOG_MOBILE_HOME}/{blog_id}")
        urls_to_try.append(f"{self.BLOG_HOME}/{blog_id}")

        for blog_url in urls_to_try:
            # URL 중복 제거
            if blog_url in urls_to_try[:urls_to_try.index(blog_url)]:
                continue
            try:
                await self.page.goto(blog_url, wait_until="domcontentloaded", timeout=15000)
                # 모바일 블로그는 댓글 영역이 지연 로딩되므로 networkidle까지 잠깐 대기
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(4)

                # 현재 URL 기록 (리다이렉트 확인)
                current_url = self.page.url
                self._log(f"  🔍 검증 URL: {current_url[:80]}", "info")

                comment_found = False
                total_comments = 0

                for frame in self.page.frames:
                    try:
                        comment_data = await frame.evaluate("""() => {
                            const result = { count: 0, texts: [] };

                            // 댓글 수 — 다양한 선택자 시도
                            const countEls = document.querySelectorAll(
                                '.u_cbox_count, .comment_count, .cbox_count, '
                                + '[class*="comment_count"], [class*="cbox_count"]'
                            );
                            for (const el of countEls) {
                                const m = el.textContent.match(/([0-9,]+)/);
                                if (m) {
                                    result.count = Math.max(result.count, parseInt(m[1].replace(/,/g, '')));
                                }
                            }

                            // 댓글 내용 수집 — 모바일/PC 모두 대응
                            const commentEls = document.querySelectorAll(
                                '.u_cbox_contents li, .u_cbox_comment_box .u_cbox_text, '
                                + '.comment_text, .cbox_comment, '
                                + '[class*="comment_text"], [class*="u_cbox_text"], '
                                + '.u_cbox_contents .u_cbox_text'
                            );
                            for (const el of commentEls) {
                                const t = el.textContent.trim();
                                if (t && t.length > 3) result.texts.push(t);
                            }

                            return result;
                        }""")

                        if comment_data.get("count", 0) > 0:
                            total_comments = max(total_comments, comment_data["count"])

                        if comment_text and comment_data.get("texts"):
                            search_text = comment_text[:15]
                            for txt in comment_data["texts"]:
                                if search_text in txt:
                                    comment_found = True
                                    self._log(f"  ✅ 검증 매칭 성공: '{search_text}' in '{txt[:40]}...'", "success")
                                    break

                    except Exception:
                        pass

                # 전체 페이지 텍스트에서도 검색
                if not comment_found and comment_text:
                    try:
                        page_text = await self.page.evaluate("() => document.body.innerText")
                        search_text = comment_text[:15]
                        if search_text in page_text:
                            comment_found = True
                            self._log(f"  ✅ 검증 페이지 텍스트 매칭 성공", "success")
                    except Exception:
                        pass

                # URL 호스트 안전 추출 (형식 이상 시 IndexError 방지)
                try:
                    url_host = current_url.split('/')[2]
                except (IndexError, AttributeError):
                    url_host = current_url[:40]

                if comment_found:
                    result["verified"] = True
                    result["found"] = True
                    result["comment_count"] = total_comments
                    result["message"] = f"댓글 확인 완료 (총 {total_comments}개) - {url_host}"
                    return result
                elif total_comments > 0:
                    result["verified"] = True
                    result["found"] = False
                    result["comment_count"] = total_comments
                    result["message"] = f"댓글 영역 확인됨 (총 {total_comments}개, 텍스트 매칭 미확인) - {url_host}"
                    return result
                else:
                    self._log(f"  ⚠️ 검증 URL={url_host} 댓글 없음, 다음 URL 시도...", "warning")

            except Exception as e:
                self._log(f"  ⚠️ 검증 URL 실패 ({blog_url[:60]}): {e}", "warning")
                continue

        result["message"] = "댓글 영역 미확인 (비공개 또는 로그인 필요)"
        return result

    # ──────────────────────────────────────────────────────
    #  댓글 작성 (타자 치듯)
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _to_mobile_url(url: str) -> str:
        """blog.naver.com URL을 m.blog.naver.com 모바일 URL로 변환"""
        if not url:
            return url
        # 이미 모바일 URL이면 그대로 반환
        if "m.blog.naver.com" in url:
            return url
        # blog.naver.com → m.blog.naver.com
        mobile = url.replace("https://blog.naver.com", "https://m.blog.naver.com")
        mobile = mobile.replace("http://blog.naver.com", "https://m.blog.naver.com")
        return mobile

    async def write_comment(self, blog_id: str, comment: str, my_blog_id: str = "", post_url: str = "", neighbor_message: str = "", stop_flag=None, do_neighbor: bool = True, do_like: bool = True, do_comment: bool = True) -> bool:
        """
        전체 자동화 흐름 (브라우저에서 모든 과정이 보이도록):
        1단계: 게시글 접속 + 페이지 상단으로 스크롤
        2단계: 서로이웃추가 → 팝업 → "서로이웃을 신청합니다" 선택 → 메시지 입력 → 신청   (do_neighbor=True일 때만)
        3단계: 공감(하트) 버튼 탐색 → scrollIntoView → viewport 확인 → 클릭              (do_like=True일 때만)
        4단계: 댓글 입력창 탐색 → scrollIntoView → viewport 확인 → 타이핑                (do_comment=True일 때만)
        5단계: 댓글 등록 버튼 클릭

        ※ do_neighbor/do_like/do_comment로 각 단계 선택 실행 가능 (작업별 보조)
        """
        if not self.page or not self.is_logged_in:
            self._log("로그인이 필요합니다.", "error")
            return False

        # 중지 체크 헬퍼
        def _stopped():
            return stop_flag is not None and stop_flag()

        try:
            if _stopped():
                self._log("  ⏹️  사용자에 의해 중지됨", "warning")
                return False

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 0단계: 브라우저 창을 항상 앞으로 (작업 시작 전)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            await self.bring_to_front()
            await asyncio.sleep(1)
            if blog_id:
                self._log(f"  ═══ 블로그 {blog_id} 작업 시작 ═══", "system")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 1단계: 게시글 페이지로 직접 접속 (모바일 URL 사용)
            # ※ open_post로 이미 접속한 경우(blog_id와 post_url이 모두 빈 값이면) 접속 건너뜀
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if blog_id or post_url:
                target_url = self._to_mobile_url(post_url)
                if not target_url:
                    blog_url = f"https://m.blog.naver.com/{blog_id}"
                    self._log(f"  📄 블로그 메인 접속: {blog_id}", "info")
                    try:
                        await self.page.goto(blog_url, wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        await self.page.goto(blog_url, wait_until="load", timeout=15000)
                    await asyncio.sleep(3)
                    await self.bring_to_front()
                    target_url = await self._find_post_url(blog_id)
                    if not target_url:
                        self._log(f"  ❌ 포스트 URL 미발견: {blog_id}", "warning")
                        return False
                    target_url = self._to_mobile_url(target_url)

                self._log(f"  📄 게시글 접속: {target_url[:80]}", "info")
                try:
                    await self.page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    try:
                        await self.page.goto(target_url, wait_until="load", timeout=15000)
                    except Exception:
                        self._log(f"  ❌ 페이지 로드 실패: {target_url[:60]}", "error")
                        return False

                # 페이지 로드 대기 + 브라우저 창 앞으로
                await asyncio.sleep(3)
                await self.bring_to_front()
                await asyncio.sleep(1)
                self._log(f"  📍 현재 URL: {self.page.url[:80]}", "info")

                # 에러 페이지 감지
                try:
                    page_text = await self.page.content()
                    error_patterns = ["페이지 주소를 확인", "존재하지 않는 페이지", "삭제된 게시물"]
                    for ep in error_patterns:
                        if ep in page_text:
                            self._log(f"  ❌ 에러 페이지 감지: {ep}", "error")
                            return False
                except Exception:
                    pass

                # 페이지 상단으로 스크롤 (서로이웃추가 버튼이 보이도록)
                self._log(f"  📜 페이지 상단으로 스크롤 중...", "info")
                await self.page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(2)
                await self.bring_to_front()
                await asyncio.sleep(1)
                self._log(f"  📜 페이지 상단 도달! (서로이웃추가 버튼이 보이는 위치)", "success")

            if _stopped():
                self._log("  ⏹️  사용자에 의해 중지됨", "warning")
                return False

            if not do_neighbor:
                self._log(f"  🤝  서로이웃 단계 건너뜀 (선택 해제)", "info")
                # 이웃 단계를 건너뛰어도 공감/댓글 단계는 계속 진행된다.
                neighbor_btn = None

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 2단계: 서로이웃추가 버튼 탐색 → scrollIntoView → 클릭
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if do_neighbor:
                self._log(f"  🤝  [1/3] 서로이웃 버튼 찾는 중...", "info")

            neighbor_selectors = [
                # 텍스트 매칭 (서로이웃 우선 — 미클릭 상태)
                "a:has-text('서로이웃추가')",
                "button:has-text('서로이웃추가')",
                "a:has-text('서로이웃')",
                "button:has-text('서로이웃')",
                # 클래스 기반
                "a.btn_follow",
                ".btn_follow",
                "button.btn_follow",
                "a[data-testid='follow']",
                "button[data-testid='follow']",
                # 구조 기반
                ".blog2_neighbor a",
                "#neighborAddButton",
                "a[href*='neighbor']",
                ".follow_btn",
                "a.btn_neighbor_add",
                ".neighbor_add",
                "button[data-testid='neighbor-add']",
                # 기타 텍스트
                "a:has-text('이웃')",
                "button:has-text('이웃')",
                "a:has-text('팔로우')",
                "button:has-text('팔로우')",
            ]

            neighbor_clicked = False
            neighbor_btn = None
            # ── [v3.4.2 신규] 서로이웃 비활성 판정 플래그:
            #   "이웃 추가(단방향)"만 있고 "서로이웃추가"가 없는 블로그의 경우
            #   불필요한 예외 대신 Skip 신호를 남겨 다음 블로그로 안내한다.
            neighbor_unavailable_skip = False

            # ──────────────────────────────────────────────
            # [v3.4.3 신규] 서로이웃추가 버튼 비활성(Disabled) 판정 헬퍼
            #  - DOM 속성(disabled/aria-disabled/readonly) 및 CSS 비활성 클래스,
            #    pointer-events:none, 요소 크기 0 등 "클릭 불가" 상태를 모두 검사
            #  - Returns: (클릭 가능 여부, 사유 문자열)
            # ──────────────────────────────────────────────
            async def _is_neighbor_btn_clickable(btn, frame=None) -> tuple:
                check_frame = frame if (frame is not None) else self.page
                try:
                    info = await check_frame.evaluate(
                        """(el) => {
                            // 1) 표준 비활성 속성 (button/a/div textarea 등 공통)
                            if (el.getAttribute('disabled') !== null || el.disabled === true) {
                                return {clickable: false, reason: 'disabled 속성'};
                            }
                            if (el.getAttribute('aria-disabled') === 'true') {
                                return {clickable: false, reason: 'aria-disabled'};
                            }
                            if (el.getAttribute('readonly') !== null) {
                                return {clickable: false, reason: 'readonly 속성'};
                            }

                            const cls = (el.className || '') + '';
                            const lc = cls.toLowerCase();

                            // 2) 클래스 기반 비활성 표시 (네이버 공통 + 널리 쓰이는 규칙)
                            const disabledClassHints = [
                                'disabled', 'off', 'inactive', 'hidden', 'blind',
                                'not_clickable', 'notclickable', 'unclickable',
                                'btn_disabled', 'disable', 'is-disabled', '_disabled',
                            ];
                            if (disabledClassHints.some(h => lc.includes(h))) {
                                return {clickable: false, reason: '비활성 클래스(' + cls.trim().slice(0, 60) + ')'};
                            }

                            // 3) 클릭 불가 CSS (pointer-events/visibility/opacity)
                            const cs = getComputedStyle(el);
                            if (cs.pointerEvents === 'none') {
                                return {clickable: false, reason: 'pointer-events:none'};
                            }
                            if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) {
                                return {clickable: false, reason: '요소가 화면에 표시되지 않음'};
                            }

                            // 4) 요소 크기 0 → 클릭 불가
                            const rc = el.getBoundingClientRect();
                            if (rc.width <= 0 || rc.height <= 0) {
                                return {clickable: false, reason: '요소 크기 0'};
                            }

                            // 5) 부 모 중 비활성 부모가 있으면 클릭이 봉쇄된다
                            let p = el.parentElement, depth = 0;
                            while (p && depth < 4) {
                                pcs = p.disabled === true
                                      || p.getAttribute('disabled') !== null
                                      || p.getAttribute('aria-disabled') === 'true';
                                // 클래스 기반 부모 비활성 (off/disabled)
                                let pcls = ((p.className || '') + '').toLowerCase();
                                let pdis = pcs || ['off'].some(h => pcls.includes(h)) || pcls.includes('disabled');
                                if (pdis) {
                                    return {clickable: false, reason: '부모요소 비활성'};
                                }
                                p = p.parentElement; depth++;
                            }

                            return {clickable: true, reason: '클릭 가능 (활성 상태)'};
                        }""", btn)
                except Exception as e:
                    return (True, f"판정 실패(안전 진행): {type(e).__name__}")
                reason = str(info.get("reason", "")) if isinstance(info, dict) else str(info)
                clickable = bool(info.get("clickable", True)) if isinstance(info, dict) else True
                return (clickable, reason)

            # 메인 페이지에서 탐색
            self._log(f"  🤝  페이지에서 서로이웃추가 버튼 탐색 중...", "info")
            for sel in neighbor_selectors:
                try:
                    btns = await self.page.query_selector_all(sel)
                    for btn in btns:
                        visible = await btn.is_visible()
                        if visible:
                            neighbor_btn = btn
                            # 버튼 텍스트 확인 (이미 이웃인 경우 필터링)
                            try:
                                btn_text = await btn.inner_text()
                                if btn_text and "서로이웃" in btn_text:
                                    self._log(f"  🤝  서로이웃추가 버튼 발견! 텍스트: '{btn_text.strip()}'", "success")
                                    break
                                elif btn_text and "이웃" in btn_text and "추가" in btn_text:
                                    self._log(f"  🤝  이웃추가 버튼 발견! 텍스트: '{btn_text.strip()}'", "success")
                                    break
                                elif btn_text and ("팔로우" in btn_text or "친구" in btn_text):
                                    # [v3.4.2] 단방향 '이웃추가/팔로우'만 있는 블로그 표시
                                    # (버튼 자체는 기억하되, 이후 서로이웃 메뉴가 없으면 Skip)
                                    self._log(f"  🤝  팔로우/단방향 이웃추가 버튼 발견! 텍스트: '{btn_text.strip()}'", "success")
                                    break
                                else:
                                    neighbor_btn = None  # 텍스트 불일치 → 계속 탐색
                            except Exception:
                                pass
                    if neighbor_btn:
                        break
                except Exception:
                    pass

            # iframe에서도 탐색
            if not neighbor_btn:
                self._log(f"  🤝  iframe에서 서로이웃추가 버튼 탐색 중...", "info")
                for frame in self.page.frames:
                    if frame == self.page.main_frame:
                        continue
                    for sel in neighbor_selectors:
                        try:
                            btns = await frame.query_selector_all(sel)
                            for btn in btns:
                                visible = await btn.is_visible()
                                if visible:
                                    neighbor_btn = btn
                                    break
                            if neighbor_btn:
                                break
                        except Exception:
                            pass
                    if neighbor_btn:
                        break

            if neighbor_btn:
                # ──────────────────────────────────────────────
                # [v3.4.3 신규] 클릭 직전 비활성(Disabled) 여부 최종 판정
                #  - 버튼이 비활성/클릭불가 상태면 예외 없이 즉시 Skip
                #  - 활성 상태면 기존 로직 그대로 진행 (1행의 동작도 유지)
                # ──────────────────────────────────────────────
                like_neighbor_frame = neighbor_btn.owner_frame if hasattr(neighbor_btn, "owner_frame") else None
                clickable, disabled_reason = await _is_neighbor_btn_clickable(neighbor_btn, like_neighbor_frame)
                if not clickable:
                    neighbor_unavailable_skip = True
                    self._log(
                        f"  🤝  [1/3] 서로이웃추가 버튼이 비활성 상태입니다 ({disabled_reason}) → 이 대상은 Skip 처리",
                        "info",
                    )
                    # Skip 시에는 이웃 클릭을 시도하지 않고 공감/댓글 단계로 그대로 넘어간다.
                    neighbor_btn = None

            if neighbor_btn:
                # 서로이웃추가 버튼을 화면 중앙으로 스크롤
                self._log(f"  🤝  [1/3] 서로이웃추가 버튼을 화면 중앙으로 스크롤 중...", "info")
                try:
                    await neighbor_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(3)  # 사용자가 준비 상태(미클릭)를 볼 수 있도록 충분한 대기
                except Exception:
                    pass

                await self.bring_to_front()
                await asyncio.sleep(1)  # 브라우저 창 포커스 확인

                # viewport 확인
                neighbor_in_viewport = False
                try:
                    neighbor_in_viewport = await self._check_in_viewport(neighbor_btn)
                except Exception:
                    neighbor_in_viewport = True

                # ── 팝업 처리용 셀렉터 (본 경로/재시도 경로 공용) ──
                # ※ 여기서 정의하지 않으면 재시도 분기에서 NameError가 나서
                #   "서로이웃을 신청합니다" 선택과 메시지 입력, 신청 클릭이 모두 건너뛰어진다.
                mutual_selectors = [
                    # 텍스트 매칭 (가장 정확)
                    "text='서로이웃을 신청합니다'",
                    "label:has-text('서로이웃을 신청합니다')",
                    "span:has-text('서로이웃을 신청합니다')",
                    "div:has-text('서로이웃을 신청합니다')",
                    "a:has-text('서로이웃을 신청합니다')",
                    # 라디오/체크박스 기반
                    "input[type='radio'][name*='neighbor']",
                    "input[type='checkbox'][name*='neighbor']",
                    "input[type='radio'][name*='mutual']",
                    "input[type='checkbox'][name*='mutual']",
                    # 부분 텍스트 매칭
                    "label:has-text('서로이웃')",
                    "span:has-text('서로이웃')",
                    # 클래스 기반 (네이버 레이어 팝업)
                    ".u_layer_radio label:first-child",
                    ".layer_radio label:first-child",
                    ".popup_radio label:first-child",
                    ".layer_radio_input label:first-child",
                ]
                apply_selectors = [
                    "button:has-text('신청')",
                    "button:has-text('확인')",
                    "a:has-text('신청')",
                    "a:has-text('확인')",
                    ".btn_ok",
                    "button.confirm",
                    "button[data-testid='confirm']",
                    ".u_layer_btn a",
                    ".layer_btn button",
                    "button:has-text('서로이웃 신청')",
                ]

                if neighbor_in_viewport:
                    self._log(f"  🤝  [1/3] 서로이웃추가 버튼 위치 확인! (미클릭 상태) → 커서 이동 후 클릭...", "info")
                    await asyncio.sleep(1.5)  # 클릭 전 사용자가 준비 상태를 볼 수 있도록
                    await self.bring_to_front()
                    await asyncio.sleep(0.5)
                    # 사람처럼 커서를 서로이웃 버튼으로 이동시킨 뒤 클릭 (화면에 보임)
                    await self.human_move_and_click(neighbor_btn)
                    neighbor_clicked = True
                    self._log(f"  🤝  [1/3] 이웃추가 버튼 클릭 완료!", "success")

                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # 🤝 [1/3] "서로이웃을 신청합니다" 팝업 선택 처리
                    # 팝업/레이어가 나타날 때까지 충분히 대기
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    await asyncio.sleep(3)  # 팝업 표시 대기
                    self._log(f"  🤝  [1/3] 서로이웃 팝업 확인 중...", "info")

                    # 팝업에서 "서로이웃을 신청합니다" 요소 찾기
                    mutual_neighbor_selected = False

                    # (mutual_selectors는 분기 이전에서 공용 정의됨)

                    # 메인 페이지에서 탐색
                    for sel in mutual_selectors:
                        try:
                            el = await self.page.query_selector(sel)
                            if el and await el.is_visible():
                                self._log(f"  🤝  [1/3] '서로이웃을 신청합니다' 요소 발견! ({sel})", "success")
                                await el.scroll_into_view_if_needed()
                                await asyncio.sleep(1)
                                await el.click()
                                await asyncio.sleep(1)
                                mutual_neighbor_selected = True
                                self._log(f"  🤝  [1/3] '서로이웃을 신청합니다' 선택 완료!", "success")
                                break
                        except Exception:
                            pass

                    # iframe에서도 탐색
                    if not mutual_neighbor_selected:
                        for frame in self.page.frames:
                            if frame == self.page.main_frame:
                                continue
                            for sel in mutual_selectors:
                                try:
                                    el = await frame.query_selector(sel)
                                    if el and await el.is_visible():
                                        self._log(f"  🤝  [1/3] iframe에서 '서로이웃을 신청합니다' 발견!", "success")
                                        await el.click()
                                        await asyncio.sleep(1)
                                        mutual_neighbor_selected = True
                                        self._log(f"  🤝  [1/3] '서로이웃을 신청합니다' 선택 완료! (iframe)", "success")
                                        break
                                except Exception:
                                    pass
                            if mutual_neighbor_selected:
                                break

                    # 선택 상태 검증 — DOM에서 실제로 선택되었는지 확인
                    if mutual_neighbor_selected:
                        self._log(f"  🤝  [1/3] 선택 상태 확인 중...", "info")
                        await asyncio.sleep(1)
                        is_checked = False
                        try:
                            is_checked = await self.page.evaluate("""() => {
                                // 라디오/체크박스 checked 확인
                                const radios = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                                for (const r of radios) {
                                    if (r.checked) return true;
                                }
                                // aria-checked 확인
                                const ariaChecked = document.querySelectorAll('[aria-checked="true"]');
                                if (ariaChecked.length > 0) return true;
                                // selected/active 클래스 확인
                                const selected = document.querySelectorAll('.selected, .active, .checked, [class*="selected"], [class*="active"]');
                                if (selected.length > 0) return true;
                                return false;
                            }""")
                        except Exception:
                            is_checked = True  # 확인 실패 시 일단 진행

                        if is_checked:
                            self._log(f"  🤝  [1/3] ✅ 선택 상태 확인 완료! (서로이웃 선택됨)", "success")
                        else:
                            self._log(f"  🤝  [1/3] ⚠️ 선택 상태 미확인 (DOM에서 확인 불가, 진행)", "warning")
                    else:
                        self._log(f"  🤝  [1/3] ⚠️ '서로이웃을 신청합니다' 요소 미발견", "warning")

                    await asyncio.sleep(1.5)  # 선택 후 충분한 대기

                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # 🤝 [1/3] 서로이웃신청 메시지 입력
                    # 팝업의 메시지 입력창에 랜덤 메시지를 한 글자씩 입력
                    # 브라우저 화면에서 사람이 직접 타이핑하는 장면이 실시간으로 보임
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    if neighbor_message:
                        self._log(f"  🤝  [1/3] 신청 메시지 입력 중...", "info")
                        msg_input = None
                        msg_frame = None

                        # 메시지 입력창 selector 탐색
                        msg_selectors = [
                            "textarea",
                            "textarea[placeholder*='메시지']",
                            "textarea[placeholder*='신청']",
                            "textarea[placeholder*='인사']",
                            "textarea[placeholder*='글']",
                            "input[type='text']",
                            ".u_layer textarea",
                            ".layer textarea",
                            ".popup textarea",
                            ".neighbor_layer textarea",
                            ".blog2_neighbor textarea",
                            "textarea.urello_textarea",
                        ]

                        # 메인 페이지에서 탐색
                        for sel in msg_selectors:
                            try:
                                elements = await self.page.query_selector_all(sel)
                                for el in elements:
                                    if await el.is_visible():
                                        msg_input = el
                                        msg_frame = self.page
                                        self._log(f"  🤝  [1/3] 메시지 입력창 발견! ({sel})", "success")
                                        break
                            except Exception:
                                pass
                            if msg_input:
                                break

                        # iframe에서도 탐색
                        if not msg_input:
                            for frame in self.page.frames:
                                if frame == self.page.main_frame:
                                    continue
                                for sel in msg_selectors:
                                    try:
                                        elements = await frame.query_selector_all(sel)
                                        for el in elements:
                                            if await el.is_visible():
                                                msg_input = el
                                                msg_frame = frame
                                                self._log(f"  🤝  [1/3] 메시지 입력창 발견! (iframe: {sel})", "success")
                                                break
                                    except Exception:
                                        pass
                                    if msg_input:
                                        break
                                if msg_input:
                                    break

                        if msg_input:
                            # 메시지 입력창을 화면 중앙으로 스크롤
                            try:
                                await msg_input.scroll_into_view_if_needed()
                                await asyncio.sleep(1.5)
                            except Exception:
                                pass

                            # 메시지 입력창 클릭 → 포커스 (사람처럼 커서 이동)
                            self._log(f"  🤝  [1/3] 메시지 입력창 클릭 중... (커서 이동)", "info")
                            await self.human_move_and_click(msg_input)
                            await asyncio.sleep(1.5)  # 포커스 후 커서 활성화 대기
                            self._log(f"  🤝  [1/3] 메시지 입력창 포커스 완료!", "success")

                            # 기존 텍스트 삭제
                            try:
                                await self.page.keyboard.press("Control+a")
                                await asyncio.sleep(0.2)
                                await self.page.keyboard.press("Backspace")
                                await asyncio.sleep(0.3)
                            except Exception:
                                try:
                                    await msg_input.fill("")
                                    await asyncio.sleep(0.3)
                                except Exception:
                                    pass

                            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                            # 한 글자씩 타이핑 — 브라우저 화면에 실시간으로 표시
                            # element.type(char) 사용 → 메인/iframe 모두 작동
                            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                            self._log(f"  🤝  [1/3] 메시지 한 글자씩 입력 시작: '{neighbor_message[:30]}...'", "info")
                            msg_total = len(neighbor_message)
                            for mi, mchar in enumerate(neighbor_message):
                                # 글자별 딜레이 (사람이 직접 타이핑하는 속도)
                                if mchar in ('.', '!', '?', ',', '~'):
                                    mdelay = random.uniform(0.25, 0.50)
                                elif mchar == ' ':
                                    mdelay = random.uniform(0.15, 0.30)
                                else:
                                    mdelay = random.uniform(0.12, 0.28)

                                # 가끔 생각하는 시간 (8% 확률)
                                if random.random() < 0.08:
                                    mpause = random.uniform(0.4, 1.0)
                                    await asyncio.sleep(mpause)

                                await asyncio.sleep(mdelay)

                                # element.type(char)으로 한 글자 입력 (브라우저 화면에 보임)
                                try:
                                    await msg_input.type(mchar, delay=0)
                                except Exception:
                                    try:
                                        await self.page.keyboard.insert_text(mchar)
                                    except Exception:
                                        pass

                                # 5자마다 진행 로그
                                if (mi + 1) % 5 == 0 or mi == msg_total - 1:
                                    msg_so_far = neighbor_message[:mi+1]
                                    self._log(f"  🤝  [{mi+1}/{msg_total}자] '{msg_so_far}'", "info")

                            await asyncio.sleep(1)  # 타이핑 완료 후 대기
                            self._log(f"  🤝  [1/3] ✅ 메시지 입력 완료!", "success")
                        else:
                            self._log(f"  🤝  [1/3] ⚠️ 메시지 입력창 미발견 (메시지 없이 신청)", "warning")
                    else:
                        self._log(f"  🤝  [1/3] 신청 메시지 없음 (메시지 입력 건너뜀)", "info")

                    await asyncio.sleep(1)  # 신청 전 최종 대기

                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # 신청/확인 버튼 클릭
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    self._log(f"  🤝  [1/3] 신청 버튼 탐색 중...", "info")
                    apply_btn = None

                    # 메인 페이지와 모든 iframe에서 탐색
                    for target_frame in [self.page] + [f for f in self.page.frames if f != self.page.main_frame]:
                        for sel in apply_selectors:
                            try:
                                btn = await target_frame.query_selector(sel)
                                if btn and await btn.is_visible():
                                    btn_text = await btn.inner_text()
                                    if btn_text and ("신청" in btn_text or "확인" in btn_text):
                                        apply_btn = btn
                                        self._log(f"  🤝  [1/3] 신청 버튼 발견: '{btn_text.strip()}' ({sel})", "info")
                                        break
                            except Exception:
                                pass
                        if apply_btn:
                            break

                    if apply_btn:
                        try:
                            await apply_btn.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                        except Exception:
                            pass
                        # 사람처럼 커서를 신청 버튼으로 이동시킨 뒤 클릭 (화면에 보임)
                        await self.human_move_and_click(apply_btn)
                        await asyncio.sleep(3)  # 결과 대기
                        self._log(f"  🤝  [1/3] ✅ 신청 버튼 클릭 완료!", "success")

                        # 결과 확인
                        try:
                            result_text = await self.page.evaluate("() => document.body.innerText")
                            if "신청완료" in result_text or "신청 완료" in result_text:
                                self._log(f"  🤝  [1/3] ✅ 서로이웃 신청 결과 확인!", "success")
                            elif "이미" in result_text and ("이웃" in result_text or "신청" in result_text):
                                self._log(f"  🤝  [1/3] ℹ️ 이미 신청된 이웃입니다.", "info")
                            else:
                                self._log(f"  🤝  [1/3] ✅ 신청 처리 완료", "success")
                        except Exception:
                            self._log(f"  🤝  [1/3] ✅ 신청 처리 완료", "success")
                    else:
                        self._log(f"  🤝  [1/3] ⚠️ 신청 버튼 미발견", "warning")
                else:
                    self._log(f"  ⚠️  서로이웃추가 버튼이 viewport 밖 → 재스크롤 시도...", "warning")
                    try:
                        await neighbor_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        await self.bring_to_front()
                        await asyncio.sleep(0.5)
                        await neighbor_btn.click()
                        neighbor_clicked = True
                        self._log(f"  🤝  [1/3] ✅ 서로이웃추가 클릭 완료! (재시도)", "success")

                        # 재시도 후에도 "서로이웃을 신청합니다" 팝업 처리
                        await asyncio.sleep(3)
                        self._log(f"  🤝  [1/3] 서로이웃 팝업 확인 중... (재시도)", "info")
                        mutual_neighbor_selected_retry = False
                        for sel in mutual_selectors:
                            try:
                                el = await self.page.query_selector(sel)
                                if el and await el.is_visible():
                                    await el.click()
                                    await asyncio.sleep(1)
                                    mutual_neighbor_selected_retry = True
                                    self._log(f"  🤝  [1/3] '서로이웃을 신청합니다' 선택 완료! (재시도)", "success")
                                    break
                            except Exception:
                                pass
                        if not mutual_neighbor_selected_retry:
                            for frame in self.page.frames:
                                if frame == self.page.main_frame:
                                    continue
                                for sel in mutual_selectors:
                                    try:
                                        el = await frame.query_selector(sel)
                                        if el and await el.is_visible():
                                            await el.click()
                                            await asyncio.sleep(1)
                                            mutual_neighbor_selected_retry = True
                                            self._log(f"  🤝  [1/3] '서로이웃을 신청합니다' 선택 완료! (iframe 재시도)", "success")
                                            break
                                    except Exception:
                                        pass
                                if mutual_neighbor_selected_retry:
                                    break

                        await asyncio.sleep(1.5)
                        # 신청 버튼 클릭
                        for target_frame in [self.page] + [f for f in self.page.frames if f != self.page.main_frame]:
                            for sel in apply_selectors:
                                try:
                                    btn = await target_frame.query_selector(sel)
                                    if btn and await btn.is_visible():
                                        btn_text = await btn.inner_text()
                                        if btn_text and ("신청" in btn_text or "확인" in btn_text):
                                            await btn.click()
                                            await asyncio.sleep(3)
                                            self._log(f"  🤝  [1/3] ✅ 신청 버튼 클릭 완료! (재시도)", "success")
                                            break
                                except Exception:
                                    pass
                            else:
                                continue
                            break
                    except Exception:
                        self._log(f"  ⚠️  서로이웃추가 클릭 실패 (건너뜀)", "warning")
            else:
                # ──────────────────────────────────────────────
                # [v3.4.2 신규] 서로이웃 비활성/단방향만 있는 블로그 → Skip
                #  - "서로이웃추가" 버튼이 전혀 없고, 페이지의 이웃 버튼들이
                #    단방향 '이웃 추가' / '팔로우'만 가리키거나 서로이웃을
                #    받을 수 없는 상태(비공개·이웃제한 등)면 예외를 만들지 않고
                #    Skip 신호를 남긴 뒤(“미발견” 로그는 기존 톤 유지)
                #    공감/댓글 후 다음 블로그로 넘어간다.
                #  - 페이지 안내 문구가 서로이웃 불가를 명시하면 명확히 표시.
                # ──────────────────────────────────────────────
                neighbor_unavailable_skip = True
                try:
                    page_text_probe = await self.page.evaluate("() => document.body.innerText") or ""
                except Exception:
                    page_text_probe = ""
                if any(ph in page_text_probe for ph in (
                    "서로이웃", "비공개 블로그", "이웃추가가 제한", "이웃 신청 불가",
                    "이웃을 받을 수 없", "서로이웃을 받을 수 없",
                    "수락 설정", "이웃 설정", "가입 허용",
                )):
                    if "서로이웃" not in page_text_probe:
                        self._log("  🤝  [1/3] 서로이웃 기능이 비활성/제한된 블로그입니다 → 이 대상은 Skip 처리", "info")
                    else:
                        # 서로이웃 안내 문구는 있지만 버튼이 없는 경우 — 이미 이웃이거나
                        # 단방향 전용으로 보아도 Skip 방침은 동일. 예외로 만들지 않는다.
                        self._log("  🤝  [1/3] 서로이웃추가 가능 상태가 아닌 것으로 판단 → 이 대상은 Skip 처리", "info")
                else:
                    self._log("  🤝  [1/3] 서로이웃 버튼 미발견 (Skip 신호 유지 — 예외 없이 다음 단계 진행)", "warning")

            if _stopped():
                self._log("  ⏹️  사용자에 의해 중지됨", "warning")
                return False

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # ❤️ [2/3] 공감(하트) 버튼 탐색 → 점진적 스크롤 → 클릭 → 상태 확인
            # (서로이웃추가 후 현재 위치에서 아래로 부드럽게 내려가며 공감 버튼 찾음)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if do_like:
                self._log(f"  ❤️  [2/3] 공감 버튼을 찾기 위해 아래로 이동 중...", "info")
                await self.bring_to_front()
                await asyncio.sleep(1)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 서로이웃 신청 팝업/레이어가 남아있으면 닫기
            # 팝업이 열려있으면 스크롤이 차단되어 공감 위치로 이동 불가
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            try:
                # ESC 키로 팝업 닫기 시도
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except Exception:
                pass

            # 닫기 버튼(X, 닫기 등) 탐색 및 클릭
            close_selectors = [
                "button.u_layer_close",
                ".u_layer_close",
                "button.close_layer",
                ".layer_close",
                "button[class*='close']",
                "a[class*='close']",
                ".popup_close",
                "button[aria-label='닫기']",
                "button[title='닫기']",
                "span.close",
                "button.close",
                "a.close",
            ]
            for close_sel in close_selectors:
                try:
                    close_btn = await self.page.query_selector(close_sel)
                    if close_btn and await close_btn.is_visible():
                        await close_btn.click()
                        self._log(f"  ❤️  팝업 닫기 완료 ({close_sel})", "info")
                        await asyncio.sleep(1)
                        break
                except Exception:
                    pass

            # ESC 한 번 더 눌러서 남은 팝업 닫기
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except Exception:
                pass

            # 페이지 높이 및 viewport 높이 확인
            try:
                page_height = await self.page.evaluate("() => document.documentElement.scrollHeight")
                viewport_height = await self.page.evaluate("() => window.innerHeight")
            except Exception:
                page_height = 5000
                viewport_height = 915

            like_selectors = [
                # ── 모바일 네이버 블로그 실제 DOM 구조 (2025.09 개편 공감 UI 기준) ──
                # 클릭 대상: emote(표정/하트) 버튼이지만, 실제로 "하트 공감 1회"를 누르려면
                # a.u_likeit_button 클릭 후 열리는 레이어의 a.u_likeit_list_button[data-type='like']를 누른다.
                # off 클래스 = 아직 공감 안 누름 / on = 이미 누름 (on이면 클릭해도 해제되므로 제외)
                "a.u_likeit_button.off",                 # 1순위: 반응 열기 버튼 (미공감 상태)
                "a.u_likeit_button",                     # 하위 호환: on/off 무관 emote 버튼
                "a.u_likeit_list_button.off[data-type='like']",   # 2순위: 하트 공감 버튼 (미공감)
                "a.u_likeit_list_button[data-type='like']",
                "a.u_likeit_list_btn.off[data-type='like']",      # 구버전 경로
                "a[class*='u_likeit'][class*='off']",
                "a[class*='u_likeit']",
                "span[class*='u_likeit']",
                "button[class*='u_likeit']",
                # 구버전 호환
                "button.u_btn_sympathy",
                "a.u_btn_sympathy",
                "button[data-type='sympathy']",
                "a[data-type='sympathy']",
                "button.u_btn_like",
                "a.u_btn_like",
                # 텍스트 기반 최종 fallback
                "button:has-text('공감')",
                "a:has-text('공감')",
                "span:has-text('공감')",
            ]

            like_clicked = False
            like_btn = None
            like_frame = None

            # ──────────────────────────────────────────────────
            # [v3.4.1 신규] 공감 안정화 헬퍼 3종
            # ──────────────────────────────────────────────────
            async def _wait_like_button_loaded(timeout_sec=5.0, poll=0.5):
                """공감 버튼이 DOM에 완전히 로드되고 화면에 보일 때까지 명시적으로 대기.
                지연 렌더링 대비하여 최대 timeout_sec까지 0.5초 간격으로 재탐색.
                Returns: (btn, frame) 또는 (None, None)"""
                waited = 0.0
                while waited <= timeout_sec:
                    cands = await _find_like_candidates()
                    if cands:
                        return cands[0]
                    await asyncio.sleep(poll)
                    waited += poll
                return (None, None)

            async def _like_state(btn, frame):
                """현재 공감 버튼 그룹의 상태를 'liked'|'off'|'unknown'으로 판정.
                - liked: 버튼(또는 같은 모듈 내 버튼)에 on 클래스가 있으면서 off 없음
                - off  : off 클래스가 있으면서 on 없음 (아직 미공감)
                - unknown: 판단 불가 (레이어/구조 변화) — 호출부 정책에 맡김"""
                try:
                    return await frame.evaluate(
                        """(el) => {
                            const group = el.closest('.u_likeit_list_module')
                                          || el.closest('li') || el.closest('div[class*="u_likeit"]')
                                          || el;
                            const all = group.querySelectorAll('[class*="u_likeit"]');
                            let hasOn = false, hasOff = false;
                            for (const b of all) {
                                const cls = (b.className || '') + '';
                                if (cls.includes('on') && !cls.includes('off')) hasOn = true;
                                if (cls.includes('off')) hasOff = true;
                            }
                            if (hasOn && !hasOff) return 'liked';
                            if (hasOff && !hasOn) return 'off';
                            return 'unknown';
                        }""", btn)
                except Exception:
                    return 'unknown'

            async def _wait_like_state_flicker(stable_before_click=True, timeout_sec=3.0):
                """레이어 상태가 안정화될 때까지 잠시 대기 (on/off 진동 방지)"""
                prev = None
                waited = 0.0
                while waited < timeout_sec:
                    cur = await _like_state(like_btn, like_frame)
                    if prev is not None and cur == prev:
                        return cur
                    prev = cur
                    await asyncio.sleep(0.4)
                    waited += 0.4
                return prev or 'unknown'

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 공감 버튼 탐색 (개선)
            # [버그 원인] 공감 버튼은 게시글 맨 아래(수천~만수천 px 지점)에 있는데,
            #   기존 루프는 "반경점씩 15번"이라 최대 약 7,000px밖에 내려가지 못해
            #   버튼에 도달하지 못했다 → 화면도 작업 위치로 이동하지 않았음.
            # [개선] 1) DOM에서 공감 버튼 후보를 먼저 찾고
            #        2) 발견 즉시 그 위치로 부드럽게 스크롤(이동 장면이 화면에 보임)
            #        3) DOM에 없으면 페이지 끝까지 단계적으로 내려가며 재탐색
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            async def _find_like_candidates():
                """현재 DOM에서 공감 버튼 후보를 셀렉터 우선순위대로 탐색 [(element, frame)]"""
                for fr in [self.page] + [f for f in self.page.frames if f != self.page.main_frame]:
                    for sel in like_selectors:
                        try:
                            btns = await fr.query_selector_all(sel)
                        except Exception:
                            continue
                        found = []
                        for b in btns:
                            try:
                                if await b.is_visible():
                                    found.append((b, fr))
                            except Exception:
                                pass
                        if found:
                            return found
                return []

            if not do_like:
                self._log(f"  ❤️  공감 단계 건너뜀 (선택 해제)", "info")
                like_btn = None
                like_frame = None

            scroll_step = max(viewport_height // 2, 200)
            try:
                scroll_pos = await self.page.evaluate("() => window.scrollY")
            except Exception:
                scroll_pos = 0
            max_scroll = max(0, page_height - viewport_height)

            # ──────────────────────────────────────────────────
            # [v3.4.1 신규] 명시적 대기 — 포스팅 로딩 후 공감 버튼이
            #   DOM에 완전히 로드되고 화면에 보일 때까지 최대 5초 대기.
            #   탐색/클릭 로직이 바로 넘어가서 하트가 안 눌리는 것을 방지.
            #   (로딩 늦으면 두 번째 시도에서도 재확인)
            # ──────────────────────────────────────────────────
            if do_like:
                self._log(f"  ❤️  [2/3] 공감 버튼 로딩 대기 중... (최대 5초)", "info")
                await asyncio.sleep(3)
                awaited_btn, awaited_frame = await _wait_like_button_loaded(timeout_sec=5.0, poll=0.5)
                if awaited_btn:
                    like_btn, like_frame = awaited_btn, awaited_frame
                    self._log("  ❤️  [2/3] 공감 버튼 로딩 완료 확인!", "success")

            search_attempt = 0
            while search_attempt < 80 and do_like:  # 공감 선택 해제 시 탐색/클릭 자체를 건너뜀 (플래그 무시 버그 수정)
                if _stopped():
                    self._log("  ⏹️  사용자에 의해 중지됨", "warning")
                    return False
                search_attempt += 1

                # 1) 후보 탐색 (viewport 위치 무관 — DOM 존재 여부만 확인)
                candidates = await _find_like_candidates()
                if candidates:
                    like_btn, like_frame = candidates[0]
                    # 2) 공감 버튼 위치로 부드럽게 이동 (작업 장면이 화면에 보임)
                    self._log(f"  ❤️  [2/3] 공감 버튼 발견! (탐색 {search_attempt}회) → 화면 중앙으로 이동 중...", "success")
                    await self._scroll_to_element_center(like_btn, like_frame)
                    await self.bring_to_front()
                    await asyncio.sleep(1)
                    break

                # 3) 후보 미발견 → 아래로 계속 스크롤 (페이지 끝까지)
                scroll_pos = min(scroll_pos + scroll_step, max_scroll)
                try:
                    await self.page.evaluate(f"window.scrollTo({{ top: {scroll_pos}, behavior: 'smooth' }})")
                except Exception:
                    pass
                await asyncio.sleep(1.2)

                if search_attempt % 3 == 0:
                    self._log(f"  ❤️  [2/3] 아래로 이동 중... ({scroll_pos}px / {page_height}px)", "info")

                if scroll_pos >= max_scroll:
                    # 페이지 끝에서 마지막 재탐색 (지연 렌더링 대비)
                    candidates = await _find_like_candidates()
                    if candidates:
                        like_btn, like_frame = candidates[0]
                        self._log(f"  ❤️  [2/3] 공감 버튼 발견! (하단) → 화면 중앙으로 이동 중...", "success")
                        await self._scroll_to_element_center(like_btn, like_frame)
                        await self.bring_to_front()
                        await asyncio.sleep(1)
                    else:
                        self._log(f"  ❤️  [2/3] 페이지 하단 도달 — 공감 버튼 미발견", "info")
                    break

            if like_btn:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ❤️ [2/3] 공감 버튼을 부드럽게 화면 중앙으로 이동
                # scrollIntoView({behavior: 'smooth'})로 사용자가 스크롤 과정을 볼 수 있도록
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                self._log(f"  ❤️  [2/3] 공감 버튼으로 이동 중...", "info")
                try:
                    # 부드러운 스크롤 (모바일에서 사람이 손으로 스크롤하는 것처럼)
                    if like_frame and like_frame != self.page:
                        await like_frame.evaluate(
                            "(el) => { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }",
                            like_btn,
                        )
                    else:
                        await self.page.evaluate("""(el) => {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }""", like_btn)
                    await asyncio.sleep(2)  # 부드러운 스크롤 완료 대기
                except Exception:
                    # fallback: 일반 스크롤
                    try:
                        await like_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                    except Exception:
                        pass

                await self.bring_to_front()
                await asyncio.sleep(1.5)  # 스크롤 후 사용자가 공감 버튼이 보이는 것을 확인할 수 있도록

                # viewport 확인
                like_in_viewport = False
                try:
                    like_in_viewport = await self._check_in_viewport(like_btn, like_frame)
                except Exception:
                    like_in_viewport = True

                if like_in_viewport:
                    self._log(f"  ❤️  [2/3] 공감 버튼 위치 확인! (하트가 보이는 상태) → 클릭합니다...", "info")
                    await asyncio.sleep(1)  # 클릭 전 사용자가 하트가 보이는 것을 볼 수 있도록

                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # [신규] 이미 공감한 상태(on)인지 확인 — on이면 재클릭 시 해제되므로 건너뜀
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    already_liked = False
                    try:
                        already_liked = await like_frame.evaluate(
                            """(el) => {
                                const b = (el.closest && (el.closest('.u_likeit_list_module') || el.closest('li'))) || null;
                                if (b) {
                                    const withOn = b.querySelector('[class*="u_likeit"][class*="on"]');
                                    if (withOn) return true;
                                }
                                const cls = el.className || '';
                                // emote 버튼 자체가 on이 아니면서 하트 버튼이 on인지는 레이어 열고 확인
                                return false;
                            }""", like_btn)
                    except Exception:
                        already_liked = False
                    if already_liked:
                        self._log("  ❤️  [2/3] 이미 공감한 게시글입니다 (on 상태) — 건너뜁니다", "info")
                        like_clicked = True  # 이미 공감 상태면 성공으로 처리
                    else:
                        self._log(f"  ❤️  [2/3] 하트 공감 진행 (off 상태 확인) → emote 버튼 클릭...", "info")

                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # 마우스 포인터를 공감 버튼 위치로 이동 (시각적 피드백)
                        # PC 모바일 에뮬레이션 환경에서 사용자가 마우스 이동을 볼 수 있음
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        try:
                            box = await like_btn.bounding_box()
                            if box:
                                target_x = box["x"] + box["width"] / 2
                                target_y = box["y"] + box["height"] / 2
                                self._log(f"  ❤️  [2/3] 마우스 포인터 이동 중... (x:{target_x:.0f}, y:{target_y:.0f})", "info")
                                await self.page.mouse.move(target_x, target_y)
                                await asyncio.sleep(0.8)  # 포인터 이동 후 잠시 대기
                        except Exception:
                            pass

                        await self.bring_to_front()
                        await asyncio.sleep(0.3)

                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # 실제 클릭 — 커서 이동 후 클릭 (화면에서 클릭 동작이 보임)
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # ※ 위의 mouse.move로 이미 커서가 이동했지만, 사람처럼 여러 단계로
                        #   움직이는 클릭을 human_move_and_click으로 다시 수행한다.
                        await self.human_move_and_click(like_btn)
                        like_clicked = True
                        frame_name = getattr(like_frame, 'name', None) or 'main'
                        self._log(f"  ❤️  [2/3] ✅ 공감 클릭 완료! 하트가 눌림! (위치: {frame_name})", "success")

                        # 클릭 후 하트 활성화 상태가 화면에 보이도록 충분히 대기
                        await asyncio.sleep(2)

                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # [신규] 2025.09 개편 공감 UI: emote(a.u_likeit_button)를 누르면
                        #   하트/공감 레이어가 열리고, 여기서 a.u_likeit_list_button[data-type='like']
                        #  (하트)를 눌러야 실제 '하트 공감 1회'가 등록된다.
                        #   해당 버튼이 있으면 사람처럼 이동해 하트를 누른다. (시각화 유지)
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        try:
                            heart_btn = None
                            for sel in (
                                "a.u_likeit_list_button.off[data-type='like']",
                                "a.u_likeit_list_button[data-type='like']",
                                "a.u_likeit_list_btn.off[data-type='like']",
                                "a[class*='u_likeit_list'][data-type='like']",
                                "a[class*='u_likeit_list'][class*='off']",
                                "button[class*='u_likeit_list'][data-type='like']",
                            ):
                                try:
                                    hs = await like_frame.query_selector_all(sel)
                                except Exception:
                                    hs = []
                                for hb in hs:
                                    try:
                                        if await hb.is_visible():
                                            heart_btn = hb
                                            break
                                    except Exception:
                                        pass
                                if heart_btn:
                                    break

                            if heart_btn:
                                self._log("  ❤️  [2/3] 공감 레이어의 하트(공감 1회) 버튼 발견 → 클릭...", "success")
                                try:
                                    await self._scroll_to_element_center(heart_btn, like_frame)
                                except Exception:
                                    try:
                                        await heart_btn.scroll_into_view_if_needed()
                                    except Exception:
                                        pass
                                await self.bring_to_front()
                                await asyncio.sleep(1)
                                # 사람처럼 커서를 하트 버튼으로 이동한 뒤 클릭 (화면에 보임)
                                await self.human_move_and_click(heart_btn)
                                self._log("  ❤️  [2/3] ✅ 하트 공감 클릭 완료! (공감 1회 등록)", "success")
                                await asyncio.sleep(2)
                            else:
                                self._log("  ❤️  [2/3] 하트 레이어 버튼 미발견 — emote 클릭으로 공감 시도 유지", "info")
                        except Exception:
                            self._log("  ❤️  [2/3] 하트 레이어 처리 중 오류 — emote 클릭 결과 유지", "warning")

                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # ❤️ [2/3] 공감(하트) 활성화 상태 검증
                        # 실제 DOM 상태가 변경되었는지 확인
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        self._log(f"  ❤️  [2/3] 하트 활성화 확인 중...", "info")
                        await asyncio.sleep(1.5)
                        heart_activated = False
                        try:
                            heart_activated = await self.page.evaluate("""() => {
                                // 0. 2025.09 개편 공감 UI: emote/하트 버튼의 on 클래스 확인
                                const likeBtns = document.querySelectorAll('[class*="u_likeit"]');
                                for (const btn of likeBtns) {
                                    const cls = btn.className || '';
                                    if (cls.includes('on') && !cls.includes('off')) return true;
                                }
                                // 1. class 변경 확인 (active, selected, on 등)
                                const sympathyBtns = document.querySelectorAll(
                                    '[class*="sympathy"], [class*="like"], [class*="heart"], '
                                    + '.u_btn_sympathy, .u_btn_like, button[data-type="sympathy"]'
                                );
                                for (const btn of sympathyBtns) {
                                    const cls = btn.className || '';
                                    if (cls.includes('active') || cls.includes('selected') || 
                                        cls.includes('on') || cls.includes('pressed') ||
                                        cls.includes('liked') || cls.includes('filled')) {
                                        return true;
                                    }
                                    // aria-pressed 확인
                                    if (btn.getAttribute('aria-pressed') === 'true') return true;
                                    // aria-checked 확인
                                    if (btn.getAttribute('aria-checked') === 'true') return true;
                                }
                                // 2. SVG/icon 변경 확인 (하트가 채워진 상태)
                                const filledHearts = document.querySelectorAll(
                                    'svg[class*="filled"], svg[class*="active"], '
                                    + '.u_btn_sympathy svg, .u_btn_like svg'
                                );
                                for (const svg of filledHearts) {
                                    const fill = svg.getAttribute('fill') || '';
                                    const cls = svg.getAttribute('class') || '';
                                    if (fill === 'red' || fill === '#f44336' || 
                                        fill === '#ff0000' || cls.includes('filled') ||
                                        cls.includes('active')) {
                                        return true;
                                    }
                                }
                                // 3. 하트 색상 변경 확인 (style)
                                const coloredHearts = document.querySelectorAll(
                                    '[style*="color: red"], [style*="color:#ff"], '
                                    + '[style*="fill: red"], [style*="fill:#ff"]'
                                );
                                if (coloredHearts.length > 0) return true;
                                // 4. 공감 수 변경 확인 (클릭 후 숫자가 1 증가)
                                const countEls = document.querySelectorAll(
                                    '.u_cbox_count, .sympathy_count, .like_count'
                                );
                                for (const el of countEls) {
                                    const num = parseInt(el.textContent.replace(/[^0-9]/g, ''));
                                    if (num > 0) return true;
                                }
                                return false;
                            }""")
                        except Exception:
                            heart_activated = True  # 확인 실패 시 일단 진행

                        if heart_activated:
                            self._log(f"  ❤️  [2/3] ✅ 하트 활성화 확인! (공감 완료)", "success")

                        # ──────────────────────────────────────────
                        # [v3.4.1 신규] 클릭 성공 여부 확인 + 재시도 (최대 2회)
                        # state가 'liked'로 전환될 때까지 off면 재클릭. 반드시
                        # 공감이 눌린 상태를 확인한 뒤 다음 단계로 넘어간다.
                        # ──────────────────────────────────────────
                        for attempt in range(3):
                            state = await _like_state(like_btn, like_frame)
                            if state == 'liked':
                                self._log("  ❤️  [2/3] ✅ 하트 상태 확인! (off → on 전환 성공, 공감 등록 완료)", "success")
                                break

                            if attempt >= 2:
                                self._log(f"  ❤️  [2/3] ⚠️ 하트 상태 재시도 실패 — 최대 2회 소진 (상태: {state})",
                                          "warning")
                                break

                            self._log("  ❤️  [2/3] 상태 확인 실패 (미체크) → 재시도 진행...",
                                      "warning")
                            # 재전송 대비 레이어/버튼 재탐색
                            re_found = await _wait_like_button_loaded(timeout_sec=3.0, poll=0.5)
                            if re_found and re_found[0]:
                                like_btn, like_frame = re_found
                            if not like_btn:
                                break
                            await self._scroll_to_element_center(like_btn, like_frame)
                            await self.bring_to_front()
                            await asyncio.sleep(1.2)
                            await self.human_move_and_click(like_btn)
                            self._log(f"  ❤️  [2/3] 재시도 클릭 {attempt + 1}/2", "info")
                            # 레이어가 계속 열려있으면 하트 버튼도 다시 클릭
                            try:
                                heart_btn_retry2 = None
                                for sel in (
                                    "a.u_likeit_list_button.off[data-type='like']",
                                    "a.u_likeit_list_button[data-type='like']",
                                    "a[class*='u_likeit_list'][data-type='like']",
                                    "a[class*='u_likeit_list'][class*='off']",
                                ):
                                    try:
                                        hs = await like_frame.query_selector_all(sel)
                                    except Exception:
                                        hs = []
                                    for hb in hs:
                                        try:
                                            if await hb.is_visible():
                                                heart_btn_retry2 = hb
                                                break
                                        except Exception:
                                            pass
                                    if heart_btn_retry2:
                                        break
                                if heart_btn_retry2:
                                    self._log("  ❤️  [2/3] (재시도) 하트 레이어 버튼 발견 → 클릭", "info")
                                    await self._scroll_to_element_center(heart_btn_retry2, like_frame)
                                    await self.bring_to_front()
                                    await asyncio.sleep(1)
                                    await self.human_move_and_click(heart_btn_retry2)
                                    self._log("  ❤️  [2/3] ✅ 하트 공감 클릭 완료! (재시도)", "success")
                                    await asyncio.sleep(2)
                            except Exception:
                                pass
                            # 상태 안정화 대기 후 재확인
                            await asyncio.sleep(2)
                        else:
                            # range(3) 루프가 break 없이 모두 돈 경우
                            state = await _like_state(like_btn, like_frame)
                            if state != 'liked':
                                self._log("  ❤️  [2/3] ⚠️ 재시도 전부 실패 — 상태 유지하지 못함, 다음 단계로 진행 (기존 로그 유지)",
                                          "warning")

                else:
                    self._log(f"  ⚠️  [2/3] 공감 버튼이 viewport 밖 → 재스크롤 시도...", "warning")
                    # [v3.4.2 신규] 서로이웃이 비활성/제한된 블로그(공감/댓찿 UI 없음) 넘어가지 않도록
                    #   neighbor_unavailable_skip=True일 때는 예외 없이 Skip으로 처리
                    try:
                        await like_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        await self.bring_to_front()
                        await asyncio.sleep(0.5)
                        # 사람처럼 커서 이동 후 클릭 (재시도)
                        await self.human_move_and_click(like_btn)
                        like_clicked = True
                        # [신규] 재시도 경로도 2025.09 개편 UI의 하트 레이어 처리
                        try:
                            heart_btn_retry = None
                            for sel in (
                                "a.u_likeit_list_button.off[data-type='like']",
                                "a.u_likeit_list_button[data-type='like']",
                                "a[class*='u_likeit_list'][data-type='like']",
                                "a[class*='u_likeit_list'][class*='off']",
                            ):
                                try:
                                    hs = await like_frame.query_selector_all(sel)
                                except Exception:
                                    hs = []
                                for hb in hs:
                                    try:
                                        if await hb.is_visible():
                                            heart_btn_retry = hb
                                            break
                                    except Exception:
                                        pass
                                if heart_btn_retry:
                                    break
                            if heart_btn_retry:
                                self._log("  ❤️  [2/3] (재시도) 하트 레이어 버튼 클릭...", "info")
                                await self._scroll_to_element_center(heart_btn_retry, like_frame)
                                await self.bring_to_front()
                                await asyncio.sleep(1)
                                await self.human_move_and_click(heart_btn_retry)
                                self._log("  ❤️  [2/3] ✅ 하트 공감 클릭 완료! (재시도)", "success")
                                await asyncio.sleep(2)
                        except Exception:
                            pass
                        self._log(f"  ❤️  [2/3] ✅ 공감 클릭 완료! (재시도)", "success")
                        await asyncio.sleep(2)
                        # 재시도 후에도 상태 확인
                        try:
                            heart_activated_retry = await self.page.evaluate("""() => {
                                const btns = document.querySelectorAll('[class*="sympathy"], [class*="like"]');
                                for (const btn of btns) {
                                    const cls = btn.className || '';
                                    if (cls.includes('active') || cls.includes('selected') || cls.includes('on')) return true;
                                }
                                return false;
                            }""")
                            if heart_activated_retry:
                                self._log(f"  ❤️  [2/3] ✅ 하트 활성화 확인! (재시도)", "success")
                        except Exception:
                            pass
                    except Exception:
                        self._log(f"  ⚠️  [2/3] 공감 클릭 실패 (건너뜀)", "warning")
            else:
                if do_like:
                    self._log(f"  ⚠️  공감 버튼 미발견 (건너뜀)", "warning")
                    # [v3.4.2 신규] 서로이웃 비활성 블로그라면 공감 실패도 Skip 처리
                    if neighbor_unavailable_skip:
                        like_clicked = True  # Skip 시 공감 미실행도 정상으로 간주해 다음 단계 진행
                # do_like=False인 경우 위에서 '공감 단계 건너뜀' 로그가 이미 기록됨

            if _stopped():
                self._log("  ⏹️  사용자에 의해 중지됨", "warning")
                return False

            if not do_comment:
                self._log(f"  ✏️  댓글 단계 건너뜀 (선택 해제) — 작업 완료", "info")
                # [v3.4.2] 서로이웃이 비활성/단방향만 있는 경우 Skip — 예외를 만들지 않고
                #   공감 등 다른 단계 성공 여부로 정상 종료한다.
                return like_clicked or do_neighbor or neighbor_unavailable_skip  # skip도 정상 종료로 처리

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # ✏️ [3/3] 댓글 입력창 탐색 → scrollIntoView → viewport 확인 → 타이핑
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 댓글 입력창 찾는 중...", "info")
            target = self.page
            comment_input = None
            comment_frame = None

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 모바일 블로그: 댓글 버튼을 먼저 클릭해야 textarea가 생성됨
            # Interact__comment_btn 을 클릭하면 댓글 입력창이 나타남
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 댓글 버튼 클릭 중 (댓글 입력창 활성화)...", "info")
            comment_btn_selectors = [
                "button.Interact__comment_btn--Wbuoq",
                "button[class*='comment_btn']",
                "button[class*='Interact__comment']",
                ".Information__comments--Kh_zi",
                "a[class*='comment']",
                "button:has-text('댓글')",
                "a:has-text('댓글')",
                "span:has-text('댓글')",
            ]
            for btn_sel in comment_btn_selectors:
                comment_btn_clicked = False
                try:
                    btns = await self.page.query_selector_all(btn_sel)
                    for btn in btns:
                        if await btn.is_visible():
                            # 댓글 버튼 위치로 부드럽게 이동 (이동 장면이 화면에 보임)
                            await self._scroll_to_element_center(btn)
                            await self.bring_to_front()
                            await asyncio.sleep(1)
                            await btn.click()
                            self._log(f"  ✏️  [3/3] 댓글 버튼 클릭 완료 ({btn_sel})", "success")
                            await asyncio.sleep(3)  # 댓글 영역(u_cbox) 로드 대기
                            comment_btn_clicked = True
                            break
                except Exception:
                    pass
                if comment_btn_clicked:
                    break

            # 댓글 버튼 클릭 후 입력창 탐색
            # 모바일 네이버: textarea가 아닌 contenteditable div 사용!
            # div.u_cbox_text[contenteditable='true']가 실제 입력 요소
            self._log(f"  ✏️  [3/3] 댓글 입력창 탐색 중...", "info")
            comment_selectors = [
                # 모바일 네이버 실제 구조 (contenteditable div)
                "div.u_cbox_text[contenteditable='true']",
                "div.u_cbox_text_mention[contenteditable='true']",
                "div[class*='u_cbox_text'][contenteditable]",
                "div[contenteditable='true'][class*='cbox']",
                "div[contenteditable='true']",
                # textarea 호환 (PC 버전 대비)
                "textarea.u_cbox_text",
                "textarea",
                "input[type='text'][placeholder*='댓글']",
            ]

            # 댓글 영역(u_cbox)은 클릭 후 로드되므로 최대 10초 대기
            for wait_attempt in range(10):
                # 메인 페이지에서 탐색
                for selector in comment_selectors:
                    try:
                        elements = await self.page.query_selector_all(selector)
                        for el in elements:
                            visible = await el.is_visible()
                            if visible:
                                comment_input = el
                                comment_frame = self.page
                                target = self.page
                                self._log(f"  ✏️  [3/3] 댓글 입력창 발견! (셀렉터: {selector}, 위치: 메인)", "success")
                                break
                        if comment_input:
                            break
                    except Exception:
                        pass

                # iframe에서도 탐색
                if not comment_input:
                    for frame in self.page.frames:
                        if frame == self.page.main_frame:
                            continue
                        for selector in comment_selectors:
                            try:
                                elements = await frame.query_selector_all(selector)
                                for el in elements:
                                    visible = await el.is_visible()
                                    if visible:
                                        comment_input = el
                                        comment_frame = frame
                                        target = frame
                                        frame_name = frame.name or 'iframe'
                                        self._log(f"  ✏️  [3/3] 댓글 입력창 발견! (셀렉터: {selector}, 위치: {frame_name})", "success")
                                        break
                            except Exception:
                                pass
                            if comment_input:
                                break
                        if comment_input:
                            break

                if comment_input:
                    break

                if wait_attempt < 9:
                    self._log(f"  ✏️  [3/3] 댓글 입력창 대기 중... ({wait_attempt + 1}/10)", "info")
                    await asyncio.sleep(1)

            if not comment_input:
                self._log(f"  ❌ 댓글 입력 영역 미발견: {blog_id}", "warning")
                return False

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 댓글 입력창을 화면 중앙으로 스크롤
            # iframe 내부 요소인 경우: 먼저 메인 페이지의 iframe을 스크롤하고, 그 다음 textarea를 스크롤
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 댓글 입력창을 화면 중앙으로 스크롤 중...", "info")
            try:
                # iframe 내부 요소인 경우: 메인 페이지에서 iframe 요소를 먼저 스크롤하고, 그 다음 입력창을 스크롤
                if comment_frame and comment_frame != self.page:
                    self._log(f"  ✏️  [3/3] iframe 내부 댓글 입력창 — 부모 페이지 스크롤 중...", "info")
                    # iframe 요소를 메인 페이지에서 찾아서 스크롤
                    try:
                        iframe_element = await self.page.query_selector(f"iframe[src*='comment'], iframe[name*='comment'], iframe")
                        if iframe_element:
                            await iframe_element.scroll_into_view_if_needed()
                            await asyncio.sleep(2)  # iframe이 화면에 보일 때까지 대기
                            self._log(f"  ✏️  [3/3] iframe 위치로 스크롤 완료", "success")
                    except Exception:
                        pass

                # 댓글 입력창을 화면 중앙으로 부드럽게 스크롤 (이동 장면이 화면에 보임)
                await self._scroll_to_element_center(comment_input, comment_frame)
                await asyncio.sleep(1.5)  # 스크롤 후 사용자가 댓글 입력창이 보이는 것을 확인할 수 있도록
            except Exception:
                pass

            await self.bring_to_front()
            await asyncio.sleep(1.5)  # 사용자가 댓글 입력창이 화면에 나타나는 것을 볼 수 있도록

            # viewport 확인
            comment_in_viewport = False
            try:
                comment_in_viewport = await self._check_in_viewport(comment_input, comment_frame)
            except Exception:
                comment_in_viewport = True

            if not comment_in_viewport:
                self._log(f"  ✏️  [3/3] 댓글 입력창이 viewport 밖 → 재스크롤 시도...", "info")
                try:
                    await comment_input.scroll_into_view_if_needed()
                    await asyncio.sleep(2)
                    comment_in_viewport = await self._check_in_viewport(comment_input, comment_frame)
                except Exception:
                    comment_in_viewport = True

            if not comment_in_viewport:
                self._log(f"  ❌ 댓글 입력창 위치 확인 실패: {blog_id}", "warning")
                return False

            self._log(f"  ✏️  [3/3] ✅ 댓글 입력창 위치 확인 완료! (화면에 표시됨)", "success")
            await asyncio.sleep(1.5)  # 사용자가 댓글 입력창이 보이는 것을 확인할 수 있도록

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 댓글 입력창 클릭 → 포커스 → 커서 활성화
            # 사용자가 브라우저에서 "입력창 클릭 → 커서 깜빡임" 과정을 볼 수 있도록
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 댓글 입력창 클릭 중...", "info")
            await self.bring_to_front()
            await asyncio.sleep(0.5)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 모바일 블로그: u_cbox_guide (placeholder)가 contenteditable 위에 overlay되어
            # 클릭이 가로채지는 문제 해결
            # 1순위: placeholder 클릭하여 제거 → 2순위: force click → 3순위: 키보드 포커스
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            guide_clicked = False
            try:
                guide = await target.query_selector(".u_cbox_guide, div[data-action='write#placeholder']")
                if guide and await guide.is_visible():
                    self._log(f"  ✏️  [3/3] placeholder 가이드 발견 → 클릭하여 제거...", "info")
                    await guide.click()
                    await asyncio.sleep(1)
                    guide_clicked = True
            except Exception:
                pass

            # 댓글 입력창 클릭 (force=True로 overlay 무시)
            click_success = False
            try:
                # 사람처럼 커서를 댓글 입력창으로 이동시킨 뒤 클릭 (화면에 보임)
                await self.human_move_and_click(comment_input)
                click_success = True
                await asyncio.sleep(2)
                self._log(f"  ✏️  [3/3] ✅ 댓글 입력창 포커스 완료! (커서가 깜빡임)", "success")
            except Exception as e1:
                self._log(f"  ✏️  [3/3] force click 실패: {e1} — 키보드 포커스 시도...", "warning")
                try:
                    # 키보드로 포커스 이동 (Tab 또는 클릭 좌표)
                    box = await comment_input.bounding_box()
                    if box:
                        await self.page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                        await asyncio.sleep(1.5)
                        click_success = True
                        self._log(f"  ✏️  [3/3] ✅ 마우스 좌표 클릭으로 포커스 설정", "success")
                except Exception:
                    pass

            if not click_success:
                self._log(f"  ✏️  [3/3] ⚠️ 포커스 설정 실패 — 타이핑 시도 진행", "warning")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 입력창 focus 상태 검증 — focus가 되지 않았으면 입력을 시작하지 않음
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            focus_verified = False
            try:
                if comment_frame and comment_frame != self.page:
                    focus_verified = await comment_frame.evaluate("""() => {
                        const el = document.activeElement;
                        return el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable);
                    }""")
                else:
                    focus_verified = await self.page.evaluate("""() => {
                        const el = document.activeElement;
                        return el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable);
                    }""")
            except Exception:
                focus_verified = True  # 검증 실패 시 일단 진행

            if focus_verified:
                self._log(f"  ✏️  [3/3] ✅ 입력창 focus 확인! 키보드 입력 준비 완료", "success")
            else:
                self._log(f"  ✏️  [3/3] ⚠️ 입력창 focus 미확인 — 재클릭 시도...", "warning")
                try:
                    await self.human_move_and_click(comment_input)
                    await asyncio.sleep(1.5)
                except Exception:
                    try:
                        # 최후수단: 마우스 좌표로 직접 클릭
                        box = await comment_input.bounding_box()
                        if box:
                            await self.page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                            await asyncio.sleep(1.5)
                    except Exception:
                        pass

            # 기존 텍스트 삭제 — fill() 대신 키보드 이벤트로 삭제 (화면에서 보이도록)
            self._log(f"  ✏️  [3/3] 기존 텍스트 삭제 중...", "info")
            try:
                # 키보드로 전체선택 + 삭제 (화면에서 보이는 동작)
                if comment_frame and comment_frame != self.page:
                    await comment_frame.keyboard.press("Control+a")
                else:
                    await self.page.keyboard.press("Control+a")
                await asyncio.sleep(0.3)
                if comment_frame and comment_frame != self.page:
                    await comment_frame.keyboard.press("Backspace")
                else:
                    await self.page.keyboard.press("Backspace")
                await asyncio.sleep(0.5)
            except Exception:
                # fallback: fill 사용
                try:
                    await comment_input.fill("")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # ✏️ 타자 치듯 댓글 입력 — element 전달하여 iframe에서도 작동
            # element.type(char)은 메인/iframe 모두에서 한 글자씩 입력 가능
            # 브라우저 화면에 안 → 안녕 → 안녕하 → ... 순서대로 실시간 표시
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 댓글 한 글자씩 입력 시작: '{comment[:30]}...'", "info")
            await self._type_on_page(comment, frame=comment_frame, element=comment_input)
            await asyncio.sleep(2)
            self._log(f"  ✏️  [3/3] ✅ 댓글 입력 완료: '{comment[:30]}...'", "success")

            # 타이핑 완료 후 브라우저에서 결과를 잠시 확인할 수 있도록 대기
            await self.bring_to_front()
            await asyncio.sleep(2)  # 사용자가 타이핑 결과(입력된 댓글)를 확인할 수 있도록

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5단계: 댓글 등록 버튼 클릭
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self._log(f"  ✏️  [3/3] 등록 버튼 탐색 중...", "info")
            submit_selectors = [
                # 모바일 네이버 댓글 전송 버튼 (최우선)
                "button[class*='comment_send']",
                "button[class*='send_btn']",
                "button[class*='btn_send']",
                "button.u_cbox_btn_upload",
                ".u_cbox_btn_upload",
                "button.u_cbox_btn_upload[type='submit']",
                "button.u_cbox_type_comment .u_cbox_btn_upload",
                # 텍스트 기반 (모바일/PC 모두)
                "button:has-text('등록')",
                "button:has-text('완료')",
                "button:has-text('쓰기')",
                "input:has-value('등록')",
                "button:has-text('댓글 쓰기')",
                # 클래스 기반
                ".comment_submit",
                "button[data-testid='comment-submit']",
                ".u_cbox_tool_btn_upload",
                "button[class*='upload']",
                "button[class*='submit']",
                "button[class*='send']",
                # 데이터-어트리뷰트 기반
                "button[data-action='write#submit']",
                "button[data-action='comment#submit']",
            ]
            submit_btn = None
            for sel in submit_selectors:
                try:
                    btn = await target.query_selector(sel)
                    if btn:
                        visible = await btn.is_visible()
                        if visible:
                            submit_btn = btn
                            self._log(f"  ✏️  [3/3] 등록 버튼 발견 ({sel})", "info")
                            break
                except Exception:
                    pass

            if submit_btn:
                try:
                    await submit_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                except Exception:
                    pass
                await self.bring_to_front()
                await asyncio.sleep(0.5)
                self._log(f"  ✏️  [3/3] 등록 버튼 클릭 중... (커서 이동)", "info")
                # 사람처럼 커서를 등록 버튼으로 이동시킨 뒤 클릭 (화면에 보임)
                await self.human_move_and_click(submit_btn)
                await asyncio.sleep(3)  # 등록 후 결과 확인 시간
                self._log(f"  ✅ 댓글 작성 완료: {blog_id}", "success")
                return True
            else:
                self._log(f"  ❌ 댓글 등록 버튼 미발견: {blog_id}", "warning")
                # [v3.4.2 신규] 서로이웃이 비활성/제한된 블로그(댓글창 자체 안 열림 등)라면
                #   댓글 등록 실패를 실패 상태로 만들지 않고 Skip처리로 다음 단계로 넘어간다.
                if neighbor_unavailable_skip:
                    self._log("  ⚠️ 서로이웃 비활성(단방향만 가능) 블로그로 확인 — 댓글 없이 Skip 처리", "warning")
                    return like_clicked or neighbor_unavailable_skip  # Skip도 정상 종료로 처리
                return False

        except Exception as e:
            self._log(f"  ❌ 댓글 작성 오류 ({blog_id}): {e}", "error")
            # 예외 발생 시 브라우저 닫지 않고 상태 유지 (로그인 재시도 가능)
            return False

    async def _find_post_url(self, blog_id: str) -> Optional[str]:
        """블로그 메인에서 첫 번째 포스트 URL을 찾아서 반환 (모바일/PC URL 패턴 모두 지원)"""
        try:
            find_post_js = r"""() => {
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    const href = a.href || '';
                    if (!href) continue;
                    // PC형: PostView.naver 또는 blog.naver.com/{id}/숫자
                    if (href.includes('PostView.naver') ||
                        (href.includes('blog.naver.com/') && /\d{8,}/.test(href))) {
                        return href;
                    }
                    // 모바일형: m.blog.naver.com/{id}/숫자
                    if (href.includes('m.blog.naver.com/') && /\d{8,}/.test(href)) {
                        return href;
                    }
                }
                return null;
            }"""

            # 모든 프레임에서 포스트 링크 검색
            for frame in self.page.frames:
                try:
                    post_url = await frame.evaluate(find_post_js)
                    if post_url:
                        return post_url
                except Exception:
                    pass

            # 메인 페이지에서 직접 검색
            post_url = await self.page.evaluate(find_post_js)
            return post_url

        except Exception:
            return None



    # ──────────────────────────────────────────────────────
    #  이웃 신청
    # ──────────────────────────────────────────────────────
    async def send_neighbor_request(self, blog_id: str) -> bool:
        if not self.page or not self.is_logged_in:
            self._log("로그인이 필요합니다.", "error")
            return False

        try:
            blog_url = f"{self.BLOG_HOME}/{blog_id}"
            await self.page.goto(blog_url, wait_until="networkidle")
            await asyncio.sleep(2)
            await self.bring_to_front()
            await asyncio.sleep(1)

            self._log(f"서로이웃 신청 시도: {blog_id}", "info")

            # 서로이웃/이웃신청 버튼 탐색 (텍스트 매칭 우선)
            neighbor_selectors = [
                # 텍스트 매칭 (서로이웃 우선)
                "a:has-text('서로이웃추가')",
                "button:has-text('서로이웃추가')",
                "a:has-text('서로이웃')",
                "button:has-text('서로이웃')",
                "a:has-text('이웃')",
                "button:has-text('이웃')",
                # 클래스 기반
                "a.btn_neighbor_add",
                ".neighbor_add",
                "button[data-testid='neighbor-add']",
                ".blog2_neighbor a",
                "#neighborAddButton",
                "a[href*='neighbor']",
                ".follow_btn",
            ]

            neighbor_btn = None
            for selector in neighbor_selectors:
                neighbor_btn = await self.page.query_selector(selector)
                if neighbor_btn:
                    break

            if neighbor_btn:
                await neighbor_btn.click()
                self._log(f"이웃추가 버튼 클릭: {blog_id}", "info")
                await asyncio.sleep(3)  # 팝업 표시 대기

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # "서로이웃을 신청합니다" 팝업 선택 처리
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                mutual_selectors = [
                    "text='서로이웃을 신청합니다'",
                    "label:has-text('서로이웃을 신청합니다')",
                    "span:has-text('서로이웃을 신청합니다')",
                    "div:has-text('서로이웃을 신청합니다')",
                    "input[type='radio'][name*='neighbor']",
                    "input[type='checkbox'][name*='neighbor']",
                    "label:has-text('서로이웃')",
                    ".u_layer_radio label:first-child",
                    ".layer_radio label:first-child",
                ]

                mutual_selected = False
                for sel in mutual_selectors:
                    try:
                        el = await self.page.query_selector(sel)
                        if el and await el.is_visible():
                            await el.click()
                            await asyncio.sleep(1)
                            mutual_selected = True
                            self._log(f"  '서로이웃을 신청합니다' 선택 완료", "success")
                            break
                    except Exception:
                        pass

                # iframe에서도 탐색
                if not mutual_selected:
                    for frame in self.page.frames:
                        if frame == self.page.main_frame:
                            continue
                        for sel in mutual_selectors:
                            try:
                                el = await frame.query_selector(sel)
                                if el and await el.is_visible():
                                    await el.click()
                                    await asyncio.sleep(1)
                                    mutual_selected = True
                                    self._log(f"  '서로이웃을 신청합니다' 선택 완료 (iframe)", "success")
                                    break
                            except Exception:
                                pass
                        if mutual_selected:
                            break

                if not mutual_selected:
                    self._log(f"  '서로이웃을 신청합니다' 요소 미발견", "warning")

                await asyncio.sleep(1.5)

                # 신청/확인 버튼 클릭
                confirm_selectors = [
                    "button:has-text('신청')",
                    "button:has-text('확인')",
                    "a:has-text('신청')",
                    "a:has-text('확인')",
                    "button.confirm",
                    ".btn_ok",
                    "button[data-testid='confirm']",
                ]
                for selector in confirm_selectors:
                    try:
                        confirm = await self.page.query_selector(selector)
                        if confirm and await confirm.is_visible():
                            btn_text = await confirm.inner_text()
                            if btn_text and ("신청" in btn_text or "확인" in btn_text):
                                await confirm.click()
                                await asyncio.sleep(2)
                                self._log(f"이웃 신청 완료: {blog_id}", "success")
                                return True
                    except Exception:
                        pass

                # 신청 버튼 미발견 시 확인 팝업만 처리
                self._log(f"이웃 신청 처리 완료: {blog_id}", "success")
                return True
            else:
                page_text = await self.page.content()
                if "이미 이웃" in page_text or "이웃입니다" in page_text:
                    self._log(f"이미 이웃: {blog_id}", "info")
                    return True
                else:
                    self._log(f"이웃 신청 버튼 미발견: {blog_id}", "warning")
                    return False

        except Exception as e:
            self._log(f"이웃 신청 오류 ({blog_id}): {e}", "error")
            return False

    # ──────────────────────────────────────────────────────
    #  사용자 직접 로그인 (비밀번호 저장 없음)
    # ──────────────────────────────────────────────────────
    async def open_login_page(self) -> bool:
        """브라우저를 열고 네이버 로그인 페이지로 이동만 한다.
        아이디/비밀번호는 사용자가 직접 입력한다 (프로그램이 저장/수집하지 않음).
        Returns: 브라우저+페이지가 정상적으로 열렸는지 여부
        """
        try:
            if not self.browser:
                await self.start_browser(headless=False)
            if not self.page:
                self._log("페이지 생성 실패", "error")
                return False

            await self.page.goto(self.NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)
            await self.bring_to_front()
            self._log("네이버 로그인 페이지를 열었습니다. 사용자가 직접 로그인하세요.", "system")
            return True
        except Exception as e:
            self._log(f"로그인 페이지 열기 실패: {e}", "error")
            return False

    async def wait_for_user_login(self, timeout_seconds: int = 300, poll_interval: float = 2.0) -> bool:
        """
        사용자가 브라우저에서 직접 로그인할 때까지 대기한다.
        - 프로그램은 아이디/비밀번호를 입력하지 않는다
        - 네이버 추가 인증(2FA/기기등록)도 사용자가 직접 완료한다
        - 로그인 완료 판정: NID_AUT 쿠키 존재 여부 (페이지 이동 없이 감지)
          → 사용자가 인증을 진행 중인 페이지를 절대 방해하지 않는다
        """
        self._log("사용자 로그인 대기 중... (브라우저에서 직접 로그인하세요)", "info")
        waited = 0.0
        last_progress = 0.0
        while waited < timeout_seconds:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            try:
                if await self._is_logged_in_now():
                    self.is_logged_in = True
                    await self._save_session()
                    self._log("✅ 네이버 로그인 완료! (사용자 직접 로그인)", "success")
                    return True
            except Exception:
                pass
            if waited - last_progress >= 30.0:
                last_progress = waited
                self._log(f"  ⏳ 로그인 대기 중... ({int(waited)}/{timeout_seconds}초) — "
                          "브라우저에서 로그인을 완료하면 자동으로 감지됩니다", "info")
        self._log(f"로그인 대기 시간 초과 ({timeout_seconds}초)", "error")
        self._log("브라우저에서 로그인이 완료되지 않았습니다. [🌐 네이버 로그인] 버튼으로 다시 시도하세요.", "warning")
        return False

    async def _has_nid_cookie(self) -> bool:
        """NID_AUT 쿠키 존재 여부 — 페이지 이동 없이 확인 (인증 방해 없음)"""
        if not self.context:
            return False
        try:
            cookies = await self.context.cookies("https://www.naver.com")
            return any(c.get("name") == "NID_AUT" for c in cookies)
        except Exception:
            return False

    async def _is_logged_in_now(self, verify: bool = False) -> bool:
        """현재 브라우저 세션이 네이버 로그인 상태인지 실시간 확인.

        [중요] 과거 버그 수정: 폴링이 사용자의 2단계 인증/기기등록 페이지
        (nid.naver.com 경로)를 m.naver.com으로 강제 이동시켜 인증을
        방해하고 로그인 감지가 실패하는 문제가 있었다.
        → 쿠키 기반(NID_AUT) 감지로 변경해 페이지 이동을 최소화한다.

        verify=True: 쿠키가 있어도 www.naver.com을 열어 실제 로그인
        상태인지 재확인 (만료된 세션 쿠키 오판 방지 — 세션 복원 판정용)
        """
        if not self.page:
            return False

        url = (self.page.url or "")

        # 1) 네이버 로그인/인증 도메인에 있는 경우: 절대 이동하지 않는다.
        #    (아이디 입력 중, 2FA 중, 기기등록 중 — 페이지 이탈 방지)
        if "nid.naver.com" in url:
            if "nidlogin.login" in url:
                # 정확히 로그인 폼 화면 → 아직 로그인 완료 아님 (폼 제출 시 리디렉션됨)
                return False
            # 기기등록/2FA 등 후속 인증 중 → 쿠키가 설정됐으면 로그인 성공으로 판단
            return await self._has_nid_cookie()

        # 2) NID_AUT 쿠키가 있으면 로그인 상태로 판단 (DOM 구조와 무관)
        if await self._has_nid_cookie():
            if not verify:
                return True
            # 만료 확인: www.naver.com을 열어 '로그인' 버튼이 있으면 세션 만료
            try:
                await self.page.goto("https://www.naver.com",
                                     wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1.2)
                has_login_btn = await self.page.evaluate(self._LOGIN_CHECK_JS)
                return not has_login_btn
            except Exception:
                # 실확인 실패 시 쿠키 존재를 신뢰
                return True

        # 3) 쿠키가 없으면 m.naver.com에서 로그인 버튼 유무로 확인 (폴백)
        try:
            await self.page.goto("https://m.naver.com", wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(1.2)

            new_url = (self.page.url or "")
            if "nid.naver.com" in new_url or "login" in new_url.lower():
                return False

            has_login_btn = await self.page.evaluate(self._LOGIN_CHECK_JS)
            return not has_login_btn
        except Exception:
            return False

    # 페이지가 로그아웃 상태임을 나타내는 '로그인' 버튼 탐지 (여러 구조 대응)
    _LOGIN_CHECK_JS = """() => {
        // 로그인 페이지로 가는 링크가 '로그인' 텍스트를 가지면 로그아웃 상태
        const links = document.querySelectorAll('a[href*="nidlogin.login"], a[href*="nid.naver.com"]');
        for (const a of links) {
            const t = (a.innerText || '').trim();
            if (t && t.includes('로그인')) return true;
        }
        // 텍스트 정확 일치 (a/button/span 등 다양한 구조 대응)
        const els = document.querySelectorAll('a, button, span, li');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (t === '로그인' || t === 'NAVER 로그인') return true;
        }
        return false;
    }"""

    async def check_login_status(self) -> bool:
        """로그인 상태 확인 (UI 표시용) — 저장된 세션 재사용 포함.
        만료된 세션 쿠키 오판을 막기 위해 실확인(verify=True)을 수행한다.
        Returns: 로그인 여부
        """
        if self.browser and self.page:
            if self.is_logged_in:
                return True
            return await self._is_logged_in_now(verify=True)

        # 브라우저가 없으면 세션 파일로 새로 열어 확인
        if self._has_saved_session():
            try:
                await self.start_browser(headless=False)
                if await self._is_logged_in_now():
                    self.is_logged_in = True
                    self._log("저장된 세션으로 로그인 상태 확인 완료", "success")
                    return True
            except Exception as e:
                self._log(f"세션 확인 중 오류: {e}", "warning")
        return False

    async def logout(self):
        """로그아웃 — 세션 파일 삭제 + 브라우저 종료"""
        try:
            if self.browser:
                await self.close()
        except Exception:
            pass
        try:
            if os.path.exists(self.SESSION_FILE):
                os.remove(self.SESSION_FILE)
                self._log("저장된 세션을 삭제했습니다 (로그아웃).", "info")
        except Exception as e:
            self._log(f"세션 삭제 실패: {e}", "warning")
        self.is_logged_in = False

    # ──────────────────────────────────────────────────────
    #  게시글 열기 (공감/댓글 개별 작업용)
    # ──────────────────────────────────────────────────────
    async def open_post(self, blog_id: str, post_url: str = "") -> bool:
        """대상 블로그의 게시글 페이지를 연다. 공감/댓글 작업 전에 호출.
        Returns: 성공 여부
        """
        if not self.page:
            self._log("브라우저가 시작되지 않았습니다.", "error")
            return False

        target_url = self._to_mobile_url(post_url) if post_url else ""
        if not target_url:
            blog_url = f"https://m.blog.naver.com/{blog_id}"
            self._log(f"  📄 블로그 메인 접속: {blog_id}", "info")
            try:
                await self.page.goto(blog_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await self.page.goto(blog_url, wait_until="load", timeout=15000)
            await asyncio.sleep(3)
            await self.bring_to_front()
            target_url = await self._find_post_url(blog_id)
            if not target_url:
                self._log(f"  ❌ 포스트 URL 미발견: {blog_id}", "warning")
                return False
            target_url = self._to_mobile_url(target_url)

        self._log(f"  📄 게시글 접속: {target_url[:80]}", "info")
        try:
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            try:
                await self.page.goto(target_url, wait_until="load", timeout=15000)
            except Exception:
                self._log(f"  ❌ 페이지 로드 실패: {target_url[:60]}", "error")
                return False

        await asyncio.sleep(3)
        await self.bring_to_front()

        # 에러 페이지 감지
        try:
            page_text = await self.page.content()
            error_patterns = ["페이지 주소를 확인", "존재하지 않는 페이지", "삭제된 게시물"]
            for ep in error_patterns:
                if ep in page_text:
                    self._log(f"  ❌ 에러 페이지 감지: {ep}", "error")
                    return False
        except Exception:
            pass

        # 페이지 상단으로 스크롤 (서로이웃 버튼이 보이도록)
        try:
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)
        except Exception:
            pass
        await self.bring_to_front()
        return True

    async def do_like(self) -> bool:
        """현재 게시글에 공감(하트) 클릭만 수행. open_post 이후 호출.
        Returns: 성공 여부
        """
        if not self.page:
            self._log("브라우저가 시작되지 않았습니다.", "error")
            return False
        return await self.write_comment(
            blog_id="", comment="", do_neighbor=False, do_like=True, do_comment=False
        )

    async def do_comment(self, comment: str) -> bool:
        """현재 게시글에 댓글 작성만 수행. open_post 이후 호출.
        Returns: 성공 여부
        """
        if not self.page:
            self._log("브라우저가 시작되지 않았습니다.", "error")
            return False
        return await self.write_comment(
            blog_id="", comment=comment, do_neighbor=False, do_like=False, do_comment=True
        )

    # ──────────────────────────────────────────────────────
    #  브라우저 종료
    # ──────────────────────────────────────────────────────
    async def close(self):
        """브라우저 종료 — 종료 전 세션 저장"""
        # 로그인된 상태이면 세션 저장
        if self.is_logged_in and self.context:
            await self._save_session()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self._log("브라우저 종료", "system")
