from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.index_contract import validate_index_contract


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate persisted indexes against the source document"
    )
    parser.add_argument("--base-dir", type=Path)
    parser.add_argument("--source-doc", type=Path)
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate_index_contract(
        base_dir=args.base_dir,
        source_doc=args.source_doc,
        check_qdrant=not args.skip_qdrant,
    )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        passed = sum(1 for check in report.checks if check.ok)
        status = "通过" if report.ok else "未通过"
        print(f"索引校验：{status}（{passed}/{len(report.checks)}）")
        for check in report.checks:
            mark = "OK  " if check.ok else "FAIL"
            print(f"- [{mark}] {check.name}：{check.detail}")
            if not check.ok:
                if check.expected:
                    print(f"        期望：{check.expected}")
                if check.actual:
                    print(f"        实际：{check.actual}")
        if not report.ok and report.next_steps:
            print()
            print("修复步骤：")
            for index, step in enumerate(report.next_steps, start=1):
                print(f"  {index}. {step}")
            print("索引重建完成后需要重启服务。")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
