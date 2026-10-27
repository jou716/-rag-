# ExoRAG

工业外骨骼产品目录的智能选型与可追溯问答系统。

当前完成节点：**N8 LLM 答案生成、引用、证据覆盖与拒答**。

> 公开仓库只包含代码、测试和验收文档。原始产品目录 DOCX、解析正文、BM25/Qdrant 索引、embedding/reranker 模型和 `.env` 均不提交。

## 技术栈

- Python 3.11
- FastAPI + Pydantic Settings
- MySQL 8.0 + SQLAlchemy + PyMySQL
- python-docx
- Qdrant 1.19（local 模式）
- BGE-small-zh-v1.5（FastEmbed + ONNX Runtime）
- BGE-reranker-v2-m3-int8（FastEmbed CrossEncoder + ONNX Runtime）
- 千问 `qwen-max`（DashScope OpenAI-compatible 接口）
- pytest

## 本地启动

公开仓库不包含原始 DOCX、`data/processed/`、`data/indexes/`、`data/models/` 和 `.env`。请使用自己的产品目录重建数据。

### 1. 创建虚拟环境

```powershell
cd industrial-exoskeleton-rag
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 2. 配置 MySQL

复制配置模板：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写本机 MySQL 账号：

```text
MYSQL_USER=exo_rag_app
MYSQL_PASSWORD=你的本地密码
```

不要使用 `root` 作为应用账号，不要把 `.env` 提交到版本库。

如果你还没有 `exo_rag` 数据库和应用账号，用 MySQL 管理员账号执行：

```text
scripts/bootstrap_mysql.sql
```

执行前先把文件中的 `CHANGE_ME_STRONG_PASSWORD` 替换成本地密码。

### 2.1 配置千问

在 `.env` 中填写 DashScope Key：

```text
ANSWER_GENERATION_MODE=llm
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max
LLM_API_KEY=你的千问Key
```

不要把 `.env` 或真实 Key 提交到版本库。模型不可用时系统返回 `status=error`，不会用本地模板冒充模型答案。

### 3. 准备源文档

将 `工业外骨骼产品目录.docx` 放到项目根目录；也可以复制到任意位置，并在 `.env` 中设置：

```text
SOURCE_DOC_PATH=./工业外骨骼产品目录.docx
```

根目录下的 `*.docx` 已被 `.gitignore` 忽略，不会误提交。

### 4. 构建数据与索引

按顺序执行以下命令。`build_vectors.py` 使用本地 Qdrant，执行期间不要同时启动 API 或其他向量脚本。

```powershell
.\.venv\Scripts\python.exe scripts\fetch_embedding_model.py
.\.venv\Scripts\python.exe scripts\fetch_reranker_model.py
.\.venv\Scripts\python.exe scripts\source_manifest.py
.\.venv\Scripts\python.exe scripts\parse_docx.py
.\.venv\Scripts\python.exe scripts\build_catalog.py
.\.venv\Scripts\python.exe scripts\load_mysql.py
.\.venv\Scripts\python.exe scripts\build_chunks.py
.\.venv\Scripts\python.exe scripts\validate_eval.py
.\.venv\Scripts\python.exe scripts\build_bm25.py
.\.venv\Scripts\python.exe scripts\build_vectors.py
```

如果使用的文档与当前评测集不是同一份，请同步调整 `eval/questions.jsonl`，或跳过 `validate_eval.py`。

### 5. 检查数据库并启动服务

```powershell
.\.venv\Scripts\python.exe scripts\check_mysql.py
.\scripts\run_dev.ps1
```

访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/db`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/ui`（Gradio 交互页面）

### 6. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

依赖本地 DOCX 或索引的测试会在文件缺失时自动跳过；完整重建数据后可运行全部测试。

## N1 验收

详细步骤见 `docs/n1-acceptance.md`。

## N2 解析

```powershell
.\.venv\Scripts\python.exe scripts\parse_docx.py
```

产物：

- `data/processed/document_blocks.jsonl`
- `data/processed/tables.json`
- `data/processed/parse_report.json`
- `data/processed/block_inventory.csv`
- `data/processed/products_raw.csv`

人工验收步骤见 `docs/n2-acceptance.md`。

## N3 产品建模与导入

在 N2 的原文块和表格基础上，生成产品模型、规格数值和问题清单，并导入 MySQL：

```powershell
.\.venv\Scripts\python.exe scripts\build_catalog.py
.\.venv\Scripts\python.exe scripts\load_mysql.py
```

产物：

- `data/processed/catalog.json`：16 款产品、167 条规格、矩阵和质量状态
- `data/processed/matrices.json`：场景、层级、类别三张矩阵
- `data/processed/quality_report.json`：机器可读的问题清单
- `data/processed/quality_report.md`：适合人工复核的问题报告
- `data/processed/product_review.csv`：按产品汇总的复核表

MySQL 表：

- `source_blocks`：271 条原文块，所有规格和矩阵的来源
- `products`：16 款产品
- `product_specs`：167 条结构化规格
- `scenario_matrix` / `tier_matrix` / `category_matrix`：5 / 3 / 3 行矩阵
- `data_quality_issues`：14 条数据质量问题

导入是幂等的：重复执行 `load_mysql.py` 会替换同一份目录数据，不会累加重复行。

人工验收步骤见 `docs/n3-acceptance.md`。

## N4 检索语料与评测集

```powershell
.\.venv\Scripts\python.exe scripts\build_chunks.py
.\.venv\Scripts\python.exe scripts\validate_eval.py
```

产物：

- `data/processed/chunks.jsonl`：48 个检索 chunk
- `data/processed/chunks.csv`：方便 Excel 查看的 chunk 清单
- `data/processed/chunk_preview.md`：逐条可读预览
- `data/processed/chunk_report.json`：类型计数、字符统计和原文覆盖检查
- `eval/questions.jsonl`：45 题人工评测集
- `eval/README.md`：字段和评测指标说明

chunk 分为：

- `product_profile`：产品概览，16 个
- `product_specs`：产品规格，16 个
- `section`：公司、技术、服务等非产品章节，4 个
- `matrix_scenario` / `matrix_tier` / `matrix_category`：矩阵行，5 / 3 / 3 个
- `matrix_legend`：矩阵符号说明，1 个

覆盖检查要求 271 个原文块全部被直接或结构化引用；评测集要求所有期望 chunk、来源块和产品真实存在。

人工验收步骤见 `docs/n4-acceptance.md`。

## N5 精确检索与 BM25F

构建 BM25F 索引：

```powershell
.\.venv\Scripts\python.exe scripts\build_bm25.py
```

产物：

- `data/indexes/bm25_index.json`：48 个 chunk 的字段化倒排索引
- `data/indexes/bm25_report.json`：词表、字段长度和 smoke query 结果

检索演示：

```powershell
# MySQL：按产品号取规格
.\.venv\Scripts\python.exe scripts\search_demo.py product --id C615 --metric runtime --metric max_assist

