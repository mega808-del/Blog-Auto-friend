"""
license_generator.py — BlogGenius 라이센스 키 발급 도구 (관리자 전용)
- 사용 기한(날짜+시간)이 내장된 라이센스 키를 생성한다.
- 발급된 키를 사용자에게 전달하면, 사용자는 프로그램 실행 화면의
  [🔑 라이센스 인증] 창에 키를 입력해 인증한다.

사용 예:
  python license_generator.py                       → (30일 키 생성 예시 출력)
  python license_generator.py --days 30             → 30일짜리 키
  python license_generator.py --hours 12            → 12시간짜리 키
  python license_generator.py --expiry 202612312359 → 2026-12-31 23:59까지 유효한 키
  python license_generator.py --count 5 --days 15   → 15일짜리 키 5개
"""

import argparse
import sys

from core import license as license_mod

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser(
        description="BlogGenius 라이센스 키 발급 도구")
    parser.add_argument("--days", type=int, default=0, help="유효 일수")
    parser.add_argument("--hours", type=int, default=0, help="유효 시간 수")
    parser.add_argument("--minutes", type=int, default=0, help="유효 분 수")
    parser.add_argument("--expiry", type=str, default="",
                        help="만료 일시 직접 지정 (YYYYMMDDHHMM)")
    parser.add_argument("--count", type=int, default=1, help="발급 개수")
    args = parser.parse_args()

    try:
        for _ in range(max(1, args.count)):
            key = license_mod.generate_license(
                days=args.days, hours=args.hours, minutes=args.minutes,
                expiry_str=args.expiry)
            # 키 안의 만료 일시를 읽어 표기
            expires = license_mod._expiry_to_text(key.split("-")[1])
            print(f"🔑 발급 키: {key}")
            print(f"   └ 사용 기한: {expires} 까지")
            if args.count > 1:
                print()
    except license_mod.LicenseError as e:
        print(f"⚠️ 발급 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
