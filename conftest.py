"""pytest 全局配置。

在项目根目录放置 conftest.py，使 pytest 把项目根目录加入 ``sys.path``，
从而测试中可以直接 ``import src.*``（无需安装为包）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
