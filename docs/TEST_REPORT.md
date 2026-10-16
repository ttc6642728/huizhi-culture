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

## P0 阶段测试记录

**执行时间**：2026-10-16
**命令**：`.venv\Scripts\python.exe -m pytest -v`

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.7.0
rootdir: E:\huizhi-culture
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 13 items

tests\test_config.py ........                                            [ 61%]
tests\test_smoke.py .....                                                [100%]

============================= 13 passed in 1.43s ==============================
```

**结果：13 通过 / 0 失败 / 0 跳过**

### 用例明细

#### tests/test_config.py（8 项）

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_paths_are_absolute_and_rooted_in_project` | 路径常量均为绝对路径且位于项目内 | PASS |
| `test_dify_config_requires_both_url_and_key` | Dify 需同时具备 URL 与 Key 才算已配置 | PASS |
| `test_llm_config_requires_url_key_and_model` | 大模型需同时具备 URL / Key / 模型名 | PASS |
| `test_resolve_backend_falls_back_to_local` | 无任何凭证时降级为本地检索式 | PASS |
| `test_resolve_backend_prefers_dify_over_llm` | 两者都配置时优先 Dify | PASS |
| `test_resolve_backend_uses_llm_when_dify_absent` | 无 Dify 时使用大模型后端 | PASS |
| `test_force_local_overrides_everything` | `QA_FORCE_LOCAL=true` 可强制离线 | PASS |
| `test_top_k_is_clamped_to_at_least_one` | 非法 / 越界配置回退默认值 | PASS |

#### tests/test_smoke.py（5 项）

使用 Streamlit 官方 `AppTest` 在无浏览器环境下真实执行 `app.py`：

| 用例 | 验证内容 | 结果 |
|---|---|---|
| `test_app_file_exists` | 应用入口文件存在 | PASS |
| `test_app_runs_without_exception` | 脚本完整执行且无异常 | PASS |
| `test_default_page_renders_navigation` | 侧边栏含全部规划页面导航项 | PASS |
| `test_pending_page_explains_its_phase` | 未实现页面如实标注交付阶段 | PASS |
| `test_unknown_page_falls_back_to_default` | 非法页面标识回退首页 | PASS |

### 附加验证

| 验证方式 | 命令 | 结果 |
|---|---|---|
| 语法编译 | `python -m compileall app.py src` | 通过，无语法错误 |
| 服务启动 | `streamlit run app.py --server.headless true` | 启动成功 |
| 健康检查 | `GET /_stcore/health` | `200` |
| 首页响应 | `GET /` | `200`，返回 6467 字节 |

---

## 尚未覆盖 / 遗留问题

| 项目 | 说明 | 计划 |
|---|---|---|
| 数据层测试 | 文化数据尚未编写，无内容可测 | P1 |
| 图谱测试 | 图谱模块尚未实现 | P2 |
| 检索与问答测试 | 检索与三层后端尚未实现 | P4 |
| 工作流测试 | 智能体工作流尚未实现 | P5 |
| 界面视觉回归 | 暂无截图对比测试 | P6 视情况补充 |
| 真实模型联调 | 尚未提供 API Key，目前仅验证本地检索式路径 | 用户提供 Key 后补充 |

> 说明：本报告只记录**实际执行过**的测试结果；未实现的模块不会被标记为通过。
