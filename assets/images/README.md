# 徽州文化图片资源

本目录用于存放**自由授权、来源可核查**的徽州文化图片，以及机器可读的清单
`manifest.json` 与人工可读的署名清单 `CREDITS.md`。

## 当前状态：尚未收录图片

本机网络对 Wikimedia 全域名（`commons.wikimedia.org`、`upload.wikimedia.org`、
`zh.wikipedia.org` 等）**TCP 层不可达**：DNS 可以正常解析出 IP，
但连接一律超时，且绕过代理直连、甚至脱离沙箱执行都一样。

实测记录：

```
nslookup commons.wikimedia.org   → 103.102.166.224（解析正常）
curl https://commons.wikimedia.org/w/api.php   → code=000（连接超时）
curl https://upload.wikimedia.org/...          → code=000（连接超时）
curl https://www.ihchina.cn / mirrors.aliyun.com → code=200（其它站点正常）
```

因此**没有把任何图片文件放进仓库**。这属于网络环境限制，不是代码问题；
仓库中也不存在占位图或来源不明的图片。

界面已按「有图就显示、无图就纯排版」实现（见 `src/data/images.py` 与
`src/ui/pages/detail.py`），所以在补齐图片之前，页面依然完整可用，
只是不含配图。

## 如何补齐图片（一条命令）

在可以访问 Wikimedia 的网络环境中执行：

```bat
python scripts/fetch_images.py --dry-run   :: 先看候选与许可，不下载
python scripts/fetch_images.py             :: 通过校验后下载并重写清单
```

脚本会：

1. 按人工撰写的检索词在 Commons 查询候选；
2. 只接受 **CC0 / CC BY / CC BY-SA / 公有领域 / GFDL** 的图片，
   含 NC / ND / 合理使用的直接丢弃；
3. 用「必须匹配 + 排除」两个正则确认图片**确实与目标实体相关**
   （例如避免把广东惠州当成徽州、把同名艺术家的作品当成徽州文物）；
4. 过滤画幅比例异常（过宽的接片）与低分辨率图片；
5. 同一张图只分配给一个实体，避免重复堆砌；
6. 下载缩略图到本目录，并重写 `manifest.json` 与 `CREDITS.md`；
7. 对确实找不到合适图片的实体**明确记录为「未取得图片」**，不塞占位图。

运行完成后重启应用即可看到配图与署名，无需改动任何代码。

## 许可与署名要求

- 图片全部为**本地文件**，应用离线可用，不依赖外链。
- 每张图在详情页下方自动标注：图注、作者、许可、来源页面与许可原文链接。
- `CREDITS.md` 为完整的署名清单，可逐条点击核对原始页面。
- 若替换或删除某张图片，请同步更新 `manifest.json` 与 `CREDITS.md`。
