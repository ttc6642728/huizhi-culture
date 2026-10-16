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
| P3 浏览体验 | 197 | 197 | 0 | 8.14s |
| P4 检索与问答 | 305 | 305 | 0 | 10.22s |
| P5 智能体工作流 | 340 | 340 | 0 | 17.96s |
| P6 质量评估与收尾 | 432 | 432 | 0 | 25.21s |
| 交付后调整（界面分层） | 437 | 437 | 0 | 27.83s |
| 交付后调整（换主视觉素材、图谱去浮层） | 437 | 437 | 0 | 34.31s |

**当前累计：437 通过 / 0 失败 / 0 跳过。** 无弃用或运行时警告。

> 两轮交付后调整都**没有增减用例总数**（各改写 2 项、新增 1 条断言）：
> 改的是「测什么」而不是「测多少」。第二轮把首页主视觉的两个用例换成了
> 「文件必须在 + 不得谎称自由授权」，图谱侧则在既有的载荷一致性用例里加了
> `assert "title" not in node`——钉住「节点不带浮层」这件事本身。

> 用例数大于测试函数数：部分测试用 `@pytest.mark.parametrize` 展开
> （如「一府六县」六个县份各一条用例、候选把关条件逐条各一条用例）。
> 当前共 **390 个测试函数 / 437 个用例**，分布在 **16 个测试模块**。

分文件用例数（交付后调整）：

```
tests/test_graph.py            69
tests/test_qa_engine.py        42
tests/test_eval.py             39
tests/test_qa_prompt.py        38
tests/test_smoke.py            35
tests/test_agent_workflow.py   27
tests/test_qa_retriever.py     27
tests/test_data_integrity.py   26
tests/test_image_library.py    25
tests/test_repository.py       25
tests/test_loader.py           20
tests/test_nav.py              16
tests/test_components.py       15
tests/test_qa_dify_http.py     15
tests/test_ui_snapshot.py      10
tests/test_config.py            8
--------------------------------------------------
合计                          437
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

## P3 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 197 items

........................................................................ [ 36%]
........................................................................ [ 73%]
.....................................................                    [100%]

============================ 197 passed in 8.14s =============================
```

### tests/test_nav.py（16 项）— 导航模型

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_nav_items_have_required_fields` | 每个导航项含 key / label / icon / module / phase | PASS |
| `test_nav_tree_is_the_only_source_of_sidebar_entries` | 侧边栏入口只来自 `NAV_ITEMS` | PASS |
| `test_nav_item_is_either_implemented_or_marked_pending` | 每个入口要么有模块文件，要么显式标注阶段 | PASS |
| `test_hidden_pages_map_to_a_visible_owner` | 隐藏页（详情页）归属到存在的可见入口 | PASS |
| `test_hidden_pages_never_appear_in_sidebar` | 隐藏页不出现在侧边栏 | PASS |
| `test_resolve_route_defaults_to_home` | 无状态时路由回落到首页 | PASS |
| `test_resolve_route_returns_stored_page` | 会话状态中的页面被正确解析 | PASS |
| `test_resolve_route_rejects_unknown_page` | 未知页面不被接受（回落到首页） | PASS |
| `test_resolve_route_ignores_legacy_query_param`（参数化） | 地址栏残留的旧 `?page=` 不会把用户拽回上一页 | PASS |
| `test_highlight_of_hidden_page_points_to_owner` | 详情页高亮到「文化百科」 | PASS |
| `test_highlight_of_visible_page_is_itself` | 可见页高亮为自身 | PASS |
| `test_goto_sets_page_and_params` | 跳转写入会话状态 | PASS |
| `test_goto_clears_stale_params` | 跳转清掉上一次的残留参数 | PASS |
| `test_nav_keys_are_unique` | 导航 key 不重复 | PASS |

### tests/test_image_library.py（13 项）— 图片库降级与真实清单合规

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_missing_manifest_is_not_an_error` | 清单不存在属正常状态、不抛错 | PASS |
| `test_valid_manifest_loads` | 正常清单载入、路径与署名正确 | PASS |
| `test_credit_without_artist_is_honest` | 作者缺失时如实说明，不编造 | PASS |
| `test_entry_with_missing_file_is_skipped` | 图片文件丢失的条目被跳过并记录 | PASS |
| `test_corrupt_manifest_degrades` | JSON 损坏时安全降级 | PASS |
| `test_manifest_images_not_a_list` | `images` 非数组时安全降级 | PASS |
| `test_entries_without_ids_are_skipped` | 缺 entity_id 的条目被跳过 | PASS |
| `test_project_library_never_crashes` | 对真实目录载入永不崩溃 | PASS |
| `test_real_manifest_meets_delivery_minimum` | **真实清单存在且 ≥ 8 张**（防止清单一度被写成空） | PASS |
| `test_real_manifest_licenses_are_free` | **每张真实图片许可都在白名单内**，且不含 NC / ND | PASS |
| `test_real_manifest_files_are_valid_images` | 每张图都是有效 JPEG 且未被截断 | PASS |
| `test_real_manifest_entities_exist_in_dataset` | 清单只引用数据集中真实存在的实体 id | PASS |
| `test_real_manifest_entries_are_fully_attributed` | 每张图都有图注、作者与 Commons 来源页面 | PASS |

### tests/test_components.py（12 项）— 展示组件

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_crumb_renders_path` | 面包屑按层级渲染 | PASS |
| `test_category_chip_uses_category_color` | 分类标签使用该分类专色 | PASS |
| `test_entity_card_contains_name_and_summary` | 实体卡片含名称与摘要 | PASS |
| `test_entity_card_escapes_html` | 卡片文本转义，防注入 | PASS |
| `test_detail_head_shows_aliases` | 详情头展示别名 | PASS |
| `test_relation_row_direction_arrows` | 出向用 `→`、入向用 `←` | PASS |
| `test_relation_row_uses_inverse_name_for_inbound` | 入向关系用 `inverse_name`（方向不造假） | PASS |
| `test_relation_row_shows_source_count` | 来源数 > 0 时显示「N 条来源」 | PASS |
| `test_source_row_is_clickable_link` | 来源行是合法可点击链接 | PASS |
| `test_count_line_reports_real_count` | 计数行显示真实数量 | PASS |
| `test_group_title_renders` | 分组标题渲染 | PASS |
| `test_empty_and_error_states_render_messages` | 空状态与错误状态各自渲染提示 | PASS |

### tests/test_smoke.py（17 项）— 脚本级冒烟（含真实点击）

P3 新增以下用例（在原有基础上扩充）：

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_explore_page_renders_real_content` | 百科页渲染、标题含「文化百科」、不含「尚未实现」 | PASS |
| `test_explore_search_returns_matching_entity` | 检索「宏村」返回对应卡片 | PASS |
| `test_explore_empty_state_on_no_match` | 无匹配时出现空状态（断言 `class="hz-ecard"` 不出现） | PASS |
| `test_explore_category_filter_counts_are_real` | 分类按钮计数与数据集一致 | PASS |
| `test_detail_page_renders_entity` | 详情页渲染指定实体 | PASS |
| `test_detail_page_relation_direction_is_honest` | 反向关系使用 `inverse_name`，不伪装成同向 | PASS |
| `test_detail_page_unknown_entity_shows_error` | 未知实体 id 显示错误状态 | PASS |
| `test_detail_page_without_selection_shows_hint` | 未选择实体时给出提示 | PASS |
| `test_clicking_entity_card_navigates_to_detail` | **真实点击**百科卡片后跳转到详情页 | PASS |

