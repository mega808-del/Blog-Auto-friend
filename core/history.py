"""
core/history.py — 작업 기록 관리
- 모든 작업(서로이웃 신청/공감/댓글)을 JSON으로 영구 기록
- 프로그램 재실행 후에도 기록 불러오기 가능
- 중복 작업 방지용 조회 (블로그 ID별 마지막 작업 상태)
- 통계 계산 (오늘/누적)
- 비밀번호 등 민감정보는 절대 저장하지 않음
"""

import json
import os
import threading
from datetime import datetime, date

HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work_history.json"
)

_lock = threading.Lock()

# 작업 종류 상수
WORK_NEIGHBOR = "서로이웃 신청"
WORK_LIKE = "공감"
WORK_COMMENT = "댓글"

RESULT_SUCCESS = "성공"
RESULT_FAIL = "실패"


def _load_all():
    """전체 기록 로드"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_all(records):
    """전체 기록 저장"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_record(work_type: str, blog_id: str, blog_name: str = "",
               message: str = "", result: str = RESULT_SUCCESS,
               error: str = ""):
    """작업 1건 기록 (작업이 끝날 때마다 호출)"""
    with _lock:
        records = _load_all()
        records.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "work_type": work_type,
            "blog_id": blog_id,
            "blog_name": blog_name,
            "message": message[:200],
            "result": result,
            "error": error[:200],
        })
        # 최근 10000건만 유지 (무한 증가 방지)
        if len(records) > 10000:
            records = records[-10000:]
        _save_all(records)


def get_all_records():
    """전체 기록 반환 (새 기록이 앞에 오도록 역순)"""
    return list(reversed(_load_all()))


def search_records(start_date: str = "", end_date: str = "",
                   work_type: str = "전체", result: str = "전체"):
    """
    조건 검색
    - start_date/end_date: YYYY-MM-DD (빈 값이면 제한 없음)
    - work_type: 전체 / 서로이웃 신청 / 공감 / 댓글
    - result: 전체 / 성공 / 실패
    """
    records = _load_all()
    out = []
    for r in records:
        d = r.get("date", "")
        if start_date and d < start_date:
            continue
        if end_date and d > end_date:
            continue
        if work_type != "전체" and r.get("work_type") != work_type:
            continue
        if result != "전체" and r.get("result") != result:
            continue
        out.append(r)
    return list(reversed(out))


def get_blog_last_status(blog_id: str):
    """
    블로그 ID의 마지막 작업 상태 반환
    Returns: None 또는 {"status": "success"|"fail", "work_type": str, "date": str, "time": str}
    """
    records = _load_all()
    for r in reversed(records):
        if r.get("blog_id") == blog_id:
            return {
                "status": "success" if r.get("result") == RESULT_SUCCESS else "fail",
                "work_type": r.get("work_type", ""),
                "date": r.get("date", ""),
                "time": r.get("time", ""),
            }
    return None


def get_stats():
    """
    통계 반환
    {
      "today": {"신청": n, "공감": n, "댓글": n, "성공": n, "실패": n},
      "total": {"서로이웃": n, "공감": n, "댓글": n},
    }
    """
    records = _load_all()
    today = date.today().strftime("%Y-%m-%d")

    stats = {
        "today": {WORK_NEIGHBOR: 0, WORK_LIKE: 0, WORK_COMMENT: 0,
                  "성공": 0, "실패": 0},
        "total": {"서로이웃": 0, "공감": 0, "댓글": 0},
    }

    for r in records:
        wt = r.get("work_type", "")
        ok = r.get("result") == RESULT_SUCCESS

        if r.get("date") == today:
            if wt == WORK_NEIGHBOR:
                stats["today"][WORK_NEIGHBOR] += 1
            elif wt == WORK_LIKE:
                stats["today"][WORK_LIKE] += 1
            elif wt == WORK_COMMENT:
                stats["today"][WORK_COMMENT] += 1
            stats["today"]["성공" if ok else "실패"] += 1

        if wt == WORK_NEIGHBOR:
            stats["total"]["서로이웃"] += 1
        elif wt == WORK_LIKE:
            stats["total"]["공감"] += 1
        elif wt == WORK_COMMENT:
            stats["total"]["댓글"] += 1

    return stats


def clear_all():
    """전체 기록 삭제"""
    with _lock:
        _save_all([])
