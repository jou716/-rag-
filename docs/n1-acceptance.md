# N1 验收清单

## 1. 启动服务

```powershell
cd industrial-exoskeleton-rag
.\scripts\run_dev.ps1
```

浏览器打开 `http://127.0.0.1:8000/health`。

预期：

- HTTP 200
- `status` 为 `ok`
- `source_doc.exists` 为 `true`
- 返回内容中不出现 MySQL 密码

## 2. 检查 MySQL

如果还没有数据库和应用账号，先用 MySQL 管理员账号执行
`scripts/bootstrap_mysql.sql`，并把文件中的占位密码替换成本地密码。

然后在 `.env` 中填写同一个密码，运行：

```powershell
.\.venv\Scripts\python.exe scripts\check_mysql.py
```

预期：

- `status` 为 `ok`
- `version` 为 `8.0.45`
- `database` 为 `exo_rag`

如果返回 `not_configured`，说明 `.env` 的 `MYSQL_PASSWORD` 还没有填写。

## 3. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

预期：全部测试通过。

## 4. 检查来源清单

```powershell
.\.venv\Scripts\python.exe scripts\source_manifest.py
```

预期：生成 `data/source_manifest.json`，其中包含原始 Word 的 SHA256、大小和修改时间。

## 5. 通过标准

- `/health` 返回 200
- `/health/db` 在配置正确时返回 200
- pytest 全部通过
- 原始 Word 文件没有被修改
- `.env` 没有进入版本控制
