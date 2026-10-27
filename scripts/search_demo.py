import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from app.db import get_engine
from core.bm25 import load_bm25_index, search_bm25
from core.embeddings import embed_query
from core.exact_search import (
    find_products_by_metric,
    get_product,
    search_products,
)
from core.evidence import DEFAULT_EVIDENCE_LIMIT
from core.hybrid_search import HybridRetriever
from core.vector_store import VectorFilters, search_vectors


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _product_summary(product: dict) -> dict:
    return {
        "product_id": product["product_id"],
        "category_label": product["category_label"],
        "tier_label": product["tier_label"],
        "power_type_label": product["power_type_label"],
        "quality_status": product["quality_status"],
        "spec_count": len(product["specs"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ExoRAG retrieval demo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    product_parser = subparsers.add_parser("product", help="Exact product lookup")
    product_parser.add_argument("--id", required=True)
    product_parser.add_argument("--metric", action="append", default=[])

    filter_parser = subparsers.add_parser("filter", help="Structured product filter")
    filter_parser.add_argument("--category", action="append", default=[])
    filter_parser.add_argument("--tier", action="append", default=[])
    filter_parser.add_argument("--power", action="append", default=[])
    filter_parser.add_argument("--quality", action="append", default=[])

    metric_parser = subparsers.add_parser("metric", help="Numeric metric filter")
    metric_parser.add_argument("--metric", required=True)
    metric_parser.add_argument(
        "--op", required=True, choices=["eq", "ge", "gt", "le", "lt"]
    )
    metric_parser.add_argument("--value", required=True, type=float)
    metric_parser.add_argument("--unit")
    metric_parser.add_argument("--category", action="append", default=[])
    metric_parser.add_argument("--tier", action="append", default=[])
    metric_parser.add_argument("--power", action="append", default=[])

    bm25_parser = subparsers.add_parser("bm25", help="BM25F chunk search")
    bm25_parser.add_argument("--query", required=True)
    bm25_parser.add_argument("--top-k", type=int, default=5)
    bm25_parser.add_argument("--product-id", action="append", default=[])
    bm25_parser.add_argument("--category", action="append", default=[])
    bm25_parser.add_argument("--tier", action="append", default=[])
    bm25_parser.add_argument("--power", action="append", default=[])
    bm25_parser.add_argument("--chunk-type", action="append", default=[])

    vector_parser = subparsers.add_parser("vector", help="Qdrant semantic search")
    vector_parser.add_argument("--query", required=True)
    vector_parser.add_argument("--top-k", type=int, default=5)
    vector_parser.add_argument("--product-id", action="append", default=[])
    vector_parser.add_argument("--category", action="append", default=[])
    vector_parser.add_argument("--tier", action="append", default=[])
    vector_parser.add_argument("--power", action="append", default=[])
    vector_parser.add_argument("--chunk-type", action="append", default=[])
    vector_parser.add_argument("--quality", action="append", default=[])

    hybrid_parser = subparsers.add_parser("hybrid", help="Fused retrieval with reranker")
    hybrid_parser.add_argument("--query", required=True)
    hybrid_parser.add_argument("--top-k", type=int, default=DEFAULT_EVIDENCE_LIMIT)
    hybrid_parser.add_argument(
        "--evidence-top-k", type=int, default=DEFAULT_EVIDENCE_LIMIT
    )
    hybrid_parser.add_argument("--no-evidence", action="store_true")
    hybrid_parser.add_argument(
        "--mode",
        choices=["exact", "bm25", "vector", "hybrid", "hybrid_rerank"],
        default="hybrid_rerank",
    )

    args = parser.parse_args()

    if args.command == "product":
        product = get_product(get_engine(), args.id)
        if not product:
            raise SystemExit(f"Product not found: {args.id}")
        if args.metric:
            wanted = set(args.metric)
            product["specs"] = [
                spec for spec in product["specs"] if spec["metric_key"] in wanted
            ]
        _print(product)
        return

    if args.command == "filter":
        products = search_products(
            get_engine(),
            category_keys=args.category or None,
            tier_keys=args.tier or None,
            power_types=args.power or None,
            quality_status=args.quality or None,
        )
        _print([_product_summary(product) for product in products])
        return

    if args.command == "metric":
        results = find_products_by_metric(
            get_engine(),
            metric_key=args.metric,
            op=args.op,
            value=args.value,
            unit=args.unit,
            category_keys=args.category or None,
            tier_keys=args.tier or None,
            power_types=args.power or None,
        )
        _print(results)
        return

    if args.command == "bm25":
        index_path = BASE_DIR / "data" / "indexes" / "bm25_index.json"
        if not index_path.exists():
            raise SystemExit("BM25 index missing. Run scripts/build_bm25.py first.")
        filters = {
            "product_ids": args.product_id or None,
            "category_keys": args.category or None,
            "tier_keys": args.tier or None,
            "power_types": args.power or None,
            "chunk_types": args.chunk_type or None,
        }
        _print(
            search_bm25(
                load_bm25_index(index_path),
                args.query,
                top_k=args.top_k,
                filters=filters,
            )
        )
        return

    if args.command == "vector":
        filters = VectorFilters(
            product_ids=tuple(args.product_id),
            category_keys=tuple(args.category),
            tier_keys=tuple(args.tier),
            power_types=tuple(args.power),
            chunk_types=tuple(args.chunk_type),
            quality_status=tuple(args.quality),
        )
        results = search_vectors(
            embed_query(args.query),
            top_k=args.top_k,
            filters=filters,
        )
        _print([result.as_dict() for result in results])
        return

    if args.command == "hybrid":
        retriever = HybridRetriever(engine=get_engine())
        if args.no_evidence:
            packet = retriever.search_with_evidence(
                args.query,
                top_k=args.top_k,
                evidence_top_k=1,
                mode=args.mode,
            )
            _print({"analysis": packet["analysis"], "results": packet["results"]})
        else:
            _print(
                retriever.search_with_evidence(
                    args.query,
                    top_k=args.top_k,
                    evidence_top_k=args.evidence_top_k,
                    mode=args.mode,
                )
            )


if __name__ == "__main__":
    main()
