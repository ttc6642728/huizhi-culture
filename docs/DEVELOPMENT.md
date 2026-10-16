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

### 2.11 检索用「BM25 + 精确命中加成」，而不是纯 BM25（P4）

**背景**：中文短查询里有两类极端情况，标准 BM25 都排不好：
「宏村」这类专名只出现一两次，IDF 高但词频低，得分被词频饱和项压住；
「徽州」这类词出现在 94/96 份资料里，IDF 只有 **0.026**，几乎无法区分任何文档。

**决策**：`BM25 得分 + 命中加成`，加成按命中位置分三档：
标题完全等于查询词（`EXACT_TITLE_BONUS = 9.0`）> 命中标题（4.0）> 命中别名（3.5）> 命中正文（0.9）。

**效果**：修前「徽州」与「徽州婚俗」得分相差 0.0008，实体本身排不到首位；
修后「徽州」稳定居首，同时「宏村」「西递」「马头墙」「程大位」等查询仍各自命中自己。

**另一处关键设计：关系叙述必须进索引**。每份资料的正文里包含一句按「关系读法」分组的叙述
（例如 `位于：黟县；包含组成：歙县、休宁…`，入向关系用 `inverse_name` 读），
否则「宏村属于哪个县」这类问题只能匹配到实体简介里的词，检索不到关系层面的信息。

### 2.12 降级「可见」，而不是「静默」（P4）

三层后端（Dify → 大模型 → 本地检索式）自动降级是既定需求，但**降级本身必须被用户看到**：

- `QAResult.degradations` 逐条记录「哪个后端被跳过、原因是什么」，问答页原样展示。
- 后端**可用性探测自身抛异常**也算不可用（`_probe()` 统一兜底）。
  这一点是测试逼出来的：`availability()` 原本有保护而 `ask()` 没有，
  一个探测失败的后端会让整个问答崩掉——补上后由 `test_availability_never_raises` 钉死。
- 模型若引用了**不存在的资料编号**，会被解析出来、渲染成划掉的红色徽标并明确提示，
  而不是悄悄丢弃。宁可暴露模型的错误，也不让用户以为引用是可信的。
- 未被引用的资料同样列出（标注「未被回答引用」），检索质量可以被直接检查。

### 2.13 问答测试必须能离线跑（P4）

自动化测试**不允许依赖外部 API**：既不可复现，又会消耗真实额度。
做法有两条：

1. **注入假后端**：`QAEngine(repo, backends=[FakeBackend(...)])`，
   降级链、空回答、异常翻译等分支全覆盖；HTTP 层通过注入 `post` 参数替换，
   用 `FakeResponse` 校验请求 URL / 鉴权头 / 提示词结构。
2. **强制本地后端**：问答页的 AppTest 用例设置 `QA_FORCE_LOCAL=1`，
   引擎只走本地检索式路径，页面交互（点击示例按钮、提问、清空）仍被真实执行。

因此 `pytest` 全程不联网；真实大模型联调单独手动执行，结果记录在测试报告中，
**不混进自动化测试**。

### 2.14 工作流必须复用问答链路，而不是另起一套（P5）

**背景**：P5 要交付「检索 → 依据资料作答 → 自我核查 → 输出」的可追踪工作流，
最省事的写法是另写一份检索与作答代码。但那样会出现两套实现：
同一个问题在「AI 问答」页与工作流里得到不同结果，日后改一处漏一处。

**决策**：把 `QAEngine.ask()` 拆成两个公开方法，工作流直接复用它们：

```python
def ask(self, question):                 # 组合式入口（问答页用）
    text = validate_question(question)
    passages = self._retriever.retrieve(text, top_k=self._top_k)
    return self.answer_from(text, passages, started=...)

def answer_from(self, question, passages, *, directive="", backends=None, started=None):
    ...   # 在「已经检索好的资料」上跑降级链
```

于是工作流与问答页**共用同一条作答链路、同一套引用溯源逻辑**，
区别只在于工作流把「检索」与「作答」当成两个可分别记录耗时与结果的步骤。

**兼容性约束**：`answer_from` 在 `directive` 为空时**只用两个位置参数**调用后端
（`backend.answer(question, passages)`），只有纠正重试才传 `directive=`。
这样既有的假后端与旧式实现不需要改签名；该行为由
`test_backend_protocol_without_directive_still_works` 钉死。

### 2.15 自我核查用程序判定，不用模型自评（P5）

**背景**：「让模型检查自己刚才的回答」听起来很智能体，但结论不可复现、无法测试，
而且模型倾向于说「我的回答没有问题」。

**决策**：核查项全部是**程序可判定**的硬条件（`src/agent/workflow.py::verify_answer`）：

