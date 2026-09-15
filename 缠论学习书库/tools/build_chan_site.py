#!/usr/bin/env python3
"""为缠论学习书库构建 harness-books 风格的统一站点。"""
from __future__ import annotations

import argparse
import os
import re
import shutil
from html import escape, unescape as html_unescape
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOOK_DIRS = [
    {"slug": "book2-chan-practice", "title": "看懂K线走势", "dir": "book2-chan-practice", "description": "从真实K线出发，看清趋势、画出走势、判断结构、确认机会"},
    {"slug": "book3-auto-marker", "title": "缠论标记工具", "dir": "book3-auto-marker", "description": "把缠论结构标出来，辅助观察、解释和复盘"},
]
DIST_DIR = REPO_ROOT / "dist"
SITE_LABEL = "缠论学习书库"
MARKER_TOOL_URL = "https://dandistudio.site/chan/"


def relative_href(from_dir: str, to_path: str) -> str:
    return os.path.relpath(to_path, start=from_dir).replace(os.sep, "/")


def build_switcher_markup(current_slug: str, current_page: str, books: list[dict]) -> str:
    current_dir = current_slug
    home_target = "index.html"  # 相对于dist根目录

    link_parts = [
        f'<a class="hb-site-switcher__link" href="{escape(relative_href(current_dir, home_target))}">首页</a>'
    ]

    for book in books:
        classes = "hb-site-switcher__link"
        if book["slug"] == current_slug:
            classes += " is-active"
        target = f'{book["slug"]}/index.html'
        link_parts.append(
            f'<a class="{classes}" href="{escape(relative_href(current_dir, target))}">'
            f'{escape(book["title"])}</a>'
        )

    links_html = "".join(link_parts)
    current_book = next(b for b in books if b["slug"] == current_slug)

    return (
        f'<div class="hb-site-switcher" role="navigation" aria-label="Book switcher">'
        '<div class="hb-site-switcher__brand">'
        f'<p class="hb-site-switcher__eyebrow">{escape(SITE_LABEL)}</p>'
        f'<p class="hb-site-switcher__title">{escape(current_book["title"])}</p>'
        "</div>"
        f'<div class="hb-site-switcher__links">{links_html}</div>'
        "</div>"
    )


def extract_navigation_target(html: str, direction: str) -> tuple[str, str] | None:
    match = re.search(
        rf'<a href="([^"]+)" class="navigation navigation-{direction}\s*[^"]*" aria-label="([^"]+)">',
        html,
    )
    if not match:
        return None
    href = html_unescape(match.group(1)).strip()
    aria_label = html_unescape(match.group(2)).strip()
    label = aria_label.split(":", 1)[1].strip() if ":" in aria_label else aria_label
    if not href or not label:
        return None
    return href, label


def build_inline_pager(html: str) -> str:
    links: list[str] = []
    has_link = False
    prev_target = extract_navigation_target(html, "prev")
    if prev_target:
        has_link = True
        href, label = prev_target
        links.append(
            '<a class="hb-inline-pager__link hb-inline-pager__link--prev" '
            f'href="{escape(href)}">'
            '<span class="hb-inline-pager__eyebrow">回到上一章</span>'
            f'<span class="hb-inline-pager__title">{escape(label)}</span>'
            "</a>"
        )
    else:
        links.append('<span class="hb-inline-pager__slot" aria-hidden="true"></span>')

    next_target = extract_navigation_target(html, "next")
    if next_target:
        has_link = True
        href, label = next_target
        links.append(
            '<a class="hb-inline-pager__link hb-inline-pager__link--next" '
            f'href="{escape(href)}">'
            '<span class="hb-inline-pager__eyebrow">继续阅读下一章</span>'
            f'<span class="hb-inline-pager__title">{escape(label)}</span>'
            "</a>"
        )
    else:
        links.append('<span class="hb-inline-pager__slot" aria-hidden="true"></span>')

    if not has_link:
        return ""
    return '<nav class="hb-inline-pager" aria-label="Chapter navigation">' + "".join(links) + "</nav>"


def build_related_reading(current_slug: str) -> str:
    if current_slug != "book2-chan-practice":
        return ""
    return f"""
<aside class="hb-related-reading" aria-label="延伸阅读">
  <div>
    <p class="hb-related-reading__eyebrow">延伸阅读</p>
    <h2>打开缠论标记工具</h2>
    <p>读懂走势之后，可以用工具把分型、笔、线段、中枢和确认位置标出来。工具负责呈现结构，判断仍然要回到你自己的复盘。</p>
  </div>
  <div class="hb-related-reading__actions">
    <a class="hb-related-reading__button hb-related-reading__button--primary" href="{escape(MARKER_TOOL_URL)}" target="_blank" rel="noopener">打开标记工具</a>
    <a class="hb-related-reading__button hb-related-reading__button--secondary" href="../book3-auto-marker/index.html">阅读工具说明</a>
  </div>
</aside>
"""


