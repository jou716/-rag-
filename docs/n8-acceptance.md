# N8 验收：LLM 答案生成、引用、证据覆盖与拒答

## 本节点做了什么

- 接入千问 `qwen-max`（DashScope OpenAI-compatible 接口），由模型基于 N7 证据包生成答案。
- 每个事实性段落必须带 `[E#]` 引用；支持 `[E1][E2]` 和 `[E1]–[E3]` 两种写法。
- 生成后执行三层确定性校验：
  1. 引用编号必须存在于当前证据包。
  2. 答案中的数值必须能在被引用的证据原文中找到。
  3. 每个事实性段落或列表必须至少有一个引用。
- 校验失败时自动重写一次，并把具体失败原因回传给模型；第二次仍失败则返回 `status=error`，不展示未经校验的答案。
- 没有证据时不调用模型，直接拒答。
- 价格、保修、CE 认证、蓝牙等目录未提供字段，明确回答“产品目录未提供”，不猜测、不补写。
- 保留 `local` 合成模式仅用于测试和显式切换；LLM 失败时不会自动回退到本地合成。
- `/ask` 返回答案、引用、校验详情和最多 15 条可溯源证据；证据不足时不凑数。

## 关键文件

- `core/answer.py`：答案引擎、引用校验、数值 grounding、缺失字段处理、单次重写。
- `core/llm.py`：OpenAI-compatible LLM 客户端。
- `core/prompting.py`：证据上下文和系统提示词。
- `app/api/ask.py`：`POST /ask`。
- `scripts/ask_demo.py`：命令行问答演示。
- `scripts/check_llm.py`：模型连通性检查。
- `scripts/check_ask_api.py`：真实 `/ask` 路由检查。
- `scripts/evaluate_answers.py`：45 题答案评测。
- `tests/test_answer.py`、`tests/test_ask_api.py`：单元与接口测试。

## 配置

`.env` 中需要以下配置（不要把真实 Key 提交到版本库）：

```dotenv
ANSWER_GENERATION_MODE=llm
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max
LLM_API_KEY=你的千问Key
LLM_TIMEOUT_SECONDS=90
```

## 人工验收

以下命令均需在项目根目录串行执行，避免 Qdrant local 多进程冲突。

### 1. 运行单元测试

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q
```

通过标准：`98 passed`，只有 Starlette/httpx 的弃用警告。

### 2. 检查模型连通性

```powershell
.\.venv\Scripts\python.exe scripts\check_llm.py
```

通过标准：输出 `model=qwen-max` 和 `output=连接成功`，不报 HTTP 错误。

### 3. 验证单事实题

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 的续航时间是多少？"
```

通过标准：

- `状态：answered`
- 答案包含 `6–8 小时` 和 `[E1]`
- 引用为 `E1`

### 4. 验证对比题

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 和 C616 的电池与续航有什么区别？"
```

通过标准：

- 同时出现 `C615` 和 `C616`
- 电池均为 `92Wh`
- 续航分别出现 `6–8 小时` 和 `3–8 小时`
- 引用同时包含 `E1`、`E2`

### 5. 验证缺失字段不硬答

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 的价格是多少？"
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "这些产品是否通过了 CE 认证？"
```

通过标准：

- 状态为 `refused` 或 `partial`
- 答案明确写“产品目录未提供……价格/CE 认证”
- 不出现具体价格、不出现“已通过 CE 认证”等推断

### 6. 验证未知产品拒答

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C999 的续航时间是多少？"
```

通过标准：状态为 `refused`，原因为“产品目录中没有找到 C999 的相关信息”，不调用模型生成答案。

### 7. 验证质量冲突会提示复核

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C655 的最大助力到底是多少？"
```

通过标准：

- 列出证据中的 `25 kg` 和 `4–10 kg`
- 明确说明存在冲突或需要人工复核
- 引用包含 `needs_review` 对应证据

### 8. 验证真实 `/ask` 路由与证据包

```powershell
.\.venv\Scripts\python.exe scripts\check_ask_api.py "C615 和 C616 的电池与续航有什么区别？"
```

通过标准：

- HTTP 200，`status=answered`
- `generation_mode=llm`
- 引用包含 `E1,E2`
- `evidence_count` 在 1–15 之间；对比题应为 2 张产品卡，`chunk_id` 为 `card_product_C615`、`card_product_C616`
- 每条证据都有 `title`、`text`、`section_path`、`source.block_ids`、`source.blocks[].locator` 和 `retrieval.final_score`

