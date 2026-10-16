"""在人工标注集上评估检索与问答效果（CLI）。

用途：不启动界面，直接输出可复现、可核对的量化结果，并可作为验收证据。
默认**完全离线**（本地检索式后端 + 本地索引），因此任何环境都能跑；
要看真实大模型的表现时加 ``--live``，报告里会写明实际使用的后端。

用法::

    python scripts/evaluate.py                     # 检索 + 问答，离线
    python scripts/evaluate.py --retrieval-only    # 只跑检索
    python scripts/evaluate.py --top-k 3           # 改截断条数
    python scripts/evaluate.py --json outputs/eval.json
    python scripts/evaluate.py --verbose           # 打印每条查询的排名明细
    python scripts/evaluate.py --live              # 用配置好的真实后端（联网）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许以 `python scripts/evaluate.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.data.loader import DataError, load_dataset  # noqa: E402
from src.data.repository import Repository  # noqa: E402
from src.eval import dataset as ev  # noqa: E402
from src.eval.runner import EvalReport, evaluate_answers, evaluate_retrieval  # noqa: E402
from src.qa.engine import QAEngine, LocalRetrievalBackend  # noqa: E402
from src.qa.retriever import Retriever  # noqa: E402


def _rule(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 58 - len(title)))


def _print_retrieval_detail(report, repo: Repository) -> None:
    name_of = {e.id: e.name for e in repo.entities}

    def show(row) -> None:
        marked = " ".join(
            f"{name_of.get(i, i)}{'*' * int(row.relevant.get(i, 0))}"
            for i in row.ranked
        )
        print(f"    {row.query} → {marked}")

    missed = report.misses
    if missed:
        print(f"\n  未命中（@{max(report.ks)} 名内无相关项）：{len(missed)} 条")
        for row in missed[:12]:
            show(row)

    false_pos = [r for r in report.negatives if not r.empty_result]
    if false_pos:
        print(f"\n  负样本误召回：{len(false_pos)} 条")
        for row in false_pos[:12]:
            show(row)


def _print_tag_breakdown(report) -> None:
    print("\n  按标签分组（* 为「期望」与「实际」的对比重点）")
    for tag, item in report.tag_breakdown.items():
        bits = [f"{int(item['cases'])} 条"]
        if "hit" in item:
            bits.append(f"命中 {item['hit']:.3f}")
            bits.append(f"召回 {item['recall']:.3f}")
            bits.append(f"nDCG {item['ndcg']:.3f}")
            bits.append(f"MRR {item['mrr']:.3f}")
        if "negative_empty" in item:
            bits.append(f"正确留空 {item['negative_empty']:.3f}")
        print(f"    {tag:<14} " + "　".join(bits))


def main() -> int:
    parser = argparse.ArgumentParser(description="徽知 · 检索与问答效果评估")
    parser.add_argument("--json", metavar="路径", help="把完整报告写成 JSON")
    parser.add_argument("--top-k", type=int, default=0, help="检索截断条数（默认沿用配置）")
    parser.add_argument("--ks", metavar="K1,K2", default="1,3,5", help="报告的截断位置，默认 1,3,5")
    parser.add_argument("--retrieval-only", action="store_true", help="只跑检索评估")
    parser.add_argument("--answers-only", action="store_true", help="只跑问答评估")
    parser.add_argument(
        "--live",
        action="store_true",
        help="用配置好的真实后端（Dify / 大模型）评估问答，会联网并消耗额度",
    )
    parser.add_argument("--verbose", action="store_true", help="打印未命中与误召回的明细")
    args = parser.parse_args()

    try:
        ks = tuple(int(x) for x in args.ks.replace("，", ",").split(",") if x.strip())
    except ValueError:
        print("[错误] --ks 应为形如 1,3,5 的整数列表")
        return 2

    try:
        repo = Repository(load_dataset())
    except DataError as exc:
        print(f"[错误] 数据加载失败：{exc}")
        return 2

    try:
        rs, qs = ev.load_all(repo)
    except ev.EvalDataError as exc:
        print(f"[错误] 标注集不可用：{exc}")
        return 2

    top_k = args.top_k or config.qa_top_k()
    report = EvalReport()

    _rule("评估设置")
    print(f"  检索标注：{len(rs.cases)} 条（有答案 {len(rs.positives)} / 负样本 {len(rs.negatives)}）")
    print(f"  问答标注：{len(qs.cases)} 条（可答 {len(qs.answerable)} / 应拒答 {len(qs.abstain)}）")
    print(f"  检索截断：top_k={top_k}　指标位置：{', '.join(str(k) for k in ks)}")

    if not args.answers_only:
        retriever = Retriever(repo, top_k=top_k)
        retrieval = evaluate_retrieval(retriever, rs, top_k=top_k, ks=ks)
        report = EvalReport(retrieval=retrieval, answers=report.answers)
        _rule("检索评估")
        for line in retrieval.summary_lines():
            print("  " + line if not line.startswith("  ") else line)
        _print_tag_breakdown(retrieval)
        if args.verbose:
            _print_retrieval_detail(retrieval, repo)

    if not args.retrieval_only:
        backends = None if args.live else [LocalRetrievalBackend()]
        engine = QAEngine(repo, top_k=top_k, backends=backends)
        active = engine.active_backend()
        _rule("问答评估")
        if args.live:
            print(f"  后端：{active.label if active else '无可用后端'}（真实调用，联网）")
        else:
            print("  后端：本地检索式（离线、确定，不消耗任何 API 额度）")
        answers = evaluate_answers(engine, qs)
        report = EvalReport(retrieval=report.retrieval, answers=answers)
        for line in answers.summary_lines():
            print("  " + line if not line.startswith("  ") else line)

        low = [r for r in answers.rows if not r.error and r.term_recall < 1.0]
        if low:
            print(f"\n  要点未答全的样本：{len(low)} 条")
            for row in low[:10]:
                missing = [t for t in row.required_terms if t not in row.hit_terms]
                print(f"    {row.question} → 缺：{'、'.join(missing)}")
        wrong = [r for r in answers.rows if not r.error and not r.abstention_correct]
        if wrong:
            print(f"\n  拒答判断有误：{len(wrong)} 条")
            for row in wrong[:10]:
                verdict = "该拒答却作答" if row.must_abstain else "该作答却拒答"
                print(f"    {row.question} → {verdict}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        payload["settings"] = {
            "top_k": top_k,
            "ks": list(ks),
            "live": bool(args.live),
            "backend": ("" if args.live else "local-retrieval"),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n完整报告：{out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
