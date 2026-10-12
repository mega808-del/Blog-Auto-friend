"""
test_fix.py — BlogGenius v3.0 구조 검증 스크립트
1. 전체 모듈 구문 검증
2. 핵심 함수 존재 확인 (2탭 구조: 수집 및 필터링 설정 / 서로이웃 자동 신청)
3. 비밀번호 저장 방지 확인
4. 엑셀 모듈 동작 확인
5. 쿠키 기반 로그인 감지 로직 확인
"""

import ast
import os
import sys

# Windows cp949 콘솔에서도 한글/유니코드 출력 가능하도록
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PASS = "[OK]"
FAIL = "[FAIL]"

results = []


def check(name, condition, detail=""):
    results.append((name, condition, detail))
    print(f"{PASS if condition else FAIL} {name}" + (f" — {detail}" if detail and not condition else ""))


# ── 1. 구문 검증 ──
files = [
    "main.py",
    "crawler/automator.py",
    "crawler/naver_crawler.py",
    "core/history.py",
    "core/settings.py",
    "core/excel.py",
    "core/templates.py",
    "core/logs.py",
]

all_ok = True
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            ast.parse(fh.read())
        check(f"구문 검사: {f}", True)
    except SyntaxError as e:
        check(f"구문 검사: {f}", False, str(e))
        all_ok = False

# ── 2. main.py 핵심 요소 ──
with open("main.py", encoding="utf-8") as fh:
    main_src = fh.read()

required_in_main = [
    # v3.2: 원스톱 흐름 — 아이디/비밀번호 입력창 + 단일 실행 버튼
    ("아이디 입력창 존재", "entry_naver_id" in main_src),
    ("비밀번호 입력창 존재 (마스킹)", "entry_naver_pw" in main_src and 'show="●"' in main_src),
    ("중복 로그인 버튼 제거 (btn_login 없음)", "self.btn_login " not in main_src),
    ("작업시작 버튼 제거 (btn_work_start 없음)", "btn_work_start" not in main_src),
    ("원스톱 실행 버튼 (_on_login_and_work)", "_on_login_and_work" in main_src),
    ("로그인 자동 타이핑 (automator.login 호출)", "await self.automator.login(naver_id, naver_pw)" in main_src),
    ("로그인 완료 후 자동 작업 진행", "로그인 완료 즉시" in main_src),
    ("자격증명 저장 방지 (naver_pw 미저장)", '"naver_pw":' not in main_src),
    # v3.0: 2탭 구조
    ("탭1: 수집 및 필터링 설정", "TAB_COLLECT" in main_src and "수집 및 필터링 설정" in main_src),
    ("탭2: 서로이웃 자동 신청", "TAB_WORK" in main_src and "서로이웃 자동 신청" in main_src),
    ("탭 구성: _build_collect_tab", "_build_collect_tab" in main_src),
    ("탭 구성: _build_work_tab", "_build_work_tab" in main_src),
    # v3.0: 수집 조건 입력란 6종
    ("수집 조건 입력란 (condition_entries)", "condition_entries" in main_src),
    ("조건: 개설 기준년도", "개설 기준년도" in main_src),
    ("조건: 최소 누적 방문자", "최소 누적 방문자 수" in main_src),
    ("조건: 최소 게시글 수", "최소 게시글 수" in main_src),
    ("조건: 최소 이웃 수", "최소 이웃 수" in main_src),
    ("조건: 최소 일일 방문자", "최소 일일 방문자 수" in main_src),
    ("조건: 목표 수집 수", "목표 수집 블로그 수" in main_src),
    ("수집 파이프라인 (_search_worker)", "_search_worker" in main_src),
    ("조건 안전 변환 (_collect_conditions_safe)", "_collect_conditions_safe" in main_src),
    # v3.0 버그 수정: 조건 완화 제거 (엄격 적용)
    ("조건 완화 제거 (엄격 적용)", "조건 자동 완화" not in main_src),
    ("작업 속도 설정 (entry_speed)", "entry_speed_min" in main_src and "entry_speed_max" in main_src),
    ("대기 단위 선택 (초/분/시간)", "var_pause_unit" in main_src and "시간 단위" in main_src
     and "lo * 3600" in main_src),
    # v3.3: 신규 기능
    ("메시지·댓글 템플릿 탭 추가", "TAB_TEMPLATES" in main_src and "_build_templates_tab" in main_src),
    ("발송 전 메시지 수정 가능 (확인창 편집)", "edited_msg" in main_src and "직접 수정할 수 있습니다" in main_src),
    ("프로그램 종료 버튼", "_on_exit_program" in main_src and "프로그램 종료" in main_src),
    ("종료 안 되는 문제 수정 (타임아웃+강제 종료)", "asyncio.wait_for(self.automator.close(), timeout=6)" in main_src
     and "os._exit(0)" in main_src),
    ("공감/댓글 진행 상태 표시 (하위 단계)", "공감 진행 중" in main_src and "댓글 작성 중" in main_src),
    ("이웃신청 실패 시에도 공감/댓글 진행", "공감/댓글은 계속 진행합니다" in main_src),
    ("속도 배율 전달 (set_speed_factor)", "set_speed_factor" in main_src),
    ("탭2 전송 (_transfer_to_work)", "_transfer_to_work" in main_src),
    ("엑셀 열기 (_open_latest_excel)", "_open_latest_excel" in main_src),
    # 공통 기능
    ("작업 전 확인창", "_show_confirm_dialog" in main_src),
    ("확인창 메시지 수정 반영 (tuple 반환)", "return confirmed[\"ok\"], edited_msg[\"text\"]" in main_src),
    ("일시정지 기능", "_on_pause" in main_src),
    ("재개 기능", "_on_resume" in main_src),
    ("작업 중지", "_on_work_stop" in main_src),
    ("로그인 상태 표시", "_set_login_indicator" in main_src),
    ("중복 작업 방지", "get_blog_last_status" in main_src),
    ("오류 일시정지 알림", "_show_pause_notice" in main_src),
    ("인증 후 다시 확인", "_on_recheck_after_auth" in main_src),
    ("작업 현황 바 (전체/완료/진행/대기/실패)", "stat_total" in main_src and "stat_fail" in main_src),
    # v3.0 레이아웃 수정
    ("수집 조건 2행 × 3열 배치", "2행 × 3열" in main_src),
    ("탭2 하단 고정 컨트롤 바", "work_ctrl_bar" in main_src),
    ("컨트롤 바에 일시정지 버튼", "🟡 일시정지" in main_src),
    ("컨트롤 바에 재개 버튼", "🟢 재개" in main_src),
    ("컨트롤 바에 중지 버튼", "🔴 중지" in main_src),
]
for name, cond in required_in_main:
    check(f"main.py: {name}", cond)

