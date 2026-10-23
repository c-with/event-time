# 封面直接上傳任務書（COVER-1）

## 現狀
- 封面數據鏈已存在：Project.cover_document_id / EventSession.cover_document_id（models.py:157/183），PATCH /api/projects/<id>（body: cover_document_id, _revision）可用（app.js:723 setCover 已實現）
- 上傳端點 POST /api/documents（FormData: files[], entity_type, entity_id）已存在（app.py:1362 upload_documents）
- 唯一問題：入口太深（上傳資料→文件頁→文件卡→設為主圖）

## 任務：封面位直接上傳（只改 static/app.js，可加少量 styles.css）

### 1. 項目詳情頁封面（detail-cover，app.js:396 附近）
- 封面 div 加 hover overlay（半透明＋「上傳封面」文字掣），撳落觸發 file picker（input type=file accept="image/*"）
- 揀完直接：FormData POST /api/documents（entity_type=projects, entity_id=項目id）→ 攞返 response 入面嘅 document id → setCover(docId)（現有函數，會行 confirm＋PATCH＋loadProject）
- 上傳中顯示 loading 態（掣文字變「上傳中…」disabled）

### 2. 場次封面（sessions 有 cover 欄位，但 UI 冇入口）
- 場次實體卡（entity-card）加一個細掣「設封面」（只喺 sessions 類卡顯示），同樣流程但 entity_type=sessions + setCover(docId, sessionId)
- 如果場次卡結構難落掣，可以喺編輯場次 modal 加「上傳場次封面」欄位（file input type）——揀你判斷最順嘅做法，講明理由

### 3. 保守約束
- 唔好改後端、唔好改 setCover 本身（佢嘅 confirm 流程＋_revision 保護原樣用）
- 上傳後 response 結構先讀 app.py:1362-1420 確認 document id 點拎（created list？）
- 失敗路徑：上傳失敗 toast error、file picker 取消唔做嘢
- styles.css 只准加 .cover-upload-overlay 之類新 class，唔准改現有 class

## 驗收自檢
1. node --check static/app.js
2. 講明：項目詳情頁封面上傳流程（揀檔→上傳→設主圖→重載）各步對應邊行代碼
3. git diff 只有 app.js（+styles.css 新 class）
4. 唔好 commit（留工作區等我復驗）
