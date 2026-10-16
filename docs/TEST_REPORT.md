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

**当前累计：72 通过 / 0 失败 / 0 跳过。**

分文件用例数：

```
tests/test_config.py            8
tests/test_data_integrity.py   14
tests/test_loader.py           20
tests/test_repository.py       25
tests/test_smoke.py             5
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

## 尚未覆盖 / 遗留问题

| 项目 | 说明 | 计划 |
|---|---|---|
| 图谱测试 | 图谱模块尚未实现 | P2 |
| 检索与问答测试 | 检索与三层后端尚未实现 | P4 |
| 工作流测试 | 智能体工作流尚未实现 | P5 |
| 界面视觉回归 | 暂无截图对比测试 | P6 视情况补充 |
| 真实模型联调 | API Key 已验证可用（HTTP 200），但问答链路尚未实现，未做端到端联调 | P4 |
| 数据规模 | 实际交付 90 个实体，略高于原计划的 60–80；已确认无孤立节点 | 视需要继续扩充 |

> 说明：本报告只记录**实际执行过**的测试结果；未实现的模块不会被标记为通过。