# main.py에 아이디/비밀번호 저장 코드가 없는지
check("main.py: settings에 naver_pw 저장 없음", '"naver_pw"' not in main_src and "'naver_pw'" not in main_src)

# ── 3. automator.py 핵심 함수 ──
with open("crawler/automator.py", encoding="utf-8") as fh:
    auto_src = fh.read()

required_in_auto = [
    ("open_login_page (로그인 페이지만 열기)", "async def open_login_page" in auto_src),
    ("wait_for_user_login (사용자 대기)", "async def wait_for_user_login" in auto_src),
    ("_is_logged_in_now (실시간 로그인 확인)", "async def _is_logged_in_now" in auto_src),
    # v3.0 수정: 쿠키 기반 감지 (인증 페이지 방해 없음)
    ("_has_nid_cookie (쿠키 기반 감지)", "async def _has_nid_cookie" in auto_src),
    ("작업 속도 배율 (set_speed_factor/_sd)", "def set_speed_factor" in auto_src and "def _sd" in auto_src),
    ("NID_AUT 쿠키 기반 로그인 판정", "NID_AUT" in auto_src),
    ("verify 옵션 (만료 쿠키 오판 방지)", "verify: bool = False" in auto_src),
    ("nid 페이지 강제 이동 금지", "절대 이동하지 않는다" in auto_src),
    ("로그인 대기 진행 로그", "로그인 대기 중" in auto_src),
    ("check_login_status", "async def check_login_status" in auto_src),
    ("logout (세션 삭제)", "async def logout" in auto_src),
    ("open_post (게시글 열기)", "async def open_post" in auto_src),
    ("do_like (공감만)", "async def do_like" in auto_src),
    ("do_comment (댓글만)", "async def do_comment" in auto_src),
    ("write_comment에 do_neighbor 옵션", "do_neighbor: bool = True" in auto_src),
    ("write_comment에 do_like 옵션", "do_like: bool = True" in auto_src),
    ("write_comment에 do_comment 옵션", "do_comment: bool = True" in auto_src),
]
for name, cond in required_in_auto:
    check(f"automator.py: {name}", cond)

