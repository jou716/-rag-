# N2 验收清单

## 1. 重新解析

```powershell
cd industrial-exoskeleton-rag
.\.venv\Scripts\python.exe scripts\parse_docx.py
```

预期计数：

- `products`: 16
- `tables`: 3
- `table_rows`: 14
- `table_cells`: 78
- `headings`: 29
- `blocks_total`: 271
- `warnings`: 空数组

## 2. 核对产品清单

用 Excel 打开：

```text
data\processed\products_raw.csv
```

预期：

- 16 行产品
- 上肢：C615、C622、C653、C683
- 腰背：C616、C655、C685、C621、C686、C619
- 下肢：C689、C654、C687、C656、C673、C680
- 每个产品都有 `heading_block_id` 和 `section_path`

## 3. 核对原文块

用 Excel 打开：

```text
data\processed\block_inventory.csv
```

重点检查：

- `block_id` 不为空
- `section_path` 不为空
- 产品参数段落的 `product_id` 正确
- 表格行是 `table_row`
- `text` 与原 Word 一致

## 4. 核对表格

打开：

```text
data\processed\tables.json
```

预期：

- 表 1：6 行 × 7 列，表头第一项为“目标用户群”
- 表 2：4 行 × 5 列，表头第一项为“产品层级”
- 表 3：4 行 × 4 列，表头第一项为“类别”
- 每个单元格都有唯一 `cell_id`

## 5. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

预期：全部通过。

## 6. 通过标准

- 16/16 产品被识别
- 3/3 表格被识别
- 14/14 表格行被识别
- 78/78 单元格被识别
- 271 个 block ID 全部唯一
- 无解析警告
- 原始 Word 未被修改
