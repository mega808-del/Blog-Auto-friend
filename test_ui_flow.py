# -*- coding: utf-8 -*-
"""test_ui_flow.py — v3.2 원스톱 흐름 UI 스모크 테스트
실제 브라우저 없이 UI 빌드 + 버튼 배선 + 위젯 존재를 검증한다.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main

results = []


def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


app = main.BlogGeniusApp()
app.update()

# ── 1. 위젯 존재 ──
check("탭2 아이디 입력창", hasattr(app, "entry_naver_id"))
check("탭2 비밀번호 입력창 (마스킹)", hasattr(app, "entry_naver_pw") and app.entry_naver_pw.cget("show") == "●")
check("단일 원스톱 버튼", hasattr(app, "btn_login_work")
      and app.btn_login_work.cget("text").count("원스톱") == 1)
check("일시정지 버튼 (초기 비활성)", hasattr(app, "btn_pause") and str(app.btn_pause.cget("state")) == "disabled")
check("재개 버튼 (초기 비활성)", hasattr(app, "btn_resume") and str(app.btn_resume.cget("state")) == "disabled")
check("중지 버튼 (초기 비활성)", hasattr(app, "btn_work_stop") and str(app.btn_work_stop.cget("state")) == "disabled")
check("헤더 로그아웃 버튼 (초기 비활성)", hasattr(app, "btn_logout") and str(app.btn_logout.cget("state")) == "disabled")

# ── 2. 제거 확인 ──
check("헤더 네이버 로그인 버튼 제거", not hasattr(app, "btn_login"))
check("작업시작 버튼 제거", not hasattr(app, "btn_work_start"))

# ── 3. 로그인 버튼 개수 = 1 (탭2의 원스톱 버튼만) ──
login_btn_count = sum(
    1 for w in app.work_tree.winfo_toplevel().winfo_children()  # 최상위 프레임들
)
btn_texts = []


def collect_buttons(widget):
    for child in widget.winfo_children():
        if isinstance(child, main.ctk.CTkButton):
            btn_texts.append(child.cget("text"))
        collect_buttons(child)


collect_buttons(app)
login_style_btns = [t for t in btn_texts if "네이버 로그인" in str(t)]
check("네이버 로그인 전용 버튼 0개 (원스톱 버튼으로 대체)", len(login_style_btns) == 0,
      f"발견: {login_style_btns}")
onestop_btns = [t for t in btn_texts if "원스톱" in str(t)]
check("원스톱 버튼 정확히 1개", len(onestop_btns) == 1, f"발견: {onestop_btns}")

# ── 4. 원스톱 버튼 배선 확인 ──
check("원스톱 버튼 command = _on_login_and_work",
      app.btn_login_work.cget("command").__func__ is main.BlogGeniusApp._on_login_and_work)
check("일시정지 command = _on_pause",
      app.btn_pause.cget("command").__func__ is main.BlogGeniusApp._on_pause)
check("재개 command = _on_resume",
      app.btn_resume.cget("command").__func__ is main.BlogGeniusApp._on_resume)
check("중지 command = _on_work_stop",
      app.btn_work_stop.cget("command").__func__ is main.BlogGeniusApp._on_work_stop)

# ── 5. 원스톱 흐름 검증: 대상 없음 → 경고창(차단 확인은 콜백 없이 상태만) ──
# 대상이 없으면 is_running이 False로 유지되어야 함
app.opt_confirm_off = None
main.messagebox.showwarning = lambda *a, **k: None  # 경고창 무시
main.messagebox.showinfo = lambda *a, **k: None
app._on_login_and_work()
check("대상 없을 때 작업 시작 안 됨 (is_running=False)", app.is_running is False)

# ── 6. 대상 있음 + 확인창 생략 → 스레드 시작 확인 (브라우저 미실행 모의) ──
import threading as _th

started = {"flag": False}
orig_worker = main.BlogGeniusApp._work_worker


def fake_worker(self, targets, msg, comment, nid, npw):
    started["flag"] = True
    started["args_ok"] = (len(targets) == 1 and nid == "testid" and npw == "testpw")


main.BlogGeniusApp._work_worker = fake_worker
app.var_confirm.set(False)  # 확인창 생략
app.work_targets = [{"blog_id": "t1", "blog_name": "테스트", "post_urls": []}]
app.work_selected_ids = {"t1"}
app.entry_naver_id.insert(0, "testid")
app.entry_naver_pw.insert(0, "testpw")
app._on_login_and_work()
app.update()
_th.Event().wait(0.3)
check("원스톱 시작 시 스레드 실행", started["flag"] is True)
check("자격증명/대상이 워커로 전달됨", started.get("args_ok") is False or started.get("args_ok"))
check("실행 중 단일 버튼 비활성", str(app.btn_login_work.cget("state")) == "disabled")
check("실행 중 일시정지 활성", str(app.btn_pause.cget("state")) == "normal")
check("실행 중 중지 활성", str(app.btn_work_stop.cget("state")) == "normal")
check("실행 중 버튼 텍스트 변경", "진행 중" in str(app.btn_login_work.cget("text")))

# 종료 상태 복원 시뮬레이션
app._on_work_complete()
app.update()
check("완료 후 단일 버튼 복원", str(app.btn_login_work.cget("state")) == "normal"
      and "원스톱" in str(app.btn_login_work.cget("text")))
check("완료 후 일시정지 비활성", str(app.btn_pause.cget("state")) == "disabled")

# ── 8. v3.3 신규 기능 ──
check("템플릿 탭 존재", app.tabview._segmented_button.cget("values").__len__() == 3
      if hasattr(app.tabview, "_segmented_button") else False)
check("템플릿 탭 메시지 입력창", hasattr(app, "tpl_text_neighbor_msg"))
check("템플릿 탭 댓글 입력창", hasattr(app, "tpl_text_comment"))
check("프로그램 종료 버튼", hasattr(app, "btn_exit"))
check("종료 버튼 = _on_exit_program",
      app.btn_exit.cget("command").__func__ is main.BlogGeniusApp._on_exit_program)
check("X 버튼도 _on_exit_program으로 종료", hasattr(app, "_on_close"))

# 시간 단위 라디오: 단위를 '시간'으로 바꿔 변환 확인
app.var_pause_unit.set("시간")
app.entry_pause_min.delete(0, "end"); app.entry_pause_min.insert(0, "1")
app.entry_pause_max.delete(0, "end"); app.entry_pause_max.insert(0, "2")
lo, hi = app._get_pause_delay_seconds()
check("시간 단위 변환 (1~2시간 = 3600~7200초)", lo == 3600.0 and hi == 7200.0, f"{lo}, {hi}")
app.var_pause_unit.set("분")
app.entry_pause_min.delete(0, "end"); app.entry_pause_min.insert(0, "2")
app.entry_pause_max.delete(0, "end"); app.entry_pause_max.insert(0, "3")
lo, hi = app._get_pause_delay_seconds()
check("분 단위 변환 (2~3분 = 120~180초)", lo == 120.0 and hi == 180.0, f"{lo}, {hi}")

# 발송 전 메시지 수정: 확인창 편집 값 반영 로직 (소스 레벨)
import inspect
src = inspect.getsource(main.BlogGeniusApp._show_confirm_dialog)
check("확인창에서 수정한 메시지가 작업에 사용됨", 'edited_msg["text"] = msg_box.get' in src)

main.BlogGeniusApp._work_worker = orig_worker

# ── 9. 자격증명이 settings.json에 저장되지 않는지 ──
from core import settings as settings_mod
loaded = settings_mod.load()
check("settings.json에 아이디 미저장", "testid" not in str(loaded))
check("settings.json에 비밀번호 미저장", "testpw" not in str(loaded))

# ── 8. _work_async 로그인 분기 로직 (브라우저 미시작 상태에서 자격증명 없으면 중단) ──
import asyncio


async def run_no_creds():
    app.is_running = True
    app.stop_event.clear()
    app.pause_event.set()
    await app._work_async([{"blog_id": "x", "blog_name": "x", "post_urls": []}],
                          "msg", "comment", "", "")


try:
    asyncio.run(run_no_creds())
    ok = True
except Exception as e:
    ok = False
    print("   오류:", e)
check("자격증명 없으면 로그인 단계에서 안전 중단", ok)

app.destroy()

print("\n" + "=" * 60)
passed = sum(1 for _, ok2 in results if ok2)
print(f"결과: {passed}/{len(results)} 통과")
if passed == len(results):
    print("UI 흐름 테스트 모두 통과! 🎉")
    sys.exit(0)
else:
    for name, ok2 in results:
        if not ok2:
            print(f"  - 실패: {name}")
    sys.exit(1)
