# 本地数据目录

公开仓库只保留目录结构，不提交原始产品目录、解析正文、索引和模型文件。

- `raw/`：原始或手工整理的辅助数据，按需本地放置。
- `processed/`：DOCX 解析、产品建模和 chunk 产物。
- `indexes/`：BM25、Qdrant 和评测报告。
- `models/`：embedding 与 reranker 模型。

把源文档放到项目根目录后，按根目录 `README.md` 的“构建数据与索引”步骤重建即可。
