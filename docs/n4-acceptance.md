# N4 验收清单

## 1. 生成检索语料

```powershell
cd industrial-exoskeleton-rag
.\.venv\Scripts\python.exe scripts\build_chunks.py
```

预期：

- `chunks`: 48
- `product_profile`: 16
- `product_specs`: 16
- `section`: 4
- `matrix_scenario`: 5
- `matrix_tier`: 3
- `matrix_category`: 3
- `matrix_legend`: 1
- 唯一 chunk ID：48
- 覆盖原文块：271 / 271
- `uncovered`: 空数组
- `warnings`: 空数组

## 2. 检查 chunk 产物

打开：

- `data\processed\chunks.jsonl`
- `data\processed\chunks.csv`
- `data\processed\chunk_preview.md`
- `data\processed\chunk_report.json`

重点检查：

- `chunk_preview.md` 中 `chunk_product_C615_profile` 能独立回答 C615 是什么、适合谁
- `chunk_product_C615_specs` 同时包含净重 3.9 kg、电池 92Wh、最大手臂助力 20 kg、续航 6–8 小时
- `chunk_product_C656_specs` 只包含少量规格，且 C656 的质量标记仍为 `needs_review`
- `chunk_matrix_scenario_tbl_ac98d42e_t01_r02` 保留物流搬运场景和推荐产品原文
- `chunk_matrix_tier_tbl_ac98d42e_t02_r04` 保留 `上肢: C616(电)`、`腰背: C615(电)` 的原始写法，没有偷偷改成正序
- 每个 chunk 都有 `source_block_ids`，能追回原文

## 3. 检查 chunk 设计

本节点只做检索语料，不生成向量，也不写 BM25：

- 产品概览：回答“这是什么、适合谁、用在哪”
- 产品规格：回答“重量、续航、助力、电池”等参数
- 非产品章节：公司、技术、服务
- 矩阵行：场景推荐、层级推荐、类别推荐
- 符号说明：解释矩阵中的“电/被”

这样切分的目的是让一个 chunk 既能独立表达语义，又不会把多个产品混在一起。

## 4. 校验评测集

```powershell
.\.venv\Scripts\python.exe scripts\validate_eval.py
```

预期：

- `questions`: 45
- `answerable`: 40
- `unanswerable`: 5
- `exact_sql`: 18
- `semantic`: 9
- `hybrid`: 13
- `unanswerable`: 5
- `errors`: 空数组

题目类型分布：

- 事实：12
- 产品概览：4
- 筛选：6
- 场景：5
- 对比：4
- 章节：5
- 数据质量：4
- 拒答：5

重点抽查：

- `q001` 期望命中 `chunk_product_C615_specs` 和 `blk_ac98d42e_p0089`
- `q023` 期望命中物流场景矩阵行 `tbl_ac98d42e_t01_r02`
- `q030` 同时保留 C655 的 25 kg 和 4–10 kg 冲突
- `q037` 到 `q041` 没有伪造 chunk 或来源，必须拒答

## 5. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

预期：20 passed。

## 6. 通过标准

- 48 个 chunk，ID 全部唯一
- 16 款产品都有概览和规格两个 chunk
- 271 个原文块全部被直接或结构化引用
- 没有分隔符以外的未覆盖块
- 评测集 45 题，所有期望 chunk / 来源块 / 产品均真实存在
- 不可回答题没有任何伪造证据
- pytest 全部通过
