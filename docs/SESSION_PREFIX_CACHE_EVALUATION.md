# 会话级 KV 前缀缓存：实现与隔离验证

2026-09-20。沿用本地 tokenizer，新增可选会话级 cache salt。没有改变模型权重、分类提示、候选内容、码表准入或 plan schema；不进行 SFT。

## 实现和部署

请求 ID 继续每次唯一，cache salt 可按会话稳定。客户端以 state 路径、服务端地址、模型、工作目录摘要、Pi session ID 计算命名空间；不同工作目录与会话隔离。必须显式设置 `PIJIT_PREFIX_CACHE=1`，服务端能力协商返回 `prefix_cache_version=1` 才发送。缺少会话或工作目录时保留原路径，旧服务器不会被误记为启用了缓存。

服务端新增可选、有长度限制的 `cache_salt` 字段；缺省继续每请求隔离。接口记录分类首次输出时的 `num_cached_tokens`，与逻辑输入 token、生成 token、分类控制记录分别统计。缓存机制来自 vLLM，TAIR 的改动是修复接入方式和提供实测记录。

当前运行模块与仓库原版本逐字节一致后才部署。分类、暂停、恢复辅助函数的字节未改，只替换接口模块；旧版本保存在远端 `/tmp/tair-prefix-cache-20260920-a/rollback.py`，也保存在冻结部署证据中。确认 running/waiting 为零后重启了实验容器，等待模型及 CUDA graph 恢复，再验证 capabilities、普通 chat 的 OK 回复，以及真实融合接口。没有清空用户 SQLite 码表，没有更改用户 Agent 默认配置。

环境：yuesheng 6×RTX 5090，DeepSeek-V4-Flash-Vision-Exp，vLLM `0.28.1rc1.dev137+g5ab628dd1`；实机 TP=2、PP=3、max-num-seqs=4，原本已启用 prefix caching。客户端 Pi 0.85.1，沿用先前验证的本地 tokenizer 快照。

## 固定输入单变量试验

真实 `/v1/openjev/toolcall`，一次引擎会话完成分类与 JSON 续写。两组仅 cache salt 不同，提示与 schema 相同。三个前缀长度、各三次重复，每组连续三个相关请求（首个冷请求，后两个暖复用机会），组顺序固定随机化，共 54 次调用，无全局缓存清空。每组序列有独立随机命名空间，不能借用其他序列的 KV。

此试验只有一个分类标签和固定 OK JSON，用于验证缓存机械行为与延迟，不是业务语义正确率测试。tokenizer 准备不计入 HTTP 时间；暖请求表按预先定义的第 2、3 次请求计算，每格 n=6，冷请求仍完整保留在原始数据。提示生成器和配对输入摘要已保存；随机 nonce 原文未单独保存，不能宣称逐字节完整重放。

| 提示前缀长度 | 随机 salt 暖机会中位数 | 稳定 salt 暖请求中位数 | 中位耗时减少 | 稳定组实际复用 |
| --- | ---: | ---: | ---: | ---: |
| 约 1.6K token | 0.777 秒 | 0.752 秒 | 3.2% | 1536 token |
| 约 8K token | 1.089 秒 | 0.836 秒 | 23.2% | 7936 token |
| 约 16K token | 1.569 秒 | 0.896 秒 | 42.9% | 15872 token |

54 次固定回复均正确。随机 salt 组每次复用为零；稳定组每个序列首请求也为零。样本量小，网络、内核预热等噪声仍在，不能把这个百分比当作完整 Agent 加速倍数。

## 完整 Agent 复测

21 个既有自编开发回归任务，两组共 42 次。TAIR 本地准备 + 会话缓存，对照同一服务上的朴素 tools；两组输出上限 17408，TAIR 每子工具参数 2048，模板关闭，动态内容码表持续学习，初始码表为用户只读快照。每题每组一次，串行随机交错，同任务同工作目录及初始文件，150 秒限制，无测试器重试。计时包括启动、工具、恢复及最终回复，独立 oracle 在外。

