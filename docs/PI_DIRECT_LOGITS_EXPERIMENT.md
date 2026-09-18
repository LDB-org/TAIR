# Pi 工具：直接 logits 分类后生成参数

本轮实现并验证了直接候选分数读取，不再用生成工具编号的方式代替分类。
这是本地 Transformers 推理原型，不是已部署到 DeepSeek/vLLM 的完整 Pi Agent。
早期 `benchmarks/schema_toolcall.py` 已有两工具的同类 toy 路径；此前 Pi 接入使用的却是受约束生成工具编号。
本轮扩展到真实 Pi 的 8 个内置工具及 reply_user，并加入参数 grammar 和逐次缓存验证。

## 实现

`deploy/logit_toolcall.py`：

1. 上下文、任务、9 个工具选项进入一次 `model.forward()`。
2. 使用 OpenJev `_slot_ids` 检查单 token 候选，直接从最后位置的原生 LM head logits 读取对应分数。
3. 在候选内 argmax 选择工具，不调用生成循环生成类别；记录全部候选 logits、条件概率和候选概率质量。
4. 引擎将已知选择及选中工具的参数指令作为确定性后缀输入。
5. 沿用同一个 KV cache，只计算新增后缀，然后按该工具的 XGrammar JSON Schema 自回归生成参数。
6. 引擎添加工具名与调用包装，构造调用对象。实验不执行工具。

分类依旧使用现有生成模型的 LM head，没有训练独立分类头。
“分类输出 token 为零”不代表免费：分类 prefill、读取分数和选择结果的缓存条件化都有成本。
选中的标签由引擎注入后缀，并非模型生成的输出 token；所有注入 token 均计入实际 prefill 处理量。
条件概率只是在给定候选内归一化的分数，不能视为校准后的正确率。

## 环境和方法

- 本地 RTX 4070 12 GB，仅暴露 CUDA GPU 0。
- Qwen3-1.7B，BF16，revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`，使用完整本地权重。
- PyTorch 2.10.0+cu128、Transformers 5.17.0、XGrammar 0.1.29。
- 真实 Pi 0.85.1 Schema，9 类工具各一个简短任务、各重复两次，三条路径共 54 次调用。
- 相同模型、greedy、参数最多 192 个输出 token；固定种子打乱运行顺序，保留但排除一次预热。
- 不修改共享 DeepSeek 服务，不调用本地工具，不宣称多轮 Agent 正确率。

三条路径：完整工具调用的受约束 JSON 生成；直接分类＋缓存参数生成；直接分类＋丢弃缓存后重算参数前缀。
后两者使用相同提示文本，差别只在参数阶段是否复用分类 cache。
完整 JSON 路径提供全套 Schema；直接路径分类时只提供工具说明，参数阶段提供选中的 Schema。
因此它也是一种提示组织优化，不能把全部时间差归因于“分类不输出 token”。

每次 forward 记录阶段、已有缓存 token 数、新处理 token 数、更新后缓存长度和计时。
模型 forward 前校验完整 token 前缀及缓存长度，防止错误拼接；18/18 缓存路径保留同一个 cache 对象，
18/18 重算路径在参数阶段从零缓存开始。GPU 同步和 Python 调度计入测试成本，不是纯 kernel 时间。

## 全部结果

| 指标，每组 18 次 | 完整 JSON | 直接分类＋缓存 | 直接分类＋重算 |
|---|---:|---:|---:|
| 工具选择正确 | 18/18 | 18/18 | 18/18 |
| 完整符合 grammar 的输出 | 18/18 | 18/18 | 18/18 |
| 完整调用精确匹配预期 | 12/18 | 10/18 | 12/18 |
| 生成 tokens，含 EOS | 378 | 300 | 278 |
| 实际 prefill 处理 tokens | 26426 | 11992 | 21426 |
| 累计生成阶段 | 10.701 s | 8.698 s | 7.951 s |
| 累计完整调用时间 | 12.691 s | 10.344 s | 9.990 s |
| 单次耗时中位数 | 0.682 s | 0.527 s | 0.566 s |

直接分类两组合计 36/36 选对工具，分类阶段生成 token 数均为 0。
缓存路径相对完整 JSON 的输出少 20.6%，累计时间少 18.5%，但精确匹配率也较低，不能宣称等质量加速。
分类缓存路径累计分类 forward 0.877 秒，参数后缀 prefill 0.629 秒；重算组分别 0.901、0.995 秒。

精确不匹配包括漏掉要求的句点、改变 glob 写法、漏掉 literal 参数，以及添加默认参数或改变等价路径写法。
这里统一按精确匹配判定，没有事后 trim 或放宽规则，也没有把所有字符串差异都称为实际行为错误。
任务较简单，部分字面文本的标点要求仍有歧义；结果不足以评价广泛工具选择能力。

## 缓存收益需单独比较

缓存和重算的实际参数输出并非全部相同，未证明逐 token 等价，也未确定差异的具体数值来源。
重算组因为输出较少，整组时间反而更低，不能据此认定缓存无效。
仅取原始参数 JSON 完全相同的 14 对结果（事后条件性子集）：两边均生成 220 tokens，
参数 prefill 总计 0.462→0.772 秒（缓存→重算），完整调用 7.535→7.926 秒。
该子集缓存省约 4.9% 完整时间，支持缓存实际被利用，但不是独立性能保证。

## 复现与边界

在现有测试环境额外安装 `xgrammar==0.1.29` 后，从仓库根目录：

```sh
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/test_direct_pi_logits.py \
  --out results/experiments/NEW-RUN \
  --model /path/to/Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --schemas results/experiments/pi-all-tools-schema-20260918-a/tools.json
.venv/bin/python benchmarks/summarize_direct_pi_logits.py results/experiments/NEW-RUN
```

证据：`results/experiments/pi-direct-logits-20260918-a/`，含源码快照、全部分数、参数输出、forward/cache 记录及独立校验哈希。
138 项 pytest、原始 raw 哈希和 69 项 published claims 校验通过。
本轮证明直接候选读取后接缓存参数生成的实现可行；不证明 DeepSeek 上的收益、Pi 多轮质量或生产可用性。
