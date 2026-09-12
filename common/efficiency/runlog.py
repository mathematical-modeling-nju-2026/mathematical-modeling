"""以正确编码运行脚本并保存日志（替代 PowerShell 的 `| Out-File`）。

为什么需要它
    之前用 PowerShell 管道保存日志：
        python run_q2_eff.py 2>&1 | Out-File -Encoding UTF8 run_log.txt
    Python 写出 UTF-8 字节 → PowerShell 按 GBK 解释 → 再以 UTF-8 存盘，
    形成「双重编码」乱码，且**部分字节不可逆**（无法事后修复，
    只能重跑）。文件里会出现「闂棰?鏁堢巼」这类字符。

本包装器
    用 subprocess 直接捕获子进程的**原始字节**并写盘，
    完全绕开 PowerShell 的文本管道，彻底避免编码转换。

用法
    python runlog.py --log <日志路径> -- <命令与参数...>

示例
    python runlog.py --log ../run_log.txt -- run_q2_eff.py --eff def2_roundtrip90
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="日志输出路径")
    ap.add_argument("--cwd", default=None, help="工作目录")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后的命令")
    args = ap.parse_args()

    cmd = [c for c in args.cmd if c != "--"]
    if not cmd:
        raise SystemExit("缺少命令；用法: python runlog.py --log x.txt -- <命令>")

    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    # 不做任何文本解码：stdout/stderr 的原始字节直接落盘
    with log.open("wb") as fh:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", *cmd],
            stdout=fh, stderr=subprocess.STDOUT,
            cwd=args.cwd,
        )

    text = log.read_text(encoding="utf-8", errors="replace")
    ok = "闂" not in text and "\ufffd" not in text
    print(f"日志已写入 {log}（{log.stat().st_size:,} 字节）")
    print(f"编码自检: {'✓ 正常 UTF-8' if ok else '✗ 仍含乱码字符'}")
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
