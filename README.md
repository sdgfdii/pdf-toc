# pdf-toc

给任意 PDF 补上侧边栏大纲（书签）。文字版直接读文字层，扫描件走 OCR。

从网上下的 PDF 十有八九没有书签，几百页只能从头翻。这个工具把标题挖出来写成 PDF 大纲，Acrobat / Edge / Chrome / WPS / macOS 预览里都能看到左侧导航树，点一下直接跳过去。

## 特性

- **双路识别**：有编号（`第X章`、`1.1`、`一、`）就按编号定级；没编号就按字号定级
- **扫描件 OCR**：RapidOCR（PP-OCRv6），纯 CPU，不需要 GPU 和 torch
- **逐页判断**：文字层和扫描页混排的文档一次搞定，只对没文字的页跑 OCR
- **可编辑**：先导出 JSON，改完再写入，不用重跑识别
- **零配置**：Windows 下拖拽 bat 双击就跑

## 快速开始

### 1. 装依赖

双击 `0-安装依赖.bat`，或：

```bash
pip install -r requirements.txt
```

### 2. 生成大纲

| 文档类型 | 拖到这个文件上 |
| --- | --- |
| 文字版 PDF | `1-扫描生成大纲.bat` |
| 扫描件 / 图片版 PDF | `3-扫描件模式.bat` |

会打印抓到的大纲，同时生成同名的 `.toc.json`。

```bash
python pdf_toc.py 文档.pdf            # 文字版
python pdf_toc.py 扫描件.pdf --ocr     # 扫描件
python pdf_toc.py 扫描件.pdf --ocr --dpi 300   # 字太小就提高分辨率
```

### 3. 写入书签

确认没问题，拖 `2-写入书签.bat`，输出 `文档_outline.pdf`。

```bash
python pdf_toc.py 文档.pdf --apply
```

## 抓不准怎么办

改 `.toc.json`，再跑一次 `--apply` 就行，不需要重新识别：

```json
{
  "toc": [
    {"level": 1, "title": "第一章 概述", "page": 3},
    {"level": 2, "title": "1.1 背景", "page": 5},
    {"level": 2, "title": "1.2 目标", "page": 8}
  ]
}
```

- `level` 从 1 开始，**不能跳级**（1 后面只能接 1 或 2，写成 3 会被自动压平）
- `page` 是**物理页码**，封面算第 1 页，和印刷页码不是一回事
- 手写整份大纲也完全可以，识别只是给个起点

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `pdf` | PDF 文件路径 |
| `--levels N` | 最多抓几级标题，默认 3 |
| `--ocr` | 对无文字层的页面跑 OCR |
| `--dpi N` | OCR 渲染分辨率，默认 200 |
| `--apply` | 读取同名 `.toc.json` 写入书签 |
| `-o FILE` | 指定输出文件名 |

## 判定逻辑

**标题来源**，二选一自动判断：

1. 页面上 `第X章` / `第X节` / `1.1` / `一、` 这类编号命中 ≥ 2 条 → 按编号定级，字号只用来过滤噪声
2. 一条编号都没有 → 按字号降序分级，正文基准取全文众数字号

**自动剔除**：

- 页眉页脚：跨页重复出现 **且** 位置在页面上下 12% 区域内（只判重复会误杀重复正文）
- 目录页自身的条目：点线引导符（`......`）或 `标题  12` 这种裸页码行
- 纯页码行

## OCR

- 引擎：RapidOCR 3.x（PP-OCRv6 det + rec + cls），onnxruntime CPU 推理
- 触发条件：该页 `get_text()` 长度 < 20 字符
- 速度：约 3 秒/页（i5 级 CPU，200 dpi）
- OCR 会把一行切成多个碎片框，工具内部按垂直中心聚行后横向拼接
- 全角数字（`１`）自动转半角，编号与标题粘连时补空格

## 已知限制

- 双栏排版、表格内文字可能被误收进大纲
- 扫描件的字号是估算值（检测框高度折算），无编号文档的分级可能有偏差
- 手写体、竖排、生僻字识别率一般
- 加密 PDF 需要先解密
- 超过 60 字符的标题会被过滤掉

## License

MIT

---

## English

Add a sidebar outline (bookmarks) to any PDF — auto-detect headings from the text layer, or fall back to OCR for scanned pages.

```bash
pip install -r requirements.txt

python pdf_toc.py book.pdf            # text-based PDF -> book.toc.json
python pdf_toc.py book.pdf --apply    # write bookmarks -> book_outline.pdf
python pdf_toc.py scan.pdf --ocr      # scanned PDF, OCR at 200 dpi
```

Headings are detected in two ways, chosen automatically: if numbered headings (`Chapter 1`, `1.1`, `一、`) appear at least twice, levels come from the numbering; otherwise headings are ranked by font size against the body-text mode. Repeated header/footer text at the page margins, orphan page numbers, and the document's own table-of-contents entries are filtered out.

Edit the generated `.toc.json` if the detection is off, then re-run with `--apply`. `page` is the physical page number (cover counts as page 1), and `level` must not skip levels.

Powered by [PyMuPDF](https://github.com/pymupdf/PyMuPDF) and [RapidOCR](https://github.com/RapidAI/RapidOCR).
