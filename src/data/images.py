"""实体图片库。

读取 ``assets/images/manifest.json``（由 ``scripts/fetch_images.py`` 生成），
为实体提供本地图片路径与**可核查的署名信息**。

设计原则
--------
- **优雅降级**：清单缺失、条目损坏、图片文件丢失都不会让应用崩溃——
  界面按「该实体没有图」处理，回退到纯排版展示，绝不显示占位图冒充真实图片。
- **署名随图走**：每张图的作者、许可与来源页面都在清单里，界面展示时必须一并给出。
- **不依赖网络**：图片全部为本地文件，离线可用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: 默认清单位置（相对项目根目录）
MANIFEST_REL = Path("assets") / "images" / "manifest.json"


@dataclass(frozen=True)
class EntityImage:
    """一张已下载的实体图片及其署名信息。"""

    entity_id: str
    path: Path
    caption: str
    title: str
    artist: str
    license: str
    license_url: str
    source_url: str
    width: int
    height: int

    @property
    def exists(self) -> bool:
        """图片文件是否真的在磁盘上。"""
        return self.path.is_file()

    @property
    def credit(self) -> str:
        """一行式署名：``作者 · 许可``；作者缺失时如实标注。"""
        who = self.artist or "作者见来源页面"
        return f"{who} · {self.license}" if self.license else who

    @property
    def rel_path(self) -> str:
        """相对项目根的 POSIX 路径，用于文档与调试输出。"""
        return f"assets/images/{self.path.name}"


class ImageLibrary:
    """图片清单的只读视图。

    Args:
        root: 项目根目录。
        manifest_path: 清单路径；默认 ``assets/images/manifest.json``。

    Notes:
        清单不存在时是**正常状态**（尚未抓取图片），不是错误：
        :attr:`available` 为 ``False``，所有查询返回空。
    """

    def __init__(self, root: Path, manifest_path: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.manifest_path = Path(manifest_path) if manifest_path else self.root / MANIFEST_REL
        self._images: Dict[str, EntityImage] = {}
        self._issues: List[str] = []
        self._loaded = False
        self._available = False
        self._load()

    # ------------------------------------------------------------------
    # 载入
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.manifest_path.is_file():
            self._issues.append(f"未找到图片清单：{self.manifest_path}（视为「暂无图片」）")
            return

        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._issues.append(f"图片清单无法解析：{exc}")
            return

        entries = data.get("images", []) if isinstance(data, dict) else []
        if not isinstance(entries, list):
            self._issues.append("图片清单 images 字段不是数组")
            return

        self._available = True
        for raw in entries:
            if not isinstance(raw, dict):
                self._issues.append("图片清单存在非对象条目，已跳过")
                continue
            entity_id = str(raw.get("entity_id", "")).strip()
            file_name = str(raw.get("file", "")).strip()
            if not entity_id or not file_name:
                self._issues.append("图片清单条目缺少 entity_id 或 file，已跳过")
                continue
            image = EntityImage(
                entity_id=entity_id,
                path=self.manifest_path.parent / file_name,
                caption=str(raw.get("caption", "")),
                title=str(raw.get("title", "")),
                artist=str(raw.get("artist", "")),
                license=str(raw.get("license", "")),
                license_url=str(raw.get("license_url", "")),
                source_url=str(raw.get("source_url", "")),
                width=int(raw.get("width", 0) or 0),
                height=int(raw.get("height", 0) or 0),
            )
            if not image.exists:
                self._issues.append(f"清单登记的图片文件缺失：{file_name}")
                continue
            self._images[entity_id] = image

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """清单是否存在且可读。"""
        return self._available

    @property
    def issues(self) -> Tuple[str, ...]:
        """载入过程中的问题说明（供「关于」页或调试输出使用）。"""
        return tuple(self._issues)

    def __len__(self) -> int:
        return len(self._images)

    def get(self, entity_id: str) -> Optional[EntityImage]:
        """取某实体的图片；没有则返回 ``None``。"""
        return self._images.get(entity_id)

    def has(self, entity_id: str) -> bool:
        return entity_id in self._images

    def ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._images))

    def all(self) -> Tuple[EntityImage, ...]:
        return tuple(self._images[k] for k in sorted(self._images))


def load_image_library(root: Path) -> ImageLibrary:
    """载入图片库（便捷入口）。"""
    return ImageLibrary(root)


__all__ = ["EntityImage", "ImageLibrary", "load_image_library", "MANIFEST_REL"]