| 核查项 | 判定方式 | 未通过的含义 |
|---|---|---|
| 回答非空 | 字符串长度 | 后端返回了空内容 |
| 标注了来源编号 | 解析出的引用数 > 0 | 回答不可溯源，属硬失败 |
| 引用编号均指向真实资料 | 与资料表比对，`invalid_citations` 为空 | 模型编造了编号 |
| 每条引用都可核查 | 每条引用的资料都有登记来源 | 引用落到无来源资料上 |
| 检索资料被有效利用 | 被引用资料占比 ≥ 50% | 属**警告**：可能检索偏了，不致命 |
| 未发生后端降级 | `QAResult.degraded` 为假 | 属**警告**：如实暴露链路情况 |

**结论分级**：任一项 `fail` → 核查未通过；仅 `warn` → 通过但有警告；否则全部通过。

### 2.16 纠正只做一次，中止要写明停在哪一步（P5）

- **纠正至多一次**：核查未通过时，带着具体缺陷（「缺编号」/「引用了不存在的编号」）
  通过 `qa_prompt.STRICT_RETRY_DIRECTIVE` 再问一次。反复重试会掩盖问题、消耗额度、
  也让日志失真；一次不成功就以「核查未通过」的状态输出，把问题交给用户而不是藏起来。
  纠正失败（例如后端不支持 `directive`）时**保留第一次的回答**，只把失败如实记在纠正步骤里。
- **中止即留痕**：问题不合法 / 检索不到资料 / 后端全部不可用三种情况会立刻中止，
  余下步骤一律记为「跳过」并写入中止原因，日志里能一眼看出流程停在哪一步。
  这比「静默降级成一段兜底话术」更符合本项目「不编造」的原则。
- **整体状态四分**：`completed`（全部步骤干净且核查通过）、
  `corrected`（中途纠正过、最终核查通过）、`degraded`（完成但核查未通过或有警告）、
  `aborted`（中途终止）。「纠正后才通过」与「一次就通过」被区分开，过程信息不被抹平。

### 2.17 「没配」不等于「出错」：降级要按性质分开（P6）

**背景**：用真实大模型跑工作流时发现，**每一次**运行都被判为「完成但存在问题」，
原因是核查项「未发生后端降级」把 `Dify：未配置 DIFY_BASE_URL` 也当成了问题。
在没有自建 Dify 的部署里，这条警告永远为真——把正常工作说成了有问题。

**决策**：在 `src/qa/errors.py` 中把降级说明按性质分两类，
智能体工作流的核查只看后者：

| 类别 | 例子 | 判定 |
|---|---|---|
| 配置性跳过 | 「未配置 DIFY_BASE_URL」「不受支持」「未安装 requests」 | **通过**，原因照旧写进核查明细与步骤日志 |
| 运行时故障 | 「请求超时」「HTTP 503」「返回了空回答」 | **警告**，这才是需要人看一眼的 |

**理由**：降级**可见性**与降级**严重性**是两件事。原因必须一直显示（用户有权知道
本次用的是哪条链路），但不该把所有原因都等同于缺陷。修正后，同样的真实运行从
「完成但存在问题」变为「已按预期完成」，而真正的运行时故障仍然报警。

### 2.18 效果评估必须建立在人工标注集上（P6）

**背景**：前五个阶段都在验证「功能是否可用」，但「效果好不好」一直只有零散的
定性判断（例如「问徽商能答对」），既不能复现，也无法发现退化。

**决策**：新增评估层 `src/eval/`，并把标注集当作**基准数据**来管理：

1. **标注先于评估**：`data/eval/*.json` 由人工编写并逐条对照 `data/entities.json` 核对，
   不拿检索结果反推标准（否则指标必然虚高）；
2. **指标是纯函数**：`metrics.py` 里每个函数的公式都写在文档字符串里、可手算核对，
   不引入评估库，避免「指标怎么来的」变成黑盒；
3. **默认离线**：检索评估只依赖本地索引，回答评估强制本地检索式后端，
   因此 `pytest` 与页面上的数字都确定、可复现、不消耗额度；
   要看真实模型的表现须显式 `--live`，报告里写明用的哪个后端；
4. **困难样本不剔除**：两个「词面重叠」负样本（`区块链共识算法` 命中《算法统宗》）
   会被误召回，这是词袋检索的固有局限。它们被单独打标签、单独统计，
   **计入总分**而不是隐藏——指标好看不值钱，能指出问题才值钱。

**回报**：首轮评估就抓到一个真实缺陷——别名参与匹配却没有出现在送进后端的资料正文里，
导致「徽商又被称为什么」这类问题永远答不出别名。修正后要点命中率 0.857 → 1.000。

### 2.19 界面回归只做**结构**快照，并如实说明边界（P6）

**决策**：新增 `tests/test_ui_snapshot.py`，把每个页面渲染结果的
**区块标题序列、用到的样式类、控件清单、侧边栏导航**压成文本快照存进
`tests/snapshots/`，发生非预期改动即失败；有意变更时用 `UPDATE_SNAPSHOTS=1` 重生成。

