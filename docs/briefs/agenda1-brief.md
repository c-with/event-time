# AGENDA-1 任務書：今日/近期執行面板打通場次數據＋活動前 2 天預警

## 背景與根因
- /api/dashboard（app.py:726-741）嘅 upcoming_nodes 只由 time_nodes 表組成
- 用戶實際錄活動用「場次」（event_sessions，有 starts_at/date_mode/status），time_nodes 全庫 0 行
- 結果「今日/近期執行」永遠空——招聘會（2026-10-22，fixed 已確認）唔顯示

## 修復方案 A（查詢層虛擬節點，唔改數據模型）

### 1. 改 app.py dashboard 端點
- 查 event_sessions：date_mode='fixed'（有 starts_at）或 window（window_start 有值），所屬 project 未歸檔
- 為每個符合日期範圍嘅場次生成虛擬節點 dict，merge 入 upcoming_nodes：
  - label = 場次 title；project_name = project.name；session_title = ''（本身係場次，唔好重複）
  - planned_start = starts_at（window 用 window_start）
  - date_status：場次 status（已確認→「已确认」tag 前端 statusTag 會處理）
- **日期範圍：today-1 至 today+7 改為 today-1 至 today+9**（用戶要求：活動前 2 天就要見到做預警，即未來 7 日窗口 + 前置 2 日預警 = 未來 9 日）
- merge 後按 planned_start 排序；虛擬節點同真 time_node 若同日同場次並存，兩條都顯示（時間節點係布場/彩排等執行動作，場次日係活動本身，唔算重複——但 session_title 為空可以區分）

### 2. 前端預警視覺（static/app.js renderAgenda）
- 虛擬節點（場次）喺 activity 前 2 日內（planned_start date - today <= 2 且 >0）加「臨近」tag（用現有 tag orange class）
- renderAgenda 而家 slice(0,8)——夠用唔使改
- agenda item 嘅 subtitle 顯示 場次狀態（已确认/待排期）

### 3. 保守約束
- 只改 app.py dashboard 端點 + app.js renderAgenda（+styles.css 如 tag 需要新 class，盡量用現有）
- 唔好改 time_nodes 相關邏輯、唔好改 /api/calendar（日曆已經顯示場次）
- serialize 場次時留意 timezone（aware()）同現有 nodes 一致

## 驗收自檣
1. python3 -m py_compile app.py；node --check static/app.js
2. 講出：招聘會（2026-10-22）喺 2026-10-23 呢天會唔會出現（today-1 包到）；2026-10-29 發哥招聘會（+6日）會出現兼帶「臨近」定唔帶（2026-10-23 起 6 日 > 2，唔帶；10-27 起就會帶）
3. git diff 只有 app.py + app.js
4. 唔好 commit
