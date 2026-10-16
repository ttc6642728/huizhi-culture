"""从 Wikimedia Commons 抓取自由授权的徽州文化图片，并生成可核查的署名清单。

设计要点
--------
1. **只接受自由授权**：白名单匹配 CC0 / CC BY / CC BY-SA / Public domain / GFDL，
   许可不明或含 NC / ND / 合理使用的一律丢弃，绝不把不清晰授权的图片放进项目。
2. **只接受与实体真正相关的图片**：每个实体自带一个检索词与一个必须匹配的正则，
   命中标题、文件名或描述任一即可；不匹配的候选直接跳过，
   避免「搜 Hongcun 却下到一张无关照片」这类污染。
3. **同一张图只用一个实体**：已用过的文件会被跳过，防止重复堆砌。
4. **联网方式**：优先使用标准库 ``urllib``；若环境限制直连（部分沙箱会按客户端拦截），
   自动回退到系统 ``curl``。两种方式都失败时如实报错，不生成占位图。
5. 结果写入 ``assets/images/`` 与 ``assets/images/CREDITS.md``，
   逐条登记标题、作者、许可、许可地址与来源页面，便于核查。

用法::

    python scripts/fetch_images.py --dry-run     # 只检索、不下载，打印候选
    python scripts/fetch_images.py               # 下载并按清单写入
    python scripts/fetch_images.py --only hongcun xidi
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "assets" / "images"
MANIFEST = IMAGES_DIR / "manifest.json"
CREDITS = IMAGES_DIR / "CREDITS.md"

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "HuizhouCultureExplorer/1.0 (course project; contact: local)"

#: 目标缩略图宽度（像素）。1000 px 在卡片与详情页都足够清晰，且体积可控。
THUMB_WIDTH = 1000

#: 许可白名单：名称以此开头即视为自由授权。
ALLOWED_LICENSE_PREFIXES = (
    "CC0",
    "CC BY",
    "CC BY-SA",
    "Public domain",
    "PD",
    "GFDL",
)

#: 明确拒绝的许可关键词（防止白名单前缀被绕过）。
REJECTED_LICENSE_KEYWORDS = ("NC", "ND", "non-commercial", "NoDerivs", "Fair use")


# --------------------------------------------------------------------------
# 目标清单：(实体 id, 检索词, 必须匹配的正则, 排除正则, 图注)
#
# 检索词刻意简短（Commons 检索默认要求**全部词**命中，词越多结果越少），
# 相关性由「必须匹配 + 排除」两个正则把关。
# --------------------------------------------------------------------------

TARGETS: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("hongcun", "Hongcun", r"hongcun|宏村", r"", "宏村村落与月沼一带"),
    ("xidi", "Xidi", r"xidi|西递", r"", "西递村落与牌坊"),
    ("chengkan", "Chengkan", r"chengkan|呈坎", r"", "呈坎村落与罗东舒祠"),
    ("tangmo", "Tangmo", r"tangmo|唐模", r"", "唐模水街"),
    ("tangyue", "Tangyue", r"tangyue|棠樾", r"", "棠樾牌坊群"),
    ("nanping", "Nanping village", r"nanping|南屏", r"fujian|福建", "南屏村落巷弄"),
    ("xucun", "Xucun", r"xucun|许村", r"", "许村牌坊与街巷"),
    ("yuliang", "Yuliang", r"yuliang|渔梁", r"pan|潘", "渔梁坝与练江"),
    ("chengzhitang", "Chengzhi Hongcun", r"chengzhi|承志堂", r"", "承志堂木雕厅堂"),
    ("tunxi_laojie", "Tunxi", r"tunxi|屯溪", r"", "屯溪老街街景"),
    ("xuguo_shifang", "Xuguo", r"xuguo|许国", r"", "许国石坊"),
    ("huipai_architecture", "Huizhou architecture", r"huizhou|徽派|徽州", r"guangdong|惠州|广东", "徽派建筑粉墙黛瓦"),
    ("matouqiang", "Matouqiang", r"matouqiang|马头墙|horsehead|horse head", r"", "马头墙"),
    ("huizhou_minju", "Huizhou house", r"huizhou|徽州民居", r"guangdong|惠州|广东", "徽州民居天井院"),
    ("huizhou_paifang", "paifang Anhui", r"paifang|牌坊", r"", "徽州牌坊"),
    ("huizhou_citang", "ancestral hall Huizhou", r"ancestral hall|祠堂", r"", "徽州祠堂"),
    ("huangshan", "Huangshan", r"huangshan|黄山", r"", "黄山花岗岩峰林"),
    ("xinanjiang", "Xin'an River", r"xin.?an river|新安江", r"genealogy|族谱|family", "新安江山水"),
    ("qiyunshan", "Qiyun", r"qiyun|齐云", r"", "齐云山丹霞与道观"),
    ("huimo", "Huizhou ink stick", r"ink.?stick|huizhou ink|徽墨", r"", "徽墨"),
    ("sheyan", "She inkstone", r"inkstone|歙砚", r"", "歙砚"),
    ("huizhou_sandiao", "Huizhou wood carving", r"carving|雕", r"", "徽州三雕"),
    ("huiju", "Hui opera", r"hui opera|徽剧", r"", "徽剧"),
    ("zhuxi", "Zhu Xi", r"zhu xi|朱熹", r"", "朱熹画像"),
    ("hushi", "Hu Shih", r"hu shih|hushi|胡适", r"father|胡传|hu chuan", "胡适肖像"),
    ("jianjiang", "Jianjiang", r"jianjiang|渐江|弘仁", r"", "渐江山水画"),
    ("huangbinhong", "Huang Binhong", r"binhong|宾虹", r"tuscan|voogd", "黄宾虹山水画"),
    ("hu_qingyutang", "Hu Qing Yu Tang", r"qing.?yu", r"", "胡庆余堂"),
    ("huizhou_yudeng", "fish lantern", r"fish.?lantern|鱼灯", r"", "徽州鱼灯"),
)

#: 画幅比例限制：过宽或过窄的图在卡片与详情页都难以排版。
MIN_ASPECT = 0.5
MAX_ASPECT = 2.1


# --------------------------------------------------------------------------
# 联网：先探测可用通道，再固定使用，避免每个请求都去重试失败的通道
# --------------------------------------------------------------------------

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: 通道顺序，首次成功者会被提到最前并复用。
_TRANSPORTS: List[str] = ["curl-noproxy", "curl", "urllib-direct", "urllib-proxy"]

#: 各通道的探测结果（None 表示尚未探测）
_PROBED: Dict[str, bool] = {}


def _via_curl(url: str, timeout: int, no_proxy: bool) -> bytes:
    if shutil.which("curl") is None:
        raise RuntimeError("系统没有 curl")
    args = ["curl", "-s", "-L", "--max-time", str(timeout), "-A", USER_AGENT]
    if no_proxy:
        args += ["--noproxy", "*"]
    done = subprocess.run(
        [*args, url], capture_output=True, timeout=timeout + 15, check=False
    )
    if done.returncode != 0 or len(done.stdout) < 32:
        raise RuntimeError(f"curl 返回码 {done.returncode}，{len(done.stdout)} 字节")
    return done.stdout


def _via_urllib(url: str, timeout: int, direct: bool) -> bytes:
    opener = _NO_PROXY if direct else urllib.request.build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return resp.read()


def _attempt(transport: str, url: str, timeout: int) -> bytes:
    if transport == "curl":
        return _via_curl(url, timeout, no_proxy=False)
    if transport == "curl-noproxy":
        return _via_curl(url, timeout, no_proxy=True)
    if transport == "urllib-direct":
        return _via_urllib(url, timeout, direct=True)
    if transport == "urllib-proxy":
        return _via_urllib(url, timeout, direct=False)
    raise RuntimeError(f"未知通道：{transport}")


def resolve_transport() -> str:
    """探测出一个可用的联网通道并固定使用。

    不同运行环境的网络策略差异很大（有的直连可用、有的只能走代理、
    有的会按客户端拦截），因此这里只探测一次，之后所有请求都复用，
    避免每个请求都因为重试失败通道而拖慢整体进度。
    """
    probe = API + "?action=query&format=json&meta=siteinfo"
    errors: List[str] = []
    for transport in _TRANSPORTS:
        if _PROBED.get(transport) is False:
            continue
        try:
            raw = _attempt(transport, probe, 20)
            json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 需要汇总多种网络/解析异常
            _PROBED[transport] = False
            errors.append(f"{transport}: {type(exc).__name__} {str(exc)[:70]}")
            continue
        _PROBED[transport] = True
        _TRANSPORTS.remove(transport)
        _TRANSPORTS.insert(0, transport)
        print(f"[网络] 使用通道：{transport}")
        return transport
    raise RuntimeError("没有任何可用的联网通道：\n  " + "\n  ".join(errors))


def _get(url: str, timeout: int = 40) -> bytes:
    """取回 URL 内容；按已探测到的通道顺序尝试，成功即返回。"""
    errors: List[str] = []
    for transport in list(_TRANSPORTS):
        if _PROBED.get(transport) is False:
            continue
        try:
            raw = _attempt(transport, url, timeout)
            _PROBED[transport] = True
            return raw
        except Exception as exc:  # noqa: BLE001
            _PROBED[transport] = False if transport.startswith("urllib") else _PROBED.get(transport)
            errors.append(f"{transport}: {type(exc).__name__} {str(exc)[:80]}")
    raise RuntimeError(f"无法访问 {url}\n  " + "\n  ".join(errors))


def _api(params: Dict[str, str]) -> Dict:
    """调用 Commons API 并解析 JSON。"""
    params = {"action": "query", "format": "json", **params}
    url = API + "?" + urllib.parse.urlencode(params)
    raw = _get(url, timeout=45)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Commons API 返回的不是 JSON：{raw[:200]!r}") from exc


# --------------------------------------------------------------------------
# 候选筛选
# --------------------------------------------------------------------------


def _strip_html(value: str) -> str:
    """去掉 HTML 标签并还原实体，用于作者等字段。"""
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _license_of(meta: Dict) -> Tuple[str, str]:
    """返回 (许可简称, 许可地址)。"""
    name = str(meta.get("LicenseShortName", {}).get("value", "")).strip()
    url = str(meta.get("LicenseUrl", {}).get("value", "")).strip()
    return name, url


def _is_free(name: str) -> bool:
    if not name:
        return False
    if any(k.lower() in name.lower() for k in REJECTED_LICENSE_KEYWORDS):
        # CC BY-SA 里的 "SA" 不冲突；只有 NC / ND 等才拒绝
        if not name.startswith("CC BY-SA"):
            return False
    return name.startswith(ALLOWED_LICENSE_PREFIXES)


def search_candidates(query: str, limit: int = 8) -> List[Dict]:
    """检索候选文件，返回按 Commons 相关性排序的候选列表。"""
    data = _api(
        {
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": "6",
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": str(THUMB_WIDTH),
        }
    )
    pages = data.get("query", {}).get("pages", {})
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 99))

    result: List[Dict] = []
    for page in ordered:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        meta = info.get("extmetadata", {})
        title = page.get("title", "")
        license_name, license_url = _license_of(meta)
        result.append(
            {
                "title": title,
                "file_name": title.removeprefix("File:"),
                "mime": info.get("mime", ""),
                "width": info.get("width", 0),
                "height": info.get("height", 0),
                "thumb_url": info.get("thumburl") or info.get("url", ""),
                "page_url": info.get("descriptionurl", ""),
                "license": license_name,
                "license_url": license_url,
                "artist": _strip_html(str(meta.get("Artist", {}).get("value", ""))),
                "credit": _strip_html(str(meta.get("Credit", {}).get("value", ""))),
                "description": _strip_html(
                    str(meta.get("ImageDescription", {}).get("value", ""))
                )[:300],
                "free": _is_free(license_name),
            }
        )
    return result


def pick_candidate(
    entity_id: str,
    query: str,
    must_match: str,
    exclude: str,
    used_titles: set,
) -> Tuple[Optional[Dict], List[str]]:
    """挑选一张合格图片；返回 (候选, 跳过原因列表)。"""
    reasons: List[str] = []
    pattern = re.compile(must_match, re.I)
    reject = re.compile(exclude, re.I) if exclude else None

    try:
        candidates = search_candidates(query)
    except RuntimeError as exc:
        return None, [f"检索失败：{exc}"]

    if not candidates:
        return None, ["检索无结果"]

    for cand in candidates:
        if cand["file_name"] in used_titles:
            reasons.append(f"已用于其它实体：{cand['file_name'][:40]}")
            continue
        if not cand["free"]:
            reasons.append(f"许可不合规（{cand['license'] or '未知'}）：{cand['file_name'][:40]}")
            continue
        if cand["mime"] not in ("image/jpeg", "image/png"):
            reasons.append(f"格式不支持（{cand['mime']}）：{cand['file_name'][:40]}")
            continue
        if cand["height"] <= 0:
            reasons.append(f"尺寸信息缺失：{cand['file_name'][:40]}")
            continue
        aspect = cand["width"] / cand["height"]
        if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
            reasons.append(
                f"画幅比例不合适（{cand['width']}×{cand['height']}，{aspect:.2f}）："
                f"{cand['file_name'][:36]}"
            )
            continue
        if min(cand["width"], cand["height"]) < 600:
            reasons.append(f"分辨率过低（{cand['width']}×{cand['height']}）：{cand['file_name'][:40]}")
            continue
        haystack = " ".join(
            [cand["title"], cand["file_name"], cand["description"], cand["credit"]]
        )
        if reject and reject.search(haystack):
            reasons.append(f"命中排除词：{cand['file_name'][:40]}")
            continue
        if not pattern.search(haystack):
            reasons.append(
                f"与实体无关：{cand['file_name'][:36]}（{cand['description'][:40]}）"
            )
            continue
        return cand, reasons

    return None, reasons or ["没有符合全部条件的候选"]


# --------------------------------------------------------------------------
# 下载与清单
# --------------------------------------------------------------------------


def download(cand: Dict, dest_stem: str) -> Path:
    """下载缩略图到 ``assets/images/``，返回实际文件路径。"""
    if not cand["thumb_url"]:
        raise RuntimeError(f"{cand['file_name']} 没有可用的缩略图地址")
    suffix = ".png" if cand["mime"] == "image/png" else ".jpg"
    dest = IMAGES_DIR / f"{dest_stem}{suffix}"
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    raw = _get(cand["thumb_url"], timeout=90)
    if len(raw) < 2048:
        raise RuntimeError(f"下载内容过小（{len(raw)} 字节），疑似失败")
    dest.write_bytes(raw)
    return dest


def write_credits(entries: List[Dict], failed: List[Tuple[str, List[str]]]) -> None:
    """生成署名清单，逐条登记作者、许可与来源。"""
    lines = [
        "# 图片署名清单",
        "",
        "本项目在界面中使用的徽州文化图片全部来自 **Wikimedia Commons**，",
        "且均为自由授权（CC0 / CC BY / CC BY-SA / 公有领域 / GFDL）。",
        "下表逐条登记来源，可点击核对原始页面。",
        "",
        "> 说明：以下图片按原许可要求署名使用；如某张图片被替换或移除，",
        "> 请同步更新本文件与 `manifest.json`。",
        "",
        "| 使用位置 | 文件 | 作者 | 许可 | 来源页面 |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        author = entry["artist"] or "见来源页面"
        license_text = entry["license"]
        if entry["license_url"]:
            license_text = f"[{entry['license']}]({entry['license_url']})"
        lines.append(
            f"| {entry['name']}（`{entry['entity_id']}`） "
            f"| `{entry['file']}` "
            f"| {author} "
            f"| {license_text} "
            f"| [Commons]({entry['page_url']}) |"
        )

    if failed:
        lines += [
            "",
            "## 未取得图片的实体",
            "",
            "以下实体在 Commons 上未找到同时满足「与实体相关」与「许可明确自由」的图片，",
            "因此**不放图**，界面会自动回退为纯排版展示（不以占位图充数）。",
            "",
        ]
        for entity_id, reasons in failed:
            reason = reasons[0] if reasons else "无合适候选"
            lines.append(f"- `{entity_id}`：{reason}")

    lines += [
        "",
        "## 复现方式",
        "",
        "```bat",
        "python scripts/fetch_images.py --dry-run   :: 先看候选，不下载",
        "python scripts/fetch_images.py             :: 下载并重写清单",
        "```",
        "",
    ]
    CREDITS.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(entries: List[Dict]) -> None:
    """写入机器可读的图片清单（供界面读取）。"""
    manifest = {
        "version": "1.0",
        "source": "Wikimedia Commons",
        "note": (
            "实体图片清单。仅收录自由授权图片，逐条登记作者、许可与来源页面。"
            "文件缺失或未登记的实体，界面会回退为无图排版。"
        ),
        "images": [
            {
                "entity_id": e["entity_id"],
                "file": e["file"],
                "caption": e["caption"],
                "title": e["title"],
                "artist": e["artist"],
                "license": e["license"],
                "license_url": e["license_url"],
                "source_url": e["page_url"],
                "width": e["width"],
                "height": e["height"],
            }
            for e in entries
        ],
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取自由授权的徽州文化图片")
    parser.add_argument("--dry-run", action="store_true", help="只检索并打印候选，不下载")
    parser.add_argument("--only", nargs="*", metavar="实体ID", help="只处理指定实体")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个实体")
    args = parser.parse_args()

    targets = TARGETS
    if args.only:
        wanted = set(args.only)
        targets = tuple(t for t in targets if t[0] in wanted)
        missing = wanted - {t[0] for t in targets}
        if missing:
            print(f"[警告] 未在目标清单中：{', '.join(sorted(missing))}")
    if args.limit:
        targets = targets[: args.limit]

    entity_names = json.loads(
        (ROOT / "data" / "entities.json").read_text(encoding="utf-8")
    )["entities"]
    name_of = {e["id"]: e["name"] for e in entity_names}

    try:
        resolve_transport()
    except RuntimeError as exc:
        print(f"[错误] {exc}")
        return 2

    print(f"目标实体 {len(targets)} 个｜缩略图宽度 {THUMB_WIDTH}px｜模式 "
          f"{'仅检索' if args.dry_run else '检索并下载'}\n")

    entries: List[Dict] = []
    failed: List[Tuple[str, List[str]]] = []
    used_titles: set = set()

    for entity_id, query, must_match, exclude, caption in targets:
        label = name_of.get(entity_id, entity_id)
        cand, reasons = pick_candidate(entity_id, query, must_match, exclude, used_titles)

        if cand is None:
            print(f"[×] {label:<10} 未取得图片")
            for reason in reasons[:3]:
                print(f"      · {reason}")
            failed.append((entity_id, reasons))
            time.sleep(0.3)
            continue

        if args.dry_run:
            print(f"[√] {label:<10} {cand['file_name'][:52]}")
            print(f"      许可 {cand['license']}｜作者 {cand['artist'][:40] or '见来源页'}"
                  f"｜{cand['width']}×{cand['height']}")
            print(f"      说明 {cand['description'][:80] or cand['title'][:80]}")
            used_titles.add(cand["file_name"])
            time.sleep(0.3)
            continue

        try:
            path = download(cand, entity_id)
        except RuntimeError as exc:
            print(f"[×] {label:<10} 下载失败：{exc}")
            failed.append((entity_id, [f"下载失败：{exc}"]))
            continue

        used_titles.add(cand["file_name"])
        entries.append(
            {
                "entity_id": entity_id,
                "name": label,
                "file": path.name,
                "caption": caption,
                "title": cand["title"],
                "artist": cand["artist"],
                "license": cand["license"],
                "license_url": cand["license_url"],
                "page_url": cand["page_url"],
                "width": cand["width"],
                "height": cand["height"],
            }
        )
        size_kb = path.stat().st_size / 1024
        print(f"[√] {label:<10} → {path.name}（{size_kb:.0f} KB，{cand['license']}）")

    if args.dry_run:
        print(f"\n检索完成：命中 {len(used_titles)} 个，未命中 {len(failed)} 个（未下载任何文件）")
        return 0

    write_manifest(entries)
    write_credits(entries, failed)
    print(
        f"\n完成：成功 {len(entries)} 张，未取得 {len(failed)} 个实体。\n"
        f"清单：{MANIFEST.relative_to(ROOT)}\n署名：{CREDITS.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
