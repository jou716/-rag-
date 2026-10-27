# N5 验收清单

## 1. 生成 BM25F 索引

```powershell
cd industrial-exoskeleton-rag
.\.venv\Scripts\python.exe scripts\build_bm25.py
```

预期：

- `chunks`: 48
- `vocabulary`: 1652
- 平均字段长度：title 10.25、text 170.4375、section 46.6042、tags 6.5208
- 索引文件：`data\indexes\bm25_index.json`
- 索引报告：`data\indexes\bm25_report.json`

## 2. 检查 MySQL 精确检索

### 2.1 按产品号取规格

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py product --id C615 --metric runtime --metric max_assist
```

预期：

- 产品：C615
- 类别：上肢外骨骼
- 层级：高端｜先进智能
- 最大手臂助力：20 kg
- 续航：6–8 小时
- 来源块分别为 `blk_ac98d42e_p0087`、`blk_ac98d42e_p0089`

### 2.2 按类别、层级、动力筛选

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py filter --category upper_limb --tier high --power electric
```

预期只返回 C615。

### 2.3 按数值条件筛选

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py metric --metric max_assist --op ge --value 60 --unit kg --category waist_back
```

预期返回 C685，原始值为 `60 kg`，可比值单位为 `kgf`。

数值比较规则：助力类指标统一成 kgf 等值，`kg` 视为 `kgf`，`N` 除以 9.80665；重量类指标统一成 kg，`g` 除以 1000。

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py metric --metric weight --op le --value 1
```

预期返回 C686（约 1 kg）和 C621（850 g → 0.85 kg）。

## 3. 检查 BM25F 检索

### 3.1 产品参数

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "C615 续航时间是多少" --top-k 3
```

预期第 1 名：

```text
chunk_product_C615_specs
```

### 3.2 场景推荐

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "物流搬运与装卸推荐哪些产品" --top-k 3
```

预期第 1 名：

```text
chunk_matrix_scenario_tbl_ac98d42e_t01_r02
```

### 3.3 非产品章节

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "公司售后响应" --top-k 3
```

预期第 1 名：

```text
chunk_section_blk_ac98d42e_p0302
```

### 3.4 数据质量

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "C656 规格不完整" --top-k 3
```

预期第 1 名：

```text
chunk_product_C656_specs
```

### 3.5 数值语义

```powershell
.\.venv\Scripts\python.exe scripts\search_demo.py bm25 --query "最大助力 60 kg 腰背外骨骼" --top-k 3
```

预期第 1 名：

```text
chunk_product_C685_specs
```

## 4. 检查两路检索的边界

- MySQL 负责产品号、类别、层级、动力、质量状态和数值比较，结果精确，但不做自由文本相关性排序。
- BM25F 负责中文关键词相关性排序，能处理“物流搬运”“售后响应”这类自然语言表达。
- BM25F 不负责 `>= 60 kg` 这类数值判断，数值过滤必须走 MySQL。
- 两者当前还没有融合；N6 接向量检索，N7 再做 RRF 和 reranker。

## 5. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

预期：24 passed。

## 6. 通过标准

- BM25F 索引包含 48 个 chunk，词表 1652
- 上述 5 条 BM25 smoke query 的第 1 名全部符合预期
- C615 精确查询和三个筛选示例结果正确
- 数值比较能把 850 g 转成 0.85 kg，把 300 N 转成约 30.6 kgf
- pytest 全部通过
