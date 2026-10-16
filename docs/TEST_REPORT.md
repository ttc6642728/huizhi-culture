# 测试报告 · Huizhou Culture Explorer

## 运行环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows（win32） |
| Python | 3.13.14 |
| pytest | 9.1.1 |
| 虚拟环境 | `E:\huizhi-culture\.venv` |
| 测试命令 | `pytest` |

---

## 汇总

| 阶段 | 用例数 | 通过 | 失败 | 耗时 |
|---|---|---|---|---|
| P0 脚手架 | 13 | 13 | 0 | 1.43s |
| P1 数据层 | 72 | 72 | 0 | 2.57s |
| P2 知识图谱 | 133 | 133 | 0 | 10.73s |

**当前累计：133 通过 / 0 失败 / 0 跳过。** 无弃用或运行时警告。

分文件用例数：

```
tests/test_config.py            8
tests/test_data_integrity.py   14
tests/test_graph.py            60
tests/test_loader.py           20
tests/test_repository.py       25
tests/test_smoke.py             6
```

---

## P1 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 72 items

tests/test_config.py ...........
tests/test_data_integrity.py ..............
tests/test_loader.py ....................
tests/test_repository.py .........................
tests/test_smoke.py .....

============================= 72 passed in 2.57s ==============================
```

### tests/test_data_integrity.py（14 项）— 真实数据文件校验

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_dataset_loads_and_passes_validation` | 数据文件加载成功且校验零问题 | PASS |
| `test_dataset_scale_meets_minimum` | 实体/关系/来源/分类数量不低于下限 | PASS |
| `test_all_ids_unique` | 实体、关系、来源 id 全部唯一 | PASS |
| `test_every_entity_is_sourced_and_described` | 每个实体都有来源、摘要、正文与属性，来源可解析 | PASS |
| `test_all_sources_have_resolvable_url` | 每条来源都有合法 http(s) 地址、出版方与访问日期 | PASS |
| `test_no_isolated_entities` | 不存在无关系的孤立实体 | PASS |
| `test_every_relation_is_sourced` | 每条关系都标注了存在的来源 | PASS |
| `test_every_category_is_used` | 不存在空分类 | PASS |
| `test_world_heritage_facts` | 西递、宏村、黄山的遗产编号与年份正确 | PASS |
| `test_unesco_sources_are_present` | UNESCO 官方条目存在且指向 whc.unesco.org | PASS |
| `test_intangible_heritage_batch_facts` | 非遗批次与申报地区与官方名录一致 | PASS |
| `test_architecture_facts` | 许国石坊立坊年份、牌坊数量、古建三绝内容正确 | PASS |
| `test_person_ranking_facts` | 人物评选名次与官方页面一致 | PASS |
| `test_category_names_match_approved_dimensions` | 十个既定分类名称稳定 | PASS |

### tests/test_loader.py（20 项）— 加载与校验边界

覆盖范围：必填字段缺失、id 重复、未知分类、来源断链、关系端点不存在、关系类型非法、重复关系、自环、无来源实体、来源缺 url、JSON 语法错误、顶层结构错误、校验失败时一次性抛出全部问题、缓存复用与清理。

| 关键用例 | 验证内容 | 结果 |
|---|---|---|
| `test_valid_synthetic_dataset_has_no_issues` | 正常数据不产生误报 | PASS |
| `test_unknown_entity_category_is_reported` | 未知分类被捕获 | PASS |
| `test_entity_with_dangling_source_reference_is_reported` | 来源断链被捕获 | PASS |
| `test_relation_with_unknown_endpoint_is_reported` | 关系端点不存在被捕获 | PASS |
| `test_duplicate_relation_triple_is_reported` | 重复关系被捕获 | PASS |
| `test_self_loop_relation_is_reported` | 自环关系被捕获 | PASS |
| `test_invalid_dataset_raises_with_all_issues` | 一次抛出全部问题，便于批量修复 | PASS |
| `test_cache_returns_same_instance_and_can_be_cleared` | 缓存复用与清理行为正确 | PASS |
| `test_invalid_json_raises_data_error` | JSON 语法错误给出明确异常 | PASS |

