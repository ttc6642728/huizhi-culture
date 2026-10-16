# 开发文档 · Huizhou Culture Explorer

本文件记录项目的架构决策、环境约束与各阶段开发记录，供后续维护与答辩说明使用。

---

## 一、架构总览

```
                 app.py（Streamlit 入口：配置 / 主题 / 导航 / 路由）
                                  │
     ┌──────────────┬─────────────┼─────────────┬──────────────┐
     ▼              ▼             ▼             ▼              ▼
  ui/pages      ui/theme      src/data       src/graph      src/qa
  页面渲染      设计系统    加载·校验·查询   建模·分析·可视化  检索·问答
     │                                                        │
     └──────────────────────► src/agent/workflow ◄─────────────┘
                          可追踪的多步问答工作流
```

分层原则：

- **数据层（src/data）** 只负责把 JSON 变成可查询的 Python 对象，不含任何界面代码。
- **图谱层（src/graph）** 只依赖 NetworkX 与数据层，输出图对象、统计结果与 HTML。
- **问答层（src/qa）** 只依赖数据层与检索结果，后端可插拔，不直接操作界面。
- **智能体层（src/agent）** 编排「意图 → 实体 → 检索 → 生成 → 溯源」，产出可追踪的步骤记录。
- **界面层（src/ui）** 只做展示与交互，业务逻辑一律下沉到上面的层，便于单测。

---

## 二、关键决策

### 2.1 问答后端采用三层自动降级

**背景**：课程要求优先使用 Dify，但本机网络下 `dify.ai` 云端不可达；自建 Dify 需要 Docker 与模型服务，
不能保证在所有环境（含答辩现场、离线场景）都可运行。

**决策**：把问答能力抽象为可插拔后端，按优先级自动降级：

| 优先级 | 后端 | 触发条件 | 特点 |
|---|---|---|---|
| 1 | `DifyBackend` | 配置了 `DIFY_BASE_URL` + `DIFY_API_KEY` | 使用 Dify 知识库检索 / 工作流 |
| 2 | `LLMBackend` | 配置了 `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` | 任意 OpenAI 兼容接口 |
| 3 | `LocalBackend` | 以上均未配置，或 `QA_FORCE_LOCAL=true` | **纯离线**：BM25 检索 + 抽取式答案 + 强制引用 |

**理由**：既满足「优先 Dify」的要求，又保证任何环境下都能演示完整问答链路，且**不会把本地检索式包装成
大模型能力**——界面会明确显示当前生效的后端。

### 2.2 PyVis 使用内联资源模式

PyVis 默认从 CDN 拉取 `vis-network` 的 JS/CSS，断网时图谱会白屏。
因此在 `src/graph/visualize.py` 中统一使用 `cdn_resources="in_line"`，把前端资源内联进生成的 HTML，
保证**离线可用**。

### 2.3 Graphviz 不作为必需依赖

`pygraphviz` / `graphviz` 需要系统级二进制，跨平台安装成本高。本项目图谱渲染使用 PyVis，
布局算法由 NetworkX 提供，无需 Graphviz。

### 2.4 依赖安装使用非清华镜像

本机环境下 `pypi.org` 不可达，`pypi.tuna.tsinghua.edu.cn` 对 pip 客户端返回 `403 Forbidden`
（同一 URL 用 curl / urllib 访问均为 `200`）。经实测 **阿里云、腾讯云、华为云镜像对 pip 正常**。

因此：

