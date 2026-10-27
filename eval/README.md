# N4 评测集

`questions.jsonl` 是人工整理的检索与问答评测集，共 45 题：

- 可回答 40 题
- 不可回答 5 题
- 覆盖事实、产品概览、筛选、场景推荐、对比、章节知识、数据质量和拒答

## 字段说明

- `question_id`：稳定题号，后续评测报告引用它
- `question_type`：题目类型
- `route_hint`：期望路由，`exact_sql` / `semantic` / `hybrid` / `unanswerable`
- `expected_product_ids`：标准答案涉及的产品
- `expected_metric_keys`：标准答案涉及的规格字段
- `expected_chunk_ids`：检索至少应命中的 chunk
- `expected_source_block_ids`：回答应能引用的原文块
- `reference_answer`：人工标准答案或正确拒答说明
- `difficulty`：easy / medium / hard

## 校验

```powershell
.\.venv\Scripts\python.exe scripts\validate_eval.py
```

校验会检查：

- 题号是否重复
- 产品和字段是否完整
- 期望 chunk 是否真实存在
- 期望原文块是否真实存在
- 可回答题是否同时有答案、chunk 和来源
- 不可回答题是否没有伪造证据

## 后续使用

- `exact_sql` 题评估 MySQL 路由和精确筛选
- `semantic` 题评估向量召回与章节问答
- `hybrid` 题评估 BM25F + 向量 + RRF + reranker
- `unanswerable` 题评估拒答，不应强行生成答案
- 主要指标：Recall@K、MRR、来源命中率、答案正确率、无依据回答率

期望来源块是最小证据集，不要求模型逐字复述；但回答中的关键数字和结论必须能落到这些来源上。

## N8 答案评测

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_answers.py
```

评测会调用真实 LLM 生成答案，并检查：

- 答案状态：`answered` / `partial` / `refused` / `error`
- 引用是否存在、编号是否有效
- 每个事实段落是否至少有一个引用
- 答案中的数字是否出现在被引用的证据原文中
- 不可回答题是否安全拒答
- 引用证据是否覆盖期望原文块

报告写入 `data/indexes/answer_eval.json` 和 `data/indexes/answer_eval.md`。
