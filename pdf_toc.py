"""pdf_toc.py - 给 PDF 生成侧边栏大纲(书签)

用法:
    python pdf_toc.py 文件.pdf               # 扫描, 生成 文件.toc.json 并打印
    python pdf_toc.py 文件.pdf --levels 2    # 最多抓 2 级
    python pdf_toc.py 扫描件.pdf --ocr       # 无文字层的页面走 OCR
    python pdf_toc.py 扫描件.pdf --ocr --dpi 300
    python pdf_toc.py 文件.pdf --apply       # 按 文件.toc.json 写入书签, 输出 文件_outline.pdf
    python pdf_toc.py 文件.pdf --apply -o 自定义名.pdf

改完 json 里的 title / page / level 再 --apply 即可。
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

CJK_NUM = "一二三四五六七八九十百千零〇两"
RE_CHAPTER = re.compile(rf"^第[{CJK_NUM}\d]+[章篇部]")
RE_SECTION = re.compile(rf"^第[{CJK_NUM}\d]+节")
RE_NUMDOT = re.compile(r"^(\d{1,3}(?:[.．]\d{1,3})+)(?![.．\d])")
RE_CNORD = re.compile(rf"^[{CJK_NUM}]+[、.]")
RE_PAGENO = re.compile(r"^[\s\-—–·]*\d{1,4}[\s\-—–·]*$")


def setup_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _normalize_ocr_text(s):
    """OCR 常把数字/字母认成全角, 只把这三段转回半角, 中文标点保持原样"""
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _is_toc_line(raw):
    """目录页里的条目: 点线引导符 或 "标题  12" 这种裸页码"""
    return bool(re.search(r"[.．·…]{3,}", raw) or re.search(r"\s{2,}\d{1,4}\s*$", raw))


def _silence_rapidocr():
    """RapidOCR 会在推理时刷 INFO 日志, 这里彻底关掉它"""
    import logging
    for name in ("RapidOCR", "rapidocr"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.CRITICAL)
        lg.propagate = False
        lg.handlers = [logging.NullHandler()]


def load_ocr_engine():
    try:
        from rapidocr import RapidOCR
    except ImportError:
        raise SystemExit(
            "缺少 OCR 依赖, 先执行:\n"
            "  python -m pip install rapidocr onnxruntime"
        )
    _silence_rapidocr()
    print("正在加载 OCR 模型 ...")
    engine = RapidOCR()
    _silence_rapidocr()
    return engine


def _page_image(page, dpi):
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr[:, :, :3]


def _merge_ocr_rows(items, dpi):
    """OCR 常把一行切成多个碎片框, 按垂直中心聚成行后横向拼接"""
    items = sorted(items, key=lambda it: ((it[1] + it[3]) / 2, it[0]))
    rows = []
    for it in items:
        cy = (it[1] + it[3]) / 2
        h = it[3] - it[1]
        if rows:
            last = rows[-1]
            if abs(cy - last["cy"]) < max(h, last["h"]) * 0.5:
                last["items"].append(it)
                if len(last["items"]) == 2:
                    last["cy"] = (last["items"][0][1] + last["items"][0][3] + cy) / 3
                last["cy"] = last["cy"] + (cy - last["cy"]) / len(last["items"])
                last["h"] = max(last["h"], h)
                continue
        rows.append({"cy": cy, "h": h, "y0": it[1], "items": [it]})

    lines = []
    for row in rows:
        parts = sorted(row["items"], key=lambda it: it[0])
        text = parts[0][4]
        prev_x1 = parts[0][2]
        for it in parts[1:]:
            gap = it[0] - prev_x1
            if gap > max(4.0, row["h"] * 0.12):
                text += " "
            text += it[4]
            prev_x1 = it[2]
        lines.append((row["y0"], row["h"], text))
    return lines


def ocr_page(page, engine, pno, dpi):
    """渲染一页为图片做 OCR, 返回与 collect_lines 同构的元组列表"""
    arr = _page_image(page, dpi)
    out = engine(arr)
    txts = getattr(out, "txts", None) if out is not None else None
    if not txts:
        return []

    boxes = getattr(out, "boxes", None)
    if boxes is None:
        boxes = []
    scores = getattr(out, "scores", None)
    if scores is None:
        scores = [1.0] * len(txts)
    page_h = page.rect.height or 1
    items = []
    for box, txt, sc in zip(boxes, txts, scores):
        if sc is not None and float(sc) < 0.5:
            continue
        clean = re.sub(r"\s+", " ", _normalize_ocr_text(str(txt))).strip()
        if not clean:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        items.append([min(xs), min(ys), max(xs), max(ys), clean])

    result = []
    for y0_px, h_px, text in _merge_ocr_rows(items, dpi):
        text = re.sub(r"\s+", " ", text).strip()
        if not text or _is_toc_line(text):
            continue
        # 编号与标题文字粘连时补一个空格, 只为显示好看, 不影响匹配
        text = re.sub(r"^(\d+(?:[.．]\d+)+)(?=[^\s\d.．])", r"\1 ", text)
        text = re.sub(r"^(第[一二三四五六七八九十百千零〇两\d]+[章篇部节])(?=[^\s])", r"\1 ", text)
        # 检测框高度约等于 1.3 倍字号, 乘 0.77 折回 pt
        size_pt = h_px * (72.0 / dpi) * 0.77
        y_ratio = (y0_px * (72.0 / dpi)) / page_h
        in_margin = y_ratio < 0.12 or y_ratio > 0.88
        result.append((pno, text, round(size_pt, 1), False, in_margin))
    return result


def collect_lines(doc, engine=None, dpi=200, ocr_min_chars=20):
    """逐页抽取文本行: (页码1基, 文本, 字号, 是否加粗, 是否在页边区域)"""
    out = []
    total = len(doc)
    for pno, page in enumerate(doc, 1):
        if engine is not None and len(page.get_text().strip()) < ocr_min_chars:
            print(f"  识别中 {pno}/{total}", end="\r", flush=True)
            out.extend(ocr_page(page, engine, pno, dpi))
            continue
        try:
            d = page.get_text("dict")
        except Exception:
            continue
        page_h = page.rect.height or 1
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                raw = "".join(s["text"] for s in spans).strip()
                if _is_toc_line(raw):
                    continue
                text = re.sub(r"\s+", " ", raw)
                if not text:
                    continue
                size = max(float(s.get("size", 0)) for s in spans)
                bold = any(int(s.get("flags", 0)) & 16 for s in spans)
                bbox = line.get("bbox") or spans[0].get("bbox") or (0, 0, 0, 0)
                y_ratio = float(bbox[1]) / page_h
                in_margin = y_ratio < 0.12 or y_ratio > 0.88
                out.append((pno, text, round(size, 1), bold, in_margin))
    if engine is not None:
        print()
    return out


def drop_headers_footers(lines, page_count):
    """剔除页眉页脚: 每页重复 + 位置在页面上下边缘。纯页码行直接丢"""
    pages_of = defaultdict(set)
    for pno, text, _, _, _ in lines:
        pages_of[text].add(pno)
    threshold = max(3, int(page_count * 0.3))
    repeated = {t for t, ps in pages_of.items() if len(ps) >= threshold and len(t) <= 40}
    kept = []
    for item in lines:
        pno, text, _, _, in_margin = item
        if text in repeated and in_margin:
            continue
        if RE_PAGENO.match(text):
            continue
        if len(text) < 2 or len(text) > 60:
            continue
        kept.append(item)
    return kept


def regex_level(text):
    """按编号规则给出层级, 认不出返回 None"""
    if RE_CHAPTER.match(text):
        return 1
    if RE_SECTION.match(text):
        return 2
    m = RE_NUMDOT.match(text)
    if m:
        depth = m.group(1).replace("．", ".").count(".") + 1
        return min(depth, 3)
    if RE_CNORD.match(text):
        return 2
    return None


def build_outline(lines, levels=3):
    """返回 [(level, title, page)]"""
    if not lines:
        return []

    body_size = Counter(sz for _, _, sz, _, _ in lines).most_common(1)[0][0]

    tagged = []
    hit_numbered = 0
    for pno, text, size, bold, _ in lines:
        lv = regex_level(text)
        if lv is not None:
            hit_numbered += 1
        tagged.append((pno, text, size, bold, lv))

    numbered_mode = hit_numbered >= 2

    if numbered_mode:
        cands = [t for t in tagged if t[4] is not None and t[4] <= levels]
    else:
        cands = [t for t in tagged if t[2] >= body_size * 1.10]

    if not cands:
        return []

    if numbered_mode:
        picked = [(t[4], t[1], t[0]) for t in cands]
    else:
        sizes = sorted({t[2] for t in cands}, reverse=True)[:levels]
        rank = {sz: i + 1 for i, sz in enumerate(sizes)}
        picked = [(rank[t[2]], t[1], t[0]) for t in cands if t[2] in rank]

    # 去重 + 同级重复标题合并
    seen = set()
    result = []
    for lv, title, pno in picked:
        key = (lv, title, pno)
        if key in seen:
            continue
        seen.add(key)
        result.append([lv, title, pno])

    # 同页同标题只留一条
    dedup = []
    for item in result:
        if dedup and dedup[-1][1] == item[1] and dedup[-1][2] == item[2]:
            continue
        dedup.append(item)

    # 修正跳级: 1 -> 3 这类压成 1 -> 2
    fixed = []
    prev = 1
    for lv, title, pno in dedup:
        lv = max(1, min(lv, prev + 1, levels))
        fixed.append([lv, title, pno])
        prev = lv
    return fixed


def disp_width(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def print_outline(toc, page_count, body_note=""):
    print(f"共 {page_count} 页 {body_note}")
    print(f"抓到 {len(toc)} 条标题:\n")
    for lv, title, pno in toc:
        indent = "  " * (lv - 1)
        dots = "." * max(2, 50 - len(indent) * 2 - disp_width(title))
        print(f"{indent}[{lv}] {title} {dots} p{pno}")


def apply_outline(src, toc, out_path):
    doc = pymupdf.open(src)
    page_count = len(doc)
    fixed = []
    prev = 1
    for item in toc:
        lv = int(item.get("level", 1))
        title = str(item.get("title", "")).strip()
        pno = int(item.get("page", 1))
        if not title:
            continue
        if pno < 1 or pno > page_count:
            print(f"  跳过(页码越界 {pno}): {title}")
            continue
        lv = max(1, min(lv, prev + 1, 9))
        fixed.append([lv, title, pno])
        prev = lv
    if not fixed:
        raise SystemExit("没有可用条目, 不生成文件")
    doc.set_toc(fixed)
    doc.save(out_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return fixed


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="给 PDF 生成侧边栏大纲")
    ap.add_argument("pdf", help="PDF 文件路径")
    ap.add_argument("--levels", type=int, default=3, help="最多抓几级标题, 默认 3")
    ap.add_argument("--ocr", action="store_true", help="对无文字层的页面跑 OCR")
    ap.add_argument("--dpi", type=int, default=200, help="OCR 渲染分辨率, 默认 200")
    ap.add_argument("--apply", action="store_true", help="按同名 .toc.json 写入书签")
    ap.add_argument("-o", "--out", help="输出文件路径")
    args = ap.parse_args()

    src = Path(args.pdf)
    if not src.is_file():
        raise SystemExit(f"找不到文件: {src}")

    json_path = src.with_suffix(".toc.json")

    if args.apply:
        if not json_path.is_file():
            raise SystemExit(f"缺少 {json_path.name}, 先不带 --apply 跑一次生成它")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        entries = data["toc"] if isinstance(data, dict) else data
        out_path = Path(args.out) if args.out else src.with_name(src.stem + "_outline.pdf")
        if out_path.resolve() == src.resolve():
            raise SystemExit("输出不能覆盖原文件")
        fixed = apply_outline(src, entries, str(out_path))
        print(f"已写入 {len(fixed)} 条书签 -> {out_path}")
        return

    doc = pymupdf.open(str(src))
    page_count = len(doc)
    engine = load_ocr_engine() if args.ocr else None
    if engine is not None:
        need = sum(1 for pg in doc if len(pg.get_text().strip()) < 20)
        print(f"OCR 已启用: {need}/{page_count} 页无文字层, 渲染分辨率 {args.dpi} dpi")
    lines = collect_lines(doc, engine=engine, dpi=args.dpi)
    lines = drop_headers_footers(lines, page_count)
    body = Counter(sz for _, _, sz, _, _ in lines).most_common(1)[0][0] if lines else 0
    toc = build_outline(lines, args.levels)
    doc.close()

    if not toc:
        print("没抓到可用的标题。")
        json_path.write_text(json.dumps({"toc": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已生成空模板 {json_path.name}, 手动填 title/page/level 后再 --apply")
        return

    print_outline(toc, page_count, f"正文字号 {body}pt")
    payload = {"toc": [{"level": lv, "title": t, "page": p} for lv, t, p in toc]}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出 {json_path.name}")
    print("改完 json 后执行: python pdf_toc.py \"%s\" --apply" % src.name)


if __name__ == "__main__":
    main()
