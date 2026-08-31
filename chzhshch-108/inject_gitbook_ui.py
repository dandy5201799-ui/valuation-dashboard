#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HonKit build 后的 UI 增强：
  1) 顶部站点切换条（.cx-site-switcher）
  2) 章末「上一章 / 下一章」翻页卡片（.hb-inline-pager）
从每页的 gitbook.page.hasChanged({...}) 数据里读取页面标题与前后章来生成。
"""
import glob
import json
import os
import re

BOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "gitbook-book", "_book")


def extract_page_json(raw):
    """从 hasChanged({...}) 里提取 'page' 与 'config' 对象。"""
    m = re.search(r'gitbook\.page\.hasChanged\(\{', raw)
    if not m:
        return None, None
    # 用花括号配平提取整个对象
    start = raw.index('{', m.start())
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(raw):
        c = raw[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
        i += 1
    obj_text = raw[start:i + 1]
    try:
        obj = json.loads(obj_text)
    except Exception:
        return None, None
    return obj.get("page"), obj.get("config")


def readme_title(grid_config):
    if grid_config and grid_config.get("title"):
        return grid_config["title"]
    return "缠中说禅教你炒股票108课"


def inject():
    pages = glob.glob(os.path.join(BOOK, "**", "*.html"), recursive=True)
    n = 0
    for path in pages:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        new = apply_one(raw, path)
        if new is not raw and new is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            n += 1
    print("injected UI into %d pages" % n)


def apply_one(raw, path):
    page, grid = extract_page_json(raw)
    if not page:
        return raw

    # 搜索框占位符简体化
    raw = raw.replace('placeholder="輸入並搜尋"', 'placeholder="搜索任意课程、关键词…"')
    raw = raw.replace('placeholder="輸入並搜尋"', 'placeholder="搜索任意课程、关键词…"')

    title = page.get("title", "")
    book_title = readme_title(grid)

    rel = os.path.relpath(BOOK, os.path.dirname(path))
    home_href = ("%s/" % rel).rstrip("/") or "index.html"

    # 顶部站点切换条
    switcher = (
        '<div class="cx-site-switcher" role="navigation" aria-label="站点切换">'
        '<div class="cx-site-switcher__brand">'
        '<p class="cx-site-switcher__eyebrow">缠中说禅</p>'
        '<p class="cx-site-switcher__title">%s</p>'
        '</div>'
        '<div class="cx-site-switcher__links">'
        '<a class="cx-site-switcher__link" href="%s">书首页</a>'
        '<a class="cx-site-switcher__link is-active" href="%s">%s</a>'
        '%s'
        '</div></div>'
    )
    from urllib.parse import quote
    github_link = '<a class="cx-site-switcher__link" href="https://github.com/stockServ/chzhshch-108-plus" target="_blank" rel="noopener">GitHub</a>'
    show_start = (
        '<a class="cx-site-switcher__link is-active" href="%s">从这里开始</a>'
        if not grid or not grid.get("title") else ""
    )
    switcher_html = switcher % (
        __import__("html").escape(book_title),
        home_href,
        home_href,
        __import__("html").escape(title),
        github_link,
    )

    # 章末翻页卡片
    prev = page.get("previous") or {}
    nxt = page.get("next") or {}
    if prev and prev.get("path") and prev["path"].endswith(".md"):
        prev_href = os.path.splitext(os.path.basename(prev["path"]))[0] + ".html"
        prev_title = re.sub(r'^\d+\.\s*', "", prev.get("title", "上一章"))
        prev_link = ('<a class="hb-inline-pager__link hb-inline-pager__link--prev" '
                     'href="%s"><span class="hb-inline-pager__eyebrow">上一章</span>'
                     '<span class="hb-inline-pager__title">%s</span></a>'
                     % (prev_href, __import__("html").escape(prev_title)))
    else:
        prev_link = '<span class="hb-inline-pager__link hb-inline-pager__link--prev" style="opacity:.4"><span class="hb-inline-pager__eyebrow">已是第一课</span></span>'

    if nxt and nxt.get("path") and nxt["path"].endswith(".md"):
        nxt_href = os.path.splitext(os.path.basename(nxt["path"]))[0] + ".html"
        nxt_title = re.sub(r'^\d+\.\s*', "", nxt.get("title", "下一章"))
        nxt_link = ('<a class="hb-inline-pager__link hb-inline-pager__link--next" '
                    'href="%s"><span class="hb-inline-pager__eyebrow">下一章</span>'
                    '<span class="hb-inline-pager__title">%s</span></a>'
                    % (nxt_href, __import__("html").escape(nxt_title)))
    else:
        nxt_link = '<span class="hb-inline-pager__link hb-inline-pager__link--next" style="opacity:.4"><span class="hb-inline-pager__eyebrow">已是最后一课</span></span>'

    pager = '<nav class="hb-inline-pager" aria-label="章节导航">%s%s</nav>' % (prev_link, nxt_link)

    # 插入位置：body 开头的 .book 容器之前插入站点条；正文 section.normal 之后插入翻页
    # 站点条插在第一个 <body 之后
    body_marker = re.search(r'<body[^>]*>', raw)
    if body_marker:
        raw = raw[:body_marker.end()] + switcher_html + raw[body_marker.end():]

    # 翻页卡片插在正文 section.normal 结束 `</section>` 之后、`<div class="hb-endcap"` （若有）之前
    section_m = re.search(r'(</section>\s*)(?=<div class="hb-endcap"|</div>\s*<div class="search-results">|<div id="book-search-results">)', raw, re.S)
    if section_m:
        end = section_m.end(1)
        raw = raw[:end] + pager + raw[end:]
    else:
        # 兜底：插到 </article><div id="book-search-results"> 之后 search-noresults 内
        m2 = re.search(r'(<section class="normal markdown-section">.*?</section>)', raw, re.S)
        if m2:
            raw = raw[:m2.end()] + pager + raw[m2.end():]

    return raw


if __name__ == "__main__":
    inject()
