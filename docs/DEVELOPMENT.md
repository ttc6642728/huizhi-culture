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

### 2.2 图谱必须用 MultiDiGraph，而不是 DiGraph

**背景**：数据中存在同向平行边——「渐江 → 新安画派」同时有 `founder_of`（创立）与
`representative_of`（代表）两种关系。

**决策**：`src/graph/builder.py::build_graph` 使用 `nx.MultiDiGraph`。

**理由**：`nx.DiGraph` 会把同向平行边**静默合并**，导致关系数凭空少 1——
图谱与源数据不一致，属于数据失真。`tests/test_graph.py` 中不仅有
`test_graph_is_multidigraph`，还有 `test_parallel_edges_are_preserved`，
并直接从渲染产物里把 JS 数据载荷解析出来核对边数与数据完全一致（当前 180 条）。

**代价与处理**：多重图的连通性、最短路、聚类等算法在无向简单视图
（`analysis.to_undirected_simple`，折叠平行边）上计算；路径展示时若某段只有反向关系，
会标记 `reversed=True` 并渲染为 `A ←标签— B`，不伪装成同向。

### 2.3 PyVis 的离线自洽：不止是 `cdn_resources="in_line"`

PyVis 默认从 CDN 拉取 `vis-network` 的 JS/CSS，断网时图谱会白屏；
但**即使设置了 `cdn_resources="in_line"` 仍不够**——实测发现 `pyvis 0.3.2` 的
`templates/template.html` 第 41–51 行会**无条件**（不受 `cdn_resources` 参数控制）
引入 Bootstrap 5 的 CSS 与 JS：

```html
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0-beta3/dist/css/bootstrap.min.css" ...>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0-beta3/dist/js/bootstrap.bundle.min.js" ...>
```

**决策**：生成后统一清洗，并**把「无外部依赖」变成运行时可断言的约束**：

1. `cdn_resources="in_line"` 内联 `vis-network` 的 CSS/JS（约 690 KB）；
2. `strip_external_resources()` 移除模板遗留的外部 `<script src>` / `<link href>`；
3. 清洗后立即扫描，若仍存在外部引用（含 `//cdn...` 协议相对写法）则**抛错**，
   宁可报错也不交付一个「看着能用、断网就白屏」的页面；
4. `tighten_layout()` 再处理模板的另外两个问题：`heading` 为空时仍渲染的两处空
   `<h1>`（合计约 160 px 无效高度）与 iframe 内 `body` 的默认外边距。

**验证**：`tests/test_graph.py` 断言产物中不含任何外部 `script/link`、不含
`@import` / `@font-face` / 外部 `url()`，且 `len(html) > 400_000`（确认库确实被内联）。

### 2.4 用 `st.iframe` 而非已废弃的 `components.html`

Streamlit 1.66 起 `st.components.v1.html` 进入废弃流程（提示改用 `st.iframe`）。
`st.iframe` 的入参判定顺序为「Path 对象 → 绝对 URL → 本地文件 → 相对 URL → 原始 HTML」，
我们的 HTML 串既不以 `http(s)://` / `data:` 开头、也不含路径特征，会走 `srcdoc` 分支
直接内嵌，不产生任何网络请求。该假设由
`test_network_html_is_not_mistaken_for_a_url` 钉死——一旦产物被误判为 URL，
页面会变成加载一个不存在的地址，测试会立即失败。

### 2.5 Graphviz 不作为必需依赖

`pygraphviz` / `graphviz` 需要系统级二进制，跨平台安装成本高。本项目图谱渲染使用 PyVis，
布局算法由 NetworkX 提供，无需 Graphviz。

### 2.6 依赖安装使用非清华镜像

本机环境下 `pypi.org` 不可达，`pypi.tuna.tsinghua.edu.cn` 对 pip 客户端返回 `403 Forbidden`
（同一 URL 用 curl / urllib 访问均为 `200`）。经实测 **阿里云、腾讯云、华为云镜像对 pip 正常**。

因此：

