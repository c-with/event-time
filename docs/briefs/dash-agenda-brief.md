# DASH-AGENDA-1：今日/近期執行面板打通場次＋活動前 2 天預警

## 現狀（已診斷）
- /api/dashboard 嘅 upcoming_nodes 只由 time_nodes 表組成（app.py:734-740），生產 time_nodes=0 行
- 同事錄活動用場次（event_sessions，有 starts_at/date_mode/status），日曆讀 sessions 所以顯示到，但右側「今日 / 近期執行」panel 讀 upcoming_nodes 所以永遠空
- renderAgenda（app.js:331）render n.label / n.project_name / n.session_title / n.planned_start / n.responsible / n.date_status

## 任務（改 app.py dashboard 端點為主，app.js 微調）

### 1. upcoming_nodes 融合場次（方案 A：虛擬節點，零寫入）
- 喺 dashboard() 入面，除咗既有 time_nodes 查詢，另查場次：
  `select(EventSession).where(EventSession.starts_at.is_not(None), EventSession.date_mode=='fixed')`（擇日窗口 window 同 undated 唔計）
- 每個符合時間窗嘅場次生成一個 virtual node dict：
  {label: 場次 title（或「活動日」）, project_name: 場次.project.name, session_title: 場次.title, planned_start: 場次.starts_at, responsible: 場次.owner 或 '', date_status: 場次.status, source: 'session'}
- 與既有 time_nodes 結果合併、按 planned_start 排序、去重（同一 session 已有 time_node 嘅話，虛擬節點唔好重複出——用 session_id 對比 existing nodes 嘅 session_id）

### 2. 時間窗：活動前 2 天預警
- 既有窗口：today-1 到 today+7。改為：**today-1 到 today+7 保留**，另外加入「前 2 天預警」語義：
  - 窗口內嘅 session 節點如果 planned_start 喺未來 2 日內（today 到 today+2），標 is_upcoming_soon: true
  - 呢啲節目排最前（今日嘅排第一，跟住未來 2 日）
- app.js renderAgenda：is_upcoming_soon 嘅 item 喺標題行加一個 tag（用現有 .tag.orange，文字「即將到來」）；今日嘅加 .tag.green「今日」

### 3. 今日判定
- 今日節點（planned_start date == today）排最頂（既有 sort 保持穩定即可，主要係加 tag）

## 嚴格禁止
- 唔好寫入任何數據（虛擬節點純查詢層）
- 唔好改 time_nodes 業務邏輯／其他端點
- styles.css 唔使改（用現有 tag class）

## 驗收自檢
1. python3 -m py_compile app.py && node --check static/app.js
2. 講述：虛擬節點生成代碼行號、去重邏輯、排序邏輯
3. git diff 只 app.py + static/app.js
4. 唔好 commit
