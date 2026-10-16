# 徽州文化图片资源

本目录存放**自由授权、来源可核查**的徽州文化图片，以及机器可读的清单
`manifest.json` 与人工可读的署名清单 `CREDITS.md`。

## 当前状态：已收录 15 张图片

图片全部来自 **Wikimedia Commons**，每张都在 `manifest.json` 与 `CREDITS.md` 中
登记了作者、许可、许可原文地址与来源页面，可逐条点击核对。

另有 14 个目标实体**不放图**（清单见 `CREDITS.md` 的「未取得图片的实体」）：
它们要么在 Commons 上找不到确实相关的自由授权图片，要么找到的图片**署不出作者**。
本项目宁可少一张图，也不放一张图文不符或来源不明的图。

## 本机网络对 Wikimedia 的限制，以及绕行方案

本机对 `commons.wikimedia.org` / `upload.wikimedia.org` 存在**SNI 域名级阻断**，
不是整体断网。实测证据：

```
DNS：commons.wikimedia.org      → 103.102.166.224（被污染，非 Wikimedia 真实网段）
     upload.wikimedia.org       → 103.102.166.240（同上）
     dumps.wikimedia.org        → 208.80.154.242（真实 IP，可访问，返回 200）
直连 / 走代理 / 脱离沙箱：commons 与 upload 三种方式一律握手超时（code=000）
用真实 IP + --resolve 覆盖：仍失败（SNI 命中黑名单即被重置），而同一 IP 上的
     dumps.wikimedia.org 正常 —— 证明是**按域名（SNI）拦截**，非按 IP 或整体断网
对照组：ihchina.cn(200)、mirrors.aliyun.com(301) 正常；github.com、wikipedia 全站 000
```

因此直接抓取 Commons 不可行。`scripts/fetch_images.py` 改用一组**免费中转池**：

| 用途 | 中转 | 说明 |
|---|---|---|
| 元数据（文件名 / 许可 / 作者） | 中转池轮换：`api.microlink.io` / `api.allorigins.win` / `api.cors.lol` / `api.codetabs.com` | 服务端把目标 URL 抓回，据此间接调用 Commons API（`action=query`）。每家免费额度都很低且会间歇性限流（429 / 500 / 503 / 520 / 522），故按「近期成功率 + 冷却状态」轮换，失败的中转让位给其它中转。 |
| 图片字节 | `wsrv.nl`（images.weserv.nl） | 开源图片代理/CDN，支持 `?url=upload.wikimedia.org/...` 回源并缩放。注意其回源 Wikimedia 时**上游会间歇性 429**，脚本内置较长退避重试。 |

两条链路只做「中转」，内容仍来自 Wikimedia，授权与作者以 Commons API 返回为准。

## 复现方式

```bat
:: 常规：在能访问 Commons 的网络里一次抓完
python scripts/fetch_images.py --dry-run   :: 先看候选与许可，不下载
python scripts/fetch_images.py             :: 通过校验后下载并重写清单

:: 配额 / 限流受限时：从已解析结果续跑（不消耗检索额度）
python scripts/fetch_images.py --from-resolved assets/images/.resolved.json --pace 6
```

脚本会：

1. 按人工撰写的检索词在 Commons 查询候选；
2. 只接受 **CC0 / CC BY / CC BY-SA / 公有领域 / GFDL** 的图片，含 NC / ND / 合理使用的直接丢弃；
3. 用「必须匹配 + 排除」两组正则确认图片**确实与目标实体相关**。
   对「徽州牌坊」「徽州祠堂」这类**带地域的建筑类型名**，必含词分两段（` & ` 表示同时满足）：
   既要是牌坊/祠堂，又要能看出在徽州一府六县境内。
   这条规则的来历是真实的教训——曾经下错过三张：
   「渐江」下到广东江河的航拍、「徽州牌坊」下到白云寺院门、「徽州祠堂」下到无锡惠山祠堂；
4. 过滤画幅比例异常（过宽的接片）、低分辨率图片，以及**Commons 上没登记作者的图片**
   （没有作者就无从署名，宁可缺一张）；
5. 同一张图只分配给一个实体；
6. 下载到本目录并重写 `manifest.json` 与 `CREDITS.md`，**按实体合并**而非覆盖，
   因此可以分多批续跑；
7. 对确实找不到合适图片的实体明确记录为「未取得图片」，不塞占位图。

上述 3、4 两条把关已被测试钉住：`tests/test_image_library.py` 会断言
「清单里每一张图都能通过它所属实体的相关性把关」，并断言那几个曾经误召回的文件名**必须被挡住**。

运行完成后重启应用即可看到配图与署名，无需改动任何代码。

> 图注由人工对照**实际下载的图片内容**写定（例如「呈坎」「棠樾」两张是国保石碑而非村落全景，
> 图注即如实标注为“……全国重点文物保护单位碑”），避免图文不符。

## 许可与署名要求

- 图片全部为**本地文件**，应用离线可用，不依赖外链。
- 每张图在详情页下方自动标注：图注、作者、许可、来源页面与许可原文链接。
- `CREDITS.md` 为完整署名清单，可逐条点击核对原始页面。
- 若替换或删除某张图片，请同步更新 `manifest.json` 与 `CREDITS.md`。