```bat
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2.7 数据真实性约束

- 所有文化事实在写入 `data/*.json` 前需经检索核实，并在 `sources.json` 中登记来源 URL / 文献。
- 无法核实的条目**不写入**数据集。
- 图片仅使用自由授权（如 Wikimedia Commons 的 CC 协议）素材，并在 `assets/images/CREDITS.md` 中署名。

### 2.8 导航模型抽离为单一来源（P3）

**背景**：原本导航项与路由判定散落在 `app.py` 里。P3 引入**实体详情页**——它需要能被百科列表
点击跳转进入，但**不应出现在侧边栏**（否则用户会看到一个没有上下文的空详情页入口）。

**决策**：抽出 `src/ui/nav.py` 作为导航的唯一来源：

- `NAV_ITEMS`：侧边栏可见的入口（含未实现页面的阶段标注）。
- `HIDDEN_PAGES = {"detail": "explore"}`：映射「隐藏页 → 其归属的可见入口」，用于侧边栏高亮。
- 路由一律通过 `nav.resolve_route()`，侧边栏高亮通过 `nav.highlight_of()`。
- 页面间跳转用 `nav.goto(page, **params)`——**刻意不把跳转状态写进 URL query params**。

**为什么不写 query params**：Streamlit 的 `st.query_params` 是持久的。若详情页把
`?page=detail&entity=hongcun` 写进地址栏，用户点侧边栏「首页」后 URL 会残留旧参数，
刷新或前进后退时会被**拽回上一页**。因此跳转状态只存 `st.session_state`，用后即清
（`st.session_state.pop("graph_focus")` 这类一次性消费）。

**约束固化**：`tests/test_nav.py` 断言「每个 `NAV_ITEMS` 条目要么有对应模块文件，要么显式标注了
`phase`」，杜绝出现既无实现、又无阶段说明、点进去一片空白的假入口。

### 2.9 分类专色上移到设计系统（P3）

**背景**：11 个分类的专属配色原本定义在 `src/graph/visualize.py`（图谱专用）。P3 的百科卡片与
详情页也要按分类着色——但如果从界面层去 import `visualize`，就会把 PyVis 这个重依赖拖进样式层。

**决策**：把 `CATEGORY_COLORS` 上移到 `src/ui/theme.py`（与 `COLORS` 同处），
`visualize.py` 改为**反向** `from src.ui.theme import CATEGORY_COLORS`。

**收益**：同一个实体在图谱节点、百科卡片、详情页色条上**颜色完全一致**，
且配色定义只有一处。`tests/test_graph.py` 保留断言「11 个分类各有专属配色，不落到兜底色」。

### 2.10 图片经中转服务获取，并做成可降级（P3）

**背景**：P3 计划从 Wikimedia Commons 下载 CC 授权真实徽州图。实测本机对 Wikimedia 存在
**SNI 域名级阻断**（不是整体断网）：`commons.wikimedia.org` 与 `upload.wikimedia.org`
的 DNS 被污染到 `103.102.166.x`（非 Wikimedia 真实网段），直连 / 走代理 / 脱离沙箱
三种方式在 TCP 层均握手超时 `code=000`；而同一台机器上 `dumps.wikimedia.org`
（真实 IP `208.80.154.242`）返回 `200`，且用真实 IP + `--resolve` 覆盖 commons/upload 仍失败
——**证明是按域名（SNI）拦截，而非按 IP 或整体断网**。对照：`ihchina.cn`、`mirrors.aliyun.com`
正常（200 / 301），`github.com`、`api.openverse.org`、Wikipedia 全站不可达。

**决策**：改用**两个可达的中转服务**取回真实内容（内容仍来自 Wikimedia，授权与作者以 Commons API 为准）：

| 用途 | 中转 | 说明 |
|---|---|---|
| 元数据（文件名 / 许可 / 作者） | `api.microlink.io` | 服务端渲染把目标 URL 抓回，据此间接调用 Commons API（`action=query`）。免费额度约 15 次/日，需可续跑。 |
| 图片字节 | `wsrv.nl`（images.weserv.nl） | 开源图片代理/CDN，`?url=upload.wikimedia.org/...` 回源并缩放。回源 Wikimedia 时**上游会间歇 429**，需较长退避重试。 |

同时把「无图」做成一等公民的正常状态：

1. `src/data/images.py` 的 `ImageLibrary` 在**清单缺失 / JSON 损坏 / 图片文件丢失**三种情况下
   全部安全降级为空结果，绝不抛错中断页面；
2. 界面在无图时显示纯排版降级形态（不显示破图）；
3. `scripts/fetch_images.py` 支持 `--from-resolved` 续跑模式——检索配额用尽时，
   可依据已解析出的候选直接下载，无需重复消耗检索额度。

**踩过的两个坑（已修复）**：

- **URL 二次编码**：`upload_url_of()` 已对中文文件名做百分号编码，若再用 `urlencode`
  包一层会变成 `%E9 → %25E9`，导致中文名图片取不到；改为只拼接定值参数、url 原样透传。
- **清单覆盖**：早期 `write_manifest` 是覆盖写，分批续跑会把上一批已成功的图片抹掉；
  改为**按 `entity_id` 合并**。

**授权白名单**：仅接受 CC0 / CC BY / CC BY-SA / Public domain / GFDL，**主动拒绝 NC / ND**。
图注由人工**对照实际下载的图片内容**写定（例如「呈坎」「棠樾」两张是国保石碑而非村落全景，
图注即如实标注为“……全国重点文物保护单位碑”）。

**成果**：收录 11 张真实图片（西递、呈坎、唐模、棠樾、许村、渔梁、承志堂、屯溪、许国石坊、黄山、齐云山），
全部通过许可白名单校验，逐条登记于 `assets/images/manifest.json` 与 `CREDITS.md`。

---

## 三、模块职责

| 文件 | 职责 |
|---|---|
| `app.py` | 页面配置、注入设计系统、侧边栏导航、页面路由、页脚 |
| `src/config.py` | 路径常量、`.env` 加载、问答后端探测与降级判断 |
| `src/ui/theme.py` | 设计令牌（配色 / 字体 / 圆角 / 间距）、11 分类专色与全局 CSS 注入 |
| `src/ui/components.py` | 卡片、面包屑、分类标签、关系行、来源行、图片图注、区块标题、空/错状态等 HTML 组件 |
| `src/ui/nav.py` | 导航模型唯一来源：可见入口、隐藏页归属、路由解析、高亮判定、跳转 |
| `src/ui/datastore.py` | 界面共享数据入口，缓存 `repository()` 与 `images()` |
| `src/ui/pages/*.py` | 各页面渲染入口，统一导出 `render()` |
| `src/data/loader.py` | 读取并校验实体 / 关系 / 来源 JSON，给出可读的错误信息 |
| `src/data/repository.py` | 搜索、分类筛选、详情查询、邻居查询、子图与路径 |
| `src/data/images.py` | 实体图片库与署名；清单/文件缺失时安全降级 |
| `src/graph/builder.py` | 构建 `MultiDiGraph`（实体为节点、关系为边，保留同向平行边）；分类/关系类型筛选、ego 子图 |
| `src/graph/analysis.py` | 结构统计、度数/介数中心性排名、连通分量、最短关联路径、模块度聚类 |
| `src/graph/visualize.py` | 生成离线自洽的交互式 HTML（内联资源、资源清洗、图例、路径链条） |
| `src/graph/runtime.py` | 图谱与数据集的界面运行时缓存（保持上述三模块不依赖 Streamlit） |
| `src/qa/retriever.py` | jieba 分词 + BM25 资料检索，返回带来源的片段 |
| `src/qa/prompt.py` | 构造带编号引用的提示词，约束模型只依据资料作答 |
| `src/qa/engine.py` | 三层后端实现与自动降级、异常与超时处理 |
| `src/agent/workflow.py` | 多步工作流编排与步骤日志 |
| `scripts/fetch_images.py` | 从 Wikimedia Commons 抓取 CC 授权图片（许可白名单 + 检索/排除正则过滤） |

---

## 四、数据模型

```
data/entities.json
  ├─ categories[]  { id, name, order, description }
  └─ entities[]    { id, name, category, aliases[], summary, description,
                     attributes{}, source_ids[], image? }

data/relations.json
  ├─ relation_types[] { id, name, inverse_name, description }
  └─ relations[]      { id, source, target, type, label, description?, source_ids[] }

data/sources.json
  └─ sources[]  { id, type, title, publisher, url, accessed, note }
```

约定：

- `entities.id`、`relations.id`、`sources.id` 全局唯一，采用小写英文与下划线。
- 每条实体与每条关系**必须**带非空 `source_ids`，且引用的 id 必须在 `sources.json` 中存在。
- 关系方向固定为 `source → target`；`relation_types[].inverse_name` 用于在界面上以当前实体为主语反向展示。
- 校验保证 `(source, target, type)` 三元组唯一，但**同一对实体在同一方向上可以存在多种关系**
  （如「渐江 → 新安画派」同时是 `founder_of` 与 `representative_of`），
  因此图谱建模必须使用 `MultiDiGraph`，详见 2.2。
- `attributes` 为字符串键值对，用于结构化展示；关键事实（年份、批次、数量）优先放进 `attributes` 以便测试断言。
- 不做「孤立实体」：校验要求每个实体至少有一条关系。

校验入口：`src/data/loader.py::validate_dataset`（11 类检查），CLI 为 `scripts/validate_data.py`。

---

## 五、界面设计系统

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

## 六、开发记录

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

### P1 数据层（已完成）

**新增文件**

```
data/entities.json        文化实体库（90 个实体 / 11 个分类）
data/relations.json       实体关系库（150 条关系 / 10 种关系类型）
data/sources.json         参考资料来源库（28 条，含 URL 与访问日期）
src/data/loader.py        数据模型、加载与 11 类校验
src/data/repository.py    检索、筛选、详情、邻居、子图、路径、统计
scripts/validate_data.py  数据校验 CLI
tests/test_data_integrity.py   真实数据文件校验（14 项）
tests/test_loader.py           加载与校验边界（20 项）
tests/test_repository.py       查询能力（25 项）
docs/DATA_SOURCES.md      数据来源与核实说明
```

**分类构成**

| 分类 | 实体数 | 分类 | 实体数 |
|---|---|---|---|
| 古村落 | 10 | 民俗节庆 | 6 |
| 徽派建筑 | 11 | 徽菜饮食 | 8 |
| 非物质文化遗产 | 9 | 宗族与文教 | 7 |
| 历史名人 | 14 | 文献典籍 | 4 |
| 徽商 | 7 | 山川地域 | 5 |
| 传统工艺与艺术 | 9 | | |

**分类维度的两处调整（需确认）**

1. **新增「山川地域」**：原定十类中无地理维度，但黄山、新安江是徽州文化不可分割的地理基底，故新增此类（5 个实体）。
2. **两处命名微调**：「传统工艺」→「传统工艺与艺术」（以容纳新安画派）；「宗族与教育」→「宗族与文教」（以容纳新安理学、新安医学）。

两处调整均为**在既定维度上的扩充**，不改变原有分类的覆盖范围。如需严格保持十类，可将「山川地域」并入「古村落」并将另两类改回原名。

**数据来源策略**

- 优先使用 UNESCO 世界遗产中心（A 级）、国务院/文化和旅游部/中国非物质文化遗产网（B 级）、地方政府与官方媒体（C 级）。
- 百科类来源仅在 A–C 未覆盖时作补充，并在 `sources.json` 的 `note` 中标注其权威性较低。
- 关键事实（世界遗产编号与年份、非遗批次与申报地区、牌坊数量、人物评选名次）已在测试中设断言，被误改会立即失败。
- 无法核实的内容不写入数据集。详见 `docs/DATA_SOURCES.md`。

**首页增强**

`src/ui/pages/home.py` 新增「文化数据概况」板块：由程序实时读取数据集计算实体/关系/来源/分类数量与分类分布，
并在数据加载失败时显示错误状态、存在孤立实体时显示告警。

**验证**

- `pytest`：72 项全部通过（P0 的 13 项 + P1 的 59 项）。
- `python scripts/validate_data.py`：数据校验全部通过，无孤立实体。
- `AppTest` 冒烟测试覆盖首页数据板块渲染，无异常。

**遗留问题**

- 图片素材尚未下载（计划在 P3 阶段处理）。
- 90 个实体略高于原计划的 60–80，已确认图谱无孤立节点。

**下一阶段（P2）**

实现 `src/graph/builder.py`（NetworkX 建图）、`analysis.py`（中心度、连通分量、最短路径、整体统计）、
`visualize.py`（PyVis 交互图，`cdn_resources="in_line"` 保证离线可用，支持聚焦与高亮），
接入知识图谱页面，配套 `tests/test_graph.py`。

### P2 知识图谱（已完成）

**新增文件**

```
src/graph/builder.py          多重有向图建模、筛选、ego 子图（不依赖 Streamlit）
src/graph/analysis.py         结构统计、中心性排名、连通分量、最短关联路径、聚类
src/graph/visualize.py        离线自洽的交互式 HTML、资源清洗、图例、路径链条
src/graph/runtime.py          界面运行时缓存（st.cache_resource 适配层）
src/ui/pages/graph.py         知识图谱页
scripts/graph_report.py       图谱验证报告 CLI（支持 --focus / --path / --export）
tests/test_graph.py           图谱测试（60 项）
src/ui/theme.py（修改）        新增图例、路径链条、排名表、步骤列表样式
src/ui/components.py（修改）   新增 table_html；card_html 补充 flat 参数
src/ui/pages/home.py（修改）   新增「知识图谱概况」，模块进度表补入图谱模块
app.py（修改）                侧边栏版本说明更新为已完成阶段
```

**图谱结构（实时计算结果）**

| 指标 | 值 |
|---|---|
| 节点 / 边 | 90 / 150（与数据完全一致，平行边未丢失） |
| 图类型 | `MultiDiGraph` |
| 连通分量 | 1（全部 90 个实体同属一个关联网络） |
| 网络直径 | 6 |
| 平均最短关联距离 | 2.939 |
| 图密度 | 0.0367 |
| 孤立实体 | 0 |

**核心枢纽**：度数最高为「徽州」（41 条，均为指向它的 `located_in`），与「徽商」（16）、
「徽州民居」（11）、「徽菜」（11）。介数中心性最高同样是「徽州」（0.7488），
其次为「徽菜」（0.2407）、「徽商」（0.1442）——度数衡量「关系多」，介数衡量「跨领域桥梁作用」。

**文化聚类**：基于模块度优化的社区发现得到 8 个聚类，与徽州文化的实际板块高度吻合——
建筑聚落群（宏村、西递、天井、马头墙…）、名人工艺群、徽商与医学、牌坊与宗族、
徽菜、理学与书院、民俗演艺、文房四宝。该结果标注为**探索性分析**，界面与文档均不作定论。

**知识图谱页功能**

| 区块 | 内容 |
|---|---|
| 结构指标 | 节点、边、连通分量、密度、平均最短关联、直径、度数分布、孤立实体 |
| 图谱筛选与布局 | 按分类 / 关系类型多选筛选；聚焦实体 + 半径 1–3；力导布局开关；关系标签开关 |
| 交互画布 | 拖拽平移、滚轮缩放、悬停查看简介与来源数、点击节点高亮邻居、按分类着色、度数决定节点大小 |
| 聚焦实体 | 该实体的出入关系明细（方向 / 类型 / 说明 / 来源数）+ 关联子图 |
| 关联路径 | 任意两实体的最短关联线路链条、逐段关系明细、等长备选线路、线路单独可视化 |
| 核心枢纽 | 度数排名、介数排名、关系类型分布 |
| 文化聚类 | 每个聚类的规模、内聚度、涉及分类与成员标签 |

**筛选后的空态处理**：分类之间往往通过少数枢纽实体相连，因此单独筛选「古村落」时
会出现「10 个实体、0 条关系」。界面在此情形下显示空状态并解释原因，
不渲染一堆游离圆点冒充图谱。

**可视化产物的实测数据**

| 项目 | 值 |
|---|---|
| 单张全图 HTML | 约 830 KB（其中约 690 KB 为内联的 vis-network CSS/JS） |
| 生成耗时 | 约 0.06 s（有缓存） |
| 外部资源引用 | 0 |
| 外部 `url()` / `@import` / `@font-face` | 0 |
| 布局随机种子 | 固定 42（同一张图初始布局可复现） |

**验证**

- `pytest`：133 项全部通过（P0 的 13 项 + P1 的 59 项 + P2 的 61 项），无警告。
- `python scripts/graph_report.py`：输出「全部检查通过」（建图保真 + 离线自洽）。
- `python scripts/graph_report.py --export outputs/huizhou-knowledge-graph.html`：
  导出可独立用浏览器打开的交互式图谱（约 830 KB，单文件，无需服务器与网络）。

**遗留问题**

- 仍存在 0 个孤立实体，但「徽州」的 41 条关系全部为入边、无出边，属于数据特征而非缺陷；
  若后续希望图谱在方向上更均衡，可为其补充部分出向关系。
- 图片素材仍未下载（计划在 P3 阶段处理）。
- 图谱页在实体数量大幅增长（例如超过 300 节点）时，一次性渲染全图会偏重；
  届时需要引入按分类分片或服务端预布局。当前 90 节点规模无需处理。

**下一阶段（P3）**

实现文化百科列表页（关键词搜索 + 分类筛选）、实体详情页（结构化属性、真实关联关系、
可点击来源）、首页文化探索区，并下载自由授权的徽州建筑图片来源，配套 `assets/images/CREDITS.md`。

### P3 浏览体验（已完成）

**新增文件**

```
data/entities.json        扩充至 96 个实体（新增「一府六县」6 个县份）
data/relations.json       扩充至 180 条关系 / 11 种关系类型（新增 declared_in 申报地区）
data/sources.json         扩充至 33 条来源
src/data/images.py        实体图片库与署名，缺失时安全降级
src/ui/nav.py             导航模型唯一来源（可见入口 / 隐藏页 / 路由 / 高亮 / 跳转）
src/ui/datastore.py       界面共享数据入口（缓存 repository 与 images）
src/ui/pages/explore.py   文化百科页（加权检索 + 分类快捷筛选 + 排序 + 分页 + 空状态）
src/ui/pages/detail.py    实体详情页（属性表 + 方向分组的关联关系 + 可点击来源 + 图片 + 跳图谱）
scripts/fetch_images.py   Commons 图片抓取脚本（许可白名单 + 检索/排除正则 + 通道探测）
assets/images/README.md   图片不可用时的说明、复现命令与署名要求
tests/test_nav.py              导航模型测试（16 项）
tests/test_image_library.py    图片库降级测试（8 项）
tests/test_components.py       组件渲染测试（12 项）
src/ui/theme.py（修改）         新增 11 分类专色、面包屑/卡片/详情/关系/来源/图注样式
src/ui/components.py（修改）    新增 crumb / category_chip / entity_card / detail_head /
                               relation_row / source_row / figure_caption / count_line / group_title
src/graph/visualize.py（修改）  分类专色改为复用 theme（消除重复定义）
src/ui/pages/home.py（修改）    P3 模块进度 + 快捷入口
src/ui/pages/graph.py（修改）   selectbox 加稳定 key；支持从详情页跳转时预置聚焦
app.py（修改）                  路由改用 nav.resolve_route / highlight_of
```

**数据扩充（用户确认后执行）**

用户指出「徽州」的 41 条关系全部为入边、无出边，「可以补充几条出向关系」。
核查后确认这是**真实的建模缺口**——徽州作为一个地域概念，本应「包含」其下辖县份，
但数据里没有任何实体承载这一层级。因此不是硬加边凑数，而是补齐缺失的概念层：

| 改动 | 内容 | 结果 |
|---|---|---|
| 新增 6 个县份实体 | 歙县 / 休宁 / 黟县 / 祁门 / 绩溪 / 婺源（归类「山川地域」） | 实体 90 → **96** |
| 新增 `composed_of`（包含组成） | `徽州 → 六县` 共 6 条 | **徽州首次获得出向关系** |
| 新增 `located_in` | 11 个村落 / 名山归入所属县 | 为县份建立真实下级挂载 |
| 新增 `native_of`（籍贯） | 胡适 / 胡雪岩 → 绩溪，詹天佑 → 婺源 | 人物与县份双向可达 |
| 新增关系类型 `declared_in`（申报地区） | 11 条非遗项目 → 申报地区 | 关系类型 10 → **11** |

**关系数 150 → 180**。校验：96 实体 / 180 关系 / 33 来源 / 11 分类 / 11 关系类型 / **无孤立节点**。
「徽州」度数 41 → **47**（出 6 / 入 41），方向不再失衡。
该约束已固化为测试 `test_huizhou_has_outgoing_relations`——若再退回纯汇点状态会立即失败。

**文化百科页（`explore.py`）**

| 区块 | 内容 |
|---|---|
| 检索 | 加权关键词检索：名称 100 / 别名 90 / 摘要 30 / 正文 15 / 属性 10 分，多词命中累加 |
| 分类筛选 | 11 个分类快捷按钮，**带真实计数**（如「古村落 10」），可叠加「全部」 |
| 排序 | 默认（检索相关度） / 按名称 / 按关联数 |
| 分页 | 每页 12 条，3 列卡片网格 |
| 空状态 | 无匹配时显示明确空状态并提示可尝试的分类，不渲染空白网格 |

**实体详情页（`detail.py`）**

| 区块 | 内容 |
|---|---|
| 头部 | 面包屑、名称、分类标签、别名 |
| 属性表 | 结构化展示 `attributes`（年份、批次、数量等） |
| 正文 | 实体 `description` |
| 关联关系 | **按方向分组**：「从本实体出发」用 `→`，「指向本实体」用 `←` 并采用关系的 `inverse_name` |
| 参考资料 | 每条来源可点击跳转（标题 + 出版方 + 访问日期） |
| 图片 | 有图时展示并署名；无图时整块省略（不显示破图） |
| 跳转 | 「在图谱中查看」——真实跳转并聚焦该实体；未选择实体 / 未知 id 显示对应错误状态 |

**方向不造假**：详情页展示反向关系时，用关系的 `inverse_name`（如反向的「位于」显示为
「境内有…」），而不是把箭头反过来仍用原标签。`tests/test_smoke.py` 中的
`test_detail_page_relation_direction_is_honest` 专门断言这一点。

**图谱指标（P3 后实时计算）**

| 指标 | P2 | P3 |
|---|---|---|
| 节点 / 边 | 90 / 150 | **96 / 180**（与数据完全一致，平行边未丢失） |
| 连通分量 | 1 | 1（全部 96 个实体同一网络） |
| 网络直径 | 6 | 6 |
| 平均最短关联距离 | 2.939 | **2.826** |
| 图密度 | 0.0367 | **0.0388** |
| 平均度 / 最大度 | 3.33 / 41 | **3.75 / 47** |
| 孤立实体 | 0 | 0 |
| 度数首位 | 徽州 41（纯入边） | **徽州 47（出 6 / 入 41）** |
| 介数首位 | 徽州 0.7488 | **徽州 0.7545** |

**验证**

- `pytest`：**178 个测试函数 / 192 个用例全部通过**（P0–P3 累计），无警告。
- `python scripts/validate_data.py`：数据校验全部通过，无孤立实体。
- `python scripts/graph_report.py`：「全部检查通过」（建图保真 + 离线自洽）。
- `AppTest` 冒烟测试含**真实点击按钮验证跳转**（不是断言文字存在而已）。
- 应用启动：`/` = 200、`/_stcore/health` = 200。

**遗留问题**

- **图片素材已收录 11 张**（经 Microlink + wsrv 中转取得，SNI 域名级阻断见 2.10）。
  检索侧受 Microlink 免费额度（约 15 次/日）限制，尚未覆盖全部 29 个目标实体；
  其余实体在额度恢复后重跑 `python scripts/fetch_images.py` 即可补齐，
  也可用 `--from-resolved` 从已解析候选续跑。
- 当前规模（96 节点 / 180 边）下单张全图 HTML 约 830 KB，一次性渲染仍流畅；
  若实体超过 300 个需引入按分类分片或服务端预布局。

**下一阶段（P4）**

实现检索与 AI 问答：`src/qa/retriever.py`（jieba + BM25，返回带来源片段）、
`src/qa/prompt.py`（带编号引用的提示词，约束模型只依据资料作答）、
`src/qa/engine.py`（三层后端与自动降级）、`src/qa/errors.py`，
接入问答页面并配套测试。回答须基于检索资料、可溯源。
