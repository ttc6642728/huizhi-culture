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

**当前累计：305 通过 / 0 失败 / 0 跳过。** 无弃用或运行时警告。

> 用例数大于测试函数数：部分测试用 `@pytest.mark.parametrize` 展开
> （如「一府六县」六个县份各一条用例）。当前共 **274 个测试函数 / 305 个用例**。

分文件用例数（P4 后）：

```
tests/test_components.py       12
tests/test_config.py            8
tests/test_data_integrity.py   26
tests/test_graph.py            60
tests/test_image_library.py    13
tests/test_loader.py           20
tests/test_nav.py              16
tests/test_qa_engine.py        39
tests/test_qa_prompt.py        33
tests/test_qa_retriever.py     27
tests/test_repository.py       25
tests/test_smoke.py            26
--------------------------------------------------
合计                          305
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

## 尚未覆盖 / 遗留问题

| 项目 | 说明 | 计划 |
|---|---|---|
| 工作流测试 | 智能体工作流尚未实现 | P5 |
| Dify 后端联调 | 本机未自建 Dify 实例，`DifyBackend` 仅通过注入的假 HTTP 响应做了单元验证，未做真实端到端联调 | 有可用 Dify 实例时补测 |
| 图片素材 | 已收录 11 张真实图片；检索侧受 Microlink 免费额度（约 15 次/日）限制，未覆盖全部 29 个目标实体 | 额度恢复后重跑 `scripts/fetch_images.py`，或用 `--from-resolved` 续跑 |
| 大图性能 | 当前 96 节点的交互式渲染实测约 830 KB；若实体超过 300 个需引入分片或预布局 | 视数据规模而定 |
| 界面视觉回归 | 暂无截图对比测试 | P6 视情况补充 |
| 回答质量评估 | 有引用覆盖率（`grounded`）等结构性断言，但没有回答内容的语义质量评估 | P6 视情况补充金标准问答对 |
| 检索召回评估 | 有确定性与排序断言，但没有 Recall@K 标注集 | 视需要补充 |

> 说明：本报告只记录**实际执行过**的测试结果；未实现的模块不会被标记为通过。
>
> 全部 305 项测试**不联网**：问答页测试通过 `QA_FORCE_LOCAL=1` 强制本地后端，
> 引擎测试通过注入假后端与假 HTTP 响应覆盖降级链，因此可离线复现、不消耗 API 额度。
> 真实大模型联调单独手动执行，结果如实记录在「附加验证」中（不混入自动化测试）。
>
> P3 阶段由测试暴露并修复的真实缺陷：百科页空状态断言把注入的 CSS 规则误判为渲染内容
> （改为断言 `class="hz-ecard"` 出现与否）、组件测试传参不一致导致「0 条来源」误断言。
> 另外 `test_graph.py` 与 `test_smoke.py` 中原先硬编码的数量断言（`== 90` / `== 150` / `== 26`）
> 已统一改为**从数据集动态取期望值**，使数据扩充不再引发脆弱的假失败。
>
> 图片抓取过程中另修复两个实际缺陷：**URL 二次编码**（中文文件名被 `urlencode` 再编码成
> `%25E9…` 导致取不到图）与**清单覆盖写**（分批续跑会抹掉上一批成果，改为按 `entity_id` 合并）。
