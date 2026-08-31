#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 honkit / GitBook CLI 准备项目输入：
  1) 把所有 108 课 md 复制为友好文件名（lesson-001.md … lesson-108.md）到 book/108/
  2) 复制配图到 book/108/pic/，保持相对引用不变
  3) 生成 SUMMARY.md、README.md、book.json
正文默认截断到「本文评论获取自」之前（即课文原文）。
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "chzhshch-108-plus", "108")
BOOK = os.path.join(ROOT, "gitbook-book", "108")

INCLUDE_COMMENTS = "--with-comments" in sys.argv

COMMENT_MARKER = "**本文评论获取自"


def classify(fname):
    m = re.search(r'-(\d{3})\.md$', fname)
    if m:
        return int(m.group(1)), ""
    m = re.search(r'-W(\d{3})\.md$', fname)
    if m:
        return int(m.group(1)), "W"
    m = re.search(r'-\((\d)\)\.md$', fname)
    if m:
        return int(m.group(1)), "P"
    return int(re.match(r'^(\d{4})', fname).group(1)), "Z"


def extract_title_and_meta(content):
    lines = content.split("\n")
    title = ""
    meta = ""
    if lines and lines[0].lstrip().startswith("#"):
        m = re.match(r'^#+\s*\d+\s*[-—:：]\s*(.*)$', lines[0].strip())
        if m:
            title = m.group(1).strip()
        rest = lines[1:]
        for i, ln in enumerate(rest):
            if ln.strip():
                if ln.strip().startswith("日期：") or ln.strip().startswith("分类："):
                    meta = ln.strip()
                    return title, meta, "\n".join(rest[i + 1:])
                return title, meta, "\n".join(rest)
    return title, meta, content


def prepare():
    os.makedirs(os.path.join(BOOK, "pic"), exist_ok=True)

    # 1+2 复制配图
    src_pic = os.path.join(SRC, "pic")
    if os.path.isdir(src_pic):
        for fn in os.listdir(src_pic):
            sp = os.path.join(src_pic, fn)
            if os.path.isfile(sp):
                shutil.copy2(sp, os.path.join(BOOK, "pic", fn))

    lessons = []          # (no, extra, title, target_file)
    for fname in sorted(os.listdir(SRC)):
        if not fname.endswith(".md"):
            continue
        no, extra = classify(fname)
        with open(os.path.join(SRC, fname), encoding="utf-8") as fh:
            content = fh.read()

        if COMMENT_MARKER in content and not INCLUDE_COMMENTS:
            content = content.split(COMMENT_MARKER, 1)[0]

        title, meta, body = extract_title_and_meta(content)
        if not title:
            title = "教程 %d" % no if not extra else "补充文章 %d" % no

        # 输出文件名
        if extra == "":
            out_name = "lesson-%03d.md" % no
            summary_title = "%d. %s" % (no, title)
        else:
            out_name = "extra-%s%03d.md" % (extra, no)
            summary_title = "补充：%s" % title

        # 全新整写：标题 + 元信息 + 正文，去掉原文件开头博客编号行
        new_content = content.strip()
        # 重新拼一个干净的正文文件（GitBook 用文件的第一个 H1 当页面标题）
        header = "# %s\n\n" % title
        meta_line = ("%s\n\n" % meta) if meta else ""
        writer = ["# %s" % title]
        if meta:
            writer += [meta, "---"]
        writer.append(body.strip())
        new_content = "\n\n".join(w for w in writer if w.strip())

        with open(os.path.join(BOOK, out_name), "w", encoding="utf-8") as fh:
            fh.write(new_content + "\n")

        lessons.append({
            "no": no, "extra": extra, "title": title,
            "file": out_name, "summary": summary_title,
        })

    lessons.sort(key=lambda x: (0 if x["extra"] == "" else 1,
                                x["no"],
                                0 if x["extra"] == "P" else (1 if x["extra"] == "W" else 2)))

    # 3a. SUMMARY.md：正文课按 10 课一组，补充文章单独一组
    sum_lines = ["# Summary", ""]
    cur_group = None
    for les in lessons:
        if les["extra"] == "":
            g = ((les["no"] - 1) // 10) * 10 + 1
            if g != cur_group:
                if cur_group is not None:
                    sum_lines.append("")
                gend = min(g + 9, 108)
                sum_lines.append("## 第 %d–%d 课" % (g, gend))
                cur_group = g
            sum_lines.append("- [%s](108/%s)" % (les["summary"], les["file"]))
        else:
            cur_group = None

    # 补充文章组
    extras = [l for l in lessons if l["extra"] != ""]
    if extras:
        sum_lines.append("")
        sum_lines.append("## 补充文章（课格外）")
        for les in extras:
            sum_lines.append("- [%s](108/%s)" % (les["summary"], les["file"]))

    sum_lines.append("")
    sum_text = "\n".join(sum_lines)
    with open(os.path.join(ROOT, "gitbook-book", "SUMMARY.md"), "w", encoding="utf-8") as fh:
        fh.write(sum_text)

    # 3b. README.md 首页
    readme = """# 缠中说禅 · 教你炒股票 108 课（加强版）

> 用 GitBook / honkit 排版的本地离线圈子书。</br>正文以缠师原课为主，配图齐备；课后评论见同目录下「单 HTML 加强版」。

## 使用

```bash
cd gitbook-book
npx honkit serve     # 本地预览 http://localhost:4000
npx honkit build     # 生成 _book/ 纯静态站，双击 index.html 即可离线浏览
```

## 目录

%i
"""
    # 把 SUMMARY 的列表部分也贴进 README 概览（简化：只列章节标题）
    toc_overview = []
    for les in lessons:
        if les["extra"] == "":
            toc_overview.append("%d. %s" % (les["no"], les["title"]))
        else:
            toc_overview.append("· %s（补充）" % les["title"])
    readme = readme.replace("%i", "\n".join(toc_overview))
    with open(os.path.join(ROOT, "gitbook-book", "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)

    # 3c. book.json
    book_json = {
        "title": "缠中说禅教你炒股票108课（加强版）",
        "description": "读缠论之书",
        "language": "zh-cn",
        "structure": {
            "readme": "README.md",
            "summary": "SUMMARY.md"
        },
        "styles": {
            "website": "styles/website.css"
        }
    }
    import json
    with open(os.path.join(ROOT, "gitbook-book", "book.json"), "w", encoding="utf-8") as fh:
        json.dump(book_json, fh, ensure_ascii=False, indent=2)

    print("Done. lessons=%d (with_comments=%s). Output dir: %s"
          % (len(lessons), INCLUDE_COMMENTS, BOOK))


if __name__ == "__main__":
    prepare()
