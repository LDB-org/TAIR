# 候选目录与生成续写的指代一致性

2026-09-21。此前目录展示源码、整任务描述和观察路径，却不展示条目哈希；续写指令用
哈希指代选中内容。分类字母仍保留在上下文中，所以不能说旧协议完全无法识别候选，
也没有发现解码器错绑数据库条目的证据。但隐藏于目录之外的哈希并不利于模型对应内容。

现在目录和续写共同使用 Candidate N; observed files: [...]，移除模型不需要的长哈希，
明确 reuse_write 只展开选中的候选。N 是本次检索中的位置，不是持久条目 ID。数据库 ID、
实际内容绑定、分类字母、参数 schema 和生成回退能力均不变。模板续写使用相同指代。
新增回归逐项验证目录、续写、实际展开内容一致；复用路由映射测试继续通过。

## 引擎组件对照

Pi 不参与本组件测试。使用 yuesheng 6×RTX 5090、DeepSeek-V4-Flash-Vision-Exp、TP2/PP3，
同一融合推理接口、本地 tokenizer。两份候选来自此前真实 Agent 保存的 Python JSONL
和 JavaScript uniqueStrings 内容。三种场景各对照旧/新表达，共六次调用，顺序交替。

通过只允许一个分类 token 指定候选，并保留其原目录字母 B/C 与完整目录；不是自然
分类命中率测试。请求参数 schema 逐项断言相同，没有模型生成的 shell 执行和额外推理。
要求生成一个目标文件的 write，随后独立 oracle 验证。不运行额外生成的测试脚本。

| 场景 | 旧表达 | 新表达 |
| --- | --- | --- |
| 指定适用的 JS 候选 | 正确复用，单 write | 正确复用，单 write |
| 指定不适用的 Python 候选 | 错误复用 Python，目标产物失败 | 放弃复用，生成正确 JS，但额外生成两份文件 |
| 指定旧 JS，但当前要求忽略大小写 | 错误复用 | 仍错误复用 |

完整遵守单 write 且产物正确的数量均为 1/3。单独检查目标文件，旧版 1/3、新版 2/3。
新表达在错误语言场景生成了正确实现，但违反组件的单文件协议，因此不能将它算作
完整通过。额外内容为测试文件和运行脚本，没有被执行。

三组对照逻辑输入分别减少 40、38、40 token。适用引用均生成 23 token；错误语言回退
新版生成 316 token，旧版错误引用仅 23 token，不能把快但错误的输出当作可接受基线。
这些是单次组件请求计时，不是完整 Agent 提速证据；本轮没有证明稳定语义选择能力。

## 状态与复核

保留指代一致性的改动。没有重新引入已撤回的短引用自述核对，也没有新增解释文本放行
规则。542 项测试、归档校验通过；未推送或重启模型服务，未清空用户码表。
语义约束变化仍未解决，组件结果不能替代自然分类和完整任务验收。

```sh
/tmp/tair-test-venv-20260918/bin/python benchmarks/probe_candidate_binding.py \
  --out results/experiments/candidate-binding-component-NEW \
  --tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920
```

[独立产物审计](CANDIDATE_BINDING_EVALUATION.json) ·
[冻结源码、原始响应与结果](../results/experiments/candidate-binding-component-20260921-a/)
