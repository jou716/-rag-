from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import BASE_DIR
from core.vector_store import COLLECTION_NAME, collection_manifest

SOURCE_DOC_NAME = "工业外骨骼产品目录.docx"

REBUILD_ALL_STEPS = (
    r".\.venv\Scripts\python.exe scripts\parse_docx.py",
    r".\.venv\Scripts\python.exe scripts\build_catalog.py",
    r".\.venv\Scripts\python.exe scripts\build_chunks.py",
    r".\.venv\Scripts\python.exe scripts\load_mysql.py",
    r".\.venv\Scripts\python.exe scripts\build_bm25.py",
    r".\.venv\Scripts\python.exe scripts\build_vectors.py",
)


@dataclass(frozen=True)
class IndexCheck:
    name: str
    ok: bool
    detail: str
    expected: str | None = None
    actual: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class IndexContractReport:
    checks: list[IndexCheck] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    @property
    def failed(self) -> list[IndexCheck]:
        return [check for check in self.checks if not check.ok]

    def add(
        self,
        name: str,
        ok: bool,
        detail: str,
        *,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        self.checks.append(
            IndexCheck(name=name, ok=ok, detail=detail, expected=expected, actual=actual)
        )

    def require(self, *steps: str) -> None:
        for step in steps:
            if step not in self.next_steps:
                self.next_steps.append(step)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "error",
            "checks": [check.as_dict() for check in self.checks],
            "failed": [check.as_dict() for check in self.failed],
            "next_steps": list(self.next_steps),
        }

    def format_error(self) -> str:
        lines = [f"索引校验未通过（{len(self.failed)} 项）："]
        for check in self.failed:
            expected = f"，期望 {check.expected}" if check.expected else ""
            actual = f"，实际 {check.actual}" if check.actual else ""
            lines.append(f"- {check.name}：{check.detail}{expected}{actual}")
        if self.next_steps:
            lines.append("修复步骤：")
            lines.extend(
                f"  {index}. {step}"
                for index, step in enumerate(self.next_steps, start=1)
            )
        lines.append("索引重建完成后需要重启服务。")
        return "\n".join(lines)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def chunk_ids_digest(chunk_ids: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(chunk_ids)).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        item = json.loads(line)
        chunk_id = item.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"第 {line_number} 行缺少 chunk_id")
        chunks.append(item)
    return chunks


def _short_hash(value: str | None) -> str:
    if not value:
        return "-"
    return f"{value[:12]}…"


