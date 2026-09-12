# question3 最终方案

先阅读 [建模说明](建模说明.md) 与 [结果说明](结果说明.md)。主代码在 `code/`，正式数据、图表及完整对照在 `results/`；交付表为 [result3.xlsx](results/result3.xlsx)。

已安装仓库根目录 `requirements.txt` 后，在根目录执行：

```powershell
python -X utf8 question3/code/run_q3.py --mode all --out reproduced
```

从其他工作目录可使用脚本绝对路径。指定 `--out` 的相对输出目录以本问 `results/` 为基准。无独立输出参数的第一问与4-2会更新同名结果，请先备份需要保留的版本。本次整理没有重新运行优化，上述命令供以后复现使用。

原验证记录保留在结果目录；新路径及文件完整性检查由根目录 `tools/validate_layout.py` 单独执行。

## 「90% 效率」两口径对照

题目只写「充放电效率为 90%」，存在两种解读（往返 0.81 vs 0.90）。
本问已在两口径下重跑，主方案总费用 14,022,396.98 → 13,558,297.17 元（−3.31%）。
详见 [efficiency/README.md](efficiency/README.md)；总说明见根目录 [EFFICIENCY.md](../EFFICIENCY.md)。

> `efficiency/results/` 是**定义二**（往返 0.90）的结果；
> **定义一**（往返 0.81）与本目录 `results/` 逐值相同，不另存副本。