### tests/test_repository.py（25 项）— 查询能力

| 分类 | 关键用例 | 结果 |
|---|---|---|
| 检索 | 精确名称排第一；别名「八脚牌楼」命中许国石坊；多词查询优先全词命中；未知词返回空；空查询返回空；分类过滤生效；limit 生效；结果确定性 | PASS |
| 详情 | `get` / `require` 行为；名称与别名查找；来源可解析 | PASS |
| 关联 | 邻居含预期实体；方向（out/in）正确上报；按关系类型过滤；缺失实体抛 KeyError | PASS |
| 子图 | 半径 0 只含中心；半径增大集合单调增长 | PASS |
| 路径 | 连通实体间最短路径端点正确；同节点路径；未知实体抛 KeyError | PASS |
| 统计 | 关系类型计数求和等于关系总数；连接度排序正确；实体数与数据一致 | PASS |

### 附加验证

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 数据校验 CLI | `python scripts/validate_data.py` | 通过，无问题 |
| 语法编译 | `python -m compileall app.py src scripts` | 通过 |
| Streamlit 脚本执行 | `AppTest`（含首页数据概况渲染） | 无异常 |
| 应用启动 | `streamlit run app.py` | 启动成功，`/_stcore/health` = 200 |

### 数据规模（校验脚本输出）

```
实体   90
关系   150
来源   28
分类   11
关系类型 10
孤立实体：无（全部实体至少有一条关系）
```

---

## P2 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 133 items

tests/test_config.py ........                                   [  6%]
tests/test_data_integrity.py ..............                     [ 16%]
tests/test_graph.py .................................................... [ 55%]
........                                                        [ 61%]
tests/test_loader.py ....................                       [ 76%]
tests/test_repository.py .........................              [ 95%]
tests/test_smoke.py ......                                      [100%]