**边界（重要）**：本项目没有引入浏览器截图比对，因此这**不是**像素级视觉回归，
发现不了「颜色变了、间距歪了」。命名与文档都按实际能力写，不夸大。

**细节**：只统计页面内容、排除全局样式表（否则每页记录的都是整份主题类名，失去区分度）；
快照里抹掉耗时、计数、绝对路径等易变内容（否则每次运行都误报，测试很快会被无视）。

### 2.20 大图按规模守卫分片，且不改变现有行为（P6）

**背景**：遗留问题里「图谱超过 300 节点需分片」一直没做，也没法验证——当前只有 96 个节点。

**决策**：在 `src/graph/visualize.py` 加入 `shard_graph()` / `build_sharded_html()`：

- 节点数 ≤ `DEFAULT_NODE_BUDGET`（400）时**原样返回一张全图**，
  因此当前规模下的行为与不分片时**逐字节一致**（有测试钉住）；
- 超过时按分类打包，单个分类自身超预算则按度数降序切块；
  分片顺序可复现，片内只保留片内的边（跨片边不画，界面明确说明）。

**验证方式**：当前数据触发不了分片，所以用**合成的 600 节点图**验证能力真的可用
（实测分 2 片、无节点丢失、无片超预算），并把渲染耗时与产物体积写成性能预算断言
（当前 96 节点：约 0.07 s / 852 KB），用于发现数量级退化。

### 2.21 图片抓取改为中转池，应对限流（P6）

**背景**：P3 依赖 Microlink 取 Commons 元数据，其免费额度约 15 次/日，用尽后持续返回 429；
备用中转（allorigins / cors.lol / codetabs）也各自限流，实测会轮流出 429 / 500 / 503 / 522，
单靠任何一家都无法连续取回十几个实体的元数据。

**决策**：把中转改成**池 + 冷却退避**（`RELAY_TEMPLATES` / `_relay_state`）：
按「近期成功率 + 是否在冷却」排序，某个中转失败即进入指数冷却（上限 180 s），
请求自动落到其它中转；两轮仍全部失败才放弃。联网通道探测也改为对池内每个中转各试一次
（Commons `siteinfo`），避免「一家在限流」被误判成「整条链路不通」。

**效果**：图片素材由 11 张增至 20 张（全部经许可白名单校验并逐条署名）。
补抓后逐张核查实际图片内容，又发现其中 4 张不该收（见 2.22），剔除后为 **15 张**。

---

### 2.22 收录一张图要有三道门槛，并且把关要被测试钉住（P6）

**背景**：补抓把图片从 11 张提到 20 张之后，交付测试
`test_real_manifest_entries_are_fully_attributed` 抓到 `huangbinhong` 缺作者。
顺着这条线索**逐张目视核查实际图片内容**，发现了比缺作者更严重的问题：

| 实体（清单图注） | 实际拿到的 Commons 文件 | 问题 |
|---|---|---|
| 渐江（`jianjiang`）「渐江山水画」 | `File:Jianjiang Delta Aerial View.png` | 广东江河的**航拍照片**，与画家渐江（弘仁）无关 |
| 徽州牌坊（`huizhou_paifang`）「徽州牌坊」 | `File:Paifang, Baiyun Temple, ...` | 白云寺的**院门**，不在徽州 |
| 徽州祠堂（`huizhou_citang`）「徽州祠堂」 | `File:Chu Hsi's ancestral temple in Wuxi Huishan ...` | **无锡惠山**祠堂，不在徽州 |
| 黄宾虹（`huangbinhong`）「黄宾虹山水画」 | `File:Huang Binhong.JPG` | 图是对的，但 Commons 上**只有 Public domain、没有 Artist/Credit**，无从署名 |

前三条会让界面**宣称错误的事实**——图注照抄实体名，看图的人却看到别处的东西。
这比「少一张图」严重得多。

**决策**：把「一张图能不能进清单」定成三道门槛，并写进代码的一处唯一定义
（`target_gate()` 与 `candidate_rejection()`，都是**纯函数**，不联网即可断言）：

1. **许可自由**（原有）；
2. **确实相关**——必含词 + 排除词。对「徽州牌坊」「徽州祠堂」这类**带地域的建筑类型名**，
   必含词拆成两段（` & ` 表示同时满足）：既要是牌坊/祠堂，又要能看出在徽州一府六县境内。
   这样「同名异地」「同物异指」都会被挡；
3. **Commons 上登记了作者**（新增）——没有作者的图片一律不收。宁可缺一张图，
   也不写一条署不出作者的图片。

处理结果：剔除 4 条（清单 19 → **15** 张，同时删掉对应图片文件，不留孤儿图），
并把剔除原因逐条写进 `CREDITS.md` 的「未取得图片的实体」。

