# 部署与交付

本文档回答两件事：**怎么把它挂到网上**（Streamlit Community Cloud 免费部署），以及
**怎么把它完整交给别人**（打包清单与对方的启动步骤）。两项均在本机实测过。

---

## 一、部署到 Streamlit Community Cloud（免服务器、免费）

用 GitHub 账号登录即可，不需要信用卡，也不需要任何 API Key。

### 前置条件

1. 仓库已推送到 GitHub，且为 **public**（免费版只支持公开仓库）。
2. 应用入口是仓库根目录的 `app.py`（本项目已满足）。

### 部署步骤

1. 打开 <https://share.streamlit.io> → **Sign in with GitHub** → 授权。
2. 点 **Create app** → 选 **Deploy a public app from GitHub**。
3. 填写：
   - Repository：`<你的用户名>/huizhi-culture`
   - Branch：`main`
   - Main file path：`app.py`
4. 展开 **Advanced settings**，把 **Python version 选成 3.12 或 3.13**。
   > 这一步不能省：`networkx 3.7` 与 `numpy 2.5` 要求 Python ≥ 3.12，
   > 用默认的低版本会在依赖解析阶段直接失败。
5. 点 **Deploy**。首次构建要装 6 个依赖，约 3–8 分钟；之后每次 `git push` 会自动重新部署。

部署完成后会得到一个形如 `https://huizhi-culture.streamlit.app` 的链接，可以直接发给别人。

### 不需要配置 Secrets

未配置任何密钥时，问答会自动落到第三层「本地检索式」后端，页面会明确显示当前后端，
回答依旧带来源引用。**不要在 Secrets 里填 `.env` 里的 Key**——公开仓库的演示没必要消耗你的额度。

如果确实想演示大模型作答，在 App → Settings → Secrets 里按 `.env.example` 的键名填写
`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（Secrets 不会进入仓库）。

### 已知的云端表现

| 现象 | 原因 |
|---|---|
| 闲置一段时间后首次访问要等 20–40 秒 | 免费版实例会休眠，有人访问时再唤醒 |
| 中文衬线字体显示为系统默认衬线体 | 云端 Linux 没有「Noto Serif SC」，会走 `serif` 回退，属预期 |
| 重启后追问历史清空 | 问答历史只存在 `st.session_state`，本设计如此（无用户系统、不落库） |

---

## 二、打包交给别人（邮件 / U 盘）

### 必须随包

```
app.py               conftest.py         pytest.ini        requirements.txt
src/                 data/               assets/images/    docs/
tests/               .env.example        .gitignore        README.md
LICENSE
```

### 不能随包

| 目录 / 文件 | 为什么不能带 |
|---|---|
| `.venv/` | Windows 虚拟环境的 `python.exe` 通过 `pyvenv.cfg` **指回你本机的解释器路径**，换机器后无法运行，必须由对方重建 |
| `.env` | 你的 API Key。已被 `.gitignore` 忽略，`git archive` 打包时不会被包含；手动复制文件夹时务必先删掉 |
| `__pycache__/` `.pytest_cache/` `outputs/` `*.log` | 本地缓存与运行产物，可重建 |
| `.workbuddy/` | 本地个人工作区记录 |

### 推荐打包方式

```bash
git archive --format=zip -o huizhi-culture.zip HEAD
```

只打包**已纳入版本库的文件**，上面不该带的东西会被自动排除。产出约 **3.3 MB**（图片占主要体积）。

### 对方收到后

```bash
python --version                      # 必须 >= 3.12
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py                  # 打开 http://localhost:8501
pytest                                # 437 个用例，不联网
```

**不需要 API Key**：未配置 `.env` 时自动降级到本地检索式后端。
这一路径已在**删除 `.env` 的干净副本**上实测：应用正常启动、问答返回可溯源引用、437 个用例全通过。

> 若对方完全无法联网安装依赖，可另行准备离线 wheel 包
> （`pip download -r requirements.txt -d wheels/ --platform win_amd64`），
> 本项目未提供开箱即用的离线包。

---

## 三、GitHub 仓库设置建议

推送后在仓库页面右上角 **About**（齿轮图标）里填：

- **Description**：`徽州文化知识图谱 + 可溯源 AI 问答：96 实体 / 180 关系，Streamlit + NetworkX + PyVis + Dify 三层降级，437 个离线测试`
- **Topics**：`knowledge-graph` `streamlit` `rag` `llm` `networkx` `pyvis` `dify` `chinese` `cultural-heritage` `python`
- **Website**：填 Streamlit Cloud 给你的那个链接

README 顶部的 CI 徽章指向 `actions/workflows/tests.yml`，仓库名与分支若与此不同需相应修改。
