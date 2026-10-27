# N7 补充验收：可溯源 Top 15 证据包

## 本补充项做了什么

- 检索结果增加 `evidence` 字段，默认最多返回 15 条证据。
- 每条证据有稳定编号 `E1`–`E15` 和引用标记 `[E1]`–`[E15]`。
- 证据保留完整 `chunk` 原文和 `section_path`。
- 证据映射回原始 Word 块，提供 `block_id` 以及“Word 段落 N”或“表格 N 第 M 行”定位。
- 证据携带产品号、质量状态、三路召回排名、RRF 分数、reranker 概率和最终分数。
- 产品级证据按“小 chunk 检索、产品卡组装”合并：`product_profile` + `product_specs` 合并成一张产品卡，卡内保留两个原始 chunk 的 ID 和全部原文块。
- `source.document` 返回源文件名、本地路径和 SHA256，防止引用到错误版本。
- 硬过滤后不足 15 条时只返回真实命中的证据，不拿无关 chunk 凑数。

## 人工验收

以下命令均需在项目根目录串行执行。

### 1. 运行全部测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

通过标准：当前预期为 **98 passed**。

### 2. 运行证据链路校验

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence.py
```

通过标准：

- 输出 `status` 为 `passed`。
- `comparison.chunks` 前两条为 `card_product_C615`、`card_product_C616`；两张卡分别包含对应产品的概览和规格 chunk。
- `scenario.chunks` 第一条为 `chunk_matrix_scenario_tbl_ac98d42e_t01_r02`。
- `scenario.first_locator.kind` 为 `table_row`，且定位到表格 1 第 2 行。

### 3. 人工查看证据 JSON

```powershell
$result = .\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C615 和 C616 的电池与续航有什么区别？" --top-k 3 --evidence-top-k 15 | ConvertFrom-Json
$result.evidence | Select-Object evidence_id,citation,rank,chunk_id,title | Format-Table -AutoSize
$result.evidence[0].source.document | Format-List
$result.evidence[0].source.blocks | Select-Object block_id,block_type,locator,text | Format-List
```

通过标准：

- `evidence_id` 从 `E1` 开始连续编号，最多 15 条。
- 每条证据都有非空 `text`、`section_path` 和 `source.blocks`。
- `source.document.file_name` 为 `工业外骨骼产品目录.docx`。
- `source.document.sha256` 为 `ac98d42e3e4294856dbc6465183fb10bceca1c7351e0a0a5d313d668f622e2f2`。
- 每个来源块都有 `locator.label`，例如 `Word 段落 89` 或 `表格 1 第 2 行`。
- 产品卡证据的 `card_chunk_ids` 至少包含 `chunk_product_<产品号>_profile` 和 `chunk_product_<产品号>_specs`。

### 4. 验证产品卡合并

```powershell
$result = .\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "腰部外骨骼和上肢外骨骼有哪些 重量是多少" --top-k 15 --evidence-top-k 15 | ConvertFrom-Json
$result.evidence | Select-Object evidence_id,chunk_id,title,card_chunk_ids | Format-Table -AutoSize
```

通过标准：

- `C615` 对应证据的 `chunk_id` 为 `card_product_C615`，`card_chunk_ids` 同时包含 `chunk_product_C615_profile` 和 `chunk_product_C615_specs`。
- 该证据原文中包含 `净重：3.9 kg`。
- 10 款腰背/上肢产品各只有一张产品卡，没有同一产品重复占两个证据槽。

### 5. 验证证据数量规则

```powershell
$scenario = .\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "物流搬运与装卸场景推荐哪些产品？" --top-k 3 --evidence-top-k 15 | ConvertFrom-Json
"returned=$($scenario.evidence.Count)"
$scenario.evidence | Select-Object evidence_id,chunk_id,title | Format-Table -AutoSize
```

通过标准：返回实际命中的场景矩阵证据，编号连续；如果没有 15 条合格证据，不补无关结果。

## 和 N8 的衔接

N8 生成答案时只能使用 `evidence[].text` 中存在的信息，并在关键结论后标注对应证据编号，例如：

```text
C615 的电池为 92Wh（36V 锂离子），续航为 6–8 小时 [E1]。
C616 的对应参数为…… [E2]。
```

最终回答下方展示 `[E1]`–`[E15]` 的证据原文和 Word 定位。没有证据覆盖的事实必须拒答，不能由模型补写。

## 通过条件

以上 1–5 项全部满足，即可判定可溯源证据补充项通过。