**把关要被钉住，而不只是「这次修好了」**：`tests/test_image_library.py` 新增 12 项用例，其中
- `test_target_gates_reject_the_candidates_actually_downloaded_by_mistake`——
  把上面三个真实误召回的文件名写成参数，断言把关**必须挡住它们**；
- `test_manifest_entries_pass_their_own_relevance_gate`——
  断言清单里**每一张图**都能通过它所属实体的把关（只看 Commons 侧的标题与文件名，
  不看我方图注，否则图注里写个实体名就能「自我证明」）；
- `test_candidate_without_author_is_rejected_not_credited_blindly`——无作者必拒。

**取舍**：门槛提高后，可收录的图片变少了（29 个目标实体中 15 个有图）。
这是有意为之：这个平台的立身之本是「来源可核查」，一张图文不符的图片比没有图片伤害更大。

**顺带修掉一处「把关过严」**：复核失败清单时发现 `huiju` 被挡的理由是候选描述写的是
「**徽戏**」而必含词只写了「徽剧」——两种写法指的是同一个剧种，属把关过严而非把关过松。
已把「徽戏」补进必含词（重跑即可取到该候选）。这说明**把关要双向看**：
既要挡住不该进的，也要检查是否把该进的错挡了。

**试过补抓替代图，但没成**：剔掉 4 条后，又用更精准的检索词
（`Hongren landscape painting` / `弘仁 山水` / `Huang Binhong landscape` / `黄宾虹 山水` /
`Tangyue archways Shexian` / `ancestral hall Shexian Anhui`）在后台跑了一轮补抓，
**跑了 10 分钟一条候选都没取回**——免费中转池当时全部处于限流或冷却状态
（Microlink 日额度、allorigins 520、cors.lol 429、codetabs 1200）。这一轮**没有产出任何结果**，
故未改动清单；等免费额度恢复后重跑 `python scripts/fetch_images.py` 即可，
把关规则已就位，取回的候选会自动按三条门槛筛一遍。

---

## 三、模块职责

| 文件 | 职责 |
|---|---|
| `app.py` | 页面配置、注入设计系统、侧边栏导航、页面路由、页脚 |
| `src/config.py` | 路径常量、`.env` 加载、问答后端探测与降级判断 |
| `src/ui/theme.py` | 设计令牌（配色 / 字体 / 圆角 / 间距）、11 分类专色与全局 CSS 注入 |
| `src/ui/components.py` | 卡片、面包屑、分类标签、关系行、来源行、图片图注、区块标题、空/错状态等 HTML 组件 |
| `src/ui/nav.py` | 导航模型唯一来源：可见入口、隐藏页归属、路由解析、高亮判定、跳转 |
| `src/ui/datastore.py` | 界面共享数据入口，缓存 `repository()` 与 `images()`；问答引擎复用缓存的检索索引 |
| `src/ui/pages/*.py` | 各页面渲染入口，统一导出 `render()` |
| `src/data/loader.py` | 读取并校验实体 / 关系 / 来源 JSON，给出可读的错误信息 |
| `src/data/repository.py` | 搜索、分类筛选、详情查询、邻居查询、子图与路径 |
| `src/data/images.py` | 实体图片库与署名；清单/文件缺失时安全降级 |
| `src/graph/builder.py` | 构建 `MultiDiGraph`（实体为节点、关系为边，保留同向平行边）；分类/关系类型筛选、ego 子图 |
| `src/graph/analysis.py` | 结构统计、度数/介数中心性排名、连通分量、最短关联路径、模块度聚类 |
| `src/graph/visualize.py` | 生成离线自洽的交互式 HTML（内联资源、资源清洗、图例、路径链条） |
| `src/graph/runtime.py` | 图谱与数据集的界面运行时缓存（保持上述三模块不依赖 Streamlit） |
| `src/qa/retriever.py` | jieba 分词 + BM25 资料检索；关系叙述进索引；结果必带来源 |
| `src/qa/prompt.py` | 编号引用提示词、引用编号解析、回答清理、问题校验 |
| `src/qa/engine.py` | 三层后端实现、自动降级、引用溯源与越界编号识别 |
| `src/qa/errors.py` | 问答层异常层级（问题非法 / 检索失败 / 后端不可用·超时·响应异常 / 全链失败） |
| `src/ui/pages/ask.py` | AI 问答页：提问、示例、后端状态、回答 + 引用 + 检索资料、会话历史 |
| `src/agent/workflow.py` | 六步可追踪工作流、结构化引用核查、纠正重试与逐步日志 |
| `src/eval/metrics.py` | 评估指标（Recall@K / Precision@K / Hit@K / MRR / AP / nDCG@K），纯函数、公式可手算 |
| `src/eval/dataset.py` | 人工标注集的模型、加载与严格校验（引用不存在的实体直接报错） |
| `src/eval/runner.py` | 在标注集上评估检索与回答，产出结构化报告与按标签分组统计 |
| `src/ui/pages/about.py` | 关于项目页：平台概览、可现场运行的工作流演示、质量评估、架构与开发原则 |
| `scripts/fetch_images.py` | 从 Wikimedia Commons 抓取 CC 授权图片（中转池 + 许可白名单 + 检索/排除正则过滤） |
| `scripts/evaluate.py` | 质量评估 CLI：离线跑检索与问答评估，可 `--live` 换真实后端，支持 `--json` |

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