def inject_switcher(book_publish_dir: Path, current_slug: str, books: list[dict]) -> None:
    for html_path in book_publish_dir.rglob("*.html"):
        # 跳过 gitbook 资源页与 interactives（嵌入式概念演示器）目录，
        # 演示器在 iframe 中独立渲染，不应注入站点切换条。
        if "gitbook" in html_path.parts or "interactives" in html_path.parts:
            continue
        html = html_path.read_text(encoding="utf-8")
        if "hb-site-switcher" in html:
            continue

        current_page = html_path.relative_to(book_publish_dir).as_posix()
        switcher_markup = build_switcher_markup(current_slug, current_page, books)

        html = html.replace(
            'content="width=device-width, initial-scale=1, user-scalable=no"',
            'content="width=device-width, initial-scale=1, viewport-fit=cover"',
        )
        html = html.replace("<body>", f"<body>\n{switcher_markup}", 1)
        html = html.replace(
            '<div class="book honkit-cloak">',
            '<div class="book honkit-cloak with-site-switcher">',
            1,
        )

        # 修复搜索框placeholder为简体中文
        html = html.replace('placeholder="輸入並搜尋"', 'placeholder="输入并搜索"')
        html = html.replace('placeholder="輸入並搜尋..."', 'placeholder="输入并搜索..."')

        # 修复HonKit页脚文字为简体中文
        html = html.replace('本書使用 HonKit 釋出', '本书使用 HonKit 生成')

        # 把自动生成的"Introduction"改成"导读"，并修复href
        html = html.replace('Introduction', '导读')
        html = html.replace('href="./"', 'href="index.html"')

        # 禁用SPA导航，让链接用普通页面跳转
        spa_disable_script = """
<script>
(function() {
  document.addEventListener('click', function(e) {
    var link = e.target.closest('a');
    if (!link) return;
    if (link.hostname !== window.location.hostname) return;
    if (link.target) return;
    if (link.hasAttribute('download')) return;
    e.preventDefault();
    e.stopPropagation();
    window.location.href = link.href;
  }, true);
})();
</script>
"""
        html = html.replace("</body>", f"{spa_disable_script}\n</body>", 1)

        # 注入自定义章节导航
        inline_pager = build_inline_pager(html)
        related_reading = build_related_reading(current_slug)
        below_article = inline_pager + related_reading
        if below_article:
            # 在正文结束前插入
            html = html.replace(
                "</section>\n                            \n    </div>\n    <div class=\"search-results\">",
                f"</section>\n{below_article}\n                            \n    </div>\n    <div class=\"search-results\">",
                1,
            )

        html_path.write_text(html, encoding="utf-8")


