"""
core/excel.py — 작업 기록 Excel(.xlsx) 저장/조회
- openpyxl 기반 (requirements.txt에 추가)
- 작업이 끝날 때마다 기록을 누적 저장
- 프로그램 재실행 후에도 과거 기록 조회 가능
"""

import os
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core import history

# 엑셀 저장 위치 (환경설정에서 변경 가능)
EXCEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "excel_records"
)

HEADER = ["날짜", "시간", "블로그명", "블로그 ID", "작업 종류",
          "메시지", "공감", "댓글", "결과", "오류내용"]


def _ensure_dir():
    os.makedirs(EXCEL_DIR, exist_ok=True)


def _get_daily_path(target_date: str = None) -> str:
    """날짜별 엑셀 파일 경로 (excel_records/work_history_YYYY-MM.xlsx)"""
    _ensure_dir()
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m")
    return os.path.join(EXCEL_DIR, f"work_history_{target_date}.xlsx")


def _ensure_header(ws):
    """1행에 헤더가 없으면 기록 (기존 데이터 보호)"""
    first = [c.value for c in ws[1]] if ws.max_row >= 1 else []
    if [str(v) if v else "" for v in first] != HEADER:
        # 기존 데이터가 1행부터 있다면 한 칸씩 아래로 밀기
        if ws.max_row >= 1 and any(ws.cell(row=1, column=c).value for c in range(1, len(HEADER) + 1)) and \
           [str(ws.cell(row=1, column=c).value or "") for c in range(1, len(HEADER) + 1)] != HEADER:
            ws.insert_rows(1)
        for col, title in enumerate(HEADER, 1):
            ws.cell(row=1, column=col, value=title)


def _style_sheet(ws):
    """시트 헤더 스타일 적용"""
    header_fill = PatternFill(start_color="6C3FA4", end_color="6C3FA4", fill_type="solid")
    header_font = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=11)
    body_font = Font(name="맑은 고딕", size=10)

    for col, title in enumerate(HEADER, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = [
            12, 10, 24, 16, 14, 40, 8, 8, 8, 30
        ][col - 1]

    thin = Side(style="thin", color="444444")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(HEADER)):
        for cell in row:
            cell.font = body_font
            cell.border = border
            cell.alignment = Alignment(vertical="center", wrap_text=False)
    ws.freeze_panes = "A2"


def append_record(rec: dict, target_date: str = None) -> str:
    """
    작업 기록 1건을 엑셀에 추가
    rec: {date, time, work_type, blog_id, blog_name, message, result, error}
    Returns: 저장된 파일 경로
    """
    path = _get_daily_path(target_date)

    if os.path.exists(path):
        wb = load_workbook(path)
        ws = wb.active
        _ensure_header(ws)
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "작업기록"
        # 새 파일: 먼저 헤더를 기록해야 append 데이터가 2행부터 저장됨
        for col, title in enumerate(HEADER, 1):
            ws.cell(row=1, column=col, value=title)

    like_col = "완료" if rec.get("work_type") == history.WORK_LIKE else "-"
    comment_col = "완료" if rec.get("work_type") == history.WORK_COMMENT else "-"
    if rec.get("result") != history.RESULT_SUCCESS:
        like_col = "실패" if rec.get("work_type") == history.WORK_LIKE else like_col
        comment_col = "실패" if rec.get("work_type") == history.WORK_COMMENT else comment_col

    ws.append([
        rec.get("date", ""),
        rec.get("time", ""),
        rec.get("blog_name", ""),
        rec.get("blog_id", ""),
        rec.get("work_type", ""),
        rec.get("message", ""),
        like_col,
        comment_col,
        rec.get("result", ""),
        rec.get("error", ""),
    ])
    _style_sheet(ws)

    wb.save(path)
    return path


def read_records(target_date: str = None) -> list:
    """엑셀 파일에서 기록 읽기"""
    path = _get_daily_path(target_date)
    if not os.path.exists(path):
        return []
    try:
        wb = load_workbook(path)
        ws = wb.active
        records = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and any(v for v in row):
                # None을 빈 문자열로 정규화
                vals = ["" if v is None else str(v) for v in row]
                vals += [""] * (len(HEADER) - len(vals))  # 부족한 칼럼 채우기
                records.append({
                    "date": vals[0],
                    "time": vals[1],
                    "blog_name": vals[2],
                    "blog_id": vals[3],
                    "work_type": vals[4],
                    "message": vals[5],
                    "like": vals[6],
                    "comment": vals[7],
                    "result": vals[8],
                    "error": vals[9],
                })
        wb.close()
        return records
    except Exception as e:
        print(f"[excel] 읽기 오류: {e}")
        return []


def get_monthly_files() -> list:
    """존재하는 월별 엑셀 파일 목록"""
    _ensure_dir()
    files = [f for f in os.listdir(EXCEL_DIR) if f.startswith("work_history_") and f.endswith(".xlsx")]
    return sorted(files, reverse=True)


def open_excel_file(path: str):
    """엑셀 파일을 기본 프로그램으로 열기 (Windows)"""
    if os.path.exists(path):
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])


def open_excel_folder():
    """엑셀 저장 폴더 열기 (Windows 탐색기)"""
    _ensure_dir()
    try:
        os.startfile(EXCEL_DIR)
    except AttributeError:
        import subprocess, sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", EXCEL_DIR])
        else:
            subprocess.Popen(["xdg-open", EXCEL_DIR])
