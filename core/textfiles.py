"""
core/textfiles.py — 메모장 텍스트 파일 연동 (줄 단위 랜덤 추출)
- 프로그램 실행 폴더의 message.txt / comment.txt 를 줄바꿈으로 구분된 후보 리스트로 읽는다.
- 서로이웃 신청 요청 시점마다 lines 중 무작위 1개를 추출해
  신청 메시지 / 댓글 내용으로 사용한다.
- 파일이 없거나 내용이 비어 있으면 None을 반환해
  기존 입력창/템플릿 로직(templates.json)으로 안전하게 폴백한다.
"""

import os
import random
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESSAGES_FILE = os.path.join(BASE_DIR, "message.txt")
COMMENTS_FILE = os.path.join(BASE_DIR, "comment.txt")

_FILES = {"message": MESSAGES_FILE, "comment": COMMENTS_FILE}

_lock = threading.Lock()

# ── 샘플 후보 (파일이 없을 때 자동 생성용 — 100줄씩) ──────────
_MSG_A = [
    "안녕하세요.",
    "안녕하세요, 반갑습니다!",
    "블로그 잘 보고 갑니다.",
    "포스팅 잘 읽었습니다.",
    "글이 정말 유익하네요.",
    "방문해서 좋은 글 많이 봤어요.",
    "즐겁게 읽고 갑니다.",
    "정보 감사합니다!",
    "좋은 글 감사합니다.",
    "꾸준히 보고 있는 독자입니다.",
]
_MSG_B = [
    " 서로이웃 신청드립니다. 함께 소통해요 :)",
    " 서로 이웃해서 좋은 글 공유하고 싶어요.",
    " 이웃 신청합니다. 승인 부탁드립니다!",
    " 서로이웃 맺고 자주 소통하겠습니다.",
    " 함께 성장하는 이웃이 되고 싶어요.",
    " 서이추 신청드립니다. 감사합니다!",
    " 이웃 신청드려요. 앞으로 잘 부탁드립니다.",
    " 서로이웃 수락 부탁드립니다!",
    " 함께 소통할 이웃을 찾고 있어요. 신청드립니다.",
    " 동네친구처럼 소통하며 지내요. 서이추 신청!",
]
_CMT_A = [
    "정말 유익한 글이네요.",
    "좋은 정보 감사합니다.",
    "글 잘 읽고 갑니다.",
    "사진도 글도 멋지네요!",
    "생각이 깊은 글이에요.",
    "꿀팁 대박이에요! 감사합니다.",
    "읽을수록 매력적인 블로그네요.",
    "오늘도 잘 보고 갑니다!",
    "이런 글이 꼭 필요했어요.",
    "리스트업 해놓고 자주 보겠습니다.",
]
_CMT_B = [
    " 다음 글도 기대할게요!",
    " 남겨둔 것처럼 자주 올게요.",
    " 공감하며 읽었습니다.",
    " 저도 같은 경험이 있어서 더 와닿네요.",
    " 덕분에 많은 도움 됐어요.",
    " 친구 분들한테도 공유할게요.",
    " 북마크 해갑니다!",
    " 화이팅입니다!",
    " 앞으로도 자주 방문하겠습니다.",
    " 좋은 하루 보내세요!",
]

DEFAULT_SAMPLE_MESSAGES = [a + b for a in _MSG_A for b in _MSG_B]      # 10×10 = 100줄
DEFAULT_SAMPLE_COMMENTS = [a + b for a in _CMT_A for b in _CMT_B]      # 10×10 = 100줄


def path_for(kind: str) -> str:
    """kind('message'|'comment')에 해당하는 텍스트 파일 경로"""
    return _FILES.get(kind, "")


def _read_text(path: str) -> str:
    """인코딩 자동 감지 텍스트 읽기 (UTF-8 → CP949). 실패 시 빈 문자열."""
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            break
    return ""


def load_lines(kind: str) -> list:
    """
    텍스트 파일을 줄 단위 후보 리스트로 읽기.
    - 빈 줄/앞뒤 공백만 있는 줄은 제외
    - 파일 없음·읽기 실패·내용 없음 → 빈 리스트
    """
    path = path_for(kind)
    if not path or not os.path.exists(path):
        return []
    text = _read_text(path)
    if not text or not text.strip():
        return []
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return [ln for ln in lines if ln]


def ensure_default_files(create_samples: bool = True) -> list:
    """
    message.txt / comment.txt 중 없는 파일을 샘플(100줄)로 생성한다.
    Returns: 새로 생성된 파일 경로 리스트 (이미 있으면 [])
    사용자가 직접 편집한 파일은 절대 건드리지 않는다.
    """
    created = []
    if create_samples:
        samples = {
            MESSAGES_FILE: DEFAULT_SAMPLE_MESSAGES,
            COMMENTS_FILE: DEFAULT_SAMPLE_COMMENTS,
        }
    else:
        samples = {}
    with _lock:
        for path, lines in samples.items():
            if os.path.exists(path):
                continue
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                created.append(path)
            except Exception:
                pass
    return created


def pick_random(kind: str, used: set):
    """
    텍스트 파일에서 줄 단위 무작위 1개 추출.
    - 최근에 사용한 줄은 used 집합으로 회피 (전부 사용 시 used 초기화 후 재추출)
    Returns: 성공 시 텍스트 문자열 / 파일 없음·비어 있음·오류 시 None
             (None이면 호출부가 기존 입력창/템플릿 로직으로 폴백)
    """
    with _lock:
        lines = load_lines(kind)
        if not lines:
            return None
        available = [ln for ln in lines if ln not in used]
        if not available:
            # 파일에 실제 존재하는 줄만 used에서 제거 (다른 출처 항목 보존)
            used.difference_update(lines)
            available = list(lines)
        picked = random.choice(available)
        used.add(picked)
        return picked