### tests/test_data_integrity.py（26 项）— 新增六县与来源校验

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_six_counties_present`（参数化，6 个县份） | 歙县/休宁/黟县/祁门/绩溪/婺源均在数据集中 | PASS |
| `test_county_placement_follows_historical_record` | 各县置县年代与史载一致 | PASS |
| `test_huizhou_has_outgoing_relations` | **「徽州」必须有出向关系**（防止退回纯汇点） | PASS |
| `test_counties_are_not_isolated` | 六个县份均有至少一条关系 | PASS |
| `test_intangible_heritage_declared_region_present` | 非遗项目均有 `declared_in` 申报地区 | PASS |
| `test_settlements_located_in_their_county` | 村落 `located_in` 所属县正确 | PASS |
| `test_new_sources_are_wellformed` | 新增来源 id / url / 出版方 / 访问日期完整 | PASS |

### 附加验证

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 数据校验 CLI | `python scripts/validate_data.py` | 通过，无孤立实体 |
| 图谱验证报告 | `python scripts/graph_report.py` | 「全部检查通过」（建图保真 + 离线自洽） |
| 图片抓取脚本 dry-run | `python scripts/fetch_images.py --dry-run` | 经 Microlink 中转真实检索，29 个实体中命中 16 个后触及免费额度 |
| 图片实际下载 | `python scripts/fetch_images.py --from-resolved assets/images/.resolved.json --pace 6` | **实际下载 11 张真实 Commons 图片**，全部通过许可白名单校验 |
| 语法编译 | `python -m compileall app.py src scripts` | 通过 |
| Streamlit 脚本执行 | `AppTest`（首页 / 图谱 / 百科 / 详情 / 待开发页） | 无异常、无警告 |
| 应用启动 | `streamlit run app.py` | 启动成功，`/_stcore/health` = 200 |

### 数据规模（校验脚本输出）

```
实体   96
关系   180
来源   33
分类   11
关系类型 11
孤立实体：无（全部实体至少有一条关系）
「徽州」度 = 47（出 6 / 入 41）
```

### P3 图谱实测数据

```
节点 96 / 边 180（与数据完全一致）      连通分量 1（全部实体同一网络）
网络直径 6                              平均最短关联距离 2.826
图密度 0.0388                           平均度 / 最大度 3.75 / 47
孤立实体 0
度数首位「徽州」47（出 6 / 入 41）        介数首位「徽州」0.7545
```

---

## P4 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 305 items

........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 70%]
........................................................................ [ 94%]
.................                                                        [100%]

============================ 305 passed in 10.22s =============================
```

### tests/test_qa_retriever.py（27 项）— 检索质量与可溯源性

| 用例组 | 验证内容 | 结果 |
|---|---|---|
| 分词 | 中文切词、停用词与标点过滤、大小写归一、缓存稳定 | PASS |
| 排序（6 条参数化） | 「宏村」「西递」「马头墙」「徽州三雕」「程大位」等查询的首位必须是对应实体 | PASS |
| 标题完全匹配优先 | 「徽州」检索时，实体本身必须显著高于「徽州婚俗」等派生名称 | PASS |
| 别名可检索 | 数据里登记了别名就必须能被检索到 | PASS |
| 关系叙述进索引 | 「宏村 黟县」能同时召回宏村，且其资料文本中含所属县份 | PASS |
| 分数单调 | 结果严格按相关度降序 | PASS |
| 边界 | 空查询、纯标点、纯虚词、词表外词一律返回空列表（不凑数） | PASS |
| top_k | 条数上限生效，`retrieve_one` 只取一条 | PASS |
| 可溯源性 | 每条结果都带来源且来源有 URL；正文长度受限；命中词被记录 | PASS |
| 确定性 | 同一查询两次结果完全一致 | PASS |

### tests/test_qa_prompt.py（33 项）— 提示词约束与引用解析