```bat
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2.5 数据真实性约束

- 所有文化事实在写入 `data/*.json` 前需经检索核实，并在 `sources.json` 中登记来源 URL / 文献。
- 无法核实的条目**不写入**数据集。
- 图片仅使用自由授权（如 Wikimedia Commons 的 CC 协议）素材，并在 `assets/images/CREDITS.md` 中署名。

---

## 三、模块职责

| 文件 | 职责 |
|---|---|
| `app.py` | 页面配置、注入设计系统、侧边栏导航、页面路由、页脚 |
| `src/config.py` | 路径常量、`.env` 加载、问答后端探测与降级判断 |
| `src/ui/theme.py` | 设计令牌（配色 / 字体 / 圆角 / 间距）与全局 CSS 注入 |
| `src/ui/components.py` | 卡片、标签、区块标题、空状态、错误状态、引用条目等 HTML 组件 |
| `src/ui/pages/*.py` | 各页面渲染入口，统一导出 `render()` |
| `src/data/loader.py` | 读取并校验实体 / 关系 / 来源 JSON，给出可读的错误信息 |
| `src/data/repository.py` | 搜索、分类筛选、详情查询、邻居查询、子图与路径 |
| `src/graph/builder.py` | 由数据构建 NetworkX 图（实体为节点、关系为边） |
| `src/graph/analysis.py` | 中心度、连通分量、最短路径、整体统计 |
| `src/graph/visualize.py` | 生成可交互 HTML 图谱（离线内联资源、支持聚焦与高亮） |
| `src/qa/retriever.py` | jieba 分词 + BM25 资料检索，返回带来源的片段 |
| `src/qa/prompt.py` | 构造带编号引用的提示词，约束模型只依据资料作答 |
| `src/qa/engine.py` | 三层后端实现与自动降级、异常与超时处理 |
| `src/agent/workflow.py` | 多步工作流编排与步骤日志 |

---

## 四、界面设计系统

| 令牌 | 值 | 用途 |
|---|---|---|
| `bg` | `#FAF7F2` | 米白主背景 |
| `bg_soft` | `#F3EEE6` | 次级背景、侧边栏 |
| `surface` | `#FFFFFF` | 卡片表面 |
| `ink` | `#22201C` | 深墨色主文字 |
| `ink_soft` | `#57534A` | 次级文字 |
| `ink_mute` | `#8C867A` | 辅助说明 |
| `line` | `#E5DED2` | 常规边框 |
| `cinnabar` | `#B23A2F` | 朱砂点缀（选中、强调、引用编号） |
| `stone_dark` / `stone` / `stone_light` | `#3B3935` / `#7C786F` / `#D8D3C9` | 徽州建筑黑白灰 |

标题使用衬线字体（Noto Serif SC → 宋体回退），正文使用无衬线字体，全部为系统字体，不依赖外链。

---

## 五、开发记录

### P0 脚手架与环境（已完成）

**新增文件**

```
.gitignore  .env.example  requirements.txt  pytest.ini  README.md  app.py
src/__init__.py  src/config.py
src/data/__init__.py  src/graph/__init__.py  src/qa/__init__.py  src/agent/__init__.py
src/ui/__init__.py  src/ui/theme.py  src/ui/components.py
src/ui/pages/__init__.py  src/ui/pages/home.py
docs/DEVELOPMENT.md
```

**环境实测结果**

| 项目 | 结果 |
|---|---|
| 工作目录 | `E:\huizhi-culture` 初始为空，非 Git 仓库 |
| Python | 3.13.14（托管）/ 3.12.10（系统） |
| 虚拟环境 | 项目内 `.venv`（Python 3.13.14） |
| pip | 26.1.2 |
| pypi.org | 不可达 |
| 清华镜像 | 对 curl/urllib 200，对 pip **403** |
| 阿里 / 腾讯 / 华为镜像 | 对 pip 正常 |
| `dify.ai` | 不可达 |
| `api.deepseek.com` | 可达（需 Key） |
| `commons.wikimedia.org` | 可达 |

**已实现**

- 设计系统与全局样式注入（`src/ui/theme.py`）
- 可复用 HTML 组件（`src/ui/components.py`）
- 基于 `importlib` 的页面路由，未实现页面如实显示所处阶段
- 问答后端探测与降级逻辑（`src/config.py`）
- 首页实时环境自检：依赖安装情况、数据文件状态、模块交付进度、当前后端

**验证**

- `python -m compileall app.py src` 通过（无语法错误）
- Streamlit 启动冒烟测试见 `docs/TEST_REPORT.md`

**遗留问题**

- 文化数据、图谱、问答链路均未接入，界面已用「待开发」状态如实标注。
- 图片素材尚未下载。

**下一阶段（P1）**

编写 `data/entities.json`、`relations.json`、`sources.json`（60–80 实体、8–10 分类、来源可核查），
实现 `src/data/loader.py` 与 `repository.py`，配套 `scripts/validate_data.py` 与单元测试。
