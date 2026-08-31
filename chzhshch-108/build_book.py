#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 chzhshch-108-plus 仓库里的 108 课 + 补充文章合并成「GitBook 风格」的单文件网页书。
图片 base64 内嵌，无任何外部 CDN 依赖，双击 HTML 即可离线阅读。
"""
import base64
import html
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(ROOT, "chzhshch-108-plus")
SRC = os.path.join(REPO, "108")
OUT = os.path.join(ROOT, "缠论108课加强版_GitBook风格.html")

# ----------------------------------------------------------------------------
# 0. 图片 → base64 data URI
# ----------------------------------------------------------------------------
def make_img_uri_map():
    m = {}
    pic = os.path.join(SRC, "pic")
    if os.path.isdir(pic):
        for fn in os.listdir(pic):
            p = os.path.join(pic, fn)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(fn)[1].lstrip(".").lower()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/%s" % ext)
            with open(p, "rb") as fh:
                m[fn] = "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode())
    return m

IMG_MAP = make_img_uri_map()


def embed_img_ref(src):
    """把 ./pic/xxx 转换为 data URI；若找不到图片则返回原样（不破坏链）。"""
    fn = os.path.basename(src)
    if fn in IMG_MAP:
        return IMG_MAP[fn]
    return src


# ----------------------------------------------------------------------------
# 1. Markdown → HTML（占位符避免转义冲突）
# ----------------------------------------------------------------------------
PLACEHOLDERS = []   # 存 {tag, html}；<img>/<code>/<pre> 等已生成的片段
_PH_IDX = [0]

def _ph(html_seg):
    PLACEHOLDERS.append(html_seg)
    return "\u0001PH%d\u0001" % (_PH_IDX[0][0] if False else len(PLACEHOLDERS) - 1)

def _restore(text):
    def rep(m):
        return PLACEHOLDERS[int(m.group(1))]
    return re.sub(r'\u0001PH(\d+)\u0001', rep, text)


def inline(text):
    """行内语法 → HTML。先用占位符取出 <img>/<code>，再转义普通文本，最后恢复占位符。"""
    text = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        lambda m: _ph('<figure class="lesson-img"><img src="%s" alt="%s" loading="lazy"></figure>'
                      % (html.escape(embed_img_ref(m.group(2))), html.escape(m.group(1)))),
        text,
    )
    text = re.sub(
        r'`([^`]+)`',
        lambda m: _ph('<code class="inline-code">%s</code>' % html.escape(m.group(1))),
        text,
    )
    # 加粗
    text = re.sub(
        r'\*\*(?!#)([^*#]+)\*\*|(?<!<)__(?!#)([^_]+)__',
        lambda m: _ph('<strong>%s</strong>' % html.escape(m.group(1) or m.group(2))),
        text,
    )
    # 现在转义剩余文本
    text = html.escape(text, quote=False)
    return _restore(text)


def block(text):
    """块级：标题/引用/表格/预格式化/段落。返回 HTML 字符串。"""
    text = text.strip("\n")
    if not text:
        return ""

    lines = text.split("\n")

    m = re.match(r'^#{1,6}\s+(.*)$', text, flags=re.S)
    if m:
        lvl = len(re.match(r'^#+', text).group(0))
        return '<h%d class="md-h">%s</h%d>' % (min(lvl, 6), inline(m.group(1).strip()), min(lvl, 6))

    # 代码块 fenced ``` ... ```
    if lines[0].strip().startswith("```") or lines[0].strip().startswith("~~~"):
        fence = lines[0].strip()
        ch = fence[0]
        # 同一字符闭包
        inside = "\n".join(lines[1:])
        if inside.endswith(ch * 3) or inside.rstrip().endswith(ch * 3):
            code = inside.rstrip()
            # 去掉末尾闭合 fence
            code = re.sub(r'(?:%s{3})\s*$' % re.escape(ch * 3), "", code)
            code = code.rstrip("\n")
        else:
            code = inside
        return '<pre class="code-block">%s</pre>' % html.escape(code)

    # 一块内若有 fenced code，也兜底
    if lines[0].strip().startswith("```") is False and (
        any(re.match(r'^```|^~~~', ln) for ln in lines)):
        # 罕见情况：拆分处理
        parts, cur, acc = [], None, []
        for ln in lines:
            if re.match(r'^```|^~~~', ln):
                if cur is None:
                    if acc:
                        parts.append(("\n".join(acc)))
                        acc = []
                    cur = ln[0]
                else:
                    acc.append(ln if False else "")
                    # 完成了——这一行是闭合
                    acc.pop()
                    parts.append("```ok")
                    acc = []
                    cur = None
            else:
                acc.append(ln)
        if acc:
            parts.append("\n".join(acc))
        out = "".join(block(p) for p in parts if p.strip())
        return out

    # 引用块
    if all(re.match(r'^>\s?', ln) for ln in lines):
        body = "\n".join(re.sub(r'^>\s?', "", ln) for ln in lines)
        return '<blockquote class="md-quote">%s</blockquote>' % inline(body)

    # 表格 / ASCII 图（以 | 开头且多行）
    if len(lines) >= 2 and all(ln.strip().startswith("|") for ln in lines if ln.strip()):
        # 是 markdown 表格（有 --- 分隔）？
        is_table = any(re.match(r'^\|?[\s:\-|]+$', ln) and "---" in ln for ln in lines)
        if is_table:
            rows = []
            for ln in lines:
                if not ln.strip():
                    continue
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if all(re.match(r'^:?-{2,}:?$', c) for c in cells if c):
                    continue
                rows.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells) + "</tr>")
            return '<table class="md-table"><tbody>%s</tbody></table>' % "".join(rows)
        # ASCII 图 → 预格式化
        return '<pre class="ascii-art">%s</pre>' % html.escape("\n".join(lines))

    # 普通段落：保留空行内多行的换行
    para = "<br>".join(inline(ln.strip()) if ln.strip() else "" for ln in lines)
    return '<p class="md-p">%s</p>' % para


def md_to_html(md_text):
    out = []
    for para in re.split(r'\n{2,}', md_text):
        if para.strip():
            out.append(block(para))
    return "\n".join(out)


# ----------------------------------------------------------------------------
# 2. 解析课程文件
# ----------------------------------------------------------------------------
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
    m = re.match(r'^(\d{4})', fname)
    return int(m.group(1)), "Z"


def build_lessons():
    lessons = []
    for fname in sorted(os.listdir(SRC)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(SRC, fname)
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()

        no, extra = classify(fname)

        # 拆分正文 / 评论区
        marker = "**本文评论获取自"
        if marker in raw:
            main_part, comments_part = raw.split(marker, 1)
        else:
            main_part, comments_part = raw, ""

        lines = main_part.split("\n")
        title = fname
        meta = ""
        if lines and lines[0].lstrip().startswith("#"):
            tm = re.match(r'^#+\s*\d+\s*-\s*(.*)$', lines[0].strip())
            if tm:
                title = tm.group(1).strip() or title
            # 标题后首个非空行若是日期/分类行，抽为 meta 并从正文剔除
            rest = lines[1:]
            content_start = 0
            for i, ln in enumerate(rest):
                if ln.strip():
                    if ln.strip().startswith("日期：") or ln.strip().startswith("分类："):
                        meta = ln.strip()
                        content_start = i + 1
                    break
            main_part = "\n".join(rest[content_start:])

        body_html = md_to_html(main_part)

        # 评论区
        comments_html = ""
        if comments_part.strip():
            items = []
            for para in re.split(r'\n{2,}', comments_part):
                b = re.sub(r'^```\s*', "", para.strip())
                b = re.sub(r'```\s*$', "", b).strip()
                if not b:
                    continue
                cm = re.match(r'(UID:\[[^\]]*\]\s*昵称：\S{1,30}\s*日期：\([^)]*\))', b, re.S)
                if cm:
                    head, body = cm.group(1), b[cm.end():].strip()
                    items.append('<div class="comment"><div class="comment-head">%s</div>'
                                 '<div class="comment-body">%s</div></div>'
                                 % (html.escape(head), md_to_html(body)))
                else:
                    items.append('<div class="comment">%s</div>' % md_to_html(b))
            if items:
                comments_html = (
                    '<details class="comments"><summary class="comments-summary">'
                    "📎 课后评论与同门回复（%d 条）</summary>\n<div class=\"comments-inner\">%s</div></details>"
                    % (len(items), "\n".join(items)))

        lessons.append({
            "no": no, "extra": extra, "title": title, "meta": meta,
            "body": body_html, "comments": comments_html,
        })

    lessons.sort(key=lambda x: (0 if x["extra"] == "" else 1,
                                x["no"],
                                0 if x["extra"] == "P" else (1 if x["extra"] == "W" else 2)))
    return lessons


# ----------------------------------------------------------------------------
# 3. 组装
# ----------------------------------------------------------------------------
LESSONS = build_lessons()

toc_parts, body_parts = [], []
cur_group = None
supp_open = False

for les in LESSONS:
    no, extra = les["no"], les["extra"]
    item_id = ("les-%d-%s" % (no, extra)) if extra else ("les-%d" % no)

    if extra == "":
        g = ((no - 1) // 10) * 10 + 1
        if g != cur_group:
            if cur_group is not None:
                toc_parts.append("</details>")
            grp_end = min(g + 9, 108)
            toc_parts.append('<details class="toc-group" open><summary>第 %d–%d 课</summary>'
                             % (g, grp_end))
            cur_group = g
        toc_label = "第 %d 课 · %s" % (no, les["title"])
        title_html = "第 %d 课　%s" % (no, les["title"])
    else:
        if not supp_open:
            if cur_group is not None:
                toc_parts.append("</details>")
            toc_parts.append('<details class="toc-group toc-supp" open><summary>补充文章（课格外）</summary>')
            supp_open, cur_group = True, None
        toc_label = "补充 · %s" % les["title"]
        title_html = "补充文章 · %s" % les["title"]

    toc_parts.append(
        '<a class="toc-item" href="#%s" data-title="%s">%s</a>'
        % (item_id, html.escape(toc_label), html.escape(toc_label)))

    meta_html = ('<div class="lesson-meta">%s</div>' % inline(les["meta"])) if les["meta"] else ""
    body_parts.append(
        '<section class="lesson" id="%s">'
        '<h1 class="lesson-title">%s</h1>%s'
        '<div class="lesson-body">%s</div>%s</section>'
        % (item_id, html.escape(title_html), meta_html, les["body"], les["comments"]))

if cur_group is not None or supp_open:
    toc_parts.append("</details>")

TOC_STR = "\n".join(toc_parts)
BODY_STR = "\n".join(body_parts)

CSS = """
:root{
  --bg:#f6f5f1; --panel:#fff; --ink:#2c2a26; --mut:#8a857b;
  --acc:#b8863b; --acc2:#7a5c2e; --line:#e6e2d8; --side-w:320px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);display:flex;}
a{color:var(--acc2);text-decoration:none}
#sidebar{position:fixed;inset:0 auto 0 0;width:var(--side-w);background:#fbfaf6;
  border-right:1px solid var(--line);display:flex;flex-direction:column;z-index:20;}
