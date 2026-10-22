# 快速开始

三步跑起「徽知 · Huizhou Culture Explorer」。完整说明见 [`../README.md`](../README.md)。

## 一、环境要求

- **Python 3.12 或更高**（查看：`python --version`）
- 首次安装依赖需要联网（约 150–250 MB），装好之后运行不再需要网络

## 二、首次运行

在本项目文件夹内打开命令行，依次执行：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
streamlit run app.py
```

macOS / Linux 把第二行换成 `source .venv/bin/activate`。

浏览器会自动打开 `http://localhost:8501`；若 8501 端口被占用，命令行会给出实际地址。

## 三、日常运行（已装好依赖后）

```bat
.venv\Scripts\activate
streamlit run app.py
```

## 四、关于 API Key（很重要）

**不需要配置任何 Key 也能正常使用。** 问答有三层后端，会自动降级：

| 顺序 | 后端 | 前提 |
|---|---|---|
| 1 | Dify 知识库 / 工作流 | 在 `.env` 里配置 |
| 2 | OpenAI 兼容大模型 | 在 `.env` 里配置 |
| 3 | 本地检索式（离线） | **无需任何配置** |

未配置 `.env` 时自动使用第 3 层：纯离线运行，问答依旧带来源引用。
页面会明确显示当前使用的是哪个后端，不会把本地检索伪装成大模型。

若要启用真实大模型，把 `.env.example` 复制为 `.env` 并填入自己的密钥即可。
`.env` 含密钥，**绝不要随项目一起发给别人**（它已被 `.gitignore` 忽略）。

## 五、其它命令

```bat
pytest                                 :: 运行全部测试（437 个用例，约 30 秒，不联网）
python scripts/validate_data.py        :: 数据校验
python scripts/evaluate.py             :: 离线质量评估
python scripts/graph_report.py         :: 图谱结构报告
```