def _dig(payload: Mapping[str, Any] | None, *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _resolve_model_manifest(
    base_dir: Path, embedding: Mapping[str, Any]
) -> Path | None:
    model_name = embedding.get("model_name")
    if model_name:
        candidate = (
            base_dir / "data" / "models" / Path(str(model_name)).name / "manifest.json"
        )
        if candidate.is_file():
            return candidate
    raw_path = embedding.get("model_manifest")
    if raw_path:
        candidate = Path(str(raw_path))
        if candidate.is_file():
            return candidate
    return None


def validate_index_contract(
    base_dir: Path | str | None = None,
    *,
    source_doc: Path | str | None = None,
    check_qdrant: bool = True,
) -> IndexContractReport:
    base_dir = Path(base_dir) if base_dir else BASE_DIR
    processed = base_dir / "data" / "processed"
    indexes = base_dir / "data" / "indexes"
    source_path = Path(source_doc) if source_doc else base_dir / SOURCE_DOC_NAME
    report = IndexContractReport()

    source_exists = source_path.is_file()
    report.add(
        "源文档存在",
        source_exists,
        f"检查 {source_path}",
        expected="文件存在",
        actual="存在" if source_exists else "缺失",
    )
    actual_source_sha = sha256_file(source_path) if source_exists else None
    if not source_exists:
        report.require("确认源文档路径，或在 .env 中设置 SOURCE_DOC_PATH")

    artifacts = {
        "chunks.jsonl": processed / "chunks.jsonl",
        "document_blocks.jsonl": processed / "document_blocks.jsonl",
        "chunk_report.json": processed / "chunk_report.json",
        "bm25_index.json": indexes / "bm25_index.json",
        "bm25_report.json": indexes / "bm25_report.json",
        "vector_manifest.json": indexes / "vector_manifest.json",
    }
    missing = [name for name, path in artifacts.items() if not path.is_file()]
    report.add(
        "索引文件完整",
        not missing,
        "必需产物齐全" if not missing else f"缺少 {', '.join(missing)}",
        expected="chunks / blocks / chunk_report / bm25 / vector_manifest",
        actual=f"{len(artifacts) - len(missing)}/{len(artifacts)}",
    )
    if missing:
        report.require(*REBUILD_ALL_STEPS)

    source_manifest: dict[str, Any] | None = None
    source_manifest_path = base_dir / "data" / "source_manifest.json"
    if not source_manifest_path.is_file():
        report.add(
            "源文档清单",
            False,
            "缺少 data/source_manifest.json",
            expected="文件存在",
            actual="缺失",
        )
        report.require(r".\.venv\Scripts\python.exe scripts\source_manifest.py")
    else:
        try:
            source_manifest = _read_json(source_manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            report.add("源文档清单", False, f"无法解析：{type(exc).__name__}")
            report.require(r".\.venv\Scripts\python.exe scripts\source_manifest.py")

    chunk_report: dict[str, Any] | None = None
    if artifacts["chunk_report.json"].is_file():
        try:
            chunk_report = _read_json(artifacts["chunk_report.json"])
        except (OSError, json.JSONDecodeError) as exc:
            report.add("chunk 报告可读", False, f"无法解析：{type(exc).__name__}")

    bm25_index: dict[str, Any] | None = None
    if artifacts["bm25_index.json"].is_file():
        try:
            bm25_index = _read_json(artifacts["bm25_index.json"])
        except (OSError, json.JSONDecodeError) as exc:
            report.add("BM25 索引可读", False, f"无法解析：{type(exc).__name__}")

    vector_manifest: dict[str, Any] | None = None
    if artifacts["vector_manifest.json"].is_file():
        try:
            vector_manifest = _read_json(artifacts["vector_manifest.json"])
        except (OSError, json.JSONDecodeError) as exc:
            report.add("向量清单可读", False, f"无法解析：{type(exc).__name__}")

    if actual_source_sha and source_manifest:
        expected_sha = source_manifest.get("sha256")
        matched = bool(expected_sha) and actual_source_sha == expected_sha
        report.add(
            "源文档 SHA256",
            matched,
            "源文档与构建时版本一致" if matched else "源文档已变更，索引仍是旧版本",
            expected=_short_hash(expected_sha),
            actual=_short_hash(actual_source_sha),
        )
        if not matched:
            report.require(*REBUILD_ALL_STEPS)

    chain: list[tuple[str, str | None]] = []
    if source_manifest:
        chain.append(("source_manifest", source_manifest.get("sha256")))
    if chunk_report:
        chain.append(("chunk_report", _dig(chunk_report, "source", "sha256")))
    if bm25_index:
        chain.append(("bm25_index", bm25_index.get("source_hash")))
    if vector_manifest:
        chain.append(("vector_manifest", vector_manifest.get("source_sha256")))
    known = [(name, value) for name, value in chain if isinstance(value, str) and value]
    if len(known) >= 2:
        unique = {value for _, value in known}
        chain_ok = len(unique) == 1
        report.add(
            "源文档版本链路",
            chain_ok,
            "source / chunk / BM25 / 向量索引指向同一版源文档"
            if chain_ok
            else "各索引产物的源文档版本不一致",
            expected=_short_hash(known[0][1]),
            actual=", ".join(f"{name}={_short_hash(value)}" for name, value in known),
        )
        if not chain_ok:
            report.require(*REBUILD_ALL_STEPS)

    chunks: list[dict[str, Any]] | None = None
    if artifacts["chunks.jsonl"].is_file():
        try:
            chunks = _load_chunks(artifacts["chunks.jsonl"])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report.add("chunk 清单可读", False, f"无法解析：{type(exc).__name__}: {exc}")
        else:
            ids = [chunk["chunk_id"] for chunk in chunks]
            unique_ids = set(ids)
            inventory_ok = bool(chunks) and len(ids) == len(unique_ids)
            report.add(
                "chunk 清单可读",
                inventory_ok,
                "chunk 编号唯一且非空"
                if inventory_ok
                else f"chunk 数量 {len(ids)}，唯一编号 {len(unique_ids)}",
                expected="非空且 chunk_id 唯一",
                actual=f"{len(unique_ids)} 个唯一 chunk",
            )
            if not inventory_ok:
                report.require(r".\.venv\Scripts\python.exe scripts\build_chunks.py")

            expected_count = _dig(chunk_report, "counts", "chunks")
            bm25_count = bm25_index.get("chunk_count") if bm25_index else None
            vector_count = (
                vector_manifest.get("points_count") if vector_manifest else None
            )
            counts = {
                "chunks.jsonl": len(chunks),
                "chunk_report": expected_count,
                "bm25_index": bm25_count,
                "vector_manifest": vector_count,
            }
            comparable = {
                name: value
                for name, value in counts.items()
                if isinstance(value, int)
            }
            counts_ok = len(set(comparable.values())) == 1
            report.add(
                "chunk 数量一致",
                counts_ok,
                "各索引 chunk 数量一致" if counts_ok else "各索引 chunk 数量不一致",
                expected=str(len(chunks)),
                actual=", ".join(f"{name}={value}" for name, value in comparable.items()),
            )
            if not counts_ok:
                report.require(*REBUILD_ALL_STEPS)

            if vector_manifest:
                expected_digest = vector_manifest.get("chunk_ids_sha256")
                actual_digest = chunk_ids_digest(unique_ids)
                digest_ok = bool(expected_digest) and actual_digest == expected_digest
                report.add(
                    "chunk ID 指纹",
                    digest_ok,
                    "向量索引覆盖的 chunk 集合与 chunks.jsonl 一致"
                    if digest_ok
                    else "向量索引的 chunk 集合已过期",
                    expected=_short_hash(expected_digest),
                    actual=_short_hash(actual_digest),
                )
                if not digest_ok:
                    report.require(r".\.venv\Scripts\python.exe scripts\build_vectors.py")

    if vector_manifest:
        embedding = vector_manifest.get("embedding")
        if isinstance(embedding, Mapping):
            model_path = _resolve_model_manifest(base_dir, embedding)
            expected_model_sha = embedding.get("model_manifest_sha256")
            if model_path is None:
                report.add(
                    "向量模型清单",
                    False,
                    "找不到 embedding 模型的 manifest.json",
                    expected=str(embedding.get("model_name") or "-"),
                    actual="缺失",
                )
                report.require(
                    r".\.venv\Scripts\python.exe scripts\fetch_embedding_model.py"
                )
            else:
                actual_model_sha = sha256_file(model_path)
                model_ok = (
                    not expected_model_sha or actual_model_sha == expected_model_sha
                )
                report.add(
                    "向量模型清单",
                    model_ok,
                    "embedding 模型与建索引时一致"
                    if model_ok
                    else "embedding 模型已变更，向量索引需要重建",
                    expected=_short_hash(expected_model_sha),
                    actual=_short_hash(actual_model_sha),
                )
                if not model_ok:
                    report.require(r".\.venv\Scripts\python.exe scripts\build_vectors.py")

    if check_qdrant and chunks is not None and vector_manifest is not None:
        index_path = indexes / "qdrant"
        collection_name = vector_manifest.get("collection_name") or COLLECTION_NAME
        if not index_path.exists():
            report.add(
                "Qdrant 集合一致",
                False,
                "本地 Qdrant 索引目录不存在",
                expected=str(index_path),
                actual="缺失",
            )
            report.require(r".\.venv\Scripts\python.exe scripts\build_vectors.py")
        else:
            try:
                live = collection_manifest(index_path, collection_name=collection_name)
            except Exception as exc:  # noqa: BLE001 - surface storage lock/corruption
                report.add(
                    "Qdrant 集合一致",
                    False,
                    f"无法读取 Qdrant：{type(exc).__name__}: {exc}",
                    expected=collection_name,
                    actual="读取失败",
                )
                report.require(
                    "停止占用 Qdrant 的进程后重试，或执行 scripts/build_vectors.py"
                )
            else:
                expected_ids = sorted(chunk["chunk_id"] for chunk in chunks)
                live_ids = sorted(value for value in live.get("chunk_ids") or [] if value)
                qdrant_ok = (
                    live.get("points_count") == len(chunks) and live_ids == expected_ids
                )
                report.add(
                    "Qdrant 集合一致",
                    qdrant_ok,
                    "Qdrant 点数与 chunk 集合一致"
                    if qdrant_ok
                    else "Qdrant 实际内容与 chunks.jsonl 不一致",
                    expected=f"{len(chunks)} points",
                    actual=f"{live.get('points_count')} points, {len(live_ids)} ids",
                )
                if not qdrant_ok:
                    report.require(r".\.venv\Scripts\python.exe scripts\build_vectors.py")

    return report


def validate_index_contract_or_raise(
    base_dir: Path | str | None = None,
    *,
    source_doc: Path | str | None = None,
    check_qdrant: bool = True,
) -> IndexContractReport:
    report = validate_index_contract(
        base_dir,
        source_doc=source_doc,
        check_qdrant=check_qdrant,
    )
    if not report.ok:
        raise RuntimeError(report.format_error())
    return report