| 用例组 | 验证内容 | 结果 |
|---|---|---|
| 系统提示词 | 含「只能使用给定资料」「不许补充」「[1] 引用格式」「资料不足的标准话术」「无关问题的处理」 | PASS |
| 资料编号 | 从 1 开始、含分类与来源出版方；无来源时不伪造「来源：」行 | PASS |
| 长资料截断 | 超出上限时截断并留可见标记 | PASS |
| 空资料 | 明确写「没有找到」而不是留白 | PASS |
| 提示词组装 | 同时包含资料与问题、结尾再强调引用要求；`messages` 角色正确 | PASS |
| 引用解析（6 条参数化） | 半角 `[1]`、全角 `【2】`、连续 `[1][2]`、多位数、非数字括号、空串 | PASS |
| 引用去重保序 | `[3]…[1]…[3]…[1]` → `[3, 1]` | PASS |
| 回答清理（6 条参数化） | 去除 ``` 包裹、「回答：」前缀；内层代码块不被误删 | PASS |
| 问题校验 | 首尾空白归一；空、单字符、超长分别抛出带可读原因的 `QuestionError` | PASS |

### tests/test_qa_engine.py（39 项）— 降级链、后端解析与引用溯源

| 用例组 | 验证内容 | 结果 |
|---|---|---|
| 降级链 | 首个可用后端被使用且不再继续尝试；不可用后端被跳过并记录原因 | PASS |
| 失败降级 | 后端抛 `BackendResponseError` / 未预期异常 / 返回空回答，三种情况均自动降级 | PASS |
| 全链失败 | 抛 `AllBackendsFailedError` 并携带逐条原因，不静默 | PASS |
| 探测健壮性 | 后端 `available()` 自身抛异常时视为不可用，**不会中断问答链路** | PASS |
| 引用溯源 | `[n]` 映射到编号对应的资料；越界编号记入 `invalid_citations` 而非隐藏 | PASS |
| 未引用资料 | 与已引用的不重叠，且两者之和等于检索总数 | PASS |
| grounded | 无引用的回答判定为不可溯源 | PASS |
| 传参正确性 | 后端收到的资料自带来源；问题不合法时**不调用任何后端** | PASS |
| 计时 | 注入 clock，验证 `elapsed_ms` 计算 | PASS |
| 本地后端 | 始终可用；如实说明「资料原文、未经生成」；无资料时说明「不会虚构」 | PASS |
| OpenAI 兼容后端 | 请求 URL/鉴权头/提示词结构（system + user）正确；解析 usage；401、空 choices、空内容、非 JSON、超时、连接失败分别抛出语义化异常 | PASS |
| Dify 后端 | chat 与 workflow 两种路径正确；输出字段回退；缺少答案时抛出异常；配置不全时不可用 | PASS |
| 后端链构造 | 默认顺序为 Dify → LLM → 本地；`QA_FORCE_LOCAL=1` 时只保留本地 | PASS |
| 依赖缺失 | `requests` 缺失时 `requests_post` 抛 `BackendUnavailableError` | PASS |

### tests/test_smoke.py（26 项）— 脚本级冒烟（含问答页真实交互）

新增 9 项问答页用例，**全部通过 `QA_FORCE_LOCAL=1` 走本地检索式后端，因此不联网、不消耗 API 额度**：

| 用例 | 验证内容 | 结果 |
|---|---|---|
| 页面渲染 | 展示真实内容与后端状态，且如实显示「已强制本地」 | PASS |
| 示例问题来源 | 示例问题由当前数据集生成，且引用的实体真实存在 | PASS |
| 真实提问 | 提交问题后返回带引用的回答，每条引用都能落到可点击来源 | PASS |
| 示例按钮 | 点击示例按钮**真的产生一轮问答**（不是装饰性按钮） | PASS |
| 空提问 | 给出提示而非报错或产生空记录 | PASS |
| 清空会话 | 真的清掉历史与输入框内容 | PASS |
| 徽标与链接 | `[n]` 渲染为引用徽标，来源区含 `href` | PASS |
| 检索条数 | 如实显示「检索到 N 条资料，其中 M 条被引用」 | PASS |
| 无降级 | 强制本地模式下不应出现「跳过后端」说明 | PASS |

### 附加验证

| 项目 | 命令 | 结果 |
|---|---|---|
| 数据校验 | `python scripts/validate_data.py` | 96 实体 / 180 关系 / 33 来源 / 11 分类 / 11 关系类型，无孤立点 |
| 图谱保真 | `python scripts/graph_report.py` | 节点 96、边 180，与数据完全一致 |
| 检索实测 | 直接调用 `Retriever.retrieve()` | 「宏村」「马头墙」「徽州三雕」「程大位」「胡适」「绩溪」等查询 Top-1 全部正确 |
| **真实大模型联调** | `QAEngine.ask()` 打真实 DeepSeek 接口 | 问「徽商是什么？」→ 检索 5 条 → `deepseek-chat` 作答 2.1 s / 1707 tokens → 5 处引用全部可核查，`grounded = True` |
| 拒答实测 | 问「量子纠缠与超导体的关系是什么？」 | 模型如实回复「本次检索到的资料与问题无关，无法回答」，未编造内容 |
| 应用健康 | `curl http://localhost:8501/` 与 `/_stcore/health` | 均返回 200 |

### 本阶段由测试暴露并修复的真实缺陷

1. **`ask()` 未保护后端可用性探测**：`availability()` 里对 `backend.available()` 做了异常保护，
   但 `ask()` 里直接调用——一个探测抛异常的后端会让整个问答崩溃。已抽出统一的 `_probe()`
   供三处复用，并补上 `test_availability_never_raises` 钉死该行为。
2. **Streamlit widget 状态回填错误**：示例按钮点击后在渲染阶段写 `st.session_state["qa_input"]`，
   触发 `StreamlitWidgetAlreadyInstantiatedError`（控件已实例化后不能再赋值）。
   改用 `on_click` 回调 + 挂起请求（`qa_pending`）机制；同样的错误也在「清空会话」按钮上修复。
3. **检索测试断言过严**：「宏村 黟县」两个实体分数接近（18.45 / 17.95，后者因标题完全等于查询词而略高），
   原断言要求宏村居首并不成立——改为断言「两个实体都被召回，且宏村的资料含所属县份」。
   「量子纠缠的退相干时间」会被通用词「时间」命中（属 BM25 正常行为，模型会正确拒答），
   原测试误判为缺陷，改用词表外的词验证「检索不到就是空列表」。
4. **设计改进（由观察驱动）**：新增 `EXACT_TITLE_BONUS`。修前「徽州」与「徽州婚俗」得分仅差 0.0008，
   实体本身排不到首位；标题完全等于查询词时给予最高加成后，「徽州」稳定居首。

---

## P5 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 340 items

........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
....................................................                     [100%]