---

### P4 检索与 AI 问答（已完成）

**交付内容**

| 模块 | 说明 |
|---|---|
| `src/qa/errors.py` | 异常层级：`QuestionError`（用户可见原因）、`RetrievalError`、`BackendUnavailableError` / `BackendTimeoutError` / `BackendResponseError`、`AllBackendsFailedError`（携带逐条原因） |
| `src/qa/retriever.py` | jieba 分词 + 停用词过滤；BM25（k1=1.5，b=0.75）+ 精确命中加成；关系叙述进索引；结果必带来源、正文有上限、命中词被记录 |
| `src/qa/prompt.py` | 系统提示词（只用资料 / 必须标编号 / 资料不足直说 / 无关问题拒答）；资料编号从 1 起；引用解析兼容半角与全角；回答清理；问题校验 |
| `src/qa/engine.py` | `DifyBackend`（chat / agent / workflow）、`OpenAICompatBackend`、`LocalRetrievalBackend`；`QAEngine` 依次尝试并记录降级原因；引用编号与资料表比对，越界编号单独记录 |
| `src/ui/pages/ask.py` | 提问输入、数据驱动的示例问题、后端状态与降级说明、回答 + 引用来源 + 检索资料、会话历史、空/错误状态 |

**检索实测**（真实数据集，96 份资料 / 1892 词表）

| 查询 | 首位结果 | 分数 |
|---|---|---|
| 宏村 | 宏村 | 13.78 |
| 徽州 | 徽州（修前是「徽州婚俗」） | 9.05 |
| 马头墙有什么特点 | 马头墙 | 14.70 |
| 徽州三雕是什么 | 徽州三雕 | 11.78 |
| 胡适是哪里人 | 胡适 | 14.47 |
| 宏村和西递是什么关系 | 宏村（西递第 3） | 12.86 |

**真实大模型联调**（`deepseek-chat`，非自动化测试）

```
问：徽商是什么？
→ 检索 5 条资料（含关系叙述）→ DeepSeek 作答 2.1 s / 1707 tokens
→ 回答 5 处引用 [1][3][2][4][5]，全部对应到可点击来源，grounded = True

问：量子纠缠与超导体的关系是什么？
→ 模型回复：「本次检索到的资料与问题无关，无法回答。」（未编造）
```

本地检索式后端（`QA_FORCE_LOCAL=1` 或未配置任何凭证时）直接呈现资料原文并标注来源，
回答开头明确说明「未经过生成式改写」，检索不到时回答「不会虚构答案」。

**验证**

- `pytest`：**274 个测试函数 / 305 个用例全部通过**（P0–P4 累计，10.22s），无警告，**全程不联网**。
- 新增 `test_qa_retriever.py`（27）、`test_qa_prompt.py`（33）、`test_qa_engine.py`（39）；
  `test_smoke.py` 扩充至 26 项（新增 9 项问答页真实交互用例）。
- 真实大模型端到端联调通过（见上），应用 `/` 与 `/_stcore/health` 均返回 200。

**遗留问题**

- **Dify 后端未做真实联调**：本机没有自建 Dify 实例，`DifyBackend` 仅通过注入的假 HTTP
  响应做了单元验证（覆盖 chat / workflow 两条路径与错误分支）。
- 回答质量目前有结构性断言（引用覆盖率），尚无语义质量评估金标准；检索也缺 Recall@K 标注集。
- 图片素材、大图性能、界面视觉回归三项遗留问题承接 P3，未在本阶段处理。

**下一阶段（P5）**

实现可追踪的智能体工作流（`src/agent/workflow.py`）：把「检索 → 依据资料作答 →
自我核查引用 → 输出」编排成带步骤日志的多步流程，并在「关于项目」页展示每一步的输入、
输出与耗时；配套测试覆盖步骤顺序、失败中止与日志完整性。

---

### P5 可追踪智能体工作流（已完成）

**新增文件**

```
src/agent/workflow.py          六步工作流、结构化引用核查、纠正重试、逐步日志
src/ui/pages/about.py          关于项目页（含可现场运行的工作流演示）
tests/test_agent_workflow.py   工作流测试（26 项）
src/agent/__init__.py（修改）   导出工作流 API 与步骤常量
src/qa/prompt.py（修改）        新增 directive 参数与 STRICT_RETRY_DIRECTIVE
src/qa/engine.py（修改）        拆出 answer_from()，支持指定后端链与纠正指令
src/ui/components.py（修改）    新增 level_tag / flow_chain / workflow_step
src/ui/theme.py（修改）         新增流程链、步骤时间线、核查标签样式
src/ui/datastore.py（修改）     新增 agent_workflow()
src/ui/nav.py（修改）           about 页阶段标注清空（已交付）
src/ui/pages/home.py（修改）    P5 进度说明、快捷入口「运行智能体工作流」、模块表补 about 页
app.py（修改）                  侧边栏版本说明补 P5
```

