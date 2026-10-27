# N3 验收清单

## 1. 重建产品目录

```powershell
cd industrial-exoskeleton-rag
.\.venv\Scripts\python.exe scripts\build_catalog.py
```

预期摘要：

- `products`: 16
- `specs`: 167
- `issues`: 14
- `high`: 6
- `medium`: 7
- `low`: 1
- 需复核产品：C615、C616、C622、C654、C655、C656、C680、C687、C689

## 2. 检查生成产物

打开：

- `data\processed\catalog.json`
- `data\processed\matrices.json`
- `data\processed\quality_report.md`
- `data\processed\product_review.csv`

重点核对：

- `quality_report.md` 的“问题明细”共有 14 行
- 严重度统计为高危 6、中危 7、低危 1
- “需人工复核的产品”共有 9 款
- C615/C616 的类别冲突、C655 的 25 kg 与 4–10 kg 冲突、C656 规格不完整都能在报告中看到
- `product_review.csv` 中 `quality_status` 为 `needs_review` 的产品与上面 9 款一致

## 3. 导入 MySQL

```powershell
.\.venv\Scripts\python.exe scripts\load_mysql.py
```

预期计数：

- `source_blocks`: 271
- `products`: 16
- `product_specs`: 167
- `scenario_matrix`: 5
- `tier_matrix`: 3
- `category_matrix`: 3
- `data_quality_issues`: 14

## 4. SQL 抽查

用 MySQL Workbench 连接 `exo_rag`，或执行：

```powershell
mysql -uexo_rag_app -p exo_rag
```

### 4.1 表计数

```sql
SELECT COUNT(*) AS source_blocks FROM source_blocks;
SELECT COUNT(*) AS products FROM products;
SELECT COUNT(*) AS product_specs FROM product_specs;
SELECT COUNT(*) AS scenario_matrix FROM scenario_matrix;
SELECT COUNT(*) AS tier_matrix FROM tier_matrix;
SELECT COUNT(*) AS category_matrix FROM category_matrix;
SELECT COUNT(*) AS quality_issues FROM data_quality_issues;
```

预期依次为：271、16、167、5、3、3、14。

### 4.2 类别分布

```sql
SELECT category_label, COUNT(*) AS product_count
FROM products
GROUP BY category_label
ORDER BY category_label;
```

预期：

- 上肢外骨骼：4
- 腰背外骨骼：6
- 负重下肢外骨骼：6

### 4.3 C615 关键字段

```sql
SELECT metric_label, raw_value, value_num, value_min, value_max,
       unit_normalized, source_block_id
FROM product_specs
WHERE product_id = 'C615'
ORDER BY spec_order;
```

预期至少包含：

- 产品层级：高端｜先进智能
- 类型：AI 动力上肢外骨骼
- 净重：3.9 kg
- 电池：92Wh，36V 锂离子
- 最大手臂助力：20 kg
- 续航：6–8 小时

### 4.4 质量分级

```sql
SELECT severity, COUNT(*) AS issue_count
FROM data_quality_issues
GROUP BY severity;
```

预期：

- `high`: 6
- `medium`: 7
- `low`: 1

```sql
SELECT product_id, issue_type, message
FROM data_quality_issues
WHERE product_id IN ('C615', 'C616', 'C655', 'C656')
ORDER BY product_id, issue_type;
```

预期能看到：

- C615/C616 在分级表与产品明细中的类别互相交叉
- C655 最大助力 25 kg，但同一原文的助力负载为 4–10 kg
- C656 原文明确标注规格不完整

### 4.5 来源可追溯

```sql
SELECT ps.spec_id, ps.metric_label, ps.raw_value,
       sb.block_id, sb.text
FROM product_specs ps
JOIN source_blocks sb ON sb.block_id = ps.source_block_id
WHERE ps.spec_id = 'spec_C615_01';
```

预期：

- `raw_value` 为 `高端｜先进智能`
- `sb.text` 包含 `**产品层级**：高端｜先进智能`
- `sb.block_id` 与 `product_specs.source_block_id` 一致

## 5. 检查导入幂等性

连续执行两次：

```powershell
.\.venv\Scripts\python.exe scripts\load_mysql.py
.\.venv\Scripts\python.exe scripts\load_mysql.py
```

两次输出的计数应完全一致，不能出现 542、334 这类累加结果。

## 6. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

预期：15 passed。

## 7. 通过标准

- 16 款产品全部进入 MySQL，规格总数为 167
- 三张矩阵分别为 5、3、3 行
- 14 条质量问题全部入库，严重度分布为 6/7/1
- 9 款 `needs_review` 产品与质量报告一致
- 任意 `product_specs` 行都能通过 `source_block_id` 追回原文
- 重复导入不会增加行数
- pytest 全部通过