============================ 340 passed in 17.96s =============================
```

### tests/test_agent_workflow.py（26 项）— 步骤顺序、失败中止、日志完整性、核查与纠正

全部用例**离线运行**：后端由 `FakeBackend` 注入、时钟由 `FakeClock` 注入，
既不联网也不消耗 API 额度。

| 用例组 | 验证内容 | 结果 |
|---|---|---|
| 步骤顺序 | `[s.key for s in steps]` 必须严格等于 `STEP_ORDER`，不允许跳步或改序 | PASS |
| 日志完整性 | 每步都有标题（与常量一致）、状态、耗时、输入与输出；**真实执行的步骤耗时必须 > 0** | PASS |
| 日志可读性 | `trace()` 覆盖全部步骤，每步都带状态标签与「输入：/ 输出：」 | PASS |
| 结果助手 | `step()` 命中与未命中、`steps_executed`、`aborted`、`answer`、`citations` 自洽 | PASS |
| 中止（问题不合法） | 第 1 步失败 + 中止，余下步骤全部「跳过」且带中止原因，不产生回答 | PASS |
| 中止（检索不到） | 第 2 步失败 + 中止，**不调用任何后端**（不让模型凭记忆作答） | PASS |
| 中止（后端全挂） | 第 3 步失败 + 中止，逐条失败原因被保留在步骤明细与中止原因里 | PASS |
| 核查（无编号） | 回答里没有 `[n]` 判定为不通过，整体状态降为「完成但存在问题」 | PASS |
| 核查（编号越界） | 引用 `[9]` 被指出，且失败项同时包含「标注了来源编号」与「编号均指向真实资料」 | PASS |
| 核查（资料利用率低） | 只用 1/5 条资料属**警告**而非失败，且警告不触发纠正 | PASS |
| 降级可见 | 后端降级同时出现在核查表与作答步骤明细，不静默发生 | PASS |
| 核查全通过 | 本地检索式后端的回答 6 项核查全过，整体状态为「已按预期完成」 | PASS |
| 纠正成功 | 第一次无编号 → 触发纠正 → 第二次带编号：只重试一次、指令确实传给后端、整体状态为「经自我纠正后完成」、归档的是纠正后的回答 | PASS |
| 纠正失败 | 纠正仍失败时保留第一次的回答，如实报告「核查未通过」，不粉饰 | PASS |
| 提问类型 | 定义类 / 关系类 / 事实属性类 / 开放类各一例（参数化 5 条） | PASS |
| 实体锚定 | 长词优先（「徽州三雕」不被「徽州」抢走）、多实体、无实体三种情形 | PASS |
| 锚定生效 | 锚定实体必须排在检索结果首位，并在检索步骤的输入输出里可见 | PASS |
| 无锚定告警 | 识别不到实体时给出警告但不中断流程 | PASS |
| 示例问题 | 由数据集实时生成，且每条都引用真实存在的实体 | PASS |
| 引擎配合改动 | `answer_from()` 复用传入资料、**不重复检索**（用计数检索器验证调用次数） | PASS |
| 旧式后端兼容 | 不接受 `directive` 参数的后端在常规问答路径上照常工作 | PASS |

### tests/test_qa_prompt.py（38 项，新增 5 项）— 纠正指令

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_prompt_without_directive_has_no_extra_section` | 正常提问的提示词不得凭空多出区块（与 P4 完全一致） | PASS |
| `test_user_prompt_appends_directive` | 传入指令时追加「【补充要求】」区块 | PASS |
| `test_messages_and_dify_query_carry_directive` | OpenAI 兼容后端与 Dify 后端两条路径都能带上指令 | PASS |
| `test_blank_directive_is_ignored` | 空白指令不产生空区块（不制造噪声） | PASS |
| `test_retry_directive_states_the_specific_defect` | 纠正指令直指缺陷（缺编号 / 编号不存在），而非笼统的「请重答」 | PASS |

### tests/test_smoke.py（30 项，P5 新增 6 项并改写 2 项）

问答页与工作流用例**全部通过 `QA_FORCE_LOCAL=1` 走本地检索式后端**，不联网、不消耗额度。

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_about_page_renders_real_content` | 关于项目页渲染真实内容：六个步骤名（来自代码常量）、架构表、开发原则、数据规模来自真实数据集，且**不含「尚未实现」** | PASS |
| `test_about_workflow_timeline_shows_every_step` | 运行工作流后逐步展示 `STEP 1..6`、步骤名、状态标签与耗时，并出现「步骤执行日志 / 引用核查结论 / 最终回答」 | PASS |
| `test_about_workflow_records_input_and_output_per_step` | 每步都有输出、耗时 ≥ 0，且确实是 `StepRecord` 结构；`trace_text()` 的「输入：」条数 = 步骤数 | PASS |
| `test_about_workflow_aborts_honestly_on_unknown_topic` | 资料库没有的主题 → 中途中止、指出「第 2 步中止」、作答步骤为「跳过」 | PASS |
| `test_about_workflow_example_button_actually_runs` | 点击示例按钮**真的运行了一次工作流**（不是装饰性按钮） | PASS |
| `test_about_workflow_clear_button_resets` | 清空按钮真的清掉运行结果与输入 | PASS |

> P4 遗留的两项「待开发页说明阶段」用例（`test_pending_page_explains_its_phase`、
> `test_pending_pages_state_their_phase`）断言的是「about 页标注 P5 且尚未实现」。
> 该页交付后这两个断言已失去意义（继续保留会把已交付说成未交付），
> 因此**改写为** `test_about_page_renders_real_content`——
> 断言它渲染真实内容、六个步骤齐全、且**不含**「尚未实现」。当前 `nav.py` 中已无待开发入口，
> `test_nav.py::test_nav_item_is_either_implemented_or_marked_pending` 仍作为长期约束保留。

### 附加验证

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 语法编译 | `python -m compileall app.py src scripts tests` | 通过 |
| 数据校验 | `python scripts/validate_data.py` | 96 实体 / 180 关系 / 33 来源，无孤立实体 |
| Streamlit 脚本执行 | `AppTest`（关于项目页 + 真实点击运行工作流） | 无异常 |
| 应用启动 | `streamlit run app.py` | `http://localhost:8501/` = 200，`/_stcore/health` = 200 |

### 工作流实测（真实数据集 + 本地检索式后端）

```
问「宏村是什么？」       → 6 步中 5 步执行、纠正被跳过
                          检索 5 条（1 条来自锚定实体）→ 引用 5 处
                          核查 6/6 通过 → 状态「已按预期完成」

问「宏村和西递有什么关系」 → 锚定实体：宏村、西递（关系类）
                          检索 5 条，其中 2 条来自锚定实体

问「量子纠缠与超导体」     → 第 2 步（资料检索）中止
                          余下 4 步全部「跳过」并附中止原因，未产生回答
```

### 本阶段由测试暴露并修正的问题

1. **「成功纠正」的整体状态一度被误判为 degraded**：测试发现纠正成功、核查已全通过，
   但整体状态仍是「完成但存在问题」——因为核查步骤本身留有 warn。
   修正为新增 `corrected`（经自我纠正后完成）状态：核查通过且中途纠正过 → `corrected`，
   既保留「过程值得记一笔」的信息，也不会把一个已修复的问题说成遗留问题。
2. **中止用例的选题不严谨**：原用例用「量子纠缠与超导体的关系」验证「检索不到」，
   但通用词「关系」真实命中了「徽州盐商」等资料（属 BM25 正常行为）。
   改为「量子纠缠与超导体」并加断言钉住「检索不到 = 空列表」，避免用错误案例证明结论。
