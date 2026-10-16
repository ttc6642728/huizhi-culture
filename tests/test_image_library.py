"""图片库测试：清单缺失/损坏/文件丢失时的行为，以及署名信息的完整性。

图片是「有则显示、无则不影响」的增强内容，因此这里重点验证**降级路径**：
任何异常都不得让应用崩溃，也不得凭空造出一张图。
"""

from __future__ import annotations

import functools
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from src import config
from src.data.images import EntityImage, ImageLibrary

MINIMAL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _write(root: Path, entries: list, make_files: bool = True) -> Path:
    images_dir = root / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if make_files and entry.get("file"):
            (images_dir / entry["file"]).write_bytes(MINIMAL_PNG)
    manifest = images_dir / "manifest.json"
    manifest.write_text(
        json.dumps({"version": "1.0", "images": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def _entry(**over: Any) -> Dict[str, Any]:
    base = {
        "entity_id": "hongcun",
        "file": "hongcun.jpg",
        "caption": "宏村月沼",
        "title": "File:Hongcun.jpg",
        "artist": "某摄影师",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source_url": "https://commons.wikimedia.org/wiki/File:Hongcun.jpg",
        "width": 1600,
        "height": 1200,
    }
    base.update(over)
    return base


def test_missing_manifest_is_not_an_error(tmp_path: Path) -> None:
    """清单不存在属正常状态（尚未抓取图片），不是错误。"""
    library = ImageLibrary(tmp_path)
    assert library.available is False
    assert len(library) == 0
    assert library.get("hongcun") is None
    assert library.issues, "应记录一条说明，便于排查"


def test_valid_manifest_loads(tmp_path: Path) -> None:
    _write(tmp_path, [_entry()])
    library = ImageLibrary(tmp_path)
    assert library.available is True
    image = library.get("hongcun")
    assert isinstance(image, EntityImage)
    assert image.exists
    assert image.rel_path == "assets/images/hongcun.jpg"
    assert "CC BY-SA 4.0" in image.credit
    assert image.caption == "宏村月沼"


def test_credit_without_artist_is_honest(tmp_path: Path) -> None:
    """作者缺失时如实说明，不编造作者名。"""
    _write(tmp_path, [_entry(artist="")])
    image = ImageLibrary(tmp_path).get("hongcun")
    assert image is not None
    assert "作者见来源页面" in image.credit


def test_entry_with_missing_file_is_skipped(tmp_path: Path) -> None:
    """清单登记了但文件缺失时，该条目不生效，并记录问题。"""
    _write(tmp_path, [_entry(file="ghost.jpg")], make_files=False)
    library = ImageLibrary(tmp_path)
    assert library.get("hongcun") is None
    assert any("缺失" in issue for issue in library.issues)


def test_corrupt_manifest_degrades(tmp_path: Path) -> None:
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "manifest.json").write_text("{ 这不是 JSON ", encoding="utf-8")
    library = ImageLibrary(tmp_path)
    assert library.available is False
    assert any("无法解析" in issue for issue in library.issues)


def test_manifest_images_not_a_list(tmp_path: Path) -> None:
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "manifest.json").write_text('{"images": {"a": 1}}', encoding="utf-8")
    library = ImageLibrary(tmp_path)
    assert library.available is False
    assert any("不是数组" in issue for issue in library.issues)


def test_entries_without_ids_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, [_entry(entity_id=""), _entry(entity_id="xidi", file="xidi.jpg")])
    library = ImageLibrary(tmp_path)
    assert library.ids() == ("xidi",)
    assert any("缺少 entity_id" in issue for issue in library.issues)


def test_project_library_never_crashes() -> None:
    """对真实项目目录载入图片库：无论有没有图，都必须安全。"""
    library = ImageLibrary(config.BASE_DIR)
    assert not any("无法解析" in issue for issue in library.issues)
    for image in library.all():
        assert image.exists, "清单里登记的图片必须真实存在"
        assert image.license, "每张图都必须登记许可"
        assert image.source_url.startswith("http"), "每张图都必须有可核查的来源页面"


