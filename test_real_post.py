#!/usr/bin/env python3
"""Find a real blog post URL and test the full flow"""
import asyncio, sys, os, random
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler.automator import NaverAutomator

async def main():
    auto = NaverAutomator()
    try:
        await auto.start_browser(headless=False)
        await asyncio.sleep(3)

        # Check session
        await auto.page.goto("https://m.blog.naver.com/MyBlog.naver", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        logged_in = await auto.page.evaluate("""() => {
            return !document.querySelector('a[href*="Login.naver"]');
        }""")
        print(f"Session: {'Active' if logged_in else 'Need login'}")
        if not logged_in:
            print("Please login in browser, then press ENTER...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await asyncio.sleep(3)

        # Find a real blog post by browsing a known blog
        print("\n=== Finding real blog post ===")
        test_blogs = [
            "https://m.blog.naver.com/mega808",
            "https://m.blog.naver.com/PostList.naver?blogId=mega808",
        ]
        
        # Navigate to blog main page to find actual post URLs
        await auto.page.goto("https://m.blog.naver.com/mega808", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(4)
        
        actual_url = auto.page.url
        print(f"Current URL: {actual_url}")
        
        # Find post links
        post_urls = await auto.page.evaluate("""() => {
            const links = document.querySelectorAll('a');
            const posts = [];
            for (const a of links) {
                const href = a.href || '';
                // Mobile blog post URL pattern
                if (href.includes('m.blog.naver.com') && /\\d{10,}/.test(href) && !href.includes('PostList') && !href.includes('MyBlog')) {
                    posts.push(href);
                }
            }
            return posts.slice(0, 10);
        }""")
        print(f"Found {len(post_urls)} post URLs:")
        for u in post_urls[:5]:
            print(f"  {u}")
        
        if not post_urls:
            print("No posts found on blog main page. Trying to find posts via search...")
            # Try navigating to a popular blog
            await auto.page.goto("https://m.blog.naver.com/PostList.naver?blogId=mega808&categoryNo=0", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(4)
            
            post_urls = await auto.page.evaluate("""() => {
                const links = document.querySelectorAll('a');
                const posts = [];
                for (const a of links) {
                    const href = a.href || '';
                    if (/\\d{10,}/.test(href) && (href.includes('m.blog.naver.com') || href.includes('blog.naver.com'))) {
                        posts.push(href);
                    }
                }
                return posts.slice(0, 10);
            }""")
            print(f"Found {len(post_urls)} post URLs from PostList:")
            for u in post_urls[:5]:
                print(f"  {u}")

        if not post_urls:
            print("\nNo valid posts found. Let me try a different approach...")
            # Navigate directly to a known good blog post
            # Search for a popular blog post
            await auto.page.goto("https://m.blog.naver.com/PostView.naver?blogId=mega808&logNo=224015879584&redirect=D4&proxyReferer=", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(4)
            actual_url = auto.page.url
            print(f"Direct nav URL: {actual_url}")
            
            if 'error' in actual_url.lower() or 'noPost' in actual_url:
                # Try yet another format
                await auto.page.goto("https://blog.naver.com/PostView.naver?blogId=mega808&logNo=224015879584", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(4)
                actual_url = auto.page.url
                print(f"PC nav URL: {actual_url}")

        # Now test the full like/comment flow with a valid post
        test_url = post_urls[0] if post_urls else actual_url
        print(f"\n=== Testing flow with: {test_url} ===")
        
        if not test_url or 'error' in test_url.lower():
            print("ERROR: Could not find a valid post URL. Exiting.")
            print("Browser stays open for manual check.")
            await asyncio.sleep(300)
            return
        
        await auto.page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        await auto.bring_to_front()
        
        final_url = auto.page.url
        print(f"Loaded: {final_url}")
        
        if 'error' in final_url.lower() or 'noPost' in final_url:
            print("ERROR: Post page returned error. Exiting.")
            await asyncio.sleep(300)
            return
        
        # Check DOM
        dom_info = await auto.page.evaluate("""() => {
            return {
                url: location.href,
                title: document.title,
                scrollHeight: document.documentElement.scrollHeight,
                textareas: document.querySelectorAll('textarea').length,
                editables: document.querySelectorAll('[contenteditable]').length,
                uLikeit: document.querySelectorAll('[class*="u_likeit"]').length,
                uCbox: document.querySelectorAll('[class*="u_cbox"]').length,
                interact: document.querySelectorAll('[class*="Interact"]').length,
                commentBtn: document.querySelectorAll('button[class*="comment_btn"]').length,
            };
        }""")
        print(f"DOM: {dom_info}")
        
        # Full flow test
        # 1. Like
        like_found = False
        for sel in ["a.u_likeit_button", "a[class*='u_likeit_button']"]:
            try:
                el = await auto.page.query_selector(sel)
                if el and await el.is_visible():
                    print(f"[LIKE] FOUND: {sel}")
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(1.5)
                    await el.click()
                    await asyncio.sleep(2)
                    like_found = True
                    print(f"[LIKE] CLICKED")
                    break
            except:
                pass
        
        # 2. Comment button
        btn_found = False
        for sel in ["button.Interact__comment_btn--Wbuoq", "button[class*='comment_btn']"]:
            try:
                el = await auto.page.query_selector(sel)
                if el and await el.is_visible():
                    print(f"[BTN] FOUND: {sel}")
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await el.click()
                    await asyncio.sleep(3)
                    btn_found = True
                    print(f"[BTN] CLICKED")
                    break
            except:
                pass
        
        # 3. Comment input
        input_found = False
        input_el = None
        for sel in ["div.u_cbox_text[contenteditable='true']", "div[class*='u_cbox_text'][contenteditable]", "div[contenteditable='true']", "textarea"]:
            try:
                elements = await auto.page.query_selector_all(sel)
                for el in elements:
                    if await el.is_visible():
                        print(f"[INPUT] FOUND: {sel}")
                        input_el = el
                        input_found = True
                        break
                if input_found:
                    break
            except:
                pass
        
        if input_found and input_el:
            try:
                await input_el.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                await input_el.click()
                await asyncio.sleep(1)
                await input_el.type("테스트", delay=150)
                await asyncio.sleep(1)
                content = await input_el.evaluate("el => el.textContent || el.innerText || ''")
                print(f"[TYPED] '{content}'")
            except Exception as e:
                print(f"[TYPING ERROR] {e}")
        
        # 4. Submit
        for sel in ["button.u_cbox_btn_upload", "button:has-text('등록')"]:
            try:
                btn = await auto.page.query_selector(sel)
                if btn and await btn.is_visible():
                    print(f"[SUBMIT] FOUND: {sel}")
                    break
            except:
                pass
        
        print(f"\n=== FLOW RESULT ===")
        print(f"Like: {'OK' if like_found else 'FAIL'}")
        print(f"Comment btn: {'OK' if btn_found else 'FAIL'}")
        print(f"Comment input: {'OK' if input_found else 'FAIL'}")
        
        print("\nBrowser remains open. Press ENTER to close.")
        await asyncio.get_event_loop().run_in_executor(None, input)

    except Exception as e:
        print(f"FATAL: {e}")
        import traceback; traceback.print_exc()
    finally:
        try:
            await auto.browser.close()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
