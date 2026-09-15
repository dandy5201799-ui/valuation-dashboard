# 缠论学习书库

[English README](./README.md)

这是一个按 `harness-books` 形式整理的缠论学习书库。根目录负责说明项目边界和在线阅读入口，每本书各自维护 `book.json / README.md / index.md / SUMMARY.md / chapters / appendices / diagrams / assets / styles`。

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <a href="./book2-chan-practice/">
        <img src="./book2-chan-practice/assets/cover.svg" alt="看懂K线走势" width="240">
      </a>
      <br>
      <strong>看懂K线走势</strong>
      <br>
      <a href="./book2-chan-practice/index.md">阅读草稿</a>
    </td>
    <td align="center" valign="top" width="50%">
      <a href="./book3-auto-marker/">
        <img src="./book3-auto-marker/assets/cover.svg" alt="缠论标记工具" width="240">
      </a>
      <br>
      <strong>缠论标记工具</strong>
      <br>
      <a href="./book3-auto-marker/index.md">阅读草稿</a>
    </td>
  </tr>
</table>

## 这两部分分别解决什么

### 看懂K线走势

解决“怎么一步步看懂一张真实 K 线图”：看清趋势、画出走势、判断结构、找到关键位置、等待确认、决定动作、配合周期、独立复盘。

原先分散讲的分型、笔、线段、中枢、走势类型、背驰、买卖点，已经按使用顺序放进这本书里。它不是“实战秘籍”，而是把学习缠论时真正会遇到的问题，按判断顺序讲清楚。

### 缠论标记工具

沉淀辅助标记工具的产品定位、规则表、算法边界和后续开发计划。

重点不是把工具吹成自动交易系统，而是明确它哪些标记能解释、能回放、能追溯，哪些仍需验证。

## 推荐阅读路径

- 想从零建立框架：看懂K线走势 → 缠论标记工具。
- 想先解决看图问题：直接读“看懂K线走势”。
- 想继续开发工具：先读“缠论标记工具”，再回看规则表和算法边界。

## 项目文件怎么读

- [项目规范](./SPEC.md)：说明哪些目录是当前有效内容、哪些是归档、哪些不提交。
- [项目进展](./PROJECT_STATUS.md)：记录当前完成度、待复核点和下一步。
- [`book2-chan-practice/`](./book2-chan-practice/)：主书源码。
- [`book3-auto-marker/`](./book3-auto-marker/)：工具说明书源码。
- [`tools/`](./tools/)：统一构建脚本。
- [`_archive/`](./_archive/)：旧书稿、早期素材、对话记录，不参与在线构建。

## 本地构建

构建整个在线书库：

```bash
python3 tools/build_chan_site.py
```

如果只想构建单本书，也可以在对应目录运行 Honkit：

```bash
npx honkit build book2-chan-practice
npx honkit build book3-auto-marker
```

也可以使用轻量脚本：

```bash
python3 tools/book-kit/build_honkit.py book2-chan-practice
```

## 配图甄选原则

这里不会把所有历史图都收入正文。只纳入后期校正过、适合教学沉淀的图。早期被指出过逻辑不清的图，会放在“待复核”而不是正文标准答案里。
