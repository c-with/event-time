# 7786aec 兩 commit 前端獨立交叉審計

審計人：Codex cross-audit  
日期：2026-10-21  
審計基線：7786aec9b61afd70f6d3f3bfb325fface703e2dd（含 7fd82b3482aabe45cf3fd801285d21bb8abc5042）；差異基準：30aa106（7fd82b3 的 parent）。

## 範圍與證據規則

只讀檢視 Git 版本中的源碼與兩份既有報告，唯一寫入為本報告。工作目錄 HEAD 為 e033df8，因此下文業務源碼行號一律指 **7786aec 的 Git blob**，不是目前工作樹；明示 30aa106 者例外。已確認兩 commit 只改 static/app.js、static/styles.css，app.py/models.py 無差異。

VERIFIED 表示靜態機制已核對；ISSUE 表示可推導的問題或限制；SKIPPED 表示未驗證，不等於通過。使用 Node 在記憶體內執行抽取的純函數與日期範例，目標 app.js 的 node --check 通過；沒有啟動應用、存取資料庫、連接 8600、操作容器、commit、push 或部署。P0 僅表示已有生產壞掉證據，本次不據靜態審計將 JC 的 P0 標籤等同生產故障。

## 1. 邏輯邊界

| 檢查 | 結果 | 證據與判斷 |
| --- | --- | --- |
| hash 渲染及 refresh 穩定性 | VERIFIED | static/app.js:204–208：純字串 FNV-1a/Math.imul，無隨機、時間或陣列序號；ID 不變則跨渲染、refresh 同色。取模有碰撞，不能保證不同場次異色。 |
| 同項目多場次及型別 | ISSUE | static/app.js:205 優先 session.id，因此同 project_id 的不同 session 不保證同色；models.py:172–173 實際為字串 ID。數字 123 與字串 '123' 經 String 後同色；0/空字串/null 的 ID 因 || 改用 project_id，'0' 則不會。不是型別隨機性；是 fallback 與識別單位的語義。見 C-02。 |
| 空 sessions/time_nodes 或集合為 null/undefined | VERIFIED | static/app.js:212、224 的 optional chaining/||[]，255–256 的 empty 文案；空 state.calendar 亦安全。Node 抽取函數驗證空集合均回 []。 |
| project=null、notes=null | VERIFIED | static/app.js:234 的 project?.name 及 title fallback、244 的 notes 條件；不拋錯。後端實際序列化仍假定 project 關聯存在（app.py:347、1052），不能把前端容錯推廣為後端孤兒資料安全。 |
| window_start=null 的 window；starts_at=null 的 fixed | VERIFIED | static/app.js:213–215 令 from=''，直接排除，日詳情顯示空或剩餘有效活動；不呼叫其卡片格式化、不拋錯。兩類缺開始日期的活動不會出現在任一天，這與 parent 原過濾規則相同（30aa106 static/app.js:217–220）。ends_at/window_end=null 時退回 from，只顯示開始日；並非從剩餘日期猜測區間。 |
| 更深層非契約資料 | SKIPPED | static/app.js:213、224 直接讀 s/n；陣列元素若是 null 會拋錯，日期若是非字串 truthy 值可能沒有 slice。API serializer 回物件及 ISO 字串/null（app.py:334–359、1048–1056），不把畸形回應列為已證實新回歸。 |
| more-events 的 date/數量 | VERIFIED | static/app.js:272、275、285：key 取當格日期，前三項以外是 todays.length-3，點擊傳同一 key；dialog 用同一 calendarSessionsOn，數量一致。 |
| day-node-count、aria-label | VERIFIED | static/app.js:274、276、286：節點按 nodes.length 計算；todays.length 在日期按鈕的 aria-label，代表全部場次而非前三項。day-node-count 本身沒有顯式 aria-label，使用「N 個执行节点」可見文字作名稱；不存在把活動數誤作節點數的程式。 |

## 2. 日期、時區與視口

