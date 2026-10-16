# 图片署名清单

本项目在界面中使用的徽州文化图片全部来自 **Wikimedia Commons**，
且均为自由授权（CC0 / CC BY / CC BY-SA / 公有领域 / GFDL）。
下表逐条登记来源，可点击核对原始页面。

> 说明：以下图片按原许可要求署名使用；如某张图片被替换或移除，
> 请同步更新本文件与 `manifest.json`。

| 使用位置 | 文件 | 作者 | 许可 | 来源页面 |
|---|---|---|---|---|
| 呈坎（`chengkan`） | `chengkan.jpg` | Doctoroftcm | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Chengkan_5456.jpg) |
| 承志堂（`chengzhitang`） | `chengzhitang.jpg` | lienyuan lee | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Hongcun_Chengzhi_Hall_%E5%AE%8F%E6%9D%91%E6%89%BF%E5%BF%97%E5%A0%82_-_panoramio.jpg) |
| 黄山（`huangshan`） | `huangshan.jpg` | Miaulian | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Anhui_Huangshan.jpg) |
| 齐云山（`qiyunshan`） | `qiyunshan.jpg` | Julienfuchs | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Qiyun_Shan_temple.JPG) |
| 唐模（`tangmo`） | `tangmo.jpg` | 江上清风1961 | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:%E9%BB%84%E5%B1%B1%E5%B8%82%E6%AD%99%E5%8E%BF%E5%94%90%E6%A8%A1%E6%9D%91%E7%89%8C%E5%9D%8A_-_panoramio.jpg) |
| 棠樾（`tangyue`） | `tangyue.jpg` | Doctoroftcm | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Tangyue_5328.jpg) |
| 屯溪老街（`tunxi_laojie`） | `tunxi_laojie.jpg` | luchangjiang~鲁昌江 | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | [Commons](https://commons.wikimedia.org/wiki/File:%E5%AE%89%E5%BE%BD%E7%9C%81%E9%BB%84%E5%B1%B1%E5%B8%82%E5%B1%AF%E6%BA%AA%E9%95%87%E4%BF%AF%E7%9E%B0%E8%A1%97%E6%99%AF_-_panoramio_-_luchangjiang~%E9%B2%81%E6%98%8C%E6%B1%9F_%287%29.jpg) |
| 西递（`xidi`） | `xidi.jpg` | Anna Frodesiak | [Public domain](https://en.wikipedia.org/wiki/Public_domain) | [Commons](https://commons.wikimedia.org/wiki/File:Xidi_-_05.JPG) |
| 许村（`xucun`） | `xucun.jpg` | Siyuwj | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Xucun_Village%2C_2021-09-26_01.jpg) |
| 许国石坊（`xuguo_shifang`） | `xuguo_shifang.jpg` | Yumeto | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | [Commons](https://commons.wikimedia.org/wiki/File:20230904_Xuguo_Shifang.jpg) |
| 渔梁（`yuliang`） | `yuliang.jpg` | Zhangzhugang | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | [Commons](https://commons.wikimedia.org/wiki/File:Shexian_Yuliang_2016.11.13_07-46-43.jpg) |

## 复现方式

```bat
python scripts/fetch_images.py --dry-run   :: 先看候选，不下载
python scripts/fetch_images.py             :: 检索并下载，重写清单
:: 检索配额受限时，可从已解析候选续跑（不消耗检索额度）
python scripts/fetch_images.py --from-resolved assets/images/.resolved.json --pace 6
```

> 详细说明（含本机网络对 Wikimedia 的 SNI 阻断与中转方案）见同目录 `README.md`。