产物正确且正常结束为主指标，不能代替所有过程指令验收。所有失败保留并计时。运行中冻结代码、任务与顺序。候选目录仍会随入表和检索结果变化，因此实际共享前缀不一定长；本轮不混入目录冻结或提示词重新布局。

完整 42 次运行已经完成，并再次独立执行全部产物 oracle。结果如下：

| 指标 | 朴素 tools | TAIR 本地准备 + 会话缓存 |
| --- | ---: | ---: |
| 正确且正常结束 | 21/21 | 20/21 |
| 累计端到端耗时（包含失败） | 209.19 秒 | 203.61 秒 |
| 生成 token | 19710 | 10671 |
| 逻辑输入 token | 223339 | 349113 |
| 分类控制记录 | 0 | 55 |
| 模型请求 | 82 | 55 |
| 工具错误 | 3 | 8 |
| 重复任务子集 | 4/4，35.93 秒 | 4/4，24.93 秒 |

TAIR 的 55 次请求全部报告 session 模式及缓存统计，其中 16 次非零，累计复用 46592 token。该数约占逻辑输入的 13.35%，不能等同 GPU 计算量下降比例。远端 `/tokenize` 调用为零，本地 tokenization 658 次；准备阶段累计 10.24 秒，生成 HTTP 158.10 秒，其余客户端、工具等耗时约 35.27 秒。

TAIR 唯一失败为 `nullable_changed`：旧 SQL 被误复用，没有排除全 NULL 分组。该任务正常结束且无工具错误，但语义 oracle 未通过；用时 8.03 秒、生成 436 token，失败保留在总量中。因此总耗时少 2.7% 不能称为等质量提速。

前一轮仅本地 tokenizer 的 TAIR 总耗时为 192.24 秒，本轮为 203.61 秒。跨轮轨迹与时序不同，不能据此证明缓存降低或提高了完整 Agent 耗时；目前明确成立的是固定输入下长前缀复用收益，完整 Agent 的增量收益尚未建立。候选及提示变化仍会缩短可共享前缀，本轮没有逐请求前缀差分证据，不能把所有零命中归因于单一原因。

`repair_failure` 两组均先运行 `python3 check_calc.py`，检查器文件未改变；这是定向过程检查，不等同完整过程指令合规验收。完整汇总见 [JSON](SESSION_PREFIX_CACHE_EVALUATION.json)。

## 草稿解码兼容性检查

已只读核对实机：Arctic Inference 未安装；当前 vLLM 配置中虽有 suffix decoding 支持，但本项目 V1 分类钩子遇到 speculative metadata 会直接拒绝，V2 钩子要求每请求只有一行 logits。两者都没有实现多草稿 token 的验证/接受路径。不能直接打开 suffix 参数并声称融合分类仍正确。

实机 streaming input 校验并没有一概禁止所有 speculative 配置，不能把限制错误归因成“整个 vLLM 都不支持”；本次明确查到的是依赖缺失和我们自己的分类钩子限制。TP/PP 与具体草稿方法的完整组合尚未实测。

下一步原型应将历史内容仅放入草稿提议通道，用当前需求下的目标模型分布验证；先隔离验证生成路径，再接分类与续写切换。分类阶段需明确不走草稿验证，生成阶段需要正确处理多 token 接受、拒绝位置、grammar 状态及 KV 更新，不能删掉保护检查冒充支持。该第三路径本轮未实现、未给出加速成绩；SFT/RL 也未启动。

参考：[vLLM prefix caching](https://github.com/vllm-project/vllm/blob/main/docs/design/prefix_caching.md)、[Suffix Decoding](https://github.com/vllm-project/vllm/blob/main/docs/features/speculative_decoding/suffix.md)、[REST](https://github.com/FasterDecoding/REST)。

[固定输入原始证据](../results/experiments/prefix-cache-fixed-20260920-a/) · [部署与回滚证据](../results/experiments/prefix-cache-deployment-20260920-a/) · [完整 Agent 证据](../results/experiments/session-prefix-paired-20260920-a/)
