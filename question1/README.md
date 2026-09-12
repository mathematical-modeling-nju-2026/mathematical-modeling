# question1 最终方案

先阅读 [建模说明](建模说明.md) 与 [结果说明](结果说明.md)。主代码在 `code/`，正式数据、图表及完整对照在 `results/`；交付表为 [result1.xlsx](results/result1.xlsx)。

已安装仓库根目录 `requirements.txt` 后，在根目录执行：

```powershell
python -X utf8 question1/code/run_q1.py
python -X utf8 question1/code/plot_q1.py
```

从其他工作目录可使用脚本绝对路径。指定 `--out` 的相对输出目录以本问 `results/` 为基准。无独立输出参数的第一问与4-2会更新同名结果，请先备份需要保留的版本。本次整理没有重新运行优化，上述命令供以后复现使用。

原验证记录保留在结果目录；新路径及文件完整性检查由根目录 `tools/validate_layout.py` 单独执行。
