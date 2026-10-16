# 徽知 · Huizhou Culture Explorer

> 徽州文化知识图谱与 AI 智能问答平台 —— 生成式 AI 与智能体开发课程设计项目

徽知把徽州文化整理成**结构化、可核查、可交互**的知识：你可以浏览文化实体、按关键词与分类检索、
在交互式知识图谱中查看实体之间真实的数据关系，并基于资料向 AI 提问，获得**带来源引用**的回答。

---

## 项目特性

| 能力 | 说明 | 状态 |
|---|---|---|
| 文化探索首页 | 平台导览、数据概况、图谱概况与环境自检 | 已完成 |
| 徽州文化数据集 | 90 个实体 / 150 条关系 / 28 条来源 / 11 个分类 | 已完成 |
| 关键词搜索与分类筛选 | 中文检索 + 分类过滤（数据层） | 已完成（界面 P3） |
| 实体关联关系查询 | 邻居、最短路径、子图、连接度统计 | 已完成 |
| 可交互知识图谱 | NetworkX `MultiDiGraph` 建模 + PyVis 离线渲染，支持筛选、聚焦、点选高亮 | 已完成 |
| 图谱结构分析 | 度数 / 介数中心性、连通分量、直径、最短关联路径、模块度聚类 | 已完成 |
| 文化百科与实体详情 | 实体卡片、详细信息、关联关系、来源 | 规划中（P3） |
| 基于资料的 AI 问答 | 三层后端自动降级 | 规划中（P4） |
| 可追溯参考资料 | 每条回答标注来源编号 | 规划中（P4） |
| 可追踪智能体工作流 | 多步流程可视化 | 规划中（P5） |
| 测试与开发文档 | pytest 133 项 + 测试报告 | 持续进行 |

> 状态栏如实反映进度，未完成的模块不会提供「空壳按钮」。

---

## 文化数据

| 项目 | 数量 |
|---|---|
| 文化实体 | 90 |
| 实体关系 | 150 |
| 参考资料 | 28 |
| 内容分类 | 11 |
| 关系类型 | 10 |
| 孤立实体 | 0（图谱连通性检查通过） |

分类构成：古村落 10 · 徽派建筑 11 · 非物质文化遗产 9 · 历史名人 14 · 徽商 7 ·
传统工艺与艺术 9 · 民俗节庆 6 · 徽菜饮食 8 · 宗族与文教 7 · 文献典籍 4 · 山川地域 5

**每条实体与每条关系都必须标注可核查来源**，这一要求已由自动化测试固化；
所有来源登记在 `data/sources.json`，来源与取舍说明见 `docs/DATA_SOURCES.md`。

校验数据：

```bat
python scripts/validate_data.py
```

---

## 知识图谱

图谱由 `data/*.json` 实时构建，**不使用任何预生成的图数据**：

| 指标 | 值 |
|---|---|
| 节点 / 边 | 90 / 150（与数据完全一致） |
| 图类型 | `MultiDiGraph`（同向平行边不会被合并） |
| 连通分量 | 1（全部实体同属一个关联网络） |
| 网络直径 | 6 |
| 平均最短关联距离 | 2.939 |
| 文化聚类 | 8 组（模块度优化，探索性分析） |

「知识图谱」页提供：按分类 / 关系类型筛选、聚焦单个实体的关联子图（半径 1–3）、
悬停查看简介、点击节点高亮邻居、任意两实体的最短关联线路查询、
度数 / 介数中心性排名，以及文化聚类浏览。

图谱渲染**完全离线自洽**：`vis-network` 的 JS/CSS 内联进 HTML，
并会清洗 PyVis 模板自带的外部 Bootstrap 引用（详见 `docs/DEVELOPMENT.md` 第 2.3 节）。

生成验证报告，或导出一份可独立打开的交互式图谱：