**ISSUE — C-01，P1【新引入：擴大既有時區缺陷的展示面】。** 新日詳情按日期字串歸類，卻按設備時區顯示時間，日期標題與卡片可互相矛盾。static/app.js:213–215、224 取 ISO 前十碼；236、251 調用既有 fmtDate/fmtDateTime（25–35），Intl 沒有 timeZone。例：`2026-10-21T00:30+08:00` 被列入 10/21，UTC 設備的卡片卻顯示 10/20 16:30（Node 已驗證）；window 的開始/結束日期也經 fmtDate，可能顯示前一天。這是 JC P1-04 既有根因在新增日詳情與節點清單的擴大，不是新寫入偏移機制。建議以 Asia/Shanghai 同時產生歸類日期、顯示日期與時間，驗收 UTC/+08/+09 跨午夜案例。

- **VERIFIED — 後端格式有 offset，但不保證統一 +08。** app.py:58 設定 TZ；222–238 對無 offset 輸入補 TZ；211–219 的 as_iso 對 datetime 使用 isoformat(timespec='minutes')，無 tzinfo 者補 TZ，有 tzinfo 者保留原 offset，沒有 astimezone(TZ)。starts_at/window_start 經 as_iso（339–340），都是 datetime 欄位（models.py:175–179）。因此有時區後綴；不能宣稱所有回應必為 +08 或無後綴。若資料庫回傳 UTC aware 值，slice 將取 UTC 日期而非上海日期，連 +08 設備也可能歸錯日。此 serializer/舊 pill slice 根因均【既有】；實際 DB 連線時區及回應 offset **SKIPPED**，未連生產。
- **VERIFIED — slice 並非兩 commit 首次引入。** 30aa106 static/app.js:217–220 已用開始/結束字串 slice 比較；7fd82b3 抽為 helper 並新增 dialog/nodes 使用。故不能把舊 pill 的跨時區歸日問題說成全新演算法回歸。節點依 planned_start 歸日的新增 UI 則繼承同一不一致（7786aec static/app.js:223–225）。
- **VERIFIED — 標題的本地 noon 本身不會做 +08 轉換。** static/app.js:231–232 的 new Date(key+'T12:00:00') 是設備本地日期中午，再於同一設備時區格式化；正常有效日期會保留 key 的日子。它不解析活動的 offset，也不能修正 C-01。日期 regex 僅檢查形狀，不驗曆日，但正常 key 全由 dateKey 生成（272、292），不列實際入口缺陷。
- **VERIFIED — 跨月補位日已定義可點，並在 API 範圍內。** static/app.js:197–202 從月首所在週的週一到 +41 日取資料；265–266 用相同 42 天生成格子。outside 只加 class，276、679–681 沒有禁止點擊。不是只查月首至月尾，正常 outside 日期可看相應活動及節點。
- **ISSUE — C-03，P3【新引入】範圍外呼叫沒有完整性提示。** openDayModal 沒有額外 fetch 或檢查回傳 from_date/to_date（static/app.js:228–230）；若程式直接呼叫視口外日期，只看到已載入 sessions 的相交項及已載入 nodes，或「当天暂无」。不能證明該日真空。正常可點 42 格不觸發此限制；建議未來開放外部日期入口時檢查/補抓，現階段不列阻斷。
- **VERIFIED — 多日與 window 使用同一區間。** static/app.js:213–215 及279–280 均依 date_mode 選 window_start/end 或 starts_at/ends_at，未將後端查詢邊界當活動邊界。從視口前跨到視口後的 window，其原始日期仍在回應（app.py:339–340、1040–1054），每格可呈 middle，dialog 列同一 session 及完整窗口，並明示「非连续举办／尚未确认该日举行」（236、242）。starts_at/ends_at 均 null 的合法 window 只要 window_start/end 有值仍正常。
- **ISSUE — C-04，P3【既有；新 dialog 沿用】午夜結束日也被納入。** static/app.js:215 是日期 <=/>=，與 parent:220 相同；10/20 23:00 至10/22 00:00 在10/22仍列活動，Node 已驗證。如產品定義結束瞬間不佔翌日，需改用半開時間區間；目前 pill 與 dialog 一致，不能說本次新增兩者不一致。同日場次 from===to 時只取 start class，沒有同時 end（280），亦屬原規則。

## 3. JC 指定缺陷逐項交叉比對

下表的 JC ID 是引用既有報告的名稱，不代表本次重用其嚴重級別。

