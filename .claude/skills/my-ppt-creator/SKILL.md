---
name: my-ppt-creator
description: Creates beautiful HTML/CSS/JS slide presentations ("PPT as Code"). Use when the user wants to build a presentation, deck, or slideshow — especially when they want it to look better than traditional PowerPoint, be shareable as a URL, or be version-controlled as code. Trigger on: "make a presentation", "create slides", "build a deck", "PPT as code", "HTML presentation".
---

# My PPT Creator — PPT as Code

## Overview

Build slide presentations as single-file HTML — no PowerPoint, no AI-generated layout messes.
The result is a reusable, linkable, versionable content asset, not a one-time file.

Core insight from Russell (@Russell3402):

> The real problem with PPT is not content — it's that you spend hours on tooling instead of expression.
> "PPT as Code" turns a one-time presentation file into a reusable, editable, deployable content system.

---

## Mental Model: 5 Parts of Any Presentation System

Every slide deck — PPT, Keynote, or HTML — is just these five things:

| Part          | What it is                                                  |
| ------------- | ----------------------------------------------------------- |
| **container** | The stage — one viewport, full screen                       |
| **slides**    | Each page's content — one `<section>` per slide             |
| **index**     | Which slide is current — one `currentIndex` integer         |
| **controls**  | How you advance — buttons, keyboard, URL, pagination        |
| **motion**    | How transitions feel — CSS transform + opacity + transition |

Animation is just the last layer. The real foundation is **state switching**.

---

## Workflow

### Step 1 — Gather requirements

Ask the user for:

- **Topic / title** of the presentation
- **Audience** (engineers, executives, customers, general)
- **Slide count** target (suggest 6–12)
- **Style direction**: minimal/technical, bold/product, editorial/story
- **Language**: Chinese or English (default: match user's language)

If the user provides an outline or content, use it directly. Skip asking.

### Step 2 — Generate the minimal HTML (master prompt)

Use this prompt with the AI coding tool (Claude Code / Cursor / Codex):

```
请帮我生成一个单文件 HTML demo，用来模拟类似 PPT 的分页展示动画。要求：

1. 只输出一个完整的 HTML 文件，包含内联 CSS 和内联 JavaScript。
2. 页面语言是中文，主题偏克制、现代，像产品发布页，不要廉价促销腔调。
3. 演示区域默认 16:9，桌面端居中展示，移动端自动切换为更适合区屏的比例。
4. 至少包含 4 张 slide，每页都有标题和一小段说明文字。
5. 每一页都用 section 表示，所有 slide 共用同一个 viewport。
6. 需要支持"上一页 / 下一页"按钮。
7. 需要支持左右方向键和 PageUp / PageDown 切页。
8. 切页动画优先使用 transform 和 opacity，不要用 top / left 做大范围动画。
9. JavaScript 里只维护一个 currentIndex 状态，当前页要有明显激活态，非当前页可以适当透明度。
10. 必须补 prefers-reduced-motion 的降级处理。
11. 代码结构尽量清晰，变量命名有意义，适合二次修改。
12. 输出时请额外代代码上方，用 6 到 10 行简要解释这个 demo 的结构：HTML 负责什么，CSS 负责什么，JavaScript 负责什么。

[在这里插入你的幻灯片内容/大纲]
```

**For English presentations**, replace the Chinese style instruction with:

```
Language: English. Style: clean, modern, technical. Like a product launch page, not a sales pitch.
```

### Step 3 — Add PPT-like capabilities (enhancement prompts)

Apply these one at a time, in order. Each builds on the previous.

#### 3a. Progress bar + dot navigation

```
基于我现在这个单文件 HTML 分页演示 demo，继续增强，但不要推倒重写。请只在现有结构上：
1. 顶部或底部加一个进度条，根据当前页数计算出百分比。
2. 还一组分页圆点，点击圆点可以跳到对应 slide。
3. 当前页的圆点要有激活态。
4. 保留原有按钮和键盘切页逻辑。
5. 不要引入任何第三方库。
6. 尽量复用 currentIndex 状态，不要重新搞一套逻辑。
7. 保持视觉风格统一，避免加出很多无关装饰。

输出时请先告诉我：这次新增功能分别属于"状态可视化"还是"导航能力"，并标出我后续如果想继续如何继续。
```

#### 3b. URL sync (for sharing specific slides)

```
请基于当前 HTML 分页演示，增加 URL 同步能力，但不要破坏现有按钮、键盘和动画逻辑。要求：
1. 当前页变化时，把 URL 更新为类似 #slide-1 #slide-2 这样的 hash。
2. 页面首次加载时，如果 URL 里已经有 hash，就需要定位到对应页面。
3. 浏览器前进后退时，演示要能跟着跳步切页。
4. 不要引入路由库，不要引入框架。
5. 优先使用 History API 或 hash 方案。
6. 请告诉我：这种 URL 同步更适合"可分享演示链接"，还是"上台播放模式"，以及为什么。
```

#### 3c. Fragment — step-by-step reveal within a slide

```
请在我现有的 HTML 分页演示上，增加类似 PPT fragment 的能力。要求：
1. 页内某些元素可以逐步显现，而不是一进页就全部显示。
2. 右方向键或空格键下一步操作时，优先显示当前页还没显现的 fragment。
3. 只有当前页全部显示完，才真正往下翻页。
4. fragment 的默认动画要轻量克制，优先用 opacity 和轻微位移，不要夸张飞入。
5. 在第 2 张 slide 里展示：标题常驻，三条 bullet 逐条出现。
6. 输出时请额外解释：为什么 fragment 的本质是"页内步骤状态"，而不是"单纯给几个 class"。
```

#### 3d. Media preloading (for image/video-heavy decks)

```
请帮我优化一个 HTML 分页演示，让它在图片和视频较多时切页更流畅。要求：
1. 优先考虑预加载当前页、前一页、后一页的重要资源。
2. 不要一口气把所有页面的资源都提前加载。
3. 如果某一页资源还没准备好，演示端显示合适的 loading 占位。
4. 不要引入打包工具或复杂工程化方案，只讨论在前端端里最实用的做法。
5. 请把建议分成三类：必须做、建议做、可选做。
```

#### 3e. Mobile adaptation

```
请基于现有 HTML 演示，补一套移动端适配方案。要求：
1. 桌面端保持 16:9 的发布会式演示观感。
2. 手机端不要简单缩小整张 slide，而要优先保证可读性。
3. 可以根据视窗尺寸切换为更接近 9:16 的布局。
4. 需要考虑移动端浏览器视口高度变化。
5. 不要做成完全两套页面，而是尽量复用同一套结构。
6. 输出时请说明：哪些是绝对必须做的，哪些是锦上添花。
```

### Step 4 — Visual design system

Before touching animations, lock in these four things:

**Typography**

- Titles: a display font with personality (Google Fonts CSS2 variable fonts work great)
- Body: a readable text font
- Numbers/stats: consistent width, single style
- Prompt: `请帮我选一套适合"[主题]"风格的 Google Fonts 字体组合：标题用有个性的 display 字体，正文用耐读的 text 字体，并输出 CSS 变量定义。`

**Color**

- Generate 3 style directions, pick one, then deepen:

```
请基于当前这个 HTML 演示项目，不直接生成最终页面，先帮我生成 3 套彼此差异明显的视觉方向：
1. 每套方案都要包括：设计关键词、设计气质、颜色气质、正文字体建议、主色 / 辅色推荐。
2. 三套方向不能只换颜色，要有明显的风格差异。
3. 风格方向尽量做到"产品 / 发布页 / 设计评论 / 信息可视化演示"这些成熟风格。
4. 输出时请告诉我：哪一套最适合"PPT as Code"这种程序性、偏设计系统的主题，为什么。
5. 不要直接写完整代码，先做视觉方案。
```

**Then lock the style (style-only pass)**:

```
请基于我已经选定的视觉方向，重构当前 HTML 演示的视觉样式，但不要推倒现有内容结构和交互逻辑。
1. 优先改 CSS，不要改写 HTML 和 JavaScript。
2. 用 CSS 变量先抽出颜色、圆角、阴影、间距、字号、字号段落。
3. 保持 slide 数量、内容排序、切页逻辑不变。
4. 目标气质风格：[你选的风格]。
5. 请重点优化：标题层级、卡片感、背景、按钮、分页器、边距条。
6. 输出时先解释：这次改动哪些是"风格层"，哪些是"结构层"，并保证只动风格层。
```

### Step 5 — Animation guidance

Good web PPT only needs heavy work in two places:

- **Slide transitions** — the big motion between pages
- **2–3 key in-slide rhythm animations** — entrance of hero elements

Everything else should be restrained.

- Simple flip: CSS `transition` is enough
- Orchestrated sequences (title enters, then number, then image): use **GSAP**
- Lens-cut between views: use **View Transition API**
- Scroll-type storytelling (not presenter-controlled): use **CSS Scroll Snap**

---

## Known Gotchas (bugs to avoid)

### 1. `classList.add("")` throws `DOMException: SyntaxError`

**Problem:** When implementing slide transitions with a "previous" direction class, a common pattern like:

```js
slides[current].classList.add(n > current ? "prev" : ""); // BROKEN
```

`classList.add("")` is spec-illegal — browsers throw `DOMException: SyntaxError` and kill the entire keydown handler silently. This manifests as: forward (→) navigation works, backward (←) navigation is completely dead.

**Fix:** Guard the add with a condition:

```js
if (n > current) slides[current].classList.add("prev");
// No else — the slide exits right via its default transform, no extra class needed
```

### 2. Keyboard stops working in fullscreen

**Problem:** When entering fullscreen (F11 or `requestFullscreen()`), browser chrome steals focus from `document`. A `document.addEventListener("keydown", ...)` listener stops receiving events. The deck appears frozen.

**Fix:** Three-part pattern:

```html
<!-- 1. Make the deck element focusable -->
<div id="deck" tabindex="0"></div>
```

```js
// 2. Refocus deck on fullscreen change and nav button clicks
const deckEl = document.getElementById("deck");
function refocus() {
  deckEl.focus({ preventScroll: true });
}
document.addEventListener("fullscreenchange", refocus);
document.addEventListener("webkitfullscreenchange", refocus);
deckEl.addEventListener("click", refocus);

// 3. Register keydown on BOTH document AND the deck element (dual listener)
document.addEventListener("keydown", handleKey);
deckEl.addEventListener("keydown", handleKey);

// 4. Buttons must also call refocus after navigation
prevBtn.addEventListener("click", () => {
  goTo(current - 1);
  refocus();
});
nextBtn.addEventListener("click", () => {
  goTo(current + 1);
  refocus();
});
```

Optional: add `F` key + double-click to toggle fullscreen programmatically:

```js
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    deckEl.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}
deckEl.addEventListener("dblclick", toggleFullscreen);
// add to handleKey: else if (e.key === "f" || e.key === "F") toggleFullscreen();
```

---

## Output format

When generating the presentation, always output:

1. **Single HTML file** — everything inline (CSS + JS + content), no external dependencies except Google Fonts CDN
2. **6–10 line architecture comment** at the top explaining what HTML / CSS / JS each handles
3. **Modification guide** — which variables to change for colors, fonts, content

Save to `/tmp/<project-name>-slides.html` by default. Open with any browser.

---

## Quick-start example

User says: "Make me a 6-slide deck about our RAG chatbot for a demo day."

1. Use the master prompt in Step 2 with this outline:
   - Slide 1: Title — "Acme RAG Chatbot"
   - Slide 2: Problem — engineers waste hours searching internal docs
   - Slide 3: Solution — team-scoped Q&A over Confluence + Jira
   - Slide 4: How it works — hybrid search pipeline diagram (text)
   - Slide 5: Live demo screenshot
   - Slide 6: What's next

2. Generate HTML → open in browser → verify 16:9, keyboard nav works
3. Add progress dots (3a) → add URL sync (3b) → done for MVP
4. Style pass with chosen direction → ship

---

## Frameworks (when to use instead of vanilla)

| Framework               | Use when                                                                                                        |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Vanilla HTML/CSS/JS** | You control the content long-term; want max flexibility                                                         |
| **reveal.js**           | You want a batteries-included system (fragments, auto-animate, Markdown slides) without maintaining it yourself |
| **CSS Scroll Snap**     | One-screen-at-a-time scroll narrative; audience browses at their own pace                                       |

**reveal.js starter prompt**:

```
请帮我用 reveal.js 将一个最小可用的 HTML 演示原型，主题是产品发布式分页展示。要求：
1. 先用 reveal.js 官方推荐结构搭建，不要引入无关插件。
2. 至少包含 4 张 slide。
3. 第 2 张演示 fragment。
4. 第 3 张演示 auto-animate。
5. 第 4 张演示一段代码或数据展版排版，但风格要简洁。
6. 优先使用 reveal.js 自带能力，不要为了技巧增加复杂定制。
7. 输出时请告诉我：如果我是内容创作者，不想长期维护自写逻辑，为什么 reveal.js 可能比手写更适合我。
```
