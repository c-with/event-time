# event-time 7786aec 部署獨立審計報告

審計人：獨立審計 subagent（只讀＋curl 驗證，未改任何檔案／未重啟容器）
日期：2026-10-21（UTC）
對象：event-time @ 7786aec（7fd82b3 + 7786aec，日曆分色＋日詳情 dialog）

---

## A. 部署聲稱核實（5 項）

| # | 聲稱 | 結論 | 證據 |
|---|------|------|------|
| 1 | 兩目錄拉到 7786aec，部署目錄保留 compose 端口＋腳本 chmod | VERIFIED | Workspace HEAD=7786aec9 且 git status 乾淨；部署目錄 HEAD=7786aec9，本地修改僅 compose.yaml（0.0.0.0:${HOST_PORT:-8600}）＋6 個腳本 mode-only chmod（-rwxrwxr-x），無意外改動。兩目錄 diff 除 compose.yaml/backups/logs/migration-source（運行時產物）外一致 |
| 2 | node --check / py_compile 全過 | VERIFIED | 重跑 node --check static/app.js PASS、python3 -m py_compile app.py PASS |
| 3 | 隔離預驗容器 et-test-7786aec 已清理 | FAILED | docker ps -a 顯示 et-test-7786aec 審計時仍運行（已於審計後由主控清理），綁 127.0.0.1:8601，接 infra-db 網絡。預驗做過（容器存在即證），但「已清理」不實 |
| 4 | 生產容器 Up healthy，容器內容為 7786aec | VERIFIED | event-time-v041 Up 3 hours (healthy)，Restarts=0，StartedAt 12:45:20Z；git show 7786aec:static/app.js 與容器內 /app/static/app.js sha256 相同（5ca5bace…），styles.css（cf13e5d9…）、app.py（b3cd1659…）同樣 byte-identical；容器內 styles.css 有 12 個 cal-theme- class、app.js 有 day-detail-modal |
| 5 | 數據零遷移 | VERIFIED | 兩 commit 僅改 static/app.js + static/styles.css（--stat 確認），無 schema 變更；生產容器啟動日誌無 ALTER/CREATE TABLE/migration 輸出（僅 db.create_all() 補缺表）；live API 返回 11 sessions 數據完好 |

---

## B. 新代碼審查（7fd82b3 + 7786aec）

### XSS — 冇發現問題
- esc()（app.js:22）覆蓋 & < > " ' 五字符，語義正確。
- day-detail modal 內所有動態插值逐個核對：name/subtitle/timeText/venue/notes/heading、node 嘅 node_type/label/project_name/session_title/responsible/date_status/planned_start、按鈕 data-project-id/data-session-id、event-pill title/data-start/data-end — 全部經 esc()。
- aria-label 中 key 由 dateKey() 內部生成（非用戶輸入），openDayModal 入口有 /^\d{4}-\d{2}-\d{2}$/ 白名單校驗。
- calendarColorClass() 輸出固定格式 cal-theme-<0..11>（FNV-1a hash % 12），冇注入面。

### 事件綁定 — 冇發現問題
- 新增兩個 listener（root 日曆格點擊、modalRoot backdrop 點擊）均為初始化時一次性掛載嘅事件委託，渲染循環唔會重複綁定；innerHTML 重寫唔會洩漏 listener（掛喺常駐父節點）。
- backdrop click → closeModal() 冪等；open-session 分支新加 closeModal() 先跳轉，修復舊代碼 modal 殘留。
- event-pill 點擊有 closest('[data-action]') 保護，唔會同 day-cell 雙觸發。
- Escape 鍵關閉已有（app.js:753）；modal 打開後關閉按鈕 focus()。

### 前後端字段對齊 — 冇發現問題（live API 實測）
用 .env 憑證登入（login 200）實測 /api/calendar（200，11 sessions）：
- session 消費字段 id/project_id/title/starts_at/ends_at/date_mode/window_start/window_end/status/notes/revision/project/is_past/has_risk 全部存在；venue 僅在有 venue_space 時由後端提供，前端 s.venue||s.location_text||'地点待确认' 三級 fallback 正確（live 數據無 venue key、有 location_text，fallback 已實際走到）。
- time_node 消費字段：後端 serialize_time_node(n) | {project_name, project_phase, session_title} 補齊（app.py:1055），對齊。live time_nodes=0 係冇數據，非假功能（查詢邏輯真實存在 app.py:1046-1048）。

### 假功能檢查 — is_past/has_risk 為真
後端 /api/calendar（app.py:1051-1052）真實計算：is_past=bool(ends_at<now)；has_risk=any(task.is_overdue) or any(node.date_status=="冲突")。live 全 False 只反映當前數據狀態，唔係前端恆 undefined。

### CSS（styles.css +48 行）
- 12 個 cal-theme 色板全部淺底深字（如 #e3f0ff/#20549b、#fff0d6/#88551c），對比度足夠。
- 新規則置於文件尾，正確覆蓋舊 .event-pill.risk；position:relative 已補，::after 角標定位正常。
- 手機媒體查詢（day-detail-node 轉 block、按鈕 min-height:44px、day-number 24px）合理，與既有 640px 斷點一致。

### 運行時
- /health 200 {"ok":true,"database":"postgresql"}；登入＋calendar API 200。
- docker logs event-time-v041 --since 4h：0 個 traceback/error/500。
- #modal-root 存在（index.html:59）；新函數引用嘅 DOM 掛載點齊全。

---

## C. 問題分級

### P0（生產壞咗）
冇發現。

### P1（功能唔完整或潛在 bug）
1. 聲稱 3 不實：et-test-7786aec 未清理。docker ps -a → Up 3 hours，綁 127.0.0.1:8601，接 infra-db 網絡，DB_HOST=postgresql（未見隔離 DB_NAME 覆蓋，很可能連生產數據庫 activity_workbench）。影響：資源/端口佔用＋一個連生產 DB 嘅第二寫入端點殘留（經 8601 操作會寫入生產數據）。建議 docker rm -f et-test-7786aec（審計按限制未執行）。

### P2（改進項）
2. legend 與新分色脫節：legend 仍三色點（綠/紅/黃，.legend-dot 舊綠 #4d9b83），pill 已係 12 色 per-activity；.event-pill.window 底色改用 var(--cal-bg)，window 與 fixed 只剩 dashed border 區分，legend 黃點對應唔上。
3. window pill 識別度下降：手機 8px 字＋1px dashed border 難分辨（dialog 有「择日待定」文字補償，影響有限）。
4. modal 無 focus trap：Tab 可移出 dialog（原有 modal 同樣，非本次退步）。

---

## D. 總結

部署真實性：4/5 VERIFIED，1 FAILED。生產部署完成且質素好——三份關鍵檔案 byte-identical（sha256 實測）、healthy 零重啟、日誌乾淨、零遷移屬實、本地修改完好。唯一不實：「臨時容器已清理」——et-test-7786aec 仍運行且接 infra-db 網絡（很可能連生產 DB），需跟進清理（P1）。

更新內容質素：良好。XSS 防護完整（esc() 全覆蓋＋key 白名單）、事件委託無重複綁定/洩漏、前後端字段 live 實測全對齊、is_past/has_risk 後端真實計算非假功能、escape/backdrop 關閉齊全、CSS 對比度足夠。本次更新冇引入 P0/P1 級代碼 bug。
