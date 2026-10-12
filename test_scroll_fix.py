#!/usr/bin/env python3
"""
스크롤 수정 검증 테스트 (부작용 없음)
- 실제 NaverAutomator의 수정된 메서드를 사용해 검증:
  1) 공감 버튼 발견 → _scroll_to_element_center 로 화면 중앙 이동 → viewport 확인
  2) 댓글 버튼 클릭 → 댓글 입력창(contenteditable) 로드 → 중앙 이동 → viewport 확인
- 공감 클릭, 댓글 입력/등록은 수행하지 않는다 (실제 데이터 변경 없음)
"""
import asyncio, sys, os, json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler.automator import NaverAutomator

POST_URL = "https://m.blog.naver.com/theboni/224405142923"


async def main():
    auto = NaverAutomator()

    def log(msg, level="info"):
        print(f"[{level}] {msg}")

    auto.set_log_callback(lambda m, l="info": print(f"[{l}] {m}"))

    ok = True
    try:
        await auto.start_browser(headless=True)
        page = auto.page
        await page.goto(POST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"\n게시글 로드: {page.url}")

        # ── 검증 1: 공감 버튼 발견 + 화면 중앙 이동 ──
        print("\n=== 검증 1: 공감 버튼 탐색 + 중앙 스크롤 ===")
        like_btn = None
        for sel in ["a.u_likeit_button", "a[class*='u_likeit']", "[class*='u_likeit']"]:
            btns = await page.query_selector_all(sel)
            for b in btns:
                if await b.is_visible():
                    like_btn = b
                    break
            if like_btn:
                break
        if not like_btn:
            print("  ❌ 공감 버튼 미발견")
            ok = False
        else:
            before = await page.evaluate("() => Math.round(window.scrollY)")
            r = await auto._scroll_to_element_center(like_btn)
            after = await page.evaluate("""() => {
                const el = document.querySelector('a.u_likeit_button');
                if (!el) return {inView: false};
                const rect = el.getBoundingClientRect();
                return {top: Math.round(rect.top), inView: rect.top >= 0 && rect.top < window.innerHeight,
                        scrollY: Math.round(window.scrollY)};
            }""")
            print(f"  scrollY: {before} → {after.get('scrollY')}")
            print(f"  버튼 화면 top: {after.get('top')}px / viewport 안: {after.get('inView')}")
            print(f"  _scroll_to_element_center 반환: {r}")
            if after.get("inView") and r:
                print("  ✅ 공감 버튼이 화면에 보이는 위치로 이동 성공")
            else:
                print("  ❌ 공감 버튼이 화면에 안 보임")
                ok = False

        # ── 검증 2: 댓글 버튼 클릭 → 입력창 로드 + 중앙 이동 ──
        print("\n=== 검증 2: 댓글 버튼 클릭 → 입력창 로드 + 중앙 스크롤 ===")
        cbtn = None
        for sel in ["button[class*='comment_btn']", "button:has-text('댓글')"]:
            btns = await page.query_selector_all(sel)
            for b in btns:
                if await b.is_visible():
                    cbtn = b
                    break
            if cbtn:
                break
        if not cbtn:
            print("  ❌ 댓글 버튼 미발견")
            ok = False
        else:
            await auto._scroll_to_element_center(cbtn)
            await asyncio.sleep(1)
            await cbtn.click()
            print("  댓글 버튼 클릭 완료, 댓글 영역 로드 대기...")
            await asyncio.sleep(4)

            comment_input = None
            for attempt in range(10):
                for sel in [
                    "div.u_cbox_text[contenteditable='true']",
                    "div[class*='u_cbox_text'][contenteditable]",
                    "div[contenteditable='true']",
                    "textarea",
                ]:
                    els = await page.query_selector_all(sel)
                    for el in els:
                        if await el.is_visible():
                            comment_input = el
                            break
                    if comment_input:
                        break
                if comment_input:
                    break
                await asyncio.sleep(1)

            if not comment_input:
                print("  ❌ 댓글 입력창 미발견")
                ok = False
            else:
                r2 = await auto._scroll_to_element_center(comment_input)
                in_view = await auto._check_in_viewport(comment_input)
                print(f"  댓글 입력창 viewport 안: {in_view} / 반환: {r2}")
                if in_view and r2:
                    print("  ✅ 댓글 입력창이 화면에 보이는 위치로 이동 성공")
                else:
                    print("  ❌ 댓글 입력창이 화면에 안 보임")
                    ok = False

        print("\n================ 검증 결과 ================")
        print("✅ 통과: 스크롤/화면 이동 문제 수정 확인" if ok else "❌ 실패: 추가 수정 필요")

    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False
    finally:
        try:
            await auto.close()
        except Exception:
            pass

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