def build_index_page(books: list[dict]) -> str:
    book_cards = ""
    for book in books:
        book_cards += f"""
        <a class="book-card" href="{book['slug']}/index.html">
          <div class="book-card__cover">
            <img src="{book['slug']}/assets/cover.svg" alt="{book['title']}封面" loading="lazy">
          </div>
          <div class="book-card__body">
            <h3>{book['title']}</h3>
            <p>{book.get('description', '')}</p>
            <span class="button">在线阅读</span>
          </div>
        </a>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>缠论学习书库</title>
<meta name="description" content="缠论学习书库：看懂K线走势与缠论标记工具">
<style>
:root {{
  --page-bg: #f4efe4;
  --panel-bg: rgba(252, 248, 239, 0.82);
  --panel-strong: rgba(247, 241, 230, 0.94);
  --panel-border: rgba(61, 47, 31, 0.12);
  --text-strong: #221b14;
  --text-body: #4c4135;
  --text-muted: #786b5c;
  --accent: #875932;
  --accent-strong: #312015;
  --shadow: 0 24px 60px rgba(50, 37, 23, 0.10);
  --shadow-soft: 0 10px 24px rgba(50, 37, 23, 0.08);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", "Source Han Serif SC", serif;
  color: var(--text-body);
  background:
    radial-gradient(circle at top left, rgba(187, 145, 94, 0.16), transparent 26%),
    radial-gradient(circle at 85% 10%, rgba(120, 100, 76, 0.12), transparent 20%),
    linear-gradient(180deg, #f8f3ea 0%, #f1eadc 100%);
  min-height: 100vh;
}}
a {{ color: var(--accent); text-decoration: none; }}
.site-shell {{
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 16px 0 44px;
}}
.hero {{
  position: relative;
  overflow: hidden;
  padding: 48px 44px 52px;
  border: 1px solid var(--panel-border);
  border-radius: 30px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.55), transparent 46%),
    linear-gradient(180deg, var(--panel-strong), rgba(249, 243, 233, 0.90));
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow);
}}
.hero__eyebrow {{
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
}}
.hero h1 {{
  margin: 0;
  max-width: 18ch;
  font-size: clamp(1.72rem, 3.3vw, 2.72rem);
  line-height: 1.08;
  color: var(--text-strong);
}}
.hero p {{
  max-width: 46em;
  margin: 18px 0 0;
  font-size: 1.05rem;
  line-height: 1.72;
}}
  .library {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 24px;
}}
.book-card {{
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--panel-border);
  border-radius: 24px;
  background: var(--panel-bg);
  box-shadow: var(--shadow-soft);
  transition: transform 160ms ease, box-shadow 160ms ease;
}}
.book-card:hover {{
  transform: translateY(-3px);
  box-shadow: var(--shadow);
}}
.book-card__cover {{
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: var(--panel-strong);
}}
.book-card__cover img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
}}
.book-card__body {{
  padding: 20px 22px 24px;
}}
.book-card__body h3 {{
  margin: 0 0 8px;
  font-size: 1.15rem;
  color: var(--text-strong);
}}
.book-card__body p {{
  margin: 0 0 16px;
  font-size: 0.92rem;
  line-height: 1.62;
  color: var(--text-muted);
}}
.button {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 16px;
  border-radius: 999px;
  background: var(--accent-strong);
  color: #f8f4ea;
  font-size: 13px;
  font-weight: 700;
}}
@media (max-width: 860px) {{
  .library {{ grid-template-columns: 1fr; }}
  .hero {{ padding: 32px 24px 36px; }}
}}
</style>
</head>
<body>
<main class="site-shell">
  <section class="hero">
    <p class="hero__eyebrow">缠论学习书库</p>
    <h1>从 K 线到判断，把缠论讲成能看的书</h1>
    <p>这里不再按“基础册、实战册”拆开，而是合成一条真实学习路径：先用《看懂K线走势》理解价格走势，再用《缠论标记工具》把标记、解释和复盘串起来。</p>
  </section>
  <section class="library">
    {book_cards}
  </section>
</main>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="构建缠论学习书库统一站点")
    parser.add_argument("--skip-build", action="store_true", help="跳过Honkit构建，只做后处理")
    args = parser.parse_args()

    books = []
    for book_info in BOOK_DIRS:
        book_dir = REPO_ROOT / book_info["dir"]
        if not book_dir.exists():
            print(f"跳过不存在的目录: {book_dir}")
            continue
        books.append(book_info)

        if not args.skip_build:
            print(f"构建 {book_info['title']}...")
            import subprocess
            result = subprocess.run(
                ["npx", "honkit", "build", ".", "_book"],
                cwd=book_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"构建失败: {result.stderr}")
                continue
            print("  构建完成")

    # 清理并创建dist目录
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    # 复制每本书的构建结果到dist
    for book_info in books:
        book_dir = REPO_ROOT / book_info["dir"]
        build_dir = book_dir / "_book"
        if not build_dir.exists():
            print(f"警告: {book_info['title']} 没有构建结果")
            continue
        target_dir = DIST_DIR / book_info["slug"]
        shutil.copytree(
            build_dir,
            target_dir,
            ignore=shutil.ignore_patterns(
                "_archive",
                "site",
                "scripts",
                "node_modules",
                "*.md",
                "package.json",
                "package-lock.json",
            ),
        )
        print(f"复制 {book_info['title']} 到 dist/{book_info['slug']}")

    # 后处理：注入导航栏和自定义样式
    for book_info in books:
        target_dir = DIST_DIR / book_info["slug"]
        if target_dir.exists():
            inject_switcher(target_dir, book_info["slug"], books)
            print(f"后处理 {book_info['title']}")

    # 创建首页
    index_html = build_index_page(books)
    (DIST_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("创建首页")

    print(f"\n构建完成！输出目录: {DIST_DIR}")
    print(f"打开: {DIST_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