3. **`answer_from` 的向后兼容**：工作流把检索与作答拆开后，引擎需要在
   `directive` 为空时**只用两个位置参数**调用后端，否则所有既有的假后端与旧式实现都会
   因多出一个关键字参数而失败；该约束由 `test_backend_protocol_without_directive_still_works` 钉死。

---

## P6 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
collected 432 items

........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 66%]
........................................................................ [ 83%]
........................................................................ [100%]

============================ 432 passed in 25.21s =============================
```

P6 不加功能，只做两件事：**把「效果」变成可量化、可复现的东西**，以及**逐条清掉前五个阶段的遗留问题**。
因此本阶段新增了 4 个测试模块/主题，并在三处原有能力上按新发现的缺陷补了断言。

### tests/test_eval.py（39 项）— 评估层：指标、标注集与运行器

**指标部分用手算例子验证**，而不是「跑一遍看它不报错」：

| 分组 | 用例数 | 覆盖内容 | 结果 |
|---|---|---|---|
| 指标纯函数 | 12 | `hit_at_k` 只看前 K 名；`precision_at_k` 的分母**固定为 K**（不是返回条数）；`recall_at_k`；`reciprocal_rank` 等于首次命中位置的倒数；`average_precision` 与逐步累加手算一致；`dcg_at_k` 用指数增益 `(2^g − 1)/log2(i+1)`；`ndcg_at_k` 在理想序下等于 1、把弱相关项放首位会被扣分、无相关项时为 0；分级标注与集合标注两种写法都能读；空序列的均值取 0 | PASS |
| 标注集加载 | 2 | 真实的 42 条检索 + 24 条问答标注能加载并通过校验；问答标注里的实体引用必须真实存在 | PASS |
| 标注集校验（严格） | 10 | 文件缺失、缺 `id`、`id` 重复、相关性等级非法、等级非数值、全是负样本、没有负样本、引用不存在的实体、**应拒答样本不得带期望引用/要点**、可答样本必须至少有一项期望——逐条都抛出可读原因 | PASS |
| 检索评估运行器 | 8 | 同一输入两次结果完全一致（确定性）；报告形状与取值范围；**召回率随 K 单调不减**；标注的负样本检索不到任何东西；词面重叠的负样本会被如实计为失败（不掩盖）；按标签分组的覆盖面；报告可 JSON 序列化 | PASS |
| 回答评估运行器 | 6 | 用 `_ScriptedBackend` 假后端控制回答内容，验证引用覆盖 / 要点命中 / 可溯源；答案缺要点时要点命中率下降；**没有引用即计为「弃答」**；越界编号被记入 `invalid_citations` 而不是隐藏；后端全挂被记录而非吞掉；报告 JSON 往返一致 | PASS |
| CLI | 2 | 离线默认跑通并打印报告；`--ks` 传非法值时报错退出 | PASS |

### tests/test_qa_dify_http.py（15 项）— Dify 后端走**真实 HTTP**，而不是注入假响应

用 `ThreadingHTTPServer` 起一个本地假 Dify 实例，让 `DifyBackend` 走真实的 `requests` 链路。

| 用例组 | 覆盖内容 | 结果 |
|---|---|---|
| 配置校验 | 未配 `DIFY_BASE_URL` / `API_KEY` 时不可用并说明缺什么；不支持的应用类型被明确拒绝 | PASS |
| 请求正确性 | chat 路径与鉴权头、请求体结构正确；`agent` 类型走 chat 端点；`workflow` 类型走 workflow 端点并从 `outputs` 取答案；`outputs` 无法直接取时回退为拼接；`completion` 类型走 completion 端点 | PASS |
| 错误翻译 | 500 / 非 JSON 响应 / 空回答 / 超时 / 连接失败，五种情况都被翻译成本项目自己的语义化异常，不把底层异常漏给上层 | PASS |
| 异常映射 | `_translate_http_error` 对异常类型的映射做确定性测试（与网络环境无关） | PASS |
| 降级联动 | Dify 可用时引擎用它作答并正确生成引用；Dify 失败时自动降级到本地检索式后端 | PASS |

### tests/test_ui_snapshot.py（10 项）— 界面**结构**快照回归

六个页面的结构基线存放在 `tests/snapshots/*.txt`。归一化会抹掉数字与绝对路径，
只统计页面内容的区块、组件类名与控件，**排除 `<style>` 块**（否则每页记录的都是整份主题类名，失去区分度）。

| 用例 | 覆盖内容 | 结果 |
|---|---|---|
| `test_page_structure_matches_snapshot`（参数化 6 页） | 首页 / 百科 / 详情 / 图谱 / 问答 / 关于项目六页的结构与基线一致 | PASS |
| `test_normalise_removes_volatile_numbers_and_paths` | 归一化确实抹掉了易变内容（否则基线会天天失败） | PASS |
| `test_snapshot_captures_sections_classes_and_widgets` | 快照确实抓到了区块、类名与控件（不是只记了个标题） | PASS |
| `test_diff_reports_added_and_missing_lines` | 差异输出能分别报出「多出来的」与「少掉的」行 | PASS |
| `test_all_nav_pages_are_covered` | 导航里的每个可见页面都在快照覆盖范围内（防止新页面漏测） | PASS |

> **边界声明**：这一层只保证**结构**不意外变形，**不宣称像素级视觉回归**——
> 样式表改了个颜色、间距变了 2px，它不会报错。真实浏览器截图对比仍未做，
> 已列入「尚未覆盖」。

### tests/test_graph.py（69 项，P6 新增 9 项）— 大图规模守卫与性能预算

当前 96 节点触发不了分片，因此用**合成大图**验证能力，同时钉住「小图行为一个字节都不变」。

| 新增用例 | 覆盖内容 | 结果 |
|---|---|---|
| `test_small_graph_is_not_sharded` | 节点数在预算内时只有一片（默认行为不变） | PASS |
| `test_sharded_html_matches_single_html_for_small_graph` | 小图的分片渲染产物与不分片渲染**逐字节一致** | PASS |
| `test_large_graph_is_split_within_budget` | 合成 600 节点图被切成多片，每片都在预算内 | PASS |
| `test_large_single_category_is_chunked` | 单个分类自身超预算时按度数降序再切块（不会产出超大片） | PASS |
| `test_shard_labels_are_reproducible` | 同一输入两次得到相同的分片标签与顺序 | PASS |
| `test_shards_keep_only_internal_edges` | 片内只保留片内的边，不把跨片边算进去 | PASS |
| `test_build_sharded_html_renders_every_shard_offline` | 每一片的 HTML 都无外部资源引用（离线自洽） | PASS |
| `test_focus_only_applies_to_the_shard_containing_it` | 聚焦节点只作用于包含它的那一片 | PASS |
| `test_current_graph_render_within_latency_and_size_budget` | 当前真实图（96 节点）渲染 < 3 s 且产物 < 2048 KB | PASS |

### tests/test_image_library.py（25 项，P6 新增 12 项）— 抓取把关必须被钉住

P6 发现补抓进来的图片里混了 4 张不该收的（详见「本阶段暴露并修正的问题」）。
把关规则因此被抽成**纯函数**（`target_gate` / `candidate_rejection`）并逐条断言：

| 新增用例 | 覆盖内容 | 结果 |
|---|---|---|
| `test_target_gates_reject_the_candidates_actually_downloaded_by_mistake`（参数化 3 条） | 三个**真实误召回**的文件名必须被挡住：广东江河航拍（渐江）、白云寺院门（徽州牌坊）、无锡惠山祠堂（徽州祠堂） | PASS |
| `test_manifest_entries_pass_their_own_relevance_gate` | 清单里**每一张图**都能通过它所属实体的把关；只看 Commons 侧的标题与文件名，不看自写图注（否则图注写个实体名就能「自我证明」） | PASS |
| `test_target_specs_cover_every_target_and_are_non_trivial` | 每个目标实体都有把关条件且必含词非空 | PASS |
| `test_candidate_rejection_rules`（参数化 8 条） | 无作者 / 空白作者 / 许可不合规 / 格式不支持 / 尺寸缺失 / 画幅异常 / 分辨率过低 各被拦下，全部合格时返回 `None` | PASS |
| `test_candidate_without_author_is_rejected_not_credited_blindly` | Commons 未登记作者的老照片一律不收——宁可缺图，也不写一条署不出作者的图片 | PASS |

### 其余模块的增补

| 文件 | 增补内容 | 结果 |
|---|---|---|
| `tests/test_qa_engine.py`（39 → 42） | `is_config_skip` 识别「未配置 / 不受支持 / 未安装」；运行时故障不被误判为配置性跳过；`split_degradations` 保持原顺序并正确分类 | PASS |
| `tests/test_agent_workflow.py`（26 → 27） | `test_config_skip_is_visible_but_not_treated_as_a_fault`——「未配 Dify」仍要**可见**，但整体状态必须是「已按预期完成」；另加 `test_runtime_backend_failure_is_warned` 保证真故障仍报警 | PASS |
| `tests/test_components.py`（12 → 15） | `metric_grid` 的渲染、HTML 转义、空输入 | PASS |
| `tests/test_smoke.py`（30） | 未增用例；六页冒烟与「真实点击」用例继续覆盖新增的评估区块与图谱分片渲染 | PASS |

### 附加验证（不在自动化测试内，单独手动执行）

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 质量评估（离线） | `python scripts/evaluate.py` | 24 条问答与 42 条检索标注全部跑通，结果见下表 |
| 质量评估（真实后端） | `python scripts/evaluate.py --live` | DeepSeek `deepseek-chat`，24 题 / 23 s |
| 真实工作流 | 走真实后端跑 4 个问题 | 1 个「已按预期完成」、1 个「完成但存在问题」（真信号）、1 个中途中止，详见下 |
| 图片抓取 | `python scripts/fetch_images.py` | 11 → 20 张；逐张目视核查后剔除 4 张，**实收 15 张** |
| 图片补抓（替代被剔除的 4 条） | 用更精准检索词后台重跑 6 次查询 | **未取到任何候选**（免费中转池全部限流/冷却，10 分钟后停止）——如实记为「没成」，未改动清单 |
| 语法编译 | `python -m compileall app.py src scripts tests` | 通过 |
| 数据校验 | `python scripts/validate_data.py` | 96 实体 / 180 关系 / 33 来源，无孤立实体 |
| 应用启动 | `streamlit run app.py` | `/` = 200，`/_stcore/health` = 200 |

**检索评估实测（离线，42 条标注）**

```
Hit@1 / @3 / @5 = 1.000 / 1.000 / 1.000      MRR = 1.000
Precision@5 = 0.372                          MAP = 0.819
Recall@1 / @3 / @5 = 0.530 / 0.814 / 0.846   nDCG@5 = 0.938
负样本正确留空 0.667（6 条中 4 条）

按标签分组（命中率 / 召回@5）
  专名 10 条   1.000 / 1.000      关系 8 条   1.000 / 0.896
  别名 10 条   1.000 / 0.783      概念 7 条   1.000 / 0.635
  属性  1 条   1.000 / 1.000      负样本 6 条 留空 0.667
  词面重叠 2 条 留空 0.000
```

> Hit@K 全为 1.000 说明「答案所在的那条资料排在前 K」几乎总成立；**短板在 Recall**——
> 一条查询通常只召回标准答案中的部分实体，概念类最明显（0.635）。

**回答评估实测（离线 / 真实后端对比）**

| 指标 | 离线（本地检索式后端） | 真实后端（DeepSeek） |
|---|---|---|
| 引用覆盖率 | 1.000 | 0.976 |
| 要点命中率 | 1.000 | 0.976 |
| 可溯源率 | 1.000 | 1.000 |
| 作答率 | 1.000 | 1.000 |
| 拒答判断正确率 | 1.000 | 1.000 |
| 无编造编号率 | 1.000 | 1.000 |

真实后端下唯一未答全的一条：「马头墙的作用是什么」没答出别名「封火墙」。
3 条域外问题全部被正确拒答，且**未出现任何编造编号**。

**真实工作流实测（DeepSeek `deepseek-chat`）**

```
问「徽商是什么？」      → 5 步执行、引用 5 处、核查 6/6 通过 → 已按预期完成
问「宏村位于哪个县？」   → 引用 2/5 条资料 → 「资料利用率偏低」警告 → 完成但存在问题
问「量子纠缠与超导体」   → 第 2 步中止、余 4 步跳过、未生成任何回答
```

中间那条的警告是**真信号**（答对了，但只用了 5 条资料里的 2 条），与「概念类召回 0.635」
指向同一个问题——工作流没有把它粉饰成「完成」。

### 本阶段由测试与真实运行暴露并修正的问题

1. **别名不可见（真实产品缺陷）**：别名参与分词与匹配，却没有出现在送进后端的资料正文里，
   于是「徽商又被称为什么」这类问题必然答不出别名。评估首轮即抓到，修正后要点命中 **0.857 → 1.000**。
2. **「没配」被当成「出错」（真实设计缺陷）**：真实运行中**每一次**都被判为「完成但存在问题」，
   因为核查项把「Dify：未配置 DIFY_BASE_URL」也算作了问题。改为按性质区分
   「配置性跳过」与「运行时故障」后，同一次运行变为「已按预期完成」，而真故障仍然报警。
3. **补抓的图片混进了图文不符的（本阶段最严重）**：交付测试先抓到 `huangbinhong` 缺作者，
   顺着逐张目视核查又发现 3 张图注与底层 Commons 文件根本不是一回事——
   「渐江」下到广东江河航拍、「徽州牌坊」下到白云寺院门、「徽州祠堂」下到无锡惠山祠堂。
   界面会因此**宣称错误的事实**。修正：剔除这 4 条（清单 19 → 15，同时删除图片文件不留孤儿图）、
   收录门槛新增「Commons 上登记了作者」、把关抽成纯函数并由 12 项新用例钉住。
4. **单线程假 HTTP 服务器挂死测试**：`HTTPServer` 在 HTTP/1.1 keep-alive 下会停在原连接上，
   `shutdown()` 永久阻塞（测试被 SIGTERM）。改用 `ThreadingHTTPServer` + 守护线程。
5. **代理环境下的断言不成立**：本机设有 HTTP 代理，连接失败可能被代理回成 502 而非抛
   `ConnectionError`。改为断言真正的不变量（异常必须被翻译成本项目自己的异常），
   并把「异常类型 → 语义化异常」的映射单独做确定性测试。
6. **快照把全局样式表算进页面**：导致每页记录的都是整份主题类名，失去区分度。改为只统计页面内容。
7. **标注 id 打错**：`chengzitang` 应为 `chengzhitang`。标注校验器直接拦下并指到具体 case——
   这正是「标注集按基准数据严格校验」的价值。

---

## 交付后调整：界面按「谁在看」重新分层

**执行时间**：2026-10-16（P6 交付后，依据实际使用反馈）
**命令**：`.venv\Scripts\python.exe -m pytest`

```
collected 437 items

........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 66%]
........................................................................ [ 83%]
........................................................................ [100%]

============================ 437 passed in 27.83s =============================
```

三处改动都不改变功能本身，只调整**信息架构**：

| 改动 | 涉及文件 | 说明 |
|---|---|---|
| 环境自检搬到「关于项目」页 | `src/ui/pages/home.py`、`about.py` | 运行依赖 / 文化数据 / 模块交付进度整块迁移；首页删除页尾的阶段进度播报 |
| 首页新增徽州主视觉图 | `src/ui/pages/home.py` | 取自图片库的「徽派建筑」图，自动继承署名（作者 / 许可 / 来源页面）；无图时整块不渲染 |
| 百科页默认顺序「有配图优先」 | `src/ui/pages/explore.py` | 仅作用于默认浏览顺序；检索结果与显式排序不受影响 |

### tests/test_smoke.py（35 项，本次新增 5 项）

| 用例 | 断言内容 | 结果 |
|---|---|---|
| `test_home_shows_a_credited_hero_image` | 首页恰好渲染 1 张图片，且图注与作者署名同时出现在页面上 | PASS |
| `test_home_hero_image_entity_is_a_real_credited_image` | 主视觉引用的实体必须在图片库中、文件存在、有作者、来源为 Commons | PASS |
| `test_environment_check_lives_on_about_page_not_home` | 首页不再出现「环境自检 / 模块交付进度 / 运行依赖」，关于页四个区块齐全 | PASS |
| `test_explore_default_order_puts_illustrated_entities_first` | 有图实体全部排在无图实体之前，且无图部分保持数据原顺序 | PASS |
| `test_explore_search_and_explicit_sorts_ignore_image_priority` | 检索结果与「按名称」「按关联关系数」排序均不受「有配图优先」影响 | PASS |

**其中第 2 项专门拦「静默失效」**：主视觉的实体 id 写错时页面**不报错**、只是少一张图，
这类问题只有断言才发现得了。

**原本依赖具体排序的断言已修正**：`test_explore_button_actually_navigates_to_detail`
原先直接点 `ex_open_hongcun`，隐含「宏村在第一页」这一前提；默认顺序改为有配图优先后
宏村不再落在第一页。改为取列表里第一张卡片的按钮、并从按钮 key 反推期望跳转的实体——
它该测的是「按钮真的会跳转」，而不是「谁排在第一」。

### 界面结构快照基线（有意变更）

`tests/snapshots/{home,about,explore}.txt` 三份基线重新生成，差异逐行核对：

| 页面 | 变化 | 结果 |
|---|---|---|
| home | 少了「环境自检 / 运行依赖 / 文化数据 / 模块交付进度」4 个区块，多了 `hz-figure` 类（主视觉图注），内容块 18 → 15 | PASS |
| about | 多出上述 4 个区块，内容块 27 → 32 | PASS |
| explore | 第一页实体卡片换成有配图的那批（`chengzhitang`、`huizhou_minju` 等进入第一页） | PASS |

### 应用实际启动验证

```
Local URL: http://localhost:8512   → HTTP 200
```

> 本节的用例名与机制在下一节（第二轮调整）中已随之更新：主视觉改为项目自备素材后，
> `test_home_shows_a_credited_hero_image` 与 `test_home_hero_image_entity_is_a_real_credited_image`
> 被替换为下面新章节列出的两个用例。此处保留当时的原始记录。

---

## 交付后调整（第二轮）：主视觉换素材、图谱去浮层

**执行时间**：2026-10-16（第一轮调整之后，依据实际使用反馈）
**命令**：`.venv\Scripts\python.exe -m pytest`

```
collected 437 items
........................................................................ [100%]
============================ 437 passed in 34.31s ============================
```

| 改动 | 涉及文件 | 说明 |
|---|---|---|
| 首页主视觉换成项目自备的宏村南湖全景图 | `src/ui/pages/home.py`、`assets/images/hero_hongcun_nanhu.jpg` | 原按实体 id 从 Commons 清单取图；新图无可追溯授权，改为独立文件常量，**不混进清单** |
| 图谱节点不再带悬停浮层 | `src/graph/visualize.py`、`src/ui/pages/graph.py` | 节点不设 `title`，鼠标停上去不弹任何内容；**关系仍保留悬停说明** |
| 侧边栏版本行去掉阶段进度 | `app.py` | 原文停在「已完成 P0 … P5」，而当时 P6 早已交付；现只留版本号 |

### 本轮新增 / 改写的用例

| 用例 | 断言内容 | 结果 |
|---|---|---|
| `test_home_shows_the_hero_image` | 首页恰好渲染 1 张图片，**图注与来源声明**同时出现 | PASS |
| `test_home_hero_image_is_a_local_asset_and_kept_out_of_the_manifest` | 主视觉文件必须存在且非空；**不得出现在 Commons 署名清单里**；首页**不得**声称它是自由授权作品 | PASS |
| `test_graph.py` 载荷一致性用例（新增一条断言） | `assert "title" not in node`——节点不带悬停浮层；关系仍必须有悬停说明 | PASS |

**这两组断言拦的都是「界面宣称错误事实」**：

- 换图后如果沿用原来那句「图片为自由授权作品，署名与许可见图注」，页面就在说假话——
  这张图没有作者与许可可查。所以断言反向钉住：首页**不得**出现这类说法。
- 主视觉文件缺失时页面**不报错**、只是静默少一张图，因此断言直接检查文件在不在。

**测试辅助函数一并修正**：`_body()` 原先只收集 `markdown`，漏掉页面上用 `st.caption`
写的说明（图注来源声明正是 caption），导致断言「说明文字在页面上」时假失败。
现同时收集 `markdown` 与 `caption`。

### 产物与性能变化

| 指标 | 改动前 | 改动后 |
|---|---|---|
| 图谱 HTML 体积（96 节点 / 180 边） | 830 KB | **790 KB**（少了 96 条节点的浮层内容） |
| 节点带悬停说明的数量 | 96 | **0** |

### 应用实际启动验证

```
Local URL: http://localhost:8514   → HTTP 200
```

---

## 尚未覆盖 / 遗留问题

下表是最终状态：已解决项写明**靠什么解决、结果如何**，未解决项写明**为什么没做**。

| 项目 | 状态 | 说明与下一步 |
|---|---|---|
| 工作流测试 | ✅ 已解决（P5） | 27 项用例覆盖步骤顺序、失败中止、日志完整性、核查与纠正 |
| 无检索召回标注集 | ✅ 已解决（P6） | 42 条人工标注（36 有答案 + 6 负样本）+ 指标实现；实测 Recall@1 0.530 / @5 0.846、nDCG@5 0.938、MRR 1.000 |
| 无语义质量金标准 | ✅ 已解决（P6） | 24 条问答标注（21 可答 + 3 应拒答）+ 6 项回答侧指标；离线全 1.000，真实 DeepSeek 下引用覆盖与要点命中 0.976 |
| 无界面回归 | ✅ 已解决（P6，有边界） | 六页**结构**快照回归；明确**不宣称**像素级视觉回归 |
| 大图性能未处理 | ✅ 已解决（P6） | 按分类规模守卫分片；实测 96 节点 0.07 s / 852 KB，合成 600 节点图正确切片；小图产物逐字节不变 |
| 图片素材 | ⚠️ 部分解决（P6） | 11 → 20 张；逐张核查后剔除 4 张图文不符/无法署名的，**实收 15/29**。其余 14 个目标的失败原因逐条登记在 `CREDITS.md`。门槛提高后本可更少——这是有意的取舍。首页主视觉是项目自备素材，已如实声明非自由授权（见决策 2.24） |
| 纠正重试无真实样本 | ⚠️ 部分解决（P6） | 用真实 DeepSeek 跑通了工作流，并借此修掉了「未配置被当成降级」的判定缺陷；但真实模型**触发纠正重试**的样本仍未取到（纠正只在回答缺编号或编号越界时才触发，真实模型很少犯这个错） |
| Dify 后端联调 | ⚠️ 部分解决（P6） | 已用**本地假 Dify 实例走真实 `requests` 链路**（15 项，覆盖路径 / 鉴权头 / 请求体 / chat·agent·workflow·completion 解析 / 500 / 非法 JSON / 空回答 / 超时 / 连接失败 / 降级联动）。仍未与**真实 Dify 服务**联调——本机没有可用实例 |
| 概念类召回偏低 | ❌ 未解决 | 概念类查询 Recall@5 仅 **0.635**，关系类查询常能召回主体却召不回对象实体（如「宏村属于哪个县」时「黟县」不在前 5）。可能的解法是引入**关系三元组级**的检索单元，而不是以「实体」为唯一资料粒度 |
| 词面重叠负样本 | ❌ 未解决 | 2 条词面重叠的负样本仍会被误召回（正确留空 0.000）。这是词袋检索（BM25）的固有局限，需换检索模型才能根治 |
| 样式退化无人看守 | ❌ 未解决 | 结构快照只保证结构不变形，改颜色 / 间距不会报错。真实浏览器截图对比仍在计划中 |
| 图片 15/29 的补齐 | ❌ 未解决 | 受免费中转额度（Microlink 约 15 次/日，其余中转间歇限流）与本机对 Wikimedia 的 SNI 域名级阻断限制。**试过一轮补抓未取到任何候选**；额度恢复后重跑 `python scripts/fetch_images.py` 即可（把关已就位，候选会自动按三条门槛筛一遍） |

> 说明：本报告只记录**实际执行过**的测试结果；未实现的模块不会被标记为通过。
>
> 全部 **437 项测试不联网**：问答页与工作流测试通过 `QA_FORCE_LOCAL=1` 强制本地后端，
> 引擎与工作流测试通过注入假后端、假时钟覆盖降级链与失败分支，
> 评估测试固定用本地检索式后端（因此指标可复现），图片库测试只读本地清单与纯函数。
> 真实大模型联调、图片抓取另行手动执行，结果如实记录在「附加验证」中（不混入自动化测试）。
>
> P3 阶段由测试暴露并修复的真实缺陷：百科页空状态断言把注入的 CSS 规则误判为渲染内容
> （改为断言 `class="hz-ecard"` 出现与否）、组件测试传参不一致导致「0 条来源」误断言。
> 另外 `test_graph.py` 与 `test_smoke.py` 中原先硬编码的数量断言（`== 90` / `== 150` / `== 26`）
> 已统一改为**从数据集动态取期望值**，使数据扩充不再引发脆弱的假失败。
>
> 图片抓取过程中另修复三个实际缺陷：**URL 二次编码**（中文文件名被 `urlencode` 再编码成
> `%25E9…` 导致取不到图）、**清单覆盖写**（分批续跑会抹掉上一批成果，改为按 `entity_id` 合并）、
> 以及 P6 发现的**相关性把关失效**（见上方「本阶段暴露并修正的问题」第 3 条）。
