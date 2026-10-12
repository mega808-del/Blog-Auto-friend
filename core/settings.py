"""
core/settings.py — 프로그램 환경설정 관리
- settings.json에 저장
- 네이버 아이디/비밀번호는 절대 저장하지 않음 (민감정보 저장 금지)
"""

import json
import os

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"
)

DEFAULTS = {
    # 기본 설정
    "confirm_before_work": True,       # 작업 전 확인 여부
    "pause_min": 30,                   # 최소 대기 시간(초)
    "pause_max": 90,                   # 최대 대기 시간(초)
    "save_logs": True,                 # 로그 저장 여부
    "excel_auto_save": True,           # 작업 후 엑셀 자동 저장
    "show_browser": True,              # 브라우저 창 표시 여부
    "pause_on_error": True,            # 오류 발생 시 자동 일시정지
    "keep_browser_after_work": True,   # 작업 완료 후 브라우저 유지

    # 엑셀 저장 위치 (빈 값이면 기본 폴더 사용)
    "excel_dir": "",

    # 검색 설정 (기존 호환)
    "keyword": "",
    "filters": {},
    "target_count": 20,

    # 블로그 설정
    "my_blog_url": "",

    # 댓글 설정
    "daily_limit": 30,
}

# 절대 저장하면 안 되는 키 (실수로라도 저장 방지)
FORBIDDEN_KEYS = {"password", "pw", "naver_pw", "passwd", "id", "naver_id", "username"}


def load() -> dict:
    """설정 로드 (기본값 병합)"""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for k, v in stored.items():
                    if k not in FORBIDDEN_KEYS:
                        settings[k] = v
        except Exception:
            pass
    return settings


def save(settings: dict) -> bool:
    """설정 저장 — 민감정보 키는 저장 전 제거"""
    clean = {k: v for k, v in settings.items() if k not in FORBIDDEN_KEYS}
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get(key: str, default=None):
    return load().get(key, default)


def set_value(key: str, value):
    settings = load()
    settings[key] = value
    return save(settings)