**六个步骤**

| 步骤 | 模块位置 | 做什么 | 中止条件 |
|---|---|---|---|
| 1 问题解析与实体锚定 | `analyse_question` / `detect_anchors` | 启发式判断提问类型；把问题里的实体名与别名锚定出来（长词优先） | 问题不合法 |
| 2 资料检索 | `AgentWorkflow._retrieve` | 放宽条件检索后，把锚定实体提到首位；锚定实体未出现时按名字补查一次 | 检索结果为空 |
| 3 依据资料作答 | `QAEngine.answer_from` | 走 P4 的同一套后端降级链 | 所有后端不可用 |
| 4 引用自我核查 | `verify_answer` | 6 项结构化核查，输出 pass / warn / fail 分级结论 | 不中止（问题如实上报） |
| 5 纠正重试 | `qa_prompt.STRICT_RETRY_DIRECTIVE` | 核查未通过且仅一次：带着具体缺陷重问一次 | 不中止（失败保留原答案） |
| 6 输出与归档 | `WorkflowResult` | 汇总答案、引用、核查结论与完整日志 | — |

步骤顺序、名称与职责以常量形式定义在 `workflow.py`（`STEP_ORDER` / `STEP_TITLES` / `STEP_DUTIES`），
**界面直接引用这些常量**，因此页面上的流程图不可能与代码里的执行顺序不一致。

**请求流的演进（P4 → P5）**

```
P4：  question → retrieve → answer_from → QAResult          （一次调用，过程不可见）

P5：  question → intent → retrieve → answer_from → verify → [revise] → finalize
                  ↑ 每步记录 输入 / 输出 / 耗时 / 状态 / 明细
```

**「关于项目」页（`about.py`）**

| 区块 | 内容 |
|---|---|
| 平台一览 | 项目定位、技术栈、数据规模（实时读取数据集）、当前问答后端、版本号 |
| 可追踪智能体工作流 | 六步流程链 + 提问输入 + 数据驱动示例问题；运行后展示整体状态、逐步时间线、核查表、最终回答与引用来源 |
| 步骤明细 | 每个步骤可展开看完整明细（含降级说明、越界编号、纠正指令原文）；另附一份纯文本追踪日志便于答辩演示 |
| 架构与模块职责 | 11 个模块的职责表，就绪状态由 `importlib` 实时探测 |
| 开发原则 | 项目的 8 条硬性约定 |

**实测（真实数据集 + 本地检索式后端）**

| 提问 | 结果 |
|---|---|
| 宏村是什么？ | 5 步执行（纠正被跳过）；检索 5 条（1 条来自锚定实体）→ 引用 5 处 → 核查 6/6 通过 → 状态「已按预期完成」 |
| 宏村和西递有什么关系 | 提问类型「关系类」，锚定实体「宏村、西递」；检索 5 条其中 2 条来自锚定实体 |
| 胡适是哪里人 | 提问类型「事实/属性类」，锚定实体「胡适」 |
| 量子纠缠与超导体 | 第 2 步（资料检索）中止，余下 4 步全部「跳过」并附中止原因，**未生成任何回答** |

**验证**

- `pytest`：**305 个测试函数 / 340 个用例全部通过**（P0–P5 累计，17.96s），无警告，**全程不联网**。
  新增 `test_agent_workflow.py`（26 项）、`test_qa_prompt.py` 补 5 项、`test_smoke.py` 补 6 项
  并把 2 项「待开发页」断言改写为 about 页真实内容断言。
- 语法编译 `python -m compileall app.py src scripts tests` 通过；
  数据校验 `python scripts/validate_data.py` 通过（96 实体 / 180 关系 / 33 来源，无孤立实体）。
- 应用启动：`http://localhost:8501/` = 200、`/_stcore/health` = 200。

**本阶段由测试暴露并修正的问题**

1. **「纠正成功」的整体状态被误判为 degraded**：核查步骤留有 warn，导致已经修复的问题仍被计入
   「完成但存在问题」。新增 `corrected` 状态区分「纠正后才通过」与「一次就通过」。
2. **中止用例选题不严谨**：原用「量子纠缠与超导体的关系」验证「检索不到」，但通用词「关系」
   真实命中了「徽州盐商」等资料。改为「量子纠缠与超导体」，并加断言钉住「检索不到 = 空列表」。