```bat
python scripts/graph_report.py
python scripts/graph_report.py --path xidi chengzhitang
python scripts/graph_report.py --export outputs/huizhou-knowledge-graph.html
```

导出的 HTML 为单文件（约 830 KB），直接双击用浏览器打开即可拖拽、缩放与点选，
不依赖服务器与网络。

---

## 快速开始

### 1. 环境要求

- Python 3.10 以上（开发环境为 3.13）
- Windows / macOS / Linux 均可

### 2. 创建虚拟环境并安装依赖

Windows（PowerShell / CMD）：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 国内网络建议使用镜像：
> `pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/`

### 3. 配置（可选）

问答功能在**未做任何配置**时即可使用——程序会自动降级到本地检索式后端（纯离线，无需 API Key）。

若要启用真实大模型生成回答：

```bat
copy .env.example .env
```

然后编辑 `.env`，任选其一填写：

- **自建 Dify**：填写 `DIFY_BASE_URL`、`DIFY_API_KEY`
- **OpenAI 兼容大模型**：填写 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`

`.env` 已被 `.gitignore` 忽略，**不会进入版本库**。

后端生效顺序：`Dify` → `OpenAI 兼容大模型` → `本地检索式`。

### 4. 启动

```bat
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

---

## 环境诊断

首页内置**实时环境自检**，会检测并展示：

- 运行依赖的安装情况
- 文化数据文件是否存在及其大小
- 各核心模块的交付进度
- 当前实际生效的问答后端

所有结果均为程序实时探测所得，不包含预设或模拟数据。

---

## 目录结构

```
huizhi-culture/
├─ app.py                   Streamlit 入口：页面配置、导航、路由
├─ requirements.txt         运行依赖
├─ .env.example             配置模板（复制为 .env 使用）
├─ pytest.ini               测试配置
│
├─ src/
│  ├─ config.py             路径、环境变量、问答后端探测
│  ├─ data/                 数据加载、校验与查询
│  │   ├─ loader.py         数据模型与 11 类校验
│  │   └─ repository.py     检索、筛选、详情、邻居、子图、路径、统计
│  ├─ graph/                知识图谱
│  │   ├─ builder.py        MultiDiGraph 建模、筛选、ego 子图
│  │   ├─ analysis.py       统计、中心性、连通分量、最短路径、聚类
│  │   ├─ visualize.py      离线自洽的交互式 HTML
│  │   └─ runtime.py        界面运行时缓存
│  ├─ qa/                   资料检索与问答引擎
│  ├─ agent/                可追踪智能体工作流
│  └─ ui/                   设计系统、组件与页面（含 pages/graph.py）
│
├─ data/                    文化实体、关系、参考资料（JSON）
├─ assets/images/           徽州文化图片（含署名清单）
├─ scripts/                 validate_data.py（数据校验）、graph_report.py（图谱验证与导出）
├─ tests/                   自动化测试（6 个模块 / 133 项）
├─ outputs/                 导出的产物（已 gitignore）
└─ docs/                    开发文档、数据来源说明与测试报告
```

---

## 运行测试

```bat
pytest
```

当前 **133 项测试全部通过**（无警告），覆盖配置层、数据校验、查询仓储、
图谱建模与分析、离线可视化自洽、以及界面冒烟。详见 `docs/TEST_REPORT.md`。

---

## 开发原则

1. 先检查现有文件与环境，再动手修改。
2. 模块化开发，每完成一个模块即运行并测试。
3. 不虚构 API、依赖或测试结果。
4. 所有按钮必须具备真实功能，不出现纯装饰按钮。
5. 文化事实必须标注可核查来源。
6. AI 回答严格基于检索到的资料；资料不足时明确说明，不编造。
7. 敏感配置只存于环境变量，绝不写入代码或版本库。
8. 所有模块均处理异常、空结果与加载状态。

---

## 技术栈

Python · Streamlit · NetworkX · PyVis · JSON · pytest · Dify（可选）· Git
