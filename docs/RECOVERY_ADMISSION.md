# 失败 plan 中已完成写入的恢复后补录

2026-09-20。write-references-ablation-20260920-b 的原 plan 组中，JavaScript 首次和
重复任务都先成功 write，再因 bash 引号错误失败；下一 plan 仅补跑检查。原学习接口
只处理整个 plan 成功时本 plan 的 write/edit，因此两次最终文件正确，却一直没有入表。

新增默认关闭的 PIJIT_RECOVERY_ADMISSION=1。在现有 generic_plan_chat 请求生成最终
reply_user 后，检查当前用户任务的实际执行历史，无需新增模型请求或桥接进程：

- 按 toolCallId 对齐调用和结果，只取失败 plan 的 completed 前缀中成功的 write/edit。
- completed 数量、failed_step 范围、工具顺序必须相符；无法确认时不补录。
- 最新 plan 必须成功且含 bash，模型必须已选择最终回复，不能有待执行调用。
- 后续成功 plan 已经 write/edit 的路径走原学习流程，不再作为漏录路径处理。
- 新用户任务隔离历史；未执行步骤、最终仍失败、仅 read 成功、未知调用均不补录。
- 读取当前工作区最终文件，沿用 UTF-8、大小及工作区路径边界，不使用历史 write 文本。
- 只入内容表，不从失败历史合成成功模板，不追补复用次数。cache_error 不阻断最终回复。

含 bash 的成功 plan 和模型结束决定都不是语义证明。补录条目仍标记为
semantic_correctness_unverified，后续复用必须判断当前要求。这是执行观察层面的修复，
不能声称任意自写检查都可靠。实际模型未到最终回复、历史被压缩丢失、纯 bash 写文件、
条件回复直接交付、普通学习接口此前发生存储错误等路径不由本改动补齐。

## 验证

新增测试覆盖真实 Pi 0.85.1 执行 write 成功、bash 失败、下一 plan bash 成功，随后读取
最终文件入表；检查输入尚未执行、跨任务、错配结果、读取成功、持续失败均拒绝。
另验证默认关闭、单次模型调用、不向工具传递额外协议、不产生模板或复用奖励。

离线回放使用上一轮真实归档消息与产物副本，独立临时 SQLite 状态，从未改动归档或
用户码表。首次漏录内容新增 1 条；重复任务检索时可见该条目。回放第二次旧轨迹又新增
不同任务 contract 下的条目，这是原存储键 contract+source 的行为；检索会去重相同源码。
SQL 的成功重写已走常规学习，不触发补录。三个保存产物重新执行独立 oracle 均通过。

本地两次实际补录约 1–2 毫秒，仅为文件读取与 SQLite 操作微测量，不包括 LLM，也不是
端到端加速证据。离线回放没有重新运行模型，不改变原轨迹已经发生的生成和工具错误。
下一次检索可见条目不等于分类会选择它，更不等于已经产生正确复用。

```sh
/tmp/tair-test-venv-20260918/bin/python benchmarks/replay_recovery_admission.py docs/RECOVERY_ADMISSION_REPLAY.json
```

[回放结果与源码哈希](RECOVERY_ADMISSION_REPLAY.json) · [原始实验](WRITE_REFERENCES_EVALUATION.md)
