# Python 本地文件读写：朴素与 TAIR 单次对照

2026-09-19，正式各一次，没有重试或删掉失败。相同现有 yuesheng 5090 模型服务、相同提示、相同绝对项目路径，先朴素原生多工具，再 TAIR。每次恢复为空 file_io.py，独立空状态和码表。单次外层输出预算均 8192 token，任务上限 180 秒。服务未重启或修改，工具在本地 macOS 隔离环境运行。

任务保持小规模：仅标准库，实现 read_text(path) 和 write_text(path,text,append=False)，支持 UTF-8、str/Path、覆盖/追加；缺失文件或父目录正常报错，无 CLI、网络或额外框架。交付 unittest 测试并运行。精确提示及独立 oracle 在 `benchmarks/benchmark_file_io.py`。

| 指标 | 朴素原生多工具 | TAIR（当前优化开启） |
|---|---:|---:|
| Agent 完整耗时 | 8.675851 秒 | 9.969769 秒 |
| 输出 token 总量 | 866 | 947 |
| 模型请求 | 3 | 3 |
| 输入 token | 6,777 | 7,640 |
| 分类控制记录 | 0 | 0 |
| compact_edit / 码表命中 | 0 / 0 | 0 / 0 |
| 工具错误 | 0 | 0 |
| 独立验收 | 通过 | 通过 |
| 独立验收额外耗时 | 0.080467 秒 | 0.118286 秒 |
| 用量完整 | 是 | 是 |

Agent 耗时从进程启动到最终回复结束，包括规划、文件工具和自测，不含 SSH/夹具准备。独立验收时间单列。输出 token 累加全部模型回复，包括生成代码、工具参数和最终回复，并非只统计最后一段文本。输入 token 和分类控制记录不混入生成 token。

**本次 TAIR 慢 1.293918 秒（约 14.91%），多输出 81 tokens（约 9.35%）。** 两组基础实现几乎相同，差异主要是说明文本与测试内容；不能把具体耗时差全部归因于某一层开销。只有一次配对、固定执行顺序，没有统计显著性或一般性能结论。

从零写文件没有进入 compact_edit，因此动态码表没有参与，不能据此否定已经测得的热复用收益；同样不能声称 TAIR 对这种小任务有加速。两组都只有 3 次模型请求，当前路由/规划优化没有减少调用数。

独立验收使用 TemporaryDirectory，检查 Unicode/LF 字节、str/Path、覆盖、追加、空内容、新文件追加、缺失文件/父目录异常，并重新运行各自产出的 unittest。源码审阅确认导入仅定义函数和导入 pathlib，无顶层文件 I/O；工具轨迹未出现网络操作或无关目录探查。没有手动修改模型产物。

原始文件：

- 朴素：`results/experiments/file-io-20260919-a/native_multi/project-after/`
- TAIR：`results/experiments/file-io-20260919-a/hybrid/project-after/`
- 公开统计：`FILE_IO_COMPARISON_RESULTS.json`

运行器复用已有冷任务对照流程，增加可传入场景，保持端口扫描任务的默认场景。357 项仓库回归测试通过。源码快照、模型用量、实际工具轨迹、服务前后状态和 SHA-256 保留；临时隧道已关闭。现有服务带有此前实验补丁，朴素组走普通 tools API，并非单独部署未修改 vLLM 的 A/B。

```sh
python benchmarks/benchmark_file_io.py --url "$URL" \
  --tokenizer-revision "$VERIFIED_REVISION" \
  --out results/experiments/file-io-NEW --timeout 180
```