# --------------------------------------------------------------------------
# 真实图片清单的合规校验（对仓库里实际交付的图片生效）
# --------------------------------------------------------------------------

#: 与 ``scripts/fetch_images.py`` 保持一致的许可白名单 / 拒绝关键词。
_ALLOWED_LICENSE_PREFIXES = ("CC0", "CC BY", "CC BY-SA", "Public domain", "PD", "GFDL")
_REJECTED_LICENSE_KEYWORDS = ("NC", "ND", "non-commercial", "NoDerivs", "Fair use")

#: 交付下限：低于此数说明图片被误删或清单被破坏。
_MIN_DELIVERED_IMAGES = 8


def test_real_manifest_meets_delivery_minimum() -> None:
    """真实清单必须存在且达到交付下限（防止清单一度被写成空而无人察觉）。"""
    library = ImageLibrary(config.BASE_DIR)
    assert library.available, "应存在 assets/images/manifest.json"
    assert len(library) >= _MIN_DELIVERED_IMAGES, (
        f"已登记图片仅 {len(library)} 张，低于交付下限 {_MIN_DELIVERED_IMAGES}"
    )


def test_real_manifest_licenses_are_free() -> None:
    """每张真实图片的许可都必须在白名单内，且不含 NC / ND 等受限条款。"""
    for image in ImageLibrary(config.BASE_DIR).all():
        name = image.license
        assert name, f"{image.entity_id} 未登记许可"
        if not name.startswith("CC BY-SA"):
            assert not any(
                kw.lower() in name.lower() for kw in _REJECTED_LICENSE_KEYWORDS
            ), f"{image.entity_id} 的许可含受限条款：{name}"
        assert name.startswith(_ALLOWED_LICENSE_PREFIXES), (
            f"{image.entity_id} 的许可不在白名单：{name}"
        )


def test_real_manifest_files_are_valid_images() -> None:
    """每张真实图片都必须是有效的 JPEG，且不是被截断的残文件。"""
    for image in ImageLibrary(config.BASE_DIR).all():
        data = image.path.read_bytes()
        assert data[:2] == b"\xff\xd8", f"{image.entity_id} 不是有效 JPEG（缺 SOI 标记）"
        assert len(data) > 10_000, f"{image.entity_id} 文件过小（{len(data)} 字节），疑似残缺"


def test_real_manifest_entities_exist_in_dataset() -> None:
    """清单只能引用数据集中真实存在的实体 id。"""
    entities = json.loads(
        (config.BASE_DIR / "data" / "entities.json").read_text(encoding="utf-8")
    )["entities"]
    known = {e["id"] for e in entities}
    unknown = [eid for eid in ImageLibrary(config.BASE_DIR).ids() if eid not in known]
    assert not unknown, f"图片清单引用了不存在的实体：{unknown}"


def test_real_manifest_entries_are_fully_attributed() -> None:
    """每张图都要有图注与作者，且署名链接与来源页面可核查。"""
    for image in ImageLibrary(config.BASE_DIR).all():
        assert image.caption.strip(), f"{image.entity_id} 缺图注"
        assert image.artist.strip(), f"{image.entity_id} 缺作者"
        assert image.source_url.startswith("https://commons.wikimedia.org/"), (
            f"{image.entity_id} 的来源页面不是 Commons：{image.source_url}"
        )


# --------------------------------------------------------------------------
# 抓取把关（对 `scripts/fetch_images.py` 里那套「相关性 + 候选硬性条件」的离线断言）
#
# 这一组存在的理由：曾经真的下错过三张图——「渐江」下到广东江河的航拍、
# 「徽州牌坊」下到白云寺院门、「徽州祠堂」下到无锡惠山祠堂，
# 而清单的图注却照抄了实体名，会让界面宣称错误事实。
# 把关规则因此必须可被断言，而不是只活在抓取脚本的一次性运行里。
# --------------------------------------------------------------------------

_FETCH_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_images.py"


