#!/usr/bin/env python
"""数据校验 CLI。

用法：
    python scripts/validate_data.py            # 校验并输出统计
    python scripts/validate_data.py --quiet    # 只输出结论，适合 CI / 钩子

退出码：0 表示校验通过，1 表示存在问题或文件缺失。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许以 `python scripts/validate_data.py` 直接运行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.loader import (  # noqa: E402
    DataError,
    DataFileMissingError,
    DatasetError,
    dataset_summary,
    load_dataset,
    validate_dataset,
)
from src.data.repository import Repository  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验徽知项目的文化数据文件")
    parser.add_argument("--quiet", action="store_true", help="只输出结论")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 data/）")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else None

    try:
        dataset = load_dataset(data_dir)
    except DataFileMissingError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    except DatasetError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        print("\n提示：运行 `python scripts/validate_data.py` 可在不抛异常的情况下查看全部问题。",
              file=sys.stderr)
        return 1
    except DataError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    issues = validate_dataset(dataset)
    if issues:
        print(f"[失败] 发现 {len(issues)} 个问题：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        return 1

    summary = dataset_summary(dataset)
    repo = Repository(dataset)
    stats = repo.stats()

    print("[通过] 数据校验全部通过。")
    if not args.quiet:
        print()
        print("规模：")
        print(f"  实体   {summary['entities']}")
        print(f"  关系   {summary['relations']}")
        print(f"  来源   {summary['sources']}")
        print(f"  分类   {summary['categories']}")
        print(f"  关系类型 {summary['relation_types']}")

        print()
        print("分类分布：")
        for cc in repo.category_counts():
            print(f"  {cc.category.name:<12} {cc.count:>3}")

        print()
        print("关系类型分布：")
        for name, count in stats["relation_type_counts"].items():  # type: ignore[union-attr]
            print(f"  {name:<10} {count:>3}")

        top = stats["top_connected"]  # type: ignore[assignment]
        print()
        print("连接度最高的实体：")
        for row in top[:5]:  # type: ignore[index]
            print(f"  {row['entity'].name:<14} 度={row['degree']}")  # type: ignore[index]

        isolated = stats["isolated_entities"]  # type: ignore[assignment]
        print()
        if isolated:
            print(f"孤立实体（无任何关系，建议补充关系）：{len(isolated)} 个")
            for name in isolated[:10]:  # type: ignore[union-attr]
                print(f"  {name}")
        else:
            print("孤立实体：无（全部实体至少有一条关系）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
