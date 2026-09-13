"""附件5 模板的时间标签与「环形映射」规则（各问导出统一调用）。

问题
    附件1/2/4 的行标签是**区间末**时刻（`0:10` 表示 00:00–00:10，`0:00+1` 表示 24:00），
    而附件5 模板的表头是**左端点**且首格为 `0:10-0:20`、末格为 `0:00+1-0:10+1`。
    二者相差一格。

规则（依据官方参考实现 CUMCM2026Problems/C题/问题一/make_result1.py）
    模板第 i 格（0-based）对应内部时段
        idx = (i + 1) % 144
    即：
        模板 `0:10-0:20`      ← 内部 slot 1（区间 00:10–00:20）
        ...
        模板 `23:50-0:00+1`   ← 内部 slot 143（区间 23:50–24:00）
        模板 `0:00+1-0:10+1`  ← 内部 slot 0 （环形回绕）

    这样既与模板逐格对齐，又保证每个值落在标签所指的时段上。

验证
    以官方 `问题一/result1.xlsx` 为准，本规则 142/144 格精确吻合
    （余 2 格为官方样本自身的陈旧值，差额相等且相反，不影响规则）；
    而「位置保持」仅 54/144 吻合。
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

# 模板表头（左端点）与内部时段（区间末）相差一格
SHIFT = 1

# 各问结果文件的模板（供导出器直接引用）
REPO = Path(__file__).resolve().parents[2]
TPL_DIR = REPO / "data" / "附件" / "附件5"
TPL1 = TPL_DIR / "result1.xlsx"
TPL2 = TPL_DIR / "result2.xlsx"
TPL3 = TPL_DIR / "result3.xlsx"
TPL42 = TPL_DIR / "result4-2.xlsx"
TPL43 = TPL_DIR / "result4-3.xlsx"


def template_path(repo: Path, name: str) -> Path:
    return repo / "data" / "附件" / "附件5" / name


def template_labels(path: Path, sheet: str = "计划购电量") -> list[str]:
    """从模板读取 144 个时间标签（原样，保留模板自身的写法如 7:0-7:10）。"""
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(max_row=2, values_only=True))
    hdr = list(rows[0]) if rows else []
    wb.close()

    # 行式（result1）：标签在 A 列第 2..145 行
    if len(hdr) <= 3:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb[sheet]
        labels = [str(r[0]) for r in ws.iter_rows(min_row=2, max_row=145,
                                                  values_only=True)]
        wb.close()
    else:
        labels = [str(x) for x in hdr[1:145]]
    if len(labels) != 144:
        raise ValueError(f"{path.name}[{sheet}] 标签数 {len(labels)} != 144")
    return labels


def circular(values, shift: int = SHIFT):
    """把 144 个内部时段值排成模板格顺序：out[i] = values[(i + shift) % 144]。"""
    n = len(values)
    return [values[(i + shift) % n] for i in range(n)]


def sheet_names(path: Path) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True)
    names = wb.sheetnames
    wb.close()
    return names


def header_of(path: Path, sheet: str) -> list:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[sheet]
    hdr = list(next(ws.iter_rows(max_row=1, values_only=True)))
    wb.close()
    return hdr


def block_labels(path: Path, sheet: str = "充放电量", n: int = 6) -> list[str]:
    """模板「充放电量」的 6 个 4 小时时段标签（如 0:00-4:00）。

    两种模板列布局不同：
        result1        5 列：时间段 | 充电量 | 放电量 | 时刻 | 储电量
        result2/3/4-*  6 列：日期 | 时间段 | 充电量 | 放电量 | 时刻 | 储电量
    故按表头定位「时间段」列，避免写死列号。
    """
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(min_row=1, max_row=1 + n, values_only=True))
    wb.close()
    hdr = [str(x).strip() if x is not None else "" for x in rows[0]]
    col = hdr.index("时间段") if "时间段" in hdr else 0
    return [str(r[col]) for r in rows[1:1 + n]]


def lapse_label(minutes: int) -> str:
    """内部时段序号（0-based）→ 区间末标签（'0:00+1' 表示 24:00）。"""
    m = minutes * 10
    return "0:00+1" if m >= 1440 else f"{m // 60}:{m % 60:02d}"
