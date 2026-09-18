# TAIR naming and compatibility

**TAIR — Typed Action Inference Runtime** is the project and research name.
The Chinese name is **类型化动作推理运行时**.

The name describes the runtime's scope:

- **Typed**: actions and arguments have declared candidate domains and schemas.
- **Action**: the interface represents executable tool calls, including `reply_user`.
- **Inference**: the engine selects actions and generates open-ended arguments.
- **Runtime**: deterministic construction, KV continuation and codebook-based action
  specialization coordinate execution at runtime.

The four engineering contributions remain compact operations, engine-side typed
classification, retained-KV continuation, and the dynamic codebook prototype.
Renaming does not change the experiments or establish new performance claims.
TAIR continues to combine classification and generation; it is distinct from the
classification-only [vllm-jev-decison](https://github.com/siliconkernel/vllm-jev-decison) plugin.

## Current names

| Surface | Name |
| --- | --- |
| Project / report | TAIR |
| Full name | Typed Action Inference Runtime |
| Python distribution | `tair` |
| GitHub repository | `LDB-org/TAIR` |
| Local workspace | `~/TAIR` |
| Interactive client | `pijit`, displaying TAIR |
| Benchmark SSH-host variable | `TAIR_ENGINE_HOST` |

The earlier research name was ClassWeave; the earlier checkout/distribution names
were `Engine-toolcall` / `engine-toolcall`. The old local checkout path remains a
symlink to `~/TAIR` so existing commands and virtual-environment launchers continue
to work. The `pijit` entry point itself uses the canonical TAIR path.

## Deliberately retained interfaces

- `openjev_phase1` remains the Python import name for historical compatibility.
- `/v1/openjev/toolcall` and `openjev_direct_classify` remain engine wire interfaces.
- Existing service filenames and installation locations are unchanged; no model
  service was restarted or reinstalled for this rename.
- `ENGINE_TOOLCALL_HOST` remains a fallback when `TAIR_ENGINE_HOST` is unset.
- `pijit` keeps its command, model identifier and `~/.pijit` state, preserving sessions
  and project codebooks. Newly loaded clients display TAIR.
- Frozen experiment files and migration manifests retain their original bytes,
  identifiers and source hashes. They describe the implementations actually tested.

## 中文说明

项目正式名称为 **TAIR（Typed Action Inference Runtime，类型化动作推理运行时）**。
中英文报告、配图、包信息和交互客户端展示名称统一使用 TAIR。

四项机制与实验结论保持原样。TAIR 仍然研究分类与生成协同，不等同于另一个纯分类插件。
旧工作目录保留兼容链接；旧 Python import、引擎 API 和服务路径保留兼容性；历史实验
原始记录不改写。现有 `pijit` 会话与码表继续使用，重新启动或加载扩展后显示新名称。
