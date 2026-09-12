# question2 最终方案

先阅读 [建模说明](建模说明.md) 与 [结果说明](结果说明.md)。主代码在 `code/`，正式数据、图表及完整对照在 `results/`；交付表为 [result2.xlsx](results/result2.xlsx)。

已安装仓库根目录 `requirements.txt` 后，在根目录执行：

```powershell
python -X utf8 question2/code/run_experiment.py --first-residual 7 --only uniform56 --out recommended_only
```

从其他工作目录可使用脚本绝对路径。指定 `--out` 的相对输出目录以本问 `results/` 为基准。无独立输出参数的第一问与4-2会更新同名结果，请先备份需要保留的版本。本次整理没有重新运行优化，上述命令供以后复现使用。

原验证记录保留在结果目录；新路径及文件完整性检查由根目录 `tools/validate_layout.py` 单独执行。

根目录 `results/run_metadata.json` 描述已经发布的推荐结果（`first_residual=7`）；`first_residual=0` 对照实验的原元数据保存在 `results/variants/run_metadata.json`，不要用它解释正式结果。


## 完整候选与发布流程（需要重新生成全套时）

```powershell
python -X utf8 question2/code/run_experiment.py
python -X utf8 question2/code/run_experiment.py --extended --only uniform28 uniform42 online_extended --out extensions/short_windows
python -X utf8 question2/code/run_experiment.py --first-residual 7 --initial 8550 --only uniform56 half_life28 online_primary --out sensitivity/valid_residuals
python -X utf8 question2/code/verify_window.py
python -X utf8 question2/code/verify_window.py --root question2/results/extensions/short_windows
python -X utf8 question2/code/verify_window.py --root question2/results/sensitivity/valid_residuals
python -X utf8 question2/code/check_information.py
python -X utf8 question2/code/report_experiment.py
```

`--root` 是显式CLI路径，相对当前工作目录；上面按仓库根目录书写。最后一步依赖完整对照并发布推荐文件。单独运行推荐候选不会覆盖 `results/result2.xlsx`，新文件在 `results/recommended_only/variants/uniform56/`。原基础程序及其历史基准输出在 `common/q2_base/`，是活动依赖，不是另一个主结果。
