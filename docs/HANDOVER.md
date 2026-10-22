# 交付与部署说明

这份文档按「**对方拿到仓库后要做什么**」整理，包含打包清单、对方的启动步骤与离线部署说明。
均在本机实测过；主页 `README.md` 只保留面向读者的内容。

---

## 打包清单

这份作品通常要发给老师验收。以下清单按「**对方拿到后会怎样**」整理，均已在本地实测。

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
| `.env` | 你的 API Key。已被 `.gitignore` 忽略，用 `git archive` 打包时**不会被包含**；若是手动复制文件夹，务必先删掉它 |
| `__pycache__/` `.pytest_cache/` `.tmp_probe/` `outputs/` `*.log` | 本地缓存与运行产物，可重建 |
| `.workbuddy/` | 本地个人工作区记录 |

### 推荐打包方式：用 `git archive`（最干净）

它只会打包**已纳入版本库的文件**，自动排除上面全部不该带的东西：

```bat
git archive --format=zip -o huizhi-culture.zip HEAD
```

产出约 **3.3 MB**（16 张徽州图片 + 5 张界面截图占主要体积），可直接作为邮件附件。

### 对方（导师）收到后要做什么

```bat
python --version                         :: 必须 >= 3.12（见「环境要求」）
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
streamlit run app.py
```

**不需要 API Key**：未配置 `.env` 时问答会自动降级到本地检索式后端（纯离线），
界面会明确显示当前后端为「本地检索式（离线可用）」，回答依旧带来源引用。
这一路径已在**删除 `.env` 的干净副本**上实测：应用正常启动、问答返回 5 条可溯源引用、
437 个用例全部通过。

> 若对方完全无法联网安装依赖，可另行准备离线 wheel 包
> （`pip download -r requirements.txt -d wheels/ --platform win_amd64 …`），
> 本项目未提供开箱即用的离线包。

> 注意：若把 `.git` 目录一并发出，对方能看到完整提交历史，
> 其中含提交者姓名与邮箱（`git log` 可见）。介意的话请只发 zip 包内容。
