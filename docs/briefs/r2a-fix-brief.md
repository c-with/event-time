# R2-A 修復任務書（Pi 施工版）

## 背景
EVENT-TIME-AUDIT-03 雙盲交叉審計（你嘅 audit-d66cf97-pi-cross.md + Claude 份）已定案 R2-A 批次。而家由你施工修復。

## 修復項（三件，一個 commit）

### 1. TEST-01：復活回歸測試（你自己審計發現嘅 PI-SEC-02）
- tests/test_editor_regression.py:13 `from models import db` → 改為由 app 取得（參考你審計報告嘅修法：`import app as m; a=m.create_app()` 用 a.test_client() 同 m.db）
- 修好後實跑：預期 4 個測試會紅喺 `assertEqual(201)` 對實際 200（你審計已預知）
- 然後修 app.py 五個端點嘅 201 bug：`return jsonify(session=result) if status == 201 else (jsonify(result), status)`（app.py:850/857/864/871/878 附近，呢個 pattern 201 分支裸返回 Response 無狀態碼）——改為統一 `return jsonify(result), status`
- 最終 `python3 -m unittest discover -s tests` 要 8/8 全綠，貼實際輸出

### 2. SEC-03：刪除 static/sample-data.json
- `git rm static/sample-data.json`（你已證實前端零引用，18KB 真實業務數據免登入可讀）
- 確認 static/ 下冇其他 .json 數據檔同類問題（grep 檢查）

### 3. SESSION_SECRET（你嘅 PI-SEC-01 獨有發現）
- app.py:130 `SECRET_KEY=os.environ.get("SESSION_SECRET") or secrets.token_hex(32)` —— fallback random 導致每次重啟全員登出
- 修復：改為冇 SESSION_SECRET 時 raise 明確錯誤（同 SHARED_PASSWORD 少過 14 位嘅處理睇齊，快速失敗好過靜默隨機）？——唔好。**保守修法**：保持 fallback 但改成啟動時 log warning；真正修復喺部署側（我主控會喺生產 .env 加 SESSION_SECRET，唔關你事）
- 你嘅任務範圍：app.py 呢行加註釋說明 + docs/audits 你份報告已記錄，代碼唔好改行為（避免破壞現有測試）

## 嚴格禁止
- 改動三件事以外嘅任何代碼
- push、deploy（commit 留本地等我復驗）
- 掂生產環境／.env

## 驗收門禁（自檢完輸出）
1. python3 -m unittest discover -s tests 輸出（8/8）
2. git diff --stat 只得 tests/test_editor_regression.py、app.py、（deleted static/sample-data.json）
3. git log --oneline -1 顯示你嘅 commit（format: fix: revive regression tests, correct 201 status codes, remove leaked sample data）
