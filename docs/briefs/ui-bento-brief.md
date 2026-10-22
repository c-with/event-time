# UI-BENTO-1 任務書：styles.css 全面重設計（便當盒＋深淺雙模式）

## 目標
將 static/styles.css 由現有綠色主題重寫為「便當盒 Bento Grid」設計系統，支援淺色/深色雙模式（跟隨系統 prefers-color-scheme 自動切換）。**只改 static/styles.css 一個檔案**，不改任何 JS/HTML/Python。

## 設計規範（已獲用戶確認，來自 stylekit bento-grid spec + 已批准的 B8/B9 樣板）
- B8 淺色樣板：/home/jc/cft/sketch-b8-bento-light.html
- B9 深色樣板：/home/jc/cft/sketch-b9-bento-dark.html
先讀呢兩個檔案，佢哋係用戶親自揀中嘅視覺方向。

### 色彩 token（CSS variables）
淺色（:root）：
- --paper:#FAFAFA（頁面底）--white:#FFFFFF（卡片）--ink:#18181B --ink-soft:#52525B --muted:#A1A1AA
- --line:#F0F0F1 --line-dark:#E4E4E7
- --primary:#3B82F6 --primary-soft:#DBEAFE --primary-ink:#1D4ED8
- accents: violet #8B5CF6 / pink #EC4899 / orange #F97316
- success:#22C55E/#DCFCE7/#15803D  danger:#F43F5E/#FFE4E6/#BE123C  warn:#F59E0B/#FEF3C7/#B45309

深色（@media(prefers-color-scheme:dark) 覆寫同名 token）：
- --paper:#18181B --white:#1F1F23 --ink:#FAFAFA --ink-soft:#A1A1AA --muted:#52525B
- --line:#27272A --line-dark:#3F3F46
- --primary:#3B82F6 --primary-soft:rgba(59,130,246,.18) --primary-ink:#93C5FD
- 卡片帶 inset 0 1px 0 rgba(255,255,255,.04) 內高光
- success/danger/warn 用 rgba 半透明底＋亮色字（照 B9 樣板數值）

### 結構規則（Bento）
- 所有卡片/panel：border-radius 20-24px、padding 20-22px、一致 gap（統一 18-20px）
- hover：translateY(-2px) scale(1.01)＋陰影變寬（transition all .2s）；按鈕 active:scale(.95)
- .stat-grid 四張卡用 nth-child 分別配唔同 accent（第3張風險紅漸變底、第1張藍調等，照 B8 c-risk/c-next 手法）
- .dashboard-grid 保持而家嘅兩欄結構都得，但視覺上要做出「大卡＋高卡＋小卡」層次
- 禁止所有卡一樣大小嘅單調感、禁止直角、禁止唔一致 gap

### 日曆 12 色（cal-theme-0..11）
呢啲 class 由 JS 按 session hash 落，必須保留全部 12 個。每個主題要淺深兩套值：
- 淺色：照現有（唔使改）
- 深色：喺 @media(prefers-color-scheme:dark) 入面為每個 .cal-theme-N 覆寫 --cal-bg/--cal-fg/--cal-border：bg 用低透明度暗色（rgba(59,130,246,.18) 風格），fg 用亮色（#93C5FD 風格），border 用中間色。12 個色系一一對應。

### 字體層級（重點：而家太細）
- body 14px；輔助文字最低 12px；pill 最低 11px
- .event-pill 由 9px 升到 11px（手機 media query 最低 10.5px）
- .tag 11px、.tiny 12px
- 頁面 h1 24px、panel h2 15px、stat-number 30px

### 必須保留嘅選擇器（JS/HTML 依賴，一個都唔可以刪）
app-shell/sidebar/brand-row/brand-mark/workspace-label/main-nav/nav-item(.active)/nav-icon/nav-count/sidebar-bottom/system-note/status-dot/operator-button/avatar/operator-copy/chevron/logout-button
main-area/topbar/breadcrumbs/breadcrumb-muted/crumb-slash/top-actions/global-search/icon-button
btn(-primary/-secondary/-quiet/-danger/-small/-full)/text-link
page-content/page-heading/eyebrow/heading-actions
stat-grid/stat-card(.alert/.warning)/stat-top/stat-icon/stat-number/stat-foot
dashboard-grid/panel/panel-header/panel-body/right-column/section-gap
calendar-toolbar/calendar-grid/calendar-weekday/calendar-day(.outside/.today/.drop-target)/day-number/day-events/event-pill(.past/.risk/.window/.middle/.start/.end)/more-events/day-node-count/calendar-legend/legend-dot(.warn/.window)
agenda-list/agenda-item/agenda-date/agenda-content
tag(.green/.orange/.red/.blue/.gray)
project-toolbar/search-field/select-control/project-list/project-card/project-cover/cover-mark/project-info/project-title-row/project-subline/project-next/project-actions/project-risk
project-detail-head/detail-cover/detail-main/detail-meta/detail-actions
tab-bar/tab-button(.active)/tab-count/detail-grid/summary-box/summary-row
entity-list/entity-card/entity-card-header/entity-meta/entity-actions/primary-mini
empty-state/empty-icon/resource-tabs/resource-tab(.active)/resource-grid/resource-card/resource-icon
change-card/change-mark/change-values/change-value/change-actions/approve
file-grid/file-card/file-preview/file-info/file-name/file-meta/file-actions
timeline/timeline-item/timeline-dot/timeline-time
modal-backdrop/modal(.wide)/modal-header/modal-close/modal-body/modal-footer
form-grid/form-field(.full)/form-error/modal-note(.warning/.danger)
toast-root/toast(.error/.warn)/login-screen/login-card
search-results/search-result/mobile-menu/hidden/muted
day-detail-modal/day-detail-body/day-detail-card(.past)/day-detail-head/day-detail-window/day-detail-risk/day-detail-notes/day-detail-node/day-detail-empty
cal-theme-0..11

### 交付檢查（自檢完先可以收工）
1. 上述選擇器清單每一個都喺新檔入面（grep -o 逐個驗證，輸出驗證結果）
2. 檔案唔超過 1200 行；純 CSS，零外部依賴
3. 深淺模式文字對比 ≥4.5:1（muted 色要驗）
4. 手機 media query（1200/950/640）三檔保留，640 檔按鈕/pill 觸控目標 ≥44px
5. prefers-reduced-motion: reduce 時關閉 hover transform
6. git diff 確認只有 styles.css 一個檔案改動

## 嚴格禁止
- 改 app.js / index.html / app.py / 任何後端
- 引入外部字體/CDN/依賴
- 刪任何選擇器
- commit（留工作區等我復驗）
