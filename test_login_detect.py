"""
로그인 감지 로직(쿠키 기반) 검증 테스트
- [1] 로그아웃 상태 www.naver.com → False
- [2] NID_AUT 쿠키 주입 → True (페이지 이동 없이 감지)
- [2b] 가짜 쿠키 + verify=True → False (만료 오판 방지 실확인)
- [3] nidlogin.login 페이지 (쿠키 있어도) → False + 페이지 이동 없음
- [4] nid 인증 경로에서 페이지가 강제 이동되지 않는지 확인
- [5] 쿠키 삭제 후 → False
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import traceback


async def run():
    from crawler.automator import NaverAutomator

    a = NaverAutomator()
    logs = []
    a.set_log_callback(lambda m, l="info": logs.append(f"[{l}] {m}"))

    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'} - {name} {detail}")

    await a.start_browser(headless=True)

    # [1] 로그아웃 상태
    await a.page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=25000)
    await asyncio.sleep(1.5)
    r1 = await a._is_logged_in_now()
    check("로그아웃 상태 www.naver.com → False", r1 is False, f"(결과: {r1})")

    # [2] NID_AUT 쿠키 주입 → 쿠키 기반 감지 (이동 없음)
    url_before = a.page.url
    await a.context.add_cookies([{
        "name": "NID_AUT", "value": "fake_test_cookie_1234",
        "domain": ".naver.com", "path": "/",
    }])
    r2 = await a._is_logged_in_now()
    moved = a.page.url == url_before
    check("NID_AUT 쿠키 존재 → True", r2 is True, f"(결과: {r2})")
    check("감지 중 페이지 이동 없음", moved, f"(URL 유지: {moved})")

    # [2b] verify=True: 가짜 쿠키는 실확인에서 로그아웃으로 판정되어야 함
    r2b = await a._is_logged_in_now(verify=True)
    check("가짜 쿠키 + verify=True → False (만료 오판 방지)", r2b is False, f"(결과: {r2b})")

    # [3] nidlogin.login (쿠키 있어도 로그인 폼이면 False)
    try:
        await a.page.goto("https://nid.naver.com/nidlogin.login",
                          wait_until="domcontentloaded", timeout=25000)
    except Exception:
        pass
    url3 = a.page.url
    r3 = await a._is_logged_in_now()
    check("nidlogin.login → False (쿠키와 무관)", r3 is False, f"(결과: {r3})")

    # [4] 감지 후 페이지가 이동하지 않았는지 (인증 방해 없음 검증)
    url4 = a.page.url
    await a._is_logged_in_now()
    check("nid 페이지에서 강제 이동 없음", a.page.url == url4 and "nid" in (a.page.url or ""),
          f"(URL 유지: {'nid' in (a.page.url or '')})")

    # [5] 쿠키 삭제 후 → False
    await a.context.clear_cookies()
    await a.page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=25000)
    await asyncio.sleep(1.0)
    r5 = await a._is_logged_in_now()
    check("쿠키 삭제 후 → False", r5 is False, f"(결과: {r5})")

    await a.close()

    print("\n===== 대기 타임아웃 안내 로그 확인 (wait_for_user_login 10초) =====")
    a2 = NaverAutomator()
    a2.set_log_callback(lambda m, l="info": print(f"   [{l}] {m}"))
    ok = await a2.wait_for_user_login(timeout_seconds=8, poll_interval=2.0)
    print(f"  -> 반환값: {ok} (기대: False — 로그인 안 함)")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n===== 결과: {passed}/{len(results)} 통과 =====")
    return passed == len(results)


if __name__ == "__main__":
    try:
        ok = asyncio.run(run())
        sys.exit(0 if ok else 1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
