# EVENT-TIME-AUDIT-03：Claude 重度審計任務書

## 類型：READ-ONLY DEEP AUDIT（只讀審計，禁止任何修改/push/deploy）

## 生產基準
- HEAD：d66cf97（branch ui/bento-redesign，已部署生產 8600，鏡像 sha 4e56a05）
- 審計範圍：e6b8de7（初始）→ d66cf97 全部 8 個 commit，重點係 6065db6..d66cf97（R1 修復＋bento UI＋quick-add＋operator 修復）
- 技術棧：Flask＋SQLAlchemy＋PostgreSQL＋零框架 vanilla JS SPA（803 行 app.js／560 行 styles.css／1550 行 app.py）

## 審計維度（逐項深挖，每項都要代碼級證據）

### A. 安全（最高優先）
1. 認證／會話：session cookie 配置（HttpOnly/Secure/SameSite）、登入暴力破解防護、logout 徹底性
2. CSRF：X-CSRF-Token 機制覆蓋面——有冇任何 POST/PATCH/DELETE 端點漏咗 CSRF 檢查？逐個端點 grep 驗證
3. 注入：SQL（SQLAlchemy 參數化但有冇 raw query 位？）、XSS（app.js 用 esc() 但有冊漏網——特別係 innerHTML 模板字符串入面嘅變數逐個檢查）、路徑穿越（文件上傳/下載端點）
4. 文件上傳：類型檢查、大小限制、儲存路徑、Magic bytes 驗證、下載端點授權
5. 信息洩漏：錯誤響應有冇 stack trace／內部路徑、debug 模式、.env 有冇被 static 目錄暴露
6. 業務邏輯授權：共享單賬號模型下有冇端點假設咗唔存在嘅角色分離？share_links 端點授權？

### B. 數據完整性
1. 樂觀鎖：_revision 檢查喺所有 PATCH 端點係咪一致？有冇漏？
2. 事務邊界：db.session.flush vs commit 順序、失敗 rollback 完整性（errorhandler 有 rollback，但每個 try/except 位都有？）
3. 級聯刪除：ondelete=CASCADE/SET NULL 配置 vs 業務預期（「人工改過嘅數據唔被靜默刪除」原則）
4. 審計日誌：write_audit 喺失敗路徑會唔會漏記？audit_log 本身 append-only 有冇被改寫嘅 API？
5. 已知潛伏 bug 複查：五個創建端點 jsonify(...,201) 實際返 200（R1 之後未修）——確認具體邊五個、影響面

### C. 前端正確性
1. esc() 覆蓋：所有 innerHTML 模板入面變數逐個數，列出入冇 esc() 嘅（XSS 風險位）
2. quick-add 新機制：pendingModalRestore 鉤子喺異常路徑（二級 modal POST 失敗、escape 关閉、backdrop 点擊）會唔會洩漏／雙重觸發
3. 競態：並發開兩個 quick-add？日曆拖拽同 PATCH revision 衝突路徑？
4. localStorage operator name encode 修復後，有冇其他非 ASCII 值塞 header 嘅同類位

### D. 運維/部署
1. compose 配置：read_only、no-new-privileges、tmpfs nosuid 有冇繞過
2. 備份腳本 scripts/*.sh：密碼處理、失敗路徑、恢復可測試性
3. 健康檢查覆蓋：health 端點檢查咩？DB 連接失敗會點？

### E. 測試債
tests/ 目錄覆蓋率 vs 上面孔位：邊啲新功能（quick-add、theme、operator encode）冇測試？

## 已知問題（唔使重複發現，但要評估優先級）
- 五個創建端點 jsonify 201 潛伏 bug
- IntegrityError 409 detail 前端 toast 唔顯示（用戶體驗）
- 客戶端 client_id="" 曾引發 FK 409（已修 d4c8a93，檢查修復完整性）

## 嚴格禁止
- 修改任何文件、commit、push、deploy
- 對生產 8600 發任何寫請求（可以 curl GET /health、讀 static 資源）
- 掃描端口/嘗試滲透基礎設施
- 輸出任何密碼/token 值（.env 只可以確認存在同權限，唔可以讀值）

## 輸出格式
寫入 docs/audits/audit-d66cf97-claude-deep.md，格式：
- 每個發現：[P0/P1/P2/P3] 編號、位置（file:line）、證據（代碼片段）、影響、建議修復
- 結尾：總體評級（PASS / PASS_WITH_FIXES / HOLD）＋ 發現統計
- 英文 commit 級標題、中文詳述

## 執行方式
用 git log/diff、grep、讀文件為主。想跑測試可以（python -m unittest discover -s tests），但唔好改任何嘢。