============================ 133 passed in 10.73s =============================
```

### tests/test_graph.py（60 项）— 图谱建模、分析、路径与离线可视化

| 分组 | 用例数 | 覆盖内容 | 结果 |
|---|---|---|---|
| 建模保真 | 7 | 必须为 `MultiDiGraph`；节点数 = 实体数；边数 = 关系数；同向平行边（`founder_of` + `representative_of`）两条都在；节点/边属性完整；`degree` 属性与图实际度数一致；关系端点不存在时建图直接报错而非静默丢弃 | PASS |
| 筛选与聚焦 | 8 | 按分类筛选（古村落 10 个节点且边两端都在集合内）；按关系类型筛选（`located_in` 26 条）；空集合不被误解释为「清空图」；筛选后度数重算；筛选不修改入参图；ego 半径 1 的节点数 = 中心度数 + 1；半径 2 严格多于半径 1；未知节点抛 `NodeNotFoundError` | PASS |
| 统计 | 7 | 节点/边/孤立数/自环数/连通分量/最大连通块；密度与定义式一致；直径与平均最短路均有定义且关系合理；关系类型计数求和 = 边数；分类计数求和 = 节点数且为 11 类；空图统计不崩溃 | PASS |
| 排名 | 4 | 度数排名降序且首位为「徽州」；`top_n` 生效；度数中心性落在 [0,1]；介数排名降序且首位为「徽州」且 > 0 | PASS |
| 连通性 | 2 | 连通分量构成全节点的一个划分（不重不漏，仅 1 块）；无孤立节点 | PASS |
| 关联路径 | 8 | 西递→承志堂 长度 2 且经「徽州民居」；每段都对应真实关系且带关系 id 与来源数；反向经过的关系被标记 `reversed` 且 `is_forward` 取反；同节点路径长度 0；不可达返回 `None`（不抛异常、不编造）；未知节点抛错；`shortest_path_all` 返回的都是等长最短路 | PASS |
| 聚类 | 5 | 聚类构成全节点的划分；按规模降序；每个聚类有分类构成且内聚度在 [0,1]；宏村与西递同属一个聚类；未知节点抛错 | PASS |
| 可视化离线自洽 | 10 | 无任何外部 `script`/`link`（含 `cdn.jsdelivr.net`、`cdnjs.cloudflare.com`）；无外部 `url()` / `@import` / `@font-face`；vis 库确已内联（> 400 KB）；HTML 不被 Streamlit 误判为 URL（`url_util.is_url` 为假）；标签中的 `<script>` 被转义；聚焦节点带朱砂描边；空图抛 `EmptyGraphError`；资源清洗能移除真实模板里的 Bootstrap 标签且不误删内联脚本；清洗不彻底时抛错；本地相对路径引用不被误删 | PASS |
| 数据载荷核对 | 1 | 从渲染产物中解析 JS 数据载荷：节点 90 个、边 150 条，id 集合与源图完全一致，边 id 唯一且等于关系 id 集合 | PASS |
| 展示辅助 | 6 | 名称截断；节点尺寸随度数单调；图例覆盖每个分类且含数量；路径链条同时体现 `→` 与 `←`；11 个分类各有专属配色（不落到兜底色）；配置可 JSON 序列化 | PASS |

### tests/test_smoke.py（6 项）— 脚本级冒烟

新增 `test_graph_page_renders_real_content`：切换到图谱页后脚本无异常，页面标题含「知识图谱」、
**不含**「尚未实现」，且概览指标实测为「实体节点 = 90、关系连线 = 150」。
`test_pending_page_explains_its_phase` 改为遍历仍未交付的 P3/P4/P5 页面，逐一断言其标注了阶段且说明尚未实现。

### 附加验证

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 数据校验 CLI | `python scripts/validate_data.py` | 通过，无问题 |
| 图谱验证报告 | `python scripts/graph_report.py` | 「全部检查通过」（建图保真 + 离线自洽） |
| 图谱导出 | `python scripts/graph_report.py --export outputs/huizhou-knowledge-graph.html` | 生成 830.7 KB 单文件，可独立用浏览器交互打开 |
| 语法编译 | `python -m compileall app.py src scripts` | 通过 |
| Streamlit 脚本执行 | `AppTest`（首页 + 图谱页 + 待开发页） | 无异常、无警告 |
| 应用启动 | `streamlit run app.py` | 启动成功，`/_stcore/health` = 200 |

### 图谱实测数据

```
节点 90 / 边 150（与数据完全一致）      连通分量 1（全部实体同一网络）
网络直径 6                              平均最短关联距离 2.939
图密度 0.0367                           孤立实体 0
度数首位「徽州」41                      介数首位「徽州」0.7488
文化聚类 8 组（模块度优化，探索性分析）
```

---

## 尚未覆盖 / 遗留问题

| 项目 | 说明 | 计划 |
|---|---|---|
| 检索与问答测试 | 检索与三层后端尚未实现 | P4 |
| 工作流测试 | 智能体工作流尚未实现 | P5 |
| 大图性能 | 当前 90 节点的交互式渲染实测约 0.06 s / 830 KB；若实体超过 300 个需引入分片或预布局 | 视数据规模而定 |
| 界面视觉回归 | 暂无截图对比测试 | P6 视情况补充 |
| 真实模型联调 | API Key 已验证可用（HTTP 200），但问答链路尚未实现，未做端到端联调 | P4 |
| 数据规模 | 实际交付 90 个实体，略高于原计划的 60–80；已确认无孤立节点 | 视需要继续扩充 |
| 方向均衡性 | 「徽州」的 41 条关系全部为入边，是数据特征而非缺陷 | 视需要补充出向关系 |

> 说明：本报告只记录**实际执行过**的测试结果；未实现的模块不会被标记为通过。
> 本阶段修复的 4 个由测试暴露的真实缺陷：`filter_graph` 把空列表误当作「筛选为空」、
> 平行边关系 id 未落到边数据导致路径无法溯源、`card_html` 缺少 `flat` 参数导致首页渲染异常、
> 资源清洗对自闭合标签处理不彻底。