# ── 4. settings 모듈: 비밀번호 저장 방지 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import settings as settings_mod

check("settings.py: FORBIDDEN_KEYS에 password 포함", "password" in settings_mod.FORBIDDEN_KEYS)
check("settings.py: FORBIDDEN_KEYS에 naver_id 포함", "naver_id" in settings_mod.FORBIDDEN_KEYS)

# 실제로 저장 차단되는지 테스트
test_settings = {"keyword": "테스트", "password": "secret123", "naver_id": "testuser"}
ok = settings_mod.save(test_settings)
loaded = settings_mod.load()
check("settings.py: 비밀번호 저장 차단", "password" not in loaded)
check("settings.py: 아이디 저장 차단", "naver_id" not in loaded)
check("settings.py: 일반 키워드는 저장됨", loaded.get("keyword") == "테스트")
# 테스트 후 정리
settings_mod.save({"keyword": ""})

# ── 5. history 모듈 ──
from core import history as work_history

work_history.clear_all()
work_history.add_record(work_history.WORK_NEIGHBOR, "testblog1", "테스트블로그", message="안녕하세요", result=work_history.RESULT_SUCCESS)
work_history.add_record(work_history.WORK_COMMENT, "testblog1", "테스트블로그", message="좋은 글", result=work_history.RESULT_SUCCESS)
work_history.add_record(work_history.WORK_LIKE, "testblog2", "실패블로그", result=work_history.RESULT_FAIL, error="테스트 실패")

last = work_history.get_blog_last_status("testblog1")
check("history.py: 블로그 상태 조회", last is not None and last["status"] == "success")

stats = work_history.get_stats()
check("history.py: 통계 계산", stats["today"]["성공"] >= 2 and stats["total"]["댓글"] >= 1)

records = work_history.search_records(work_type="공감")
check("history.py: 조건 검색", len(records) == 1 and records[0]["blog_id"] == "testblog2")

# ── 6. templates 모듈 ──
from core import templates as templates_mod

check("templates.py: 기본 신청 메시지 존재", len(templates_mod.get_neighbor_messages()) > 0)
# 기본 템플릿은 모듈 DEFAULTS 기준으로 검사 (templates.json은 사용자가 삭제/수정 가능)
check("templates.py: 기본 댓글 템플릿 존재", len(templates_mod.DEFAULTS["comments"]) >= 3)

used = set()
picked = templates_mod.pick_random("comment", used)
check("templates.py: 랜덤 선택", picked != "")
check("templates.py: used 갱신", picked in used)

# ── 7. excel 모듈 ──
from core import excel as excel_mod

test_rec = {
    "date": "2026-10-01", "time": "10:21:00",
    "work_type": "서로이웃 신청", "blog_id": "unittest", "blog_name": "단위테스트",
    "message": "테스트 메시지", "result": "성공", "error": "",
}
try:
    path = excel_mod.append_record(test_rec, target_date="1999-01")
    check("excel.py: 기록 추가", os.path.exists(path))
    recs = excel_mod.read_records(target_date="1999-01")
    check("excel.py: 기록 읽기", len(recs) >= 1 and recs[-1]["blog_id"] == "unittest")
    os.remove(path)
    check("excel.py: 테스트 파일 정리", True)
except Exception as e:
    check("excel.py: 동작", False, str(e))

# ── 8. 로그인 자동화 요소 ──
check("automator.py: login() 사람처럼 타이핑 (_type_like_human)",
      "async def login" in auto_src and "_type_like_human(id_input, naver_id)" in auto_src
      and "_type_like_human(pw_input, naver_pw)" in auto_src)
check("automator.py: login() 화면 전면화 (bring_to_front)",
      auto_src.split("async def login")[1].split("async def login_with_saved_session")[0].count("bring_to_front") >= 3)
check("automator.py: 사람 이동 클릭 (human_move_and_click)", "async def human_move_and_click" in auto_src)
check("automator.py: 한 글자씩 타이핑 (_type_on_page)", "async def _type_on_page" in auto_src)

# ── 결과 요약 ──
print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"결과: {passed}/{total} 통과")
if passed == total:
    print("모든 테스트 통과! 🎉")
else:
    failed = [name for name, ok, _ in results if not ok]
    print("실패 항목:")
    for name in failed:
        print(f"  - {name}")
    sys.exit(1)