3. **`answer_from` 的向后兼容**：拆出该方法后，引擎必须在 `directive` 为空时只用两个位置参数
   调用后端，否则既有的假后端与旧式实现都会因多出一个关键字参数而失败。

**遗留问题**

- 工作流的纠正重试路径只在假后端下验证过；真实模型触发纠正的概率较低，尚无真实样本。
- Dify 后端仍未做真实联调（承接 P4）。
- 图片素材 11/29、大图性能、界面视觉回归、回答语义质量评估四项承接前序阶段，未在本阶段处理。

**下一阶段（可选）**

若继续推进，建议按以下顺序：真实模型下的工作流联调与纠正样本采集 →
检索召回标注集（Recall@K）→ 界面视觉回归（截图对比）→ 补齐剩余图片素材。

---

### P6 质量评估与工程收尾（已完成）

P5 是原计划的最后一个功能阶段，因此 P6 不再加功能，而是**把「效果」变成可量化的东西，
并逐条处理前五个阶段留下的遗留问题**。

**新增文件**

```
src/eval/__init__.py           评估层说明与模块导航
src/eval/metrics.py            指标（Recall@K / Precision@K / Hit@K / MRR / AP / nDCG@K）
src/eval/dataset.py            标注集模型、加载与严格校验
src/eval/runner.py             检索评估与回答评估、按标签分组统计
data/eval/retrieval_eval.json  检索标注集（42 条：36 有答案 + 6 负样本）
data/eval/qa_eval.json         问答标注集（24 条：21 可答 + 3 应拒答）
scripts/evaluate.py            质量评估 CLI（离线 / --live / --json / --verbose）
tests/test_eval.py             评估层测试（39 项，指标用手算例子验证）
tests/test_qa_dify_http.py     Dify 后端真实 HTTP 路径集成测试（15 项）
tests/test_ui_snapshot.py      界面结构快照回归（10 项）
tests/snapshots/*.txt          六个页面的结构快照基线
```

**修改文件**

```
src/qa/retriever.py            别名进资料正文（评估发现的缺陷修复）
src/qa/errors.py               新增 is_config_skip / split_degradations / CONFIG_SKIP_MARKERS
src/agent/workflow.py          核查与作答步骤改用「配置性跳过 vs 运行时故障」判定
src/graph/visualize.py         新增 shard_graph / build_sharded_html / GraphShard / DEFAULT_NODE_BUDGET
src/ui/pages/graph.py          画布改用分片渲染（小图行为不变，大图按分类分页）
src/ui/pages/about.py          新增「质量评估」区块；模块表补 eval 三模块
src/ui/components.py           新增 metric_grid 指标格子
src/ui/theme.py                新增指标格子样式
src/ui/datastore.py            新增 eval_report() / eval_sets()（评估结果缓存）
scripts/fetch_images.py        元数据中转改为「中转池 + 冷却退避」；
                                相关性把关抽成纯函数 target_gate / candidate_rejection，
                                并对「徽州牌坊」「徽州祠堂」加地域必含词；新增「无作者不收」门槛
tests/test_graph.py            新增规模守卫与性能预算用例
tests/test_image_library.py    新增把关断言（清单每张图必须过自身实体的关、无作者必拒等）12 项
```

**遗留问题的处理结果**

| 原遗留项 | 处理方式 | 结果 |
|---|---|---|
| 无检索召回标注集 | 编写 42 条标注 + 指标实现 | 已解决（Recall@1 0.530 / @5 0.846，nDCG@5 0.938） |
| 无语义质量金标准 | 编写 24 条问答标注 + 5 项回答侧指标 | 已解决（离线引用覆盖 1.000；真实 DeepSeek 下 0.976） |
| Dify 仅经注入假响应验证 | 本地假 Dify 实例走真实 `requests` 链路 | 协议层已实测（路径 / 鉴权头 / 请求体 / chat·workflow 解析 / 500 / 非法 JSON / 超时） |
| 无界面回归 | 结构快照回归（明确不宣称像素级） | 已解决（6 页基线，故意改动能被测出） |
| 大图性能未处理 | 规模守卫分片 + 合成大图验证 + 性能预算 | 已解决（实测 96 节点 0.07 s / 852 KB） |
| 图片 11/29 | 中转池改造 + 补抓，并逐张目视核查 | 11 → 20 张，核查后又剔除 4 张图文不符/无法署名的，**实收 15 张**（其余或检索无结果、或与实体无关、或低于分辨率门槛、或 Commons 未登记作者，均如实登记在 `CREDITS.md`） |
| 纠正重试无真实样本 | 用真实 DeepSeek 跑工作流 | 部分解决：真实运行反而暴露了「未配置也被算作降级」的判定缺陷（见 2.17），已修复 |

**真实运行实测（`python scripts/evaluate.py --live`，DeepSeek `deepseek-chat`）**