# MySQL：按类别、层级、动力筛选
.\.venv\Scripts\python.exe scripts\search_demo.py filter --category upper_limb --tier high --power electric

# MySQL：数值比较
.\.venv\Scripts\python.exe scripts\search_demo.py metric --metric max_assist --op ge --value 60 --unit kg --category waist_back

# BM25F：自然语言检索
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "物流搬运与装卸推荐哪些产品" --top-k 3
```

BM25F 字段权重：`title=3.0`、`text=1.0`、`section=1.5`、`tags=2.0`。中文使用字符 unigram + bigram，数字和单位会生成 `60kg` 这类组合 token。

人工验收步骤见 `docs/n5-acceptance.md`。

## N6 Qdrant 向量索引与语义召回

先拉取固定版本的中文 embedding 模型，再构建 Qdrant 向量索引：

```powershell
.\.venv\Scripts\python.exe scripts\fetch_embedding_model.py
.\.venv\Scripts\python.exe scripts\build_vectors.py
```

模型与索引产物：

- `data/models/bge-small-zh-v1.5/`：BGE-small-zh-v1.5 ONNX 模型和 SHA256 manifest
- `data/indexes/qdrant/`：本地 Qdrant collection `exo_chunks`
- `data/indexes/vector_manifest.json`：索引、模型、源文档版本的机器可读清单
- `data/indexes/qdrant_report.json`：点数、维度、耗时和 smoke query 结果

语义检索演示：

```powershell
# 场景语义召回
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "物流搬运与装卸推荐哪些产品" --top-k 3

