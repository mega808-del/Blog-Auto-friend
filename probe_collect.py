"""
probe_collect.py — 최종 시나리오 테스트
실제 UI 설정값(개설 2003년/이웃500/누적5000/일일100/게시글30)으로
전체 파이프라인(검색→수집→필터)이 동작하는지 검증
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from crawler.naver_crawler import NaverBlogCrawler


def main():
    c = NaverBlogCrawler()
    c.set_log_callback(lambda m, l="info": None)

    print("=== 시나리오: UI 기본 조건 (개설2003/이웃500/누적5000/일일100/게시글30) ===")
    ids = c.search_blog_ids_http("맛집", max_pages=1)
    print(f"[1] 검색: {len(ids)}개")

    meta = dict(getattr(c, "_search_metadata", {}))
    pre = c.http_prefilter_batch(
        ids, keyword="맛집", max_candidates=50,
        callback=None, stop_flag=lambda: False, max_workers=10,
    )
    print(f"[2] 수집: {len(pre)}건")

    # main.py와 동일한 필터 로직
    conds = {"open_year": 2003, "neighbors": 500, "visitors": 5000, "daily": 100, "posts": 30}

    def apply_conds(c_, prefiltered, strict_unknown=False):
        out = []
        for info in prefiltered:
            y = info.get("blog_open_year", 0) or 0
            n = info.get("neighbor_count", 0) or 0
            v = info.get("visitor_count", 0) or 0
            d = info.get("daily_visitor_count", 0) or 0
            p = info.get("post_count", 0) or 0
            if c_["open_year"]:
                if y and y < c_["open_year"]:
                    continue
                if strict_unknown and not y:
                    continue
            if n and c_["neighbors"] and n < c_["neighbors"]:
                continue
            if v and c_["visitors"] and v < c_["visitors"]:
                continue
            if d and c_["daily"] and d < c_["daily"]:
                continue
            if p and c_["posts"] and p < c_["posts"]:
                continue
            out.append(info)
        return out

    passed = apply_conds(conds, pre)
    print(f"[3] 1차 통과: {len(passed)}건")
    if len(passed) < 15:  # target 30의 절반 미만
        strict = apply_conds(conds, pre, strict_unknown=True)
        if strict:
            passed = strict
            print(f"[3b] 엄격 재시도: {len(passed)}건")

    print("\n=== 탈락 사유 분석 (상위 5건) ===")
    rejected = [i for i in pre if i not in passed]
    for info in rejected[:5]:
        y = info.get("blog_open_year", 0)
        n = info.get("neighbor_count", 0)
        v = info.get("visitor_count", 0)
        d = info.get("daily_visitor_count", 0)
        p = info.get("post_count", 0)
        reasons = []
        if y and y < 2003: reasons.append(f"개설{y}")
        if n and n < 500: reasons.append(f"이웃{n}")
        if v and v < 5000: reasons.append(f"누적{v}")
        if d and d < 100: reasons.append(f"일일{d}")
        if p and p < 30: reasons.append(f"게시글{p}")
        print(f"  {info['blog_id']}: {', '.join(reasons) if reasons else '(미확인 데이터로 통과됨)'}")

    print(f"\n결과: {len(passed)}건 수집 가능 — 이전 버전은 0건이었음")
    assert len(passed) > 0, "FAIL: 여전히 0건"
    print("PIPELINE TEST: PASS")


if __name__ == "__main__":
    main()