```
24 条问答标注 / 23 秒：引用覆盖 0.976　要点命中 0.976　可溯源 1.000
                        作答率 1.000　拒答判断正确 1.000　无编造编号 1.000
唯一未答全的一条：问「马头墙的作用是什么」时没有答出别名「封火墙」
```

三条域外问题全部被正确拒答，且未出现任何编造编号——这印证了「资料不足时直说」的约束
在真实模型上同样成立，而不只是在假后端里成立。

**真实工作流实测（同上后端）**

```
问「徽商是什么？」      → 5 步执行、引用 5 处、核查 6/6 通过 → 已按预期完成
问「宏村位于哪个县？」   → 引用 2/5 条资料 → 「检索资料被有效利用」警告 → 完成但存在问题
问「量子纠缠与超导体」   → 第 2 步中止、余 4 步跳过、未生成任何回答
```

中间那条的警告是**真信号**：模型给出的答案正确，但只引用了 5 条检索资料中的 2 条，
说明检索结果里混入了无关内容（与评估里「概念类召回 0.635」指向同一个问题）。
工作流没有把它粉饰成「完成」，这也是核查项存在的意义。

**验证**

- `pytest`：**385 个测试函数 / 432 个用例全部通过**（P0–P6 累计，24.53s），无警告，**全程不联网**。
  其中 P6 新增 `test_eval.py`（39 项）、`test_qa_dify_http.py`（15 项）、
  `test_ui_snapshot.py`（10 项）、`test_image_library.py` 补 12 项，
  `test_graph.py` / `test_qa_engine.py` / `test_agent_workflow.py` / `test_components.py` 亦有增补。
- 评估默认**离线**跑（固定本地检索式后端），因此指标可复现；`--live` 才打真实后端。
- 语法编译 `python -m compileall app.py src scripts tests` 通过；
  数据校验 `python scripts/validate_data.py` 通过（96 实体 / 180 关系 / 33 来源，无孤立实体）。

**本阶段由真实运行与评估暴露并修正的问题**

1. **别名不可见**：别名参与分词与匹配，却没有出现在送进后端的资料正文里，
   于是「徽商又被称为什么」必然答不出别名。评估首轮即抓到，修正后要点命中 0.857 → 1.000。
2. **「没配」被当成「出错」**：见 2.17。真实运行中**每次**都被判为「完成但存在问题」，
   修正后同一次运行变为「已按预期完成」，而运行时故障仍然报警。
3. **单线程假 HTTP 服务器挂死测试**：`HTTPServer` 在 HTTP/1.1 keep-alive 下会停在原连接上，
   `shutdown()` 永久阻塞。改用线程化服务器 + 守护线程。
4. **代理环境下的断言不成立**：本机设有 HTTP 代理，连接失败可能被代理回成 502 而非抛
   `ConnectionError`。改为断言真正的不变量（异常必须被翻译成本项目自己的异常），
   并把「异常类型 → 语义化异常」的映射单独做确定性测试。
5. **快照把全局样式表算进页面**：导致每页记录的都是整份主题类名，失去区分度。改为只统计页面内容。
6. **标注 id 打错**：`chengzitang` 应为 `chengzhitang`。标注校验器直接拦下并指到具体 case——
   这正是「标注集要按基准数据严格校验」的价值。
7. **补抓的图片里混进了图文不符的**（本阶段最严重的一处）：交付测试先抓到 `huangbinhong` 缺作者，
   顺着逐张目视核查又发现 3 张图注与底层 Commons 文件根本不是一回事——「渐江」下到广东江河航拍、
   「徽州牌坊」下到白云寺院门、「徽州祠堂」下到无锡惠山祠堂。界面会因此**宣称错误的事实**。
   处理：剔除这 4 条（删除图片文件，不留孤儿图），收录门槛加一条「Commons 上登记了作者」，
   并把把关抽成纯函数、由 12 项新用例钉住（详见 2.22）。

**遗留问题**

- Dify 仍未与**真实实例**联调（本机没有可用实例）。协议层已由本地假实例实测覆盖，
  但真实 Dify 的鉴权、应用类型差异与返回体细节仍可能有意料之外的差异。
- 召回率是明确的改进空间：概念类查询 Recall@5 只有 0.635，关系类查询能召回主体
  却常召不回对象实体（如问「宏村属于哪个县」时「黟县」不在前 5）。
  可能的解法是引入关系三元组级的检索单元，而不是以「实体」为唯一资料粒度。
- 词面重叠的负样本仍会被误召回（0/2 留空），属词袋检索的固有局限，需换检索模型才能根治。
- 界面回归只到结构层，样式退化仍无人看守。
- 图片 15/29：其余目标的失败原因已在 `CREDITS.md` 里逐条写明
  （检索无结果 / 与实体无关 / 分辨率低于门槛 / Commons 未登记作者）。
  其中「未登记作者」是新增门槛带来的——这类图片本身可能相关，但署不出名就一律不收。