# 产品号 + chunk 类型过滤
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "电池续航时间多久" --product-id C615 --chunk-type product_specs --top-k 3

# 类别过滤
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "最大助力是多少" --category waist_back --top-k 3
```

向量配置为 BGE-small-zh-v1.5、512 维、余弦距离、L2 归一化。文档向量包含标题、产品/类别/层级/动力标签和章节路径，不只编码正文。

当前使用 Qdrant local 模式，适合单进程本地演示与测试；它不支持真正的 payload 索引，也不支持多进程并发打开同一目录。生产部署时应切换为 Qdrant Server。N6 只负责语义召回，精确产品号、数值比较和 BM25 仍由 N5 负责，N7 再做 RRF 融合。

人工验收步骤见 `docs/n6-acceptance.md`。

## 索引一致性校验

服务启动时会校验持久化索引是否仍与源文档一致，任何一项不一致都会直接拒绝启动，避免“文档已更新但索引没重建”时继续返回旧答案。检查项包括：

- 源文档存在，且 SHA256 与 `data/source_manifest.json` 一致
- `source_manifest`、`chunk_report`、BM25 索引、向量清单指向同一版源文档
- `chunks.jsonl` 编号唯一，chunk 数量与 `chunk_report`、BM25、向量清单一致
- `chunk_ids_sha256` 与向量清单一致
- embedding 模型 manifest 与建索引时一致
- Qdrant 实际点数、chunk ID 集合与 `chunks.jsonl` 一致

手工检查：

```powershell
.\.venv\Scripts\python.exe scripts\check_indexes.py

# 跳过 Qdrant（不占用本地索引锁）
.\.venv\Scripts\python.exe scripts\check_indexes.py --skip-qdrant

# 机器可读输出
.\.venv\Scripts\python.exe scripts\check_indexes.py --json
```

校验通过返回退出码 `0`，失败返回 `1`，并输出具体是哪一项不一致、应该执行哪些重建命令。校验结果按进程缓存；重建索引后需要重启服务。

## N7 混合检索与重排

拉取并校验 reranker，然后运行检索评测：

```powershell
.\.venv\Scripts\python.exe scripts\fetch_reranker_model.py
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

N7 的检索链路：

1. 规则化查询分析：识别产品号、类别、层级、动力、指标和问题意图。
2. MySQL 精确通道：产品号事实、结构化筛选和矩阵行映射。
3. BM25F 通道：产品号、规格词、章节词和中文术语召回。
4. Qdrant 通道：BGE 语义召回，支持产品/类别/层级/动力/chunk 类型过滤。
5. RRF：三路排名按 `1 / (60 + rank)` 加权融合。
6. Cross-Encoder：对融合后的前 20 个候选，用 BGE-reranker-v2-m3-int8 重排。
7. 可溯源证据包：默认返回最多 15 条证据，编号 `E1`–`E15`，包含原文、章节路径、Word 段落或表格行、原文块 ID、三路排名和最终分数。

列举型问题（“有哪些 / 列出 / 都有哪些”）会先按类别、层级、动力做 MySQL 过滤，再按“一个产品一张卡”组装证据：先放矩阵行，再为每个命中产品组装一张产品卡。产品卡采用 small-to-big：索引仍是 `product_profile` 和 `product_specs` 两个细粒度 chunk，进入证据包时合并成一张卡，卡内保留两个原始 chunk ID 和完整原文，避免同一产品重复占槽，也避免概览卡挤掉规格卡导致重量、电池等字段漏答。动力过滤中，泛化“电动”会同时匹配 `electric` 和 `electric_cart`，避免矩阵里写作 `C680(电)`、产品表却标为“电动推车联动”的产品被漏掉；明确问“电动推车”时只匹配 `electric_cart`。

检索演示：

```powershell
# 对比题：应同时召回 C615 和 C616 规格
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C615 和 C616 的电池与续航有什么区别？" --top-k 3

# 筛选题：MySQL 先过滤，再做融合和重排
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "高端电动上肢外骨骼有哪些？" --top-k 3

# 场景题：命中对应场景矩阵
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "物流搬运与装卸场景推荐哪些产品？" --top-k 3

# 只运行 RRF，不启用 reranker
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C655 的最大助力到底是多少？" --mode hybrid --top-k 3
```

