"""
core/logs.py — 로그 파일 저장 (환경설정의 '로그 저장' 옵션)
"""

import os
from datetime import datetime

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)

_log_file = None


def _get_log_file():
    global _log_file
    if _log_file is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        _log_file = os.path.join(LOG_DIR, f"worklog_{datetime.now().strftime('%Y%m%d')}.log")
    return _log_file


def append(message: str, level: str = "info", enabled: bool = True):
    """로그 파일에 한 줄 추가"""
    if not enabled:
        return
    try:
        with open(_get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level.upper()}] {message}\n")
    except Exception:
        pass
