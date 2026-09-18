# TAIR figures / TAIR 配图

The English paper embeds PNGs from `en/`; the Chinese paper embeds matching
PNGs from `zh-CN/`. Each figure also has SVG and PDF exports. Both editions
use the same data and layout. Figure numbers below follow the papers, while
file prefixes remain stable for reproduction.

英文与中文 README 分别内嵌对应语言的 PNG；每张图同时提供 SVG 与 PDF。
两套图使用相同数据与布局。下表编号为正文图号，文件前缀保持稳定。

| Figure / 图 | File prefix | Subject / 内容 | Basis / 依据 |
| --- | --- | --- | --- |
| 1 | 01-architecture | Architecture / 整体架构 | Implementation schematic / 实现示意 |
| 2 | 05-protocol-compression | Compact edits / 紧凑编辑协议 | Mechanism schematic / 机制示意 |
| 3 | 10-schema-boundary | Schema guarantees / 结构约束边界 | Interface checks and observed counterexample / 接口检查与实测反例 |
| 4 | 06-kv-continuation | Retained KV / KV 续写 | Schematic with measured prefix reuse / 示意与实测前缀复用 |
| 5 | 07-codebook-lifecycle | Codebook lifecycle / 码表生命周期 | Prototype flow / 原型流程 |
| 6 | 02-output-accounting | Output accounting / 输出开销 | Archived experiment / 实验归档 |
| 7 | 03-service-intervals | Service intervals / 服务内时间 | Two distinct workloads / 两种不同工作负载 |
| 8 | 09-codebook-timeline | Ten-task timeline / 十任务时间线 | Archived experiment / 实验归档 |
| 9 | 04-gate-reliability | Gate reliability / 门控可靠性 | Five classification events / 五次分类记录 |
| 10 | 08-break-even-model | Break-even model / 收益条件 | Illustrative assumptions, not measurements / 假设曲线，非实测 |

From the repository root / 在仓库根目录执行：

```sh
pip install -e '.[paper]'
python benchmarks/render_paper_figures.py
```

Chinese rendering requires Noto Sans CJK or WenQuanYi Zen Hei at one of the
font paths declared in the renderer. PNGs and PDFs are suitable for viewing
without those fonts installed; text-based SVGs may require a compatible font.
`data.json` records the experimental source paths and hashes, plus assumptions
used by the illustrative cost model. Frozen experimental evidence is not modified.

中文渲染需要脚本指定路径下的 Noto Sans CJK 或文泉驿正黑字体。
PNG 和 PDF 可直接查看；保留文本的 SVG 可能需要兼容字体。
`data.json` 记录实验来源及哈希和成本模型假设，不改动冻结实验数据。