| JC 項目 | 結果／來源 | 交叉判斷與證據 |
| --- | --- | --- |
| P0-01 backdrop 誤關 | ISSUE【既有】 | 30aa106 static/app.js:389、579–582 已有 backdrop data-action 加 closest 分發；7786aec:443、633–636 保留。普通輸入點擊可命中祖先 close action，新 listener 沒修復這個舊問題。 |
| P0-02 欄位白名單 | ISSUE【既有】 | static/app.js:553–562 提交關聯字段；app.py:89–101、518–524、993–1018 校驗/處理契約衝突。兩 commit 未改此表單、API 或白名單，沒有新增或加重證據。 |
| P1-03 二級確認 | ISSUE【既有】 | static/app.js:456 的 await onSubmit 後無條件 close，708–720 的二級 confirmModal；parent:402 已有相同關閉機制，本次 open-day/open-session 不走提交器，不構成此問題新增來源。 |
| P1-04 時區 | ISSUE【既有根因；新引入展示面加重】 | static/app.js:25–43、735–738、app.py:222–238；parent 原 slice 已存在；新增236、251 顯示與213–224 歸日混用，詳 C-01。 |
| P1-05 事務 | ISSUE【既有】 | app.py:518–586、960–1018；後端檔案在兩 commit 完全未變。本次只讀日詳情不新增寫入或事務。 |
| P2-09 色彩 | ISSUE【新引入】 | static/app.js:204–208 的12色 hash，273–285 前三項；此前無「每場次 hash 色」機制。穩定不代表唯一、同項目同色；詳 C-02。 |
| P2-10 草稿保護 | ISSUE【既有】 | static/app.js:474 清 DOM、753 Escape；parent 已有直接關閉。新增日詳情是無表單的只讀視圖，不新增可丟草稿。668 新 closeModal 從現有日曆/只讀詳情跳轉，未見新增可達的編輯草稿丟失路徑。 |

**VERIFIED — 日詳情不受 P0-01 影響。** static/app.js:252 的 day-detail-backdrop **沒有 data-action**。點卡片文字時 handleClick:633 找不到 action 返回，第二 listener:685 因 target 不是 backdrop 亦不關。點「查看项目详情」時 closest 找按鈕 open-session（245），668 主動關閉並導航，這是預期行為；第二 listener 不會把卡片/按鈕誤認為遮罩。點空白遮罩則第一 listener 無 action，第二 listener 精確按 target class 關閉。不能把通用 openModal 的帶 action 遮罩與這個新遮罩混為一談。

## 4. CSS 48 行

| 檢查 | 結果 | 證據與判斷 |
| --- | --- | --- |
| event-pill 選擇器範圍 | VERIFIED | Git 全庫搜尋（排除文檔）中 HTML 產生點僅 static/app.js:283，725 是日曆拖動 selector；沒有非日曆元件使用。styles.css:24–28 雖未加父級 scope，現有頁面無跨頁污染證據。 |
| 空日期 cursor | VERIFIED | styles.css:21；app.js:255–256、679–681 保證空日也開 empty dialog。判為 feature：可查「無活動／無節點」，cursor 與行為相符。 |
| 深色模式 | SKIPPED（N/A） | 全庫搜尋未見 prefers-color-scheme、data-theme、dark-mode 切換；styles.css:1 為淺色 :root，static/index.html:45–61 無 theme 控制。無深色模式契約可驗收，不能據此宣稱深色已支援。 |
| !important | VERIFIED | styles.css:38–39 的 window/risk 用於覆蓋35 的 .day-detail-card p（特異性0,1,1，高於單 class）。可達目的且限定新文案；可改為 .day-detail-card .day-detail-risk/window 避免 important，但目前非缺陷。 |
| 手機覆蓋實際結果 | VERIFIED（層疊結果；真機 SKIPPED） | styles.css:4 的 event-pill 左框1px，被後置24/26 改成3px，包括手機；Claude 所稱手機「1px dashed」只適用其餘邊。小字仍8px（4），不是全部行動樣式都未改。無真機驗證，勿聲稱已驗收閱讀性。 |

