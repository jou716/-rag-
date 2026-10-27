# N7 验收：混合检索、RRF 与 Cross-Encoder 重排

## 本节点做了什么

- 增加规则化查询分析，识别产品号、类别、层级、动力、指标和问题意图。
- 增加 MySQL 精确候选通道：产品事实、结构化筛选和矩阵 chunk 映射。
- 保留 BM25F 和 Qdrant 两路召回，并按查询意图加硬过滤。
- 使用加权 RRF 融合三路排名，默认 `k=60`，权重 `exact=1.6`、`bm25=1.0`、`vector=1.0`。
- 增加 `BAAI/bge-reranker-v2-m3-int8` 交叉编码器，对 RRF 前 20 个候选重排。
- 最终分数为 `0.75 × reranker_probability + 0.25 × minmax(RRF)`。
- 输出每一路排名、RRF 分数、reranker logit、概率和最终分数，便于解释。
- 增加 45 题检索评测脚本和可读报告。

## 人工验收

以下命令均需在项目根目录串行执行。

### 1. 校验 reranker 资产

```powershell
.\.venv\Scripts\python.exe scripts\fetch_reranker_model.py
```

通过标准：

- 5 个文件全部为 `cached` 或成功下载。
- 总大小为 `587813009` 字节。
- manifest revision 为 `cb859a7bfce86974a7e15899e2f993b4c9aa108c`。

### 2. 运行单元测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

通过标准：全部通过。当前预期为 56 个测试。

### 3. 跑完整检索评测

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

通过标准（40 道可回答题）：

| 模式 | Hit@1 | Hit@3 | Hit@5 | Chunk Recall@5 | Chunk Recall@10 | MRR@10 | Source Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| exact | 0.8250 | 0.8750 | 0.8750 | 0.8595 | 0.8667 | 0.8500 | 0.8750 |
| bm25 | 0.9500 | 1.0000 | 1.0000 | 0.9929 | 1.0000 | 0.9750 | 1.0000 |
| vector | 0.9750 | 1.0000 | 1.0000 | 0.9929 | 1.0000 | 0.9875 | 1.0000 |
| hybrid | 0.9750 | 1.0000 | 1.0000 | 0.9929 | 1.0000 | 0.9875 | 1.0000 |
| hybrid_rerank | 1.0000 | 1.0000 | 1.0000 | 0.9929 | 1.0000 | 1.0000 | 1.0000 |

允许精确值因运行时间有极小浮动，但 Hybrid + Rerank 不应低于：

- Hit@1 ≥ 0.975
- Hit@3 = 1.0
- Source Hit@5 = 1.0
- MRR@10 ≥ 0.9875

### 4. 检查机器可读报告

```powershell
Get-Content data\indexes\retrieval_eval.json -Raw | ConvertFrom-Json | Select-Object evaluated_questions,skipped_unanswerable,top_k
```

通过标准：`evaluated_questions=40`、`skipped_unanswerable=5`、`top_k=10`。

### 5. 验证三类典型查询

对比题：

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C615 和 C616 的电池与续航有什么区别？" --top-k 3
```

通过标准：`results` 前两条仍是细粒度 `chunk_product_C615_specs`、`chunk_product_C616_specs`；`evidence` 前两条是合并后的 `card_product_C615`、`card_product_C616`。

筛选题：

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "高端电动上肢外骨骼有哪些？" --top-k 3
```

通过标准：第 1 条是 `chunk_product_C615_profile`；结果中能看到 `exact`、`bm25`、`vector` 三路排名。

场景题：

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "物流搬运与装卸场景推荐哪些产品？" --top-k 3
```

通过标准：第 1 条是 `chunk_matrix_scenario_tbl_ac98d42e_t01_r02`。

### 6. 验证关闭 reranker 的差异

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C655 的最大助力到底是多少？" --mode hybrid --top-k 3
```

通过标准：结果包含 `rrf_score`，但不包含 `reranker_logit` 和 `reranker_probability`。

### 7. 验证不可回答题不会被伪造召回

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C999 的续航时间是多少？" --top-k 3
```

通过标准：`results` 为空。说明未知产品号被精确过滤，没有拿相似产品冒充 C999。拒答策略将在 N8 统一实现。

## 技术边界

- 查询分析是可解释规则，不是生成式模型；规则只负责路由和过滤，不生成事实。
- 40 道可回答题的检索命中是当前版本指标，不能等同于最终答案正确率。
- 不可回答题本轮跳过检索指标，N8 仍需基于证据覆盖和未知字段做拒答。
- Cross-Encoder 在 CPU 上平均单题约 426 ms，适合本地演示；生产环境应做批处理、服务化或 GPU 推理。
- Qdrant local 仍只支持单进程访问，评测和 CLI 不要并发打开同一索引目录。

## 通过条件

以上 1-7 项全部满足，且 `data/indexes/retrieval_eval.md` 中 Hybrid + Rerank 达到上述阈值，即可判定 N7 通过。