### 9. 验证“电动”包含电动推车联动产品

```powershell
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "下肢外骨骼有哪些是电动的"
```

通过标准：

- 泛化问题“下肢外骨骼有哪些是电动的”答案包含 `C689`、`C654`、`C680` 三款，且 `C680` 的动力类型写成“电动推车联动”，不能写成普通“电动/动力”。
- 明确问“电动推车联动的下肢外骨骼有哪些”时，只返回 `C680`，不会把普通电动产品 `C689`、`C654` 混进来。

### 10. 跑完整 45 题答案评测

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_answers.py
```

当前基准（qwen-max，45 题）：

| 指标 | 结果 |
| --- | ---: |
| 可回答题回答率 | 1.0000 |
| 可回答题完整回答率 | 1.0000 |
| 不可回答题严格拒答率 | 1.0000 |
| 不可回答题安全处理率 | 1.0000 |
| 引用存在率 | 1.0000 |
| 引用编号有效率 | 1.0000 |
| 数值 grounding 有效率 | 1.0000 |
| 预期原文块命中率 | 1.0000 |
| 预期原文块平均召回 | 0.9917 |
| 平均单题延迟 | 约 2922 ms |

通过标准：

- `answer_rate=1.0`
- `safe_unanswerable_rate=1.0`
- `citation_presence_rate=1.0`
- `citation_validity_rate=1.0`
- `grounding_validity_rate=1.0`
- 没有 `status=error` 的题
- `mean_source_recall >= 0.99`

`mean_source_recall` 当前为 0.9917，唯一未满分的是 q020（“中端上肢外骨骼有哪些？”）：答案引用了 C653/C683 两张产品卡，但没有额外引用“中端”分级矩阵行。答案本身正确且可核对，因此这是引用粒度选择，不是事实错误。

也可以一键执行：

```powershell
.\scripts\check_n8.ps1
```

## 结果文件

- `data/indexes/answer_eval.json`：逐题答案、状态、引用、来源命中、时延。
- `data/indexes/answer_eval.md`：适合简历和验收查阅的指标表。

## 技术边界

- 答案完全依赖 DashScope 网络与 `qwen-max`；模型不可用时返回 `status=error`，不会用本地合成器兜底。
- 校验失败最多重写一次，避免无限重试和不可控时延。
- 数值 grounding 只校验“数字 + 单位”，不替代人工事实审查；非数值结论仍依赖引用约束和提示词。
- Qdrant local 只支持单进程访问，评测和 CLI 不要并发运行。
- 45 题评测集是项目内人工评测，不等同于线上大规模基准。

## Gradio 页面验收

启动服务后打开 `http://127.0.0.1:8000/ui`（与 `/ask` 同进程，不要单独起第二个进程）。

| # | 操作 | 通过标准 |
|---|---|---|
| 1 | 打开页面 | 正常渲染中文界面，有输入框和示例问题；没有数量滑块，固定请求 15 条证据 |
| 2 | 问 `C615 和 C616 的电池与续航有什么区别？` | 状态为“已回答”，答案含 `92Wh`、`6–8 小时`、`3–8 小时`，引用 `E1`/`E2` |
| 3 | 对照证据卡 | 2 条证据，`chunk_id` 为 `card_product_C615`、`card_product_C616`；卡内“产品卡合并”显示 profile + specs，原文和 Word 段落均可核对 |
| 4 | 问 `C615 的价格是多少？` | 状态为“已拒答”，明确写“产品目录未提供”价格，不猜测 |
| 5 | 问 `C999 的续航时间是多少？` | 状态为“已拒答”，不编造该产品 |
| 6 | 展开原始 JSON | 字段与页面展示一致，`citations`、`evidence`、`status` 可对照 |
| 7 | 问 `腰部外骨骼和上肢外骨骼有哪些 重量是多少` | 证据 14 条；答案列出 10 款产品，C615 归入上肢且净重 `3.9 kg`，不出现“未提供重量” |

页面与 `/ask` 使用同一个 `GroundedAnswerService`，因此页面结果应与接口结果一致；证据数量按实际命中返回，不补足到 15 条。

## 通过条件

以上 1–10 项全部满足，且 `data/indexes/answer_eval.md` 达到上述阈值，即可判定 N8 通过。