**ISSUE — C-02，P2【新引入】顏色與項目/狀態語義未統一。** 同項目不能保證同色、不同場次可能撞色（app.js:204–208）；這是可證明的限制，不是 refresh 不穩定。legend 仍以原本狀態色說明（static/app.js:183、styles.css:1），新 window/risk 改用活動變數（styles.css:26–28），因此不能再單靠原黃/紅底判讀；risk 的 ! 及右框、window 的「择日」與虛線提供另一通道。建議先定義項目色或場次色語義，再同步 legend，勿承諾12色可唯一識別活動。與 Claude 的 legend 補充及 JC P2-09 一致，但明確歸因為本次新增機制。

## 5. 舊 modal 與事件回歸

- **VERIFIED — open-session 關閉時序。** static/app.js:668 先同步 closeModal（474），才讀按鈕 dataset、設定 state/hash、await loadProject。DOM 被移除不會令仍被 b 引用的按鈕失去 dataset。載入失敗則進676 toast，原詳情已關閉，是可恢復的導航失敗表現，未見新二級彈窗競態。sessionId 原分支已讀但未用，沒有新增定位場次功能，按鈕文案也僅承諾項目詳情。
- **VERIFIED — 兩個 root listener 不雙開。** static/app.js:678–682 註冊順序先 handleClick、後格子 listener；day-number/more-events/node-count 的 data-action 由667 開一次，第二個以 closest('[data-action]') 排除。event-pill 走668，亦被排除；格內無 action 的空白/容器則僅第二個開一次。同步 innerHTML 寫到 modalRoot 不改原日期按鈕的祖先，無重入觸發 click。
- **VERIFIED — root 與 modalRoot 不形成重複代理路徑。** static/index.html:55、59 為不同子樹，日詳情按鈕只冒泡到 modalRoot；handleClick 於683 分發，684–685 僅判斷實際 target 是否遮罩。無把同一 modal click 經兩個 handleClick 的 DOM 路徑。
- **ISSUE — C-05，P3【既有；新 dialog 延伸】鍵盤焦點生命週期不足。** 新 dialog 有 aria-labelledby、關閉按鈕 focus（app.js:252、258），但無 focus trap/恢復來源焦點，753 全局 Escape 直接移除；舊 modal 亦無完整處理。日詳情內 Tab 可離開 modal，移除焦點按鈕後未明確回日期入口。建議封裝 modal 焦點管理；此不是 P0-01 誤關。

## 6. 與 Claude 結論的差異

1. **補充其未覆蓋的 P1：** C-01 是新增日詳情可確定推導的「日期歸類與設備時區顯示矛盾」，所以不接受其 docs/audits/audit-7786aec-deploy-claude.md:74 無條件「本次更新冇引入 P0/P1 級代碼 bug」。根因既有、展示面新加，不能說所有時區問題都首次出現於本次。
2. **限制「事件綁定沒問題」的範圍：** Claude:29–33 對新 listener 無重複綁定/雙觸發的判斷成立；舊 openModal 的 closest 遮罩誤關仍在。另一方面，日詳情恰好沒有 close action 祖先，不能依 JC P0-01 推論它也會誤關。
3. **補齊邊界證據：** Claude:35–41 的欄位存在與 live 成功不能證明 null、跨月、多日和 offset 一致性。本次確認指定 null 安全、42格全覆蓋、window 原始邊界一致；另記錄 C-03/C-04 的完整性與午夜語義限制。
4. **CSS 結論補充：** Claude:45–46 的「覆蓋正確、手機合理」沒有交代後置3px左框覆蓋手機1px，亦不能推廣為真機閱讀性驗收；其 legend/focus-trap（64–66）問題成立。本次未做對比度全色板量測或真機測試，不重複宣稱全部對比度足夠。
5. **部署 4/5 不重驗：SKIPPED。** Claude:13–17、60–61 的容器、健康與清理狀態是當時環境觀察，本次沒有操作生產環境，既不確認也不否定。本報告的 VERIFIED 僅限源碼/記憶體檢查，不拿靜態審計背書部署現況。

## 結論

未證實本次造成生產 P0；新增日詳情擴大既有時區不一致（P1），分色語義有 P2 限制，而日詳情誤關、補位日漏查與雙開 modal 的疑慮均未獲源碼支持。
