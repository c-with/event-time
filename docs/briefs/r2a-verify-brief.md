# R2-A-VERIFY：Claude 審計檢驗任務書（修復驗收審計）

## 類型：READ-ONLY VERIFICATION AUDIT（只讀檢驗，零修改）

## 背景
AUDIT-03（你嘅 audit-d66cf97-claude-deep.md＋Pi 交叉 audit-d66cf97-pi-cross.md）定案 R2-A 批次已由 Pi 施工完成（commit b30188e）並已部署生產。而家由你做獨立審計檢驗：修復係咪真係修好咗、有冇引入新問題。

## 檢驗項（每項要代碼＋運行時雙證據）

### 1. TEST-01 修復檢驗
- tests/test_editor_regression.py import 修正係咪正確（`from app import db` vs 之前 `from models import db`）
- 實跑 `python3 -m unittest discover -s tests`（用 .venv/bin/python，Pi 起嘅環境）——確認 8/8
- 檢查測試內容本身：有冇為咗綠而弱化斷言？（對比 git show 674afbd 原版斷言 vs b30188e 版）

### 2. 五端點 201 修正檢驗
- git show b30188e -- app.py：五處改動逐處核對，`jsonify(session=result), status` 寫法係咪真係修正咗「201 分支裸 Response」問題
- 有冇第六處同 pattern 嘅端點漏修？（全檔 grep `if status == 201`）
- 呢個修正會唔會影響前端？（前端 create 後讀 response 嘅位置 grep 檢查 data.task/data.session 等取值）

### 3. SEC-03 修復檢驗
- git 確認 sample-data.json 已刪；grep 確認零殘留引用
- 生產驗證（可以 GET）：/static/sample-data.json 應該 404
- 順手掃 static/ 目錄：仲有冇其他檔案包含真實業務數據（人名/項目名/電話格式）？

### 4. SESSION_SECRET 部署檢驗（只驗存在同效果，禁讀值）
- 生產容器 SESSION_SECRET 存在（docker exec 檢查鍵存在）
- 跨重啟 session 存活：任務書聲稱已實證（重啟前後 /api/me 都 200）——你用自己方法再證一次（login 拎 cookie → docker restart 要主控做，你冇權——改為：驗證 app.py:130 邏輯＋SECRET_KEY 由 env 讀取嘅代碼路徑，推導 SESSION_SECRET 固定時 session 簽名穩定）
- codebase 有冇其他「隨機 fallback 導致重啟狀態丟失」嘅同類位？

### 5. 回歸檢查（最重要）
- b30188e 全 diff 審閱：+10/−635 行入面，除咗三件指定修復有冇夾帶任何其他改動？
- 修復有冇引入新缺陷？（特別係 201 修正對既有消費者嘅影響）
- 生產容器（event-time-v041，鏡像 b30188e）同 git HEAD 逐 byte比對：docker exec sha256sum /app/app.py vs 宿主 git 版

## 嚴格禁止
- 修改任何文件、commit、push
- 對生產發任何寫請求（GET /health、GET static 可以）
- 讀 .env 任何值（SESSION_SECRET 只驗存在）
- docker restart / down 等生命周期操作

## 輸出
直接輸出到 stdout（唔使寫報告檔案）：
- 每項檢驗：PASS/FAIL＋證據
- 總結：R2-A 修復驗收 PASS 定 FAIL；如有新發現（夾帶改動/新缺陷/弱化斷言）即管報
