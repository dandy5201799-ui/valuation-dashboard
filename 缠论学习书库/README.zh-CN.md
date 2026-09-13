# 缠论学习书库

[English README](./README.md)

这是一个按 `harness-books` 形式整理的缠论学习书库：根目录负责展示整套书，三本书各自独立维护 `book.json / README.md / index.md / SUMMARY.md / chapters / appendices / diagrams / assets / styles`。

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <a href="./book1-chan-foundation/">
        <img src="./book1-chan-foundation/assets/cover.svg" alt="缠论结构基础" width="240">
      </a>
      <br>
      <strong>第一册：缠论结构基础</strong>
      <br>
      <a href="./book1-chan-foundation/index.md">阅读草稿</a>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="./book2-chan-practice/">
        <img src="./book2-chan-practice/assets/cover.svg" alt="观察区、确认点与错误承担" width="240">
      </a>
      <br>
      <strong>第二册：观察区、确认点与错误承担</strong>
      <br>
      <a href="./book2-chan-practice/index.md">阅读草稿</a>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="./book3-auto-marker/">
        <img src="./book3-auto-marker/assets/cover.svg" alt="缠论自动标记工具" width="240">
      </a>
      <br>
      <strong>第三册：缠论自动标记工具</strong>
      <br>
      <a href="./book3-auto-marker/index.md">阅读草稿</a>
    </td>
  </tr>
</table>

## 三本书分别解决什么

### 第一册：缠论结构基础

解决“严格结构如何从 K 线推导出来”：包含、分型、笔、线段、中枢、走势类型、背驰、买卖点。

适合用来建立底层语言，避免只凭感觉画线。

### 第二册：观察区、确认点与错误承担

解决“实际看盘时怎么从结构走向动作”：防守区、压力位、观察区、确认点、失败线，以及判断错了怎么认。

这是目前最接近实战训练的一册。

### 第三册：缠论自动标记工具

沉淀自动标记工具的产品定位、规则表、算法边界和后续开发计划。

重点不是把工具吹成全自动交易系统，而是明确它哪些已经能做，哪些仍需验证。

## 推荐阅读路径

- 想从零建立框架：第一册 → 第二册 → 第三册。
- 已经能画结构，想练实战：直接读第二册。
- 想继续开发工具：先读第三册，再回看第一册的严格规则。

## 本地构建

如果本机安装了 Honkit，可以直接构建单本书：

```bash
npx honkit build book1-chan-foundation
npx honkit build book2-chan-practice
npx honkit build book3-auto-marker
```

也可以使用轻量脚本：

```bash
python3 tools/book-kit/build_honkit.py book1-chan-foundation
```

## 配图甄选原则

这里不会把所有历史图都收入正文。只纳入后期校正过、适合教学沉淀的图。早期被指出过逻辑不清的图，会放在“待复核”而不是正文标准答案里。