@functools.lru_cache(maxsize=1)
def _fetch_module():
    """按路径加载抓图脚本（`scripts/` 不是包，故用显式路径加载）。"""
    spec = importlib.util.spec_from_file_location("fetch_images", _FETCH_SCRIPT)
    assert spec and spec.loader, f"无法加载 {_FETCH_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(**overrides: Any) -> Dict[str, Any]:
    """一张「各项都合格」的候选，供逐条破坏某一项来验证把关。"""
    base: Dict[str, Any] = {
        "title": "File:Chengkan 5456.jpg",
        "file_name": "Chengkan 5456.jpg",
        "mime": "image/jpeg",
        "width": 1600,
        "height": 1200,
        "artist": "Doctoroftcm",
        "credit": "",
        "description": "Chengkan village, Huizhou, Anhui",
        "license": "CC BY-SA 3.0",
        "free": True,
    }
    base.update(overrides)
    return base


#: 真实下错过、后来被剔除的三个候选。文件名取自当时清单里的 `title`。
_KNOWN_WRONG_CANDIDATES = (
    ("jianjiang", "File:Jianjiang Delta Aerial View.png"),
    ("huizhou_paifang", "File:Paifang, Baiyun Temple, 26 September 2020X.jpg"),
    (
        "huizhou_citang",
        "File:Chu Hsi's ancestral temple in Wuxi Huishan ancient town.JPG",
    ),
)


def test_target_gates_reject_the_candidates_actually_downloaded_by_mistake() -> None:
    """这三个真实误召回必须被挡住（同名异地 / 同物异指）。"""
    module = _fetch_module()
    for entity_id, title in _KNOWN_WRONG_CANDIDATES:
        assert not module.target_gate(entity_id, title=title, file_name=title[5:]), (
            f"{entity_id} 的把关竟然放过了错误候选：{title}"
        )


def test_manifest_entries_pass_their_own_relevance_gate() -> None:
    """清单里每一张图都必须能通过**它所属实体**的把关。

    只看 Commons 侧的字段（标题 + 文件名），不看我们自己写的图注——
    否则图注里出现实体名就能「自我证明」，把关也就失效了。
    """
    module = _fetch_module()
    offenders: list = []
    for image in ImageLibrary(config.BASE_DIR).all():
        if not module.target_gate(
            image.entity_id, title=image.title, file_name=image.path.name
        ):
            offenders.append(f"{image.entity_id} ← {image.title}")
    assert not offenders, "以下图片通不过自身实体的相关性把关：\n  " + "\n  ".join(offenders)


def test_target_specs_cover_every_target_and_are_non_trivial() -> None:
    """每个目标实体都有把关条件，且必含词非空。"""
    module = _fetch_module()
    assert len(module.TARGET_SPECS) == len(module.TARGETS)
    for entity_id, (musts, _exclude) in module.TARGET_SPECS.items():
        assert musts, f"{entity_id} 没有必含词，等于不做把关"
        assert all(pattern.strip() for pattern in musts), f"{entity_id} 有空的必含词段"


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"artist": ""}, "作者"),
        ({"artist": "   "}, "作者"),
        ({"free": False, "license": "CC BY-NC 4.0"}, "许可"),
        ({"mime": "application/pdf"}, "格式"),
        ({"height": 0}, "尺寸"),
        ({"width": 3000, "height": 800}, "画幅"),
        ({"width": 500, "height": 700}, "分辨率"),
        ({}, None),
    ],
)
def test_candidate_rejection_rules(overrides: Dict[str, Any], expected: Any) -> None:
    """候选硬性条件逐条生效；全部满足时返回 None。"""
    reason = _fetch_module().candidate_rejection(_candidate(**overrides))
    if expected is None:
        assert reason is None, f"合格候选被误拦：{reason}"
    else:
        assert reason and expected in reason, f"期望因「{expected}」被拦，实际：{reason}"


def test_candidate_without_author_is_rejected_not_credited_blindly() -> None:
    """Commons 未登记作者的老照片一律不收——宁可缺图，也不写一条署不出作者的图。"""
    module = _fetch_module()
    # 这正是 `File:Huang Binhong.JPG` 的真实情况：有许可、无 Artist / Credit。
    reason = module.candidate_rejection(_candidate(artist="", license="Public domain"))
    assert reason is not None and "作者" in reason