可溯源证据演示：

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py hybrid --query "C615 和 C616 的电池与续航有什么区别？" --top-k 3 --evidence-top-k 8
```

输出中的 `evidence` 是最终答案可直接引用的证据包。硬过滤后候选不足 15 条时只返回实际命中的证据，不用无关内容凑数。验收步骤见 `docs/n7-evidence-acceptance.md`。

评测产物：

- `data/indexes/retrieval_eval.json`：逐题检索结果、分路由指标
- `data/indexes/retrieval_eval.md`：适合简历和验收查阅的指标表

当前 40 道可回答题的 Hybrid + Rerank 结果：Hit@1 100%、Hit@3 100%、Hit@5 100%、MRR@10 1.0、Source Hit@5 100%；Chunk Recall@5 99.29%，Chunk Recall@10 100%，平均单题检索约 426 ms。

人工验收步骤见 `docs/n7-acceptance.md` 和 `docs/n7-evidence-acceptance.md`。

## N8 LLM 答案、引用与拒答

配置千问后，可以直接对证据包做受约束的答案生成：

```powershell
# 单事实题
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 的续航时间是多少？"

# 对比题
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 和 C616 的电池与续航有什么区别？"

# 缺失字段：应明确回答“产品目录未提供”
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C615 的价格是多少？"

# 未知产品：应直接拒答
.\.venv\Scripts\python.exe scripts\ask_demo.py --query "C999 的续航时间是多少？"
```

`POST /ask` 返回：

- `status`：`answered` / `partial` / `refused` / `error`
- `answer`：已通过引用和数值 grounding 校验的答案
- `citations`：答案实际使用的证据编号
- `citation_validation`：引用编号和段落覆盖校验
- `grounding_validation`：数字是否能在被引用证据中找到
- `evidence`：最多 15 条可溯源证据，含原文、章节、Word 段落/表格行、原文块 ID 和三路检索分数

N8 的生成流程：

1. N7 返回证据包；无证据时直接拒答，不调用模型。
2. `qwen-max` 只基于证据生成答案，每个事实段落必须带 `[E#]`。
3. 确定性校验引用编号、段落覆盖和数值来源。
4. 校验失败时带失败原因重写一次；仍失败则返回 `error`，不展示未经校验的答案。
5. 价格、保修、认证、蓝牙等未提供字段明确写“产品目录未提供”，不猜测。

45 题答案评测：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_answers.py
```

当前指标：可回答题回答率 100%、引用存在率 100%、引用编号有效率 100%、数值 grounding 有效率 100%、不可回答题安全处理率 100%、预期原文块平均召回 0.9917，平均单题约 2922 ms。产物为 `data/indexes/answer_eval.json` 和 `data/indexes/answer_eval.md`。

一键验收：

```powershell
.\scripts\check_n8.ps1
```

人工验收步骤见 `docs/n8-acceptance.md`。

## Gradio 交互页面

页面挂载在同一个 FastAPI 进程里（`/ui`），与 `/ask` 共用同一个 `GroundedAnswerService`。Qdrant local 只能单进程访问，所以不要把 UI 单独起进程或与评测脚本并发运行。

```powershell
.\scripts\run_dev.ps1
```

打开 `http://127.0.0.1:8000/ui`，页面提供：

- 中文问题输入和示例问题；每次固定返回最多 15 条证据，不提供数量滑块。
- 状态徽标（已回答 / 部分回答 / 已拒答 / 生成失败）、答案、引用编号、识别到的产品、缺失字段。
- 可溯源证据卡：`[E#]`、标题、章节路径、Word 段落 / 表格行定位、原文块 ID 与类型、质量状态与标记、原文、三路检索排名和最终分数。
- 折叠的原始 JSON，便于排查。

页面并发队列固定为 1，避免本地 Qdrant 被并发读写。

验收要点：

- 输入 `C615 和 C616 的电池与续航有什么区别？`，应得到含 `92Wh`、`6–8 小时`、`3–8 小时` 的对比答案，引用 `E1`、`E2`，证据 2 条。
- 输入 `C615 的价格是多少？`，应显示“已拒答”，并说明产品目录未提供价格。
- 证据卡里的 chunk ID 和 Word 段落 / 表格行号，应能在原始文档中逐条核对。