.side-head{padding:16px 16px 10px;border-bottom:1px solid var(--line);}
.side-head h1{font-size:15px;margin:0 0 4px;color:var(--acc2);}
.side-head .sub{font-size:11px;color:var(--mut);}
#search{width:100%;margin-top:10px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff;}
#toc{flex:1;overflow:auto;padding:8px 8px 24px;}
.toc-group{margin:4px 0;}
.toc-group summary{cursor:pointer;font-size:12px;font-weight:600;color:var(--mut);padding:7px 6px;border-radius:6px;user-select:none;}
.toc-group summary:hover{background:#f0ece2;}
.toc-item{display:block;font-size:12.5px;line-height:1.4;padding:6px 8px 6px 18px;color:#4c463c;
  border-left:2px solid transparent;margin:1px 0;border-radius:0 6px 6px 0;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.toc-item:hover{background:#f0ece2;color:var(--acc2);}
.toc-item.active{background:#f3ead2;color:var(--acc2);border-left-color:var(--acc);font-weight:600;}
#content{padding:0 0 0 var(--side-w);flex:1;min-width:0;}
article{max-width:820px;margin:0 auto;padding:44px 52px 120px;}
.lesson{margin-bottom:64px;border-bottom:1px dashed var(--line);padding-bottom:44px;}
.lesson:last-child{border-bottom:none;}
.lesson-title{font-size:22px;line-height:1.45;margin:0 0 6px;color:var(--ink);}
.lesson-meta{font-size:12px;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:22px;}
.lesson-body{font-size:15.5px;line-height:1.95;text-align:justify;}
.md-p{margin:0 0 1em;}
.md-h{font-size:19px;color:var(--acc2);margin:1.3em 0 .6em;}
.md-quote{border-left:3px solid var(--acc);background:#faf5e8;margin:1em 0;padding:10px 14px;color:#5c564a;}
.md-table{border-collapse:collapse;margin:1em 0;max-width:100%;}
.md-table td{border:1px solid var(--line);padding:6px 10px;font-size:13px;}
.code-block{background:#f2eee4;border:1px solid var(--line);border-radius:8px;padding:12px 14px;
  font-family:Consolas,"PingFang SC",monospace;font-size:13px;overflow:auto;white-space:pre-wrap;}
.inline-code{background:#f0ece0;border-radius:4px;padding:0 5px;font-family:Consolas,monospace;font-size:.9em;}
.ascii-art{background:#f2eee4;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:11.5px;line-height:1.35;}
.lesson-img{margin:1.2em auto;text-align:center;}
.lesson-img img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.06);}
.comments{margin-top:26px;background:#fffdf6;border:1px solid var(--line);border-radius:10px;}
.comments-summary{cursor:pointer;padding:12px 16px;font-size:13px;color:var(--acc2);background:#f8f3e4;border-radius:10px;user-select:none;}
.comments[open] .comments-summary{border-bottom:1px solid var(--line);border-radius:10px 10px 0 0;}
.comments .comments-inner{padding:2px 16px 12px;}
.comment{border-bottom:1px dashed var(--line);padding:10px 0;}
.comment:last-child{border-bottom:none;}
.comment-head{font-size:12px;color:var(--mut);font-weight:600;margin-bottom:4px;}
.comment-body{font-size:13.5px;line-height:1.7;}
.comment .code-block{font-size:12px;}
#floatbar{position:fixed;right:22px;bottom:22px;display:flex;gap:8px;z-index:30;}
#floatbar button{background:var(--acc2);color:#fff;border:none;border-radius:50%;width:46px;height:46px;
  font-size:17px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25);transition:transform .12s ease;}
#floatbar button:hover{transform:translateY(-2px);}
#floatbar button:disabled{opacity:.35;cursor:default;transform:none;}
#backtop{background:#8a857b;}
#progress{position:fixed;top:0;left:var(--side-w);right:0;height:3px;z-index:40;}
#prog{height:100%;width:0;background:var(--acc);}
@media (max-width:820px){:root{--side-w:240px}article{padding:24px 18px 96px;}}
"""

JS = """
(function(){
  var tocItems=Array.prototype.slice.call(document.querySelectorAll('.toc-item'));
  var lessons=Array.prototype.slice.call(document.querySelectorAll('.lesson'));
  var search=document.getElementById('search');
  var prevBtn=document.getElementById('prev'),nextBtn=document.getElementById('next');
  var prog=document.getElementById('prog');
  var whole=lessons, current=0;

  function idxOf(id){for(var i=0;i<whole.length;i++)if(whole[i].id==id)return i;return 0;}
  var lastActive=null;
  function onScroll(){
    var y=window.scrollY+120,active=whole[0];
    for(var i=0;i<whole.length;i++){var el=whole[i];if(el.offsetTop<=y)active=el;else break;}
    current=idxOf(active.id);
    tocItems.forEach(function(a){a.classList.remove('active');lastActive=null;});
    var curA=document.querySelector('.toc-item[href="#'+active.id+'"]');
    if(curA){curA.classList.add('active');if(curA!==lastActive){curA.scrollIntoView({block:'nearest'});lastActive=curA;}}
    prevBtn.disabled=(current===0);
    nextBtn.disabled=(current===whole.length-1);
    var h=document.documentElement,max=h.scrollHeight-h.clientHeight;
    prog.style.width=(max>0?(window.scrollY/max*100):0)+'%';
  }
  function go(i){if(i<0||i>=whole.length)return;whole[i].scrollIntoView({behavior:'auto',block:'start'});onScroll();}
  prevBtn.addEventListener('click',function(){go(current-1);});
  nextBtn.addEventListener('click',function(){go(current+1);});
  document.getElementById('backtop').addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});
  tocItems.forEach(function(a){a.addEventListener('click',function(){var id=a.getAttribute('href').slice(1);
    var el=document.getElementById(id);if(el){el.scrollIntoView({behavior:'auto',block:'start'});}});});
  document.addEventListener('keydown',function(e){
    if(e.target&&(e.target.tagName=='INPUT'||e.target.tagName=='TEXTAREA'))return;
    if(e.key=='ArrowDown'){e.preventDefault();go(current+1);}
    else if(e.key=='ArrowUp'){e.preventDefault();go(current-1);}
    else if(e.key=='Home'){window.scrollTo({top:0});}
    else if(e.key=='End'){window.scrollTo({top:document.body.scrollHeight});}
  });
  search.addEventListener('input',function(){
    var q=search.value.trim().toLowerCase();
    tocItems.forEach(function(a){a.style.display=(q&&a.dataset.title.toLowerCase().indexOf(q)<0)?'none':'';});
    var groups=[].slice.call(document.querySelectorAll('.toc-group'));
    groups.forEach(function(g){
      var items=g.querySelectorAll('.toc-item'),any=false;
      for(var i=0;i<items.length;i++){if(items[i].style.display!=='none'){any=true;break;}}
      g.style.display=any?'':'none';
    });
  });
  window.addEventListener('scroll',onScroll,{passive:true});
  onScroll();
})();
"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>缠中说禅教你炒股票108课（加强版）· 网页书</title>
<style>%s</style>
</head>
<body>
<div id="sidebar">
  <div class="side-head">
    <h1>缠中说禅 · 教你炒股票</h1>
    <div class="sub">108课加强版 · 含课后评论与配图</div>
    <input id="search" type="text" placeholder="🔍 按标题搜索（分型 / 中枢 / 背驰）…">
  </div>
  <nav id="toc">%s</nav>
</div>
<div id="progress"><div id="prog"></div></div>
<main id="content"><article>%s</article></main>
<div id="floatbar">
  <button id="prev" title="上一课">↑</button>
  <button id="next" title="下一课">↓</button>
  <button id="backtop" title="回顶部">☰</button>
</div>
<script>%s</script>
</body>
</html>
""" % (CSS, TOC_STR, BODY_STR, JS)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(HTML)

print("OK 输出:", OUT)
print("大小: %.1f MB" % (os.path.getsize(OUT) / 1024 / 1024))
print("课程总数:", len(LESSONS))
