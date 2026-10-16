"""图片库测试：清单缺失/损坏/文件丢失时的行为，以及署名信息的完整性。

图片是「有则显示、无则不影响」的增强内容，因此这里重点验证**降级路径**：
任何异常都不得让应用崩溃，也不得凭空造出一张图。
"""

from __future__ import annotations

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
