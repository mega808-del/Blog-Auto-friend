"""
core/license.py — 라이센스 키 / 사용 기간 제어
- 프로그램 실행 시 라이센스 키를 입력받아 검증
- 키 형식: KEY-YYYYMMDDHHMM-<무작위 6자리>
  예) BLOGGENIUS-202610312359-7K3F9Q
- 관리자(라이센스 생성 프로그램/license_generator.py)가 발급하며
  키 안에 만료 일시(날짜+시간)가 내장되어 있다.
- 형식이 맞고 기한이 남아 있어야 인증 통과.
  만료되었거나 형식이 잘못된 키는 차단한다.
- 검증 성공 시 발급일 기준 만료 일시를 license.json에 기록하고
  재실행 시 동일한 키인지 확인한다 (키가 바뀌면 다시 검증).
"""

import os
import re
import json
import hmac
import hashlib
import random
import socket
import threading
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_FILE = os.path.join(BASE_DIR, "license.json")

# 관리자 서명용 비밀 (키 위조 방지 — 키 뒤 6자리는 이 시드에서 파생)
_SECRET = "BlogGenius##2026##license"

KEY_NAME = "BLOGGENIUS"
KEY_LENGTH = 6

_lock = threading.Lock()

_KEY_RE = re.compile(
    r"^[A-Za-z]+-([0-9]{12})-([A-Za-z0-9]{6})$"
)


class LicenseError(Exception):
    """검증 실패 사유와 함께 발생"""


# ──────────────────────────────────────────────────────────
#  내부 헬퍼
# ──────────────────────────────────────────────────────────
def _expiry_to_text(expiry_str: str) -> str:
    """YYYYMMDDHHMM → 읽기 쉬운 한글 표기"""
    try:
        dt = datetime.strptime(expiry_str, "%Y%m%d%H%M")
        return dt.strftime("%Y년 %m월 %d일 %H시 %M분")
    except Exception:
        return expiry_str


def _generate_suffix(expiry_str: str, name: str) -> str:
    """만료 일시 + 프로그램명 시드로 6자리 서명 생성 (위조 방지)"""
    basis = f"{name}|{expiry_str}|{_SECRET}"
    digest = hmac.new(_SECRET.encode(), basis.encode(), hashlib.sha256).hexdigest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(alphabet[int(digest[i * 2:i * 2 + 2], 16) % len(alphabet)]
                   for i in range(KEY_LENGTH))


# ──────────────────────────────────────────────────────────
#  라이센스 생성 (관리자/발급 프로그램용)
# ──────────────────────────────────────────────────────────
def generate_license(days: int = 0, hours: int = 0, minutes: int = 0,
                     expiry_str: str = "") -> str:
    """
    라이센스 키 발급.
    - days/hours/minutes 지정: 현재 시각부터 계산
    - expiry_str 지정("YYYYMMDDHHMM"): 그 일시까지 유효 (우선 적용)
    Returns: 키 문자열 (예: BLOGGENIUS-202610312359-7K3F9Q)
    """
    if expiry_str:
        expiry = datetime.strptime(expiry_str, "%Y%m%d%H%M")
    else:
        total_minutes = max(0, int(days) * 1440 + int(hours) * 60 + int(minutes))
        if total_minutes <= 0:
            raise LicenseError("유효 기간을 1분 이상 지정하세요.")
        expiry = datetime.now() + timedelta(minutes=total_minutes)
    text = expiry.strftime("%Y%m%d%H%M")
    suffix = _generate_suffix(text, KEY_NAME)
    return f"{KEY_NAME}-{text}-{suffix}"


# ──────────────────────────────────────────────────────────
#  상태 저장/조회 (license.json)
# ──────────────────────────────────────────────────────────
def _read_state() -> dict:
    if not os.path.exists(LICENSE_FILE):
        return {}
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(key: str, expiry_str: str, device_note: str = "") -> bool:
    """검증 성공 시 상태 기록 (키·만료 일시·기기 참고용 노트)"""
    state = {
        "product": KEY_NAME,
        "key": key,
        "expires": expiry_str,
        "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": socket.gethostname()[:32] if device_note else "",
    }
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_saved_state() -> dict:
    with _lock:
        return dict(_read_state())


def get_expiry_text() -> str:
    """저장된 라이센스의 만료 일시 표기 (없으면 빈 문자열)"""
    state = _read_state()
    return _expiry_to_text(state.get("expires", "")) if state.get("expires") else ""


# ──────────────────────────────────────────────────────────
#  검증
# ──────────────────────────────────────────────────────────
def validate_key(key: str) -> str:
    """
    라이센스 키 검증 → 만료 일시("YYYYMMDDHHMM") 반환.
    실패 시 LicenseError 발생 (사유 메시지 포함).
    """
    key = (key or "").strip().upper()
    if not key:
        raise LicenseError("라이센스 키가 입력되지 않았습니다.")

    m = _KEY_RE.match(key)
    if not m:
        raise LicenseError(
            "라이센스 키 형식이 올바르지 않습니다.\n"
            "형식: BLOGGENIUS-YYYYMMDDHHMM-XXXXXX"
        )

    expiry_text, suffix = m.group(1), m.group(2)

    # 서명(마지막 6자리) 일치 확인
    expected = _generate_suffix(expiry_text, KEY_NAME).upper()
    if suffix != expected:
        raise LicenseError("유효하지 않은 라이센스 키입니다. (서명 불일치)")

    # 만료 일시 확인
    try:
        expiry = datetime.strptime(expiry_text, "%Y%m%d%H%M")
    except Exception:
        raise LicenseError("라이센스 기한 해석 오류. 키를 재발급 받아주세요.")

    if expiry < datetime.now():
        raise LicenseError("라이센스 기간이 만료되었습니다. 키를 재발급 받아주세요.")

    return expiry_text


def check_saved_license() -> str:
    """
    license.json의 기존 인증 상태 재확인 (프로그램 재시작 시).
    Returns: "ok" | "expired" | "invalid"
    """
    state = _read_state()
    key = state.get("key", "")
    expires = state.get("expires", "")
    if not key or not expires:
        return "invalid"
    try:
        ok_expiry = validate_key(key)
    except LicenseError as e:
        # "만료" 사유는 expired로 구분하고, 나머지(형식/서명 오류 등)는 invalid 처리
        if "만료" in str(e):
            return "expired"
        return "invalid"
    if ok_expiry != expires:
        # 다른 유효 키로 덮어쓴 것 — 상태를 다시 기록
        _write_state(key, ok_expiry, device_note="1")
        return "ok"
    if datetime.strptime(expires, "%Y%m%d%H%M") < datetime.now():
        return "expired"
    return "ok"
