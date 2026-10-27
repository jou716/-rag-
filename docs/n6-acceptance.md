# N6 验收：Qdrant 向量索引与语义召回

## 本节点做了什么

- 从 ModelScope 固定 revision 拉取 `BAAI/bge-small-zh-v1.5` 的 ONNX 模型。
- 对每个模型文件做大小和 SHA256 校验，并生成 `data/models/bge-small-zh-v1.5/manifest.json`。
- 将 48 个 chunk 编码为 512 维归一化向量。
- 在 `data/indexes/qdrant/` 创建本地 Qdrant collection `exo_chunks`。
- payload 保留 `chunk_id`、类型、标题、正文、产品、类别、层级、动力、质量状态和来源块。
- 支持按产品、类别、层级、动力、chunk 类型、质量状态过滤。
- 新增 `scripts/search_demo.py vector` 语义检索命令。
- 新增 embedding 与 Qdrant 的自动化测试。

## 人工验收

在项目根目录依次执行以下命令。所有命令必须串行执行，不要同时开两个 Qdrant local 客户端。

### 1. 校验模型资产

```powershell
.\.venv\Scripts\python.exe scripts\fetch_embedding_model.py
```

通过标准：

- 6 个文件全部显示 `cached` 或成功下载。
- 输出包含 `total_size_bytes: 95330972`。
- `data/models/bge-small-zh-v1.5/manifest.json` 存在，revision 为 `677b527935023b31f309ecb027745526aa5f680f`。

### 2. 构建并观察索引

```powershell
.\.venv\Scripts\python.exe scripts\build_vectors.py
```

通过标准：

- 输出 `points_count: 48`。
- 输出 `vector_size: 512`。
- 输出 `distance: Cosine`。
- `embedding_model` 为 `BAAI/bge-small-zh-v1.5`。
- `data/indexes/qdrant_report.json` 和 `data/indexes/vector_manifest.json` 均存在。

### 3. 检查报告

```powershell
Get-Content data\indexes\qdrant_report.json -Raw | ConvertFrom-Json | Select-Object points_count,vector_size,distance,index_size_bytes
```

通过标准：

- `points_count = 48`。
- `vector_size = 512`。
- `distance = Cosine`。
- `index_size_bytes` 大于 0。

### 4. 验证语义召回

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "物流搬运与装卸推荐哪些产品" --top-k 3
```

通过标准：第 1 条应为 `chunk_matrix_scenario_tbl_ac98d42e_t01_r02`，标题为“场景矩阵｜物流搬运与装卸”。

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "公司售后怎么联系" --top-k 3
```

通过标准：第 1 条应为 `chunk_section_blk_ac98d42e_p0302`，标题为“7. 服务与支持”。

### 5. 验证 payload 过滤

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py vector --query "电池续航时间多久" --product-id C615 --chunk-type product_specs --top-k 3
```

通过标准：

- 只返回 `C615` 的 `product_specs` chunk。
- 第 1 条 `chunk_id` 为 `chunk_product_C615_specs`。
- `source_block_ids` 非空，能回溯到 Word 原文块。

### 6. 验证幂等重建

串行执行两次：

```powershell
.\.venv\Scripts\python.exe scripts\build_vectors.py
.\.venv\Scripts\python.exe scripts\build_vectors.py
```

通过标准：两次都输出 `points_count: 48`，不会变成 96 或出现重复点。

### 7. 验证测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

通过标准：全部通过。当前预期为 33 个测试。

## 技术边界

- 当前 embedding 是真实 BGE 中文语义模型，不是哈希 baseline。
- BGE 擅长语义相近表达，但不擅长精确保留 `C615` 这类产品编号；产品号精确问题必须交给 MySQL/BM25，N7 做融合。
- Qdrant local 模式不支持真正的 payload 索引，也不支持多进程并发打开同一目录。48 个 chunk 下过滤正常；生产部署需切换 Qdrant Server。
- 本节点不包含最终答案生成，只交付可复现的向量索引和语义召回。

## 通过条件

以上 1-7 项全部满足，且没有修改原始 Word 文档，即可判定 N6 通过。
