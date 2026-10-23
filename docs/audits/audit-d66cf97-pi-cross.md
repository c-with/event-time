# EVENT-TIME-AUDIT-03-CROSS：Pi 交叉審計報告（d66cf97）

- **審計基準**：HEAD `d66cf97`（branch `ui/bento-redesign`）；生產容器 `event-time-v041`、鏡像 `event-time:0.4.1` sha `4e56a05f8f12`（docker inspect 實測與任務書一致）。
- **交叉審計方法**：先**獨立完成全部五維審計**（未讀 Claude 報告，避免 anchor），之後先讀 `audit-d66cf97-claude-deep.md` 做逐項對比同複核。
- **獨立審計手段**：`app.py`(1562 行)/`models.py`(407)/`static/app.js`(875)/`static/index.html` 全文精讀；全部路由 grep 枚舉 CSRF／鑑權；`db_schema.sql` 與 models 級聯比對；`python3 -m unittest discover -s tests` 實跑；生產端**只讀**探測（GET `/health`、GET static、`docker inspect` 鍵名——未讀取任何密碼/token 值）；`ss -tlnp` 被動查監聽（非端口掃描）。
- **紅線遵守**：零修改（本報告係唯一寫入檔案）、零 commit/push/deploy、對 8600 只發 GET、`.env` 只查存在性（repo 內無 `.env`）。

---

## Part 1：Pi 獨立審計結果（讀 Claude 報告之前定稿）

### 獨立評級：**PASS_WITH_FIXES**（P0=0，P1=3，P2=7，P3=7）

核心代碼安全設計（CSRF 全覆蓋、上傳防護鏈、分享 token、審計 append-only、無 DELETE 端點）對「內網共享單賬號」威脅模型而言健全；P1 全部集中喺**部署偏離**與**測試債**，唔需要數據遷移即可修復。

---

### A. 安全

#### PI-SEC-01 [P1] Production published on 0.0.0.0:8600 deviates from repo compose baseline

**證據**（獨立實測）：
```
$ docker inspect event-time-v041 --format '{{.HostConfig.PortBindings}}'
map[8097/tcp:[{0.0.0.0 8600}]]
$ ss -tlnp | grep 8600
LISTEN 0 4096 0.0.0.0:8600 ...（docker-proxy 監聽所有介面）
```
repo 基線 `compose.yaml:19` 明確 `127.0.0.1:${HOST_PORT:-8601}:8097`；`app.py:1556` `host = os.environ.get("ACTIVITY_HOST", "0.0.0.0")`（容器內綁 0.0.0.0 屬正常，問題在 host 側 binding）。同時實測 `COOKIE_SECURE=0`（`compose.yaml:18` 基線為 `${COOKIE_SECURE:-1}`，`.env.example:8` 為 1），`app.py:137` 因此關閉 Secure 標記。**登入密碼明文 POST（`app.py:695-706`）＋cookie 無 Secure＋全介面監聽**，同網段（活動場地 Wi-Fi 係本系統典型場景）可嗅探憑證。
**建議**：生產改回 `127.0.0.1` 綁定＋TLS 反代＋`COOKIE_SECURE=1`；將生產 compose 差異回填倉庫。

#### PI-SEC-02 [P1] HTTP regression suite has never run — import fails AND assertions contradict actual status codes

獨立發現（兩層證據，先於 Claude 報告）：
1. 實跑 `python3 -m unittest discover -s tests`：`test_editor_regression` loader ERROR——`ModuleNotFoundError: No module named 'flask'`（`tests/test_editor_regression.py:12` `from app import ...` 即爆）。
2. 純代碼推理：`tests/test_editor_regression.py:44-46` `create()` 斷言 `status_code == 201`，但五個子創建端點（`app.py:850/857/864/871/878`）實際返 200（見 PI-DATA-01）——**即使裝好 Flask，4 個測試全部會 assert 失敗**。且 `git show 674afbd:app.py` 證實 201 bug 喺測試提交當刻已存在。
**影響**：commit 674afbd 聲稱嘅「R1 回歸覆蓋」從未生效過任何一分鐘。
（Claude 報告其後揭示第三層更根本嘅原因：`from models import db` 本身錯誤——見 Part 2 複核。）

#### PI-SEC-03 [P1] /static/sample-data.json serves real business data without login (verified live)

**證據**：`curl http://127.0.0.1:8600/static/sample-data.json` → **200，18,420 bytes，無需任何 cookie**。內容：22 個真實項目（「洪湾渔港安全生产方案」「澳门青年实习计划」…）＋18 個任務＋內部人員名（JC、DDme、Fantasy 等）。Flask static 路由（`app.py:128` `static_folder="static"`）不經 `login_required`；全 repo 無任何代碼引用該檔（V0.3 遺留，758277e 入庫）；`Dockerfile:9` `COPY static ./static` 令佢入埋鏡像。
**影響**：完全繞過登入門檻讀取客戶項目名單與內部人名；疊加 PI-SEC-01 即整個 LAN 可讀。無電話/郵箱/密碼（已掃描），故定 P1 而非 P0。
**建議**：移出 `static/`（歸檔 `migration-source/`，已 gitignore）並重建鏡像。

#### PI-SEC-04 [P2] No brute-force protection on /api/login

`app.py:695-706`：直接 `check_password_hash`，全倉無 rate limiter／失敗計數／鎖定（grep `rate|limit|attempt|lockout|throttle` 零命中於認證路徑）；失敗登入不寫 audit。錯誤訊息統一「账号或密码不正确」（不洩漏用戶存在性，好）。結合 PI-SEC-01 直連面，可無限速撞 14+ 位共享密碼。**建議**：per-IP 限速＋失敗登入記審計。

#### PI-SEC-05 [P2] IntegrityError 409 leaks raw DB error detail to client

`app.py:175`：`detail=str(error.orig)[:240]`——約束名/表名/值片段直接回傳客戶端。前端 `app.js:131` 只讀 `data?.error`，`detail` 用戶睇唔到（已知 UX 問題）——洩漏咗但無 UX 補償。**建議**：detail 結構化（`{"constraint": ...}`），原文入 log，前端顯示友好版。

#### PI-SEC-06 [P2] /health leaks raw DB exception unauthenticated

`app.py:692`：`jsonify(ok=False, error=str(exc)[:200]), 503`——`/health` 無 `@login_required`（`app.py:684`），DB 故障時驅動錯誤字串（可含主機/埠資訊）對外暴露。**建議**：對外只回 `ok:false`，細節入 log。

#### PI-SEC-07 [P2] X-Operator-Name audit actor is client-spoofable

`app.py:203-217`：`actor` 完全信任客戶端 header；`app.js:99-111` localStorage 任改。共享單賬號模型下 `audit_log.actor`、`ChangeRequest.proposed_by` 嘅追責建立在誠實申報上。屬設計取捨，但應文檔明示「operator 名非強身份證明」。

#### PI-SEC-08 [PASS] CSRF 覆蓋完整（逐端點核驗）

`app.py:147-160` before_request 攔截所有 `/api/*` 寫方法（唯一豁免 `/api/login`）；`hmac.compare_digest`（`app.py:158`）✓；Origin 檢查 ✓；枚舉全部路由：**所有狀態變更端點都在 `/api/` 下**，`/`、`/health`、`/share/<token>` 全部 GET——零漏網。`@app.delete` grep 計數 0（無任何 DELETE 端點）。登入時 `session.clear()`＋csrf_token 輪換（`app.py:701-703`）防 fixation ✓。

#### PI-SEC-09 [PASS] 上傳／路徑穿越防護鏈完整

PDF magic bytes `raw.startswith(b"%PDF")`（`app.py:1270`）；圖片一律 PIL 重編碼（`app.js` 無關，`app.py:1302-1334`）消解 polyglot 載荷；`secure_filename`（`app.py:1377`）；副檔名白名單（`app.py:66`）；100MB/250MB 上限＋`MAX_CONTENT_LENGTH`（`app.py:64-65,134`）＋413 handler；儲存名伺服器生成 uuid（`app.py:1268`）；下載雙保險 `Path(path).resolve()` 後驗 `DATA_DIR in p.parents`（`app.py:1420-1421, 1464-1465`）；分享 token `secrets.token_urlsafe(32)` 只存 sha256（`app.py:1436-1437`），過期＋撤銷＋`allow_download` 全部強制（`app.py:1461-1466`）。

#### PI-SEC-10 [PASS] XSS：esc() 覆蓋無活路

逐模板插值點算：所有用戶可控文本（name/title/notes/owner/label/resolution_note/JSON.stringify 快照等）全部經 `esc()`（`app.js:46-48`）；`toast()` 用 textContent（`app.js:95`）。未 esc 嘅插值只剩伺服器生成 UUID（`app.js:321` `data-session-id="${s.id}"` 等）、代碼生成日期鍵（`app.js:314` `data-date="${key}"`）、固定集合（`app.js:399` `data-tab="${id}"`、`app.js:454` `data-kind="${k}"`）、`fmtDateTime` 輸出（後端 DateTime 型別強制）——**目前全部安全值空間**，建議作零成本縱深防禦統一包 esc()。

---

### B. 數據完整性

#### PI-DATA-01 [P2] Five child-create endpoints return 200, not 201 (known bug — confirmed with exact lines)

`app.py:850`（sessions）、`857`（time-nodes）、`864`（work-packages）、`871`（requirements）、`878`（tasks）：統一寫法 `return jsonify(session=result) if status == 201 else (jsonify(result), status)`——201 分支裸返 Response，Flask 預設 200。`make_child` 本身正確返 `(serialize, 201)`（`app.py:678`）。前端 `res.ok` 不受影響（200 亦 ok），純 REST 契約斷裂；但佢正正令 PI-SEC-02 嘅測試斷言失敗。`create_project`（`app.py:808`）、`create_resource`（`app.py:1248`）、`create_share`（`app.py:1442`）三處 201 正確——所以係「五個」唔係「八個」，與已知問題清單一致。

#### PI-DATA-02 [P2] SESSION_SECRET absent from production container — sessions die on every restart

**證據**（獨立實測，呢個係同 Claude 報告嘅事實分歧，見 Part 2）：
```
$ docker inspect event-time-v041 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c "^SESSION_SECRET"
0        # DB_PASSWORD、SHARED_PASSWORD 都在，獨缺 SESSION_SECRET
```
`app.py:130`：`SECRET_KEY=os.environ.get("SESSION_SECRET") or secrets.token_hex(32)`——缺 env 時每個進程隨機生成。密碼學上無問題（隨機好過固定），但**每次容器重啟/重新部署，全體用戶即時登出、CSRF token 全部失效**（長開頁面會見「CSRF 校验失败」）。`.env.example:6` 明確包含 `SESSION_SECRET`，生產 `.env` 漏咗。**建議**：補回 env 並重啟一次（順便做有意義嘅 maintenance window）。

#### PI-DATA-03 [P2] Optimistic locking is application-level read-modify-write (no DB guard)

`app.py:545-566`：`entity_revision(obj)` 讀 → 比對 → `obj.revision = current_revision + 1`（`app.py:583-585`），全程無 `SELECT FOR UPDATE`、無 ORM `version_id_col`。兩個並發 PATCH 可同讀 N 各寫 N+1。字段級合併＋`FieldRevision` 後寫查詢（`app.py:550-552`）令同字段衝突大概率被抓到，**唔會靜默丟數據**，但 revision 號可重複、歷史亂序。共享單賬號低併發下屬可接受設計限制，建議文檔化或改原子 `UPDATE … SET revision=revision+1 RETURNING`。

#### PI-DATA-04 [P3] parse_field ValueError uncaught in make_child / create_resource → 500

`app.py:617`：`fields = {k: parse_field(k, v) for k, v in fields.items()}` 與 `app.py:1235` 同款——`parse_dt` 對無法辨識嘅日期時間 raise `ValueError`（`app.py:243`），呢兩處無 try/except，一路炸到 `errorhandler(Exception)`（`app.py:184`）返 500「服务器处理失败」；而 `apply_entity_changes` 同一路徑有 catch 返 400 帶原因（`app.py:563-565`）。API 層送垃圾 datetime 會得到 500 而非 400。**建議**：兩處補同款 try/except。

#### PI-DATA-05 [P3] /api/audit/<id>/restore hard-fails (400) for update_links and archive entries

`app.py:1203-1213`：`restore_audit` 將 `entry.before_json` 直接餵 `apply_entity_changes`；`update_links` 審計嘅 before 含 `session_ids`/`task_ids`/`requirement_ids`/`dependency_ids`，`archive` 審計嘅 before 含 `archived_at`——全部唔喺 `FIELD_ALLOWLIST`（`app.py:76-90`），`unknown` 檢查（`app.py:538-540`）一律 400「包含不允许修改的字段」。呢兩類記錄嘅「按此记录恢复」按鈕（`app.js:488`）永遠失敗。**建議**：restore 前過濾可恢復欄位或明確提示該類記錄不支援恢復。

#### PI-DATA-06 [P3] resolve_change conflict transition is not audited

`app.py:1148-1156`：提案衝突時只改 `change.status="conflict"`＋commit，無 `write_audit`——「點解變咗 conflict」喺審計鏈無記錄（confirm/reject 都有審計）。

#### PI-DATA-07 [P3] Orphan uploaded files on partial batch failure

`app.py:1360-1412`：逐文件「寫盤 → flush → commit」；某文件 DB 失敗時 rollback 只棄 DB rows，已寫入 `FILES_DIR` 嘅檔案永留；`/data/tmp` 中間檔異常中斷亦殘留，無清理任務。**建議**：失敗路徑 best-effort unlink＋cron 清老 `.tmp`。

#### PI-DATA-08 [PASS] 事務邊界／級聯／審計完整性

- `patch_with_links`（`app.py:974-1061`）：全量驗證 → `apply_entity_changes(commit=False)` → 連結變更 → 單一 commit；`except: rollback; raise` ✓；status≠200 先 rollback 再返 ✓（f4d19b4/8afff1a R1 修復核實）。
- `errorhandler(IntegrityError)` 有 rollback（`app.py:174`）；`errorhandler(Exception)` 無顯式 rollback 但 Flask-SQLAlchemy teardown `session.remove()` 兜底，無持久化風險（風格不一，建議補一行）。
- 級聯：`db_schema.sql` 與 `models.py` 全量比對**一致**（時間節點/需求/任務嘅 `work_package_id` 兩邊都係 SET NULL——初次 grep 行號誤配一度以為有 CASCADE 漂移，逐表覆核後排除）；且**無任何 DELETE 路由**，級聯休眠。contacts 隨 client/supplier CASCADE（`models.py:77-78`）只影響直接 DB 操作，建議 ops runbook 註明。
- 審計 append-only：無任何 API 改寫 AuditLog/FieldRevision 舊記錄；`write_audit` 與業務寫同事務 commit。
- `d4c8a93`（client_id="" → NULL）修復**完整**：`create_project` 手工路徑已修（`app.py:795-797`）；其餘入口全經 `parse_field`（`app.py:267-268`）FK ""→None 統一處理；`cover_document_id`/`evidence_document_id` 故意例外（String 列非 FK，`models.py:157,285`）語義一致。同類欄位（supplier_id/venue_space_id/work_package_id/session_id/space_id）無殘留炸彈。

---

### C. 前端正確性

#### PI-FE-01 [PASS] quick-add pendingModalRestore 異常路徑全推演無洩漏

（d66cf97 新機制，逐路徑）
- **二級 POST 失敗**：`openModal` submit handler（`app.js:502-507`）錯誤留喺二級 modal 錯誤欄、按鈕復位，`pendingModalRestore` 保持 → 重試或取消都正確回收一級表單 ✓
- **Escape**（`app.js:859`）/**backdrop 點擊**（`app.js:510`）/**取消鈕**：全經 `requestCloseModal` dirty 檢查（`app.js:536-542`）→ `closeModal` → restore ✓
- **雙重觸發**：`closeModal` 先取 null 再執行（`app.js:532-534`）✓；無三級嵌套（`RESOURCE_FORM_SPECS`（`app.js:546-553`）嘅 select 欄位無 `quickAdd` 屬性）✓
- **值保全**：live 值快取齊全（checkbox/multiple 分支，`app.js:570-576`）＋基線還原（`app.js:596`）令「未保存守護」語義連續 ✓
- **確認 modal 銜接**：`modalRoot.contains(activeBackdrop)` 檢查（`app.js:497-499`）防止完成舊表單時誤關新 confirmation modal（a625204 修復）✓

#### PI-FE-02 [PASS] operator name encode 修復完整，同類位無殘留

`app.js:123` `encodeURIComponent(operator)`；後端 `app.py:206-211` 條件 unquote（僅 `%` 存在時；非法 escape `unquote` 原樣保留＋try/except 雙保險，舊客戶端含 `%` 嘅名唔會誤解碼）。全前端唯一非 ASCII 入 header 位就係呢處（`api()` 係唯一 fetch 封裝；X-CSRF-Token 恒為 ASCII）。服務端截 `[:160]`（`app.py:217`）防 header 溢出。

#### PI-FE-03 [PASS] 競態防護鏈閉合

日曆 pill 帶 `data-revision`（`app.js:831`）→ reschedule POST 帶 `_revision`（`app.js:850`）→ 伺服器 409（`app.py:931-933`）；全部編輯 PATCH 帶 `_revision`；409 錯誤留喺 modal 內資料唔丟（`app.js:502-507`）；兩個 quick-add 並發喺 UI 唔可能（單 modal 佔 modalRoot）。日曆數據過期 → 拖拽 409 → toast，正確降級。

#### PI-FE-04 [P3] index.html 依賴 Google Fonts CDN；無 CSP

`static/index.html:9-11`：外鏈 `fonts.googleapis.com`——內網/場地離線環境加載失敗（有系統字體 fallback，視覺降級）＋用戶 IP 對 Google 洩漏；全站無 CSP header。**建議**：字體自托管或刪外鏈。

---

### D. 運維/部署

#### PI-OPS-01 [P3] requirements.txt 未釘版本

`requirements.txt:1-6` 全部係範圍（`Flask>=3.0,<4` 等）——构建唔可重現，上游 minor 更新可靜默改變生產行為。**建議**：釘死目前實測版本（生產鏡像 `pip freeze` 對齊）。

#### PI-OPS-02 [P3] 環境衛生：生產 host 有唔相關嘅 0.0.0.0 檔案服務器

`ss -tlnp` 實測：`python3 -m http.server 8601 --bind 0.0.0.0`（pid 1098899，user jc，cwd `/home/jc/cft`）監聽所有介面。已驗證佢**唔係**本 repo 服務、且 cwd 唔係本 repo（`GET /.env`、`GET /app.py` 均 404，本 repo 根目錄亦無 `.env`）——唔屬本應用漏洞，但同一台生產 host 上跑一個免認證全介面檔案服務器屬衛生問題，值得清理。（按紅線無進一步掃描該服務。）

#### PI-OPS-03 [PASS] 容器加固與備份腳本（repo 基線）

實測：`ReadonlyRootfs=true` ✓、`no-new-privileges:true` ✓、非 root UID 1000 ✓、healthcheck 帶 DB 探活（`SELECT 1`，`app.py:687`）✓、`restart: unless-stopped` ✓。`scripts/backup.sh`：pg_dump 經既有容器、`pg_restore --list` 驗證、SHA256 清單、trap 清 .tmp、7 日/4 週保留＋每條清理管線 `|| true` 護欄 ✓；`restore-test.sh`：臨時庫還原＋7 核心表斷言＋`DROP … FORCE` cleanup ✓。缺口（P3 併入）：不驗文件包恢復、無異地副本自動化、`.env` 唔喺備份範圍。

---

### E. 測試債

#### PI-TEST-01 [P1]（= PI-SEC-02）回歸套件從未運行

見 PI-SEC-02。補充：`tests/__pycache__/test_editor_regression.cpython-314.pyc`（10-21 16:47）只證明 import 嘗試過，唔證明通過過。

#### PI-TEST-02 [P2] 新功能零測試覆蓋

quick-add（d66cf97）、theme 三態（8884575）、operator encode、bento UI、`d4c8a93` 修復、reschedule、上傳/分享/撤銷、restore_audit、search、resources CRUD——`tests/` 兩個檔案零覆蓋。

---

## Part 2：與 Claude 報告（audit-d66cf97-claude-deep.md）交叉對比

### 2.1 共識發現（互相印證）—— 12 項

| # | 主題 | Pi 評級 | Claude 評級 | 印證要點 |
|---|------|---------|------------|----------|
| 1 | 生產 0.0.0.0:8600＋COOKIE_SECURE=0 偏離 repo 基線 | P1（PI-SEC-01） | P1（SEC-01） | 兩邊各自 docker inspect 實測同一事實；Claude 額外指出 repo 基線「127.0.0.1＋反代 TLS」嘅設計意圖，同意 |
| 2 | test_editor_regression 從未運行 | P1（PI-SEC-02） | P1（TEST-01） | Pi 證據鏈：flask 缺失＋201 斷言矛盾＋674afbd 當刻已有 bug；Claude 證據鏈：`from models import db` 永遠 ImportError＋容器內對照實驗。**三層證據互相加強，結論鐵實** |
| 3 | sample-data.json 免登入公開 | P1（PI-SEC-03） | P2（SEC-03） | 兩邊各自 live curl 得 200/18,420B。評級分歧見 2.4 |
| 4 | 登入無防爆破 | P2（PI-SEC-04） | P2（SEC-02） | 代碼位一致（`app.py:695-706`） |
| 5 | IntegrityError 409 detail 洩漏＋前端 toast 唔顯示 | P2→覆核後同意 P3（PI-SEC-05） | P3（SEC-05） | 同一代碼位（`app.py:175`＋`app.js:131`）；Claude 指出需登入先見到——成立，採納 P3 |
| 6 | /health 洩漏 DB 異常細節 | P2→覆核後同意 P3（PI-SEC-06） | P3（SEC-04） | 同一代碼位（`app.py:692`）；僅 DB 故障時觸發，P3 合理 |
| 7 | X-Operator-Name 可偽冒 | P2→同意設計取捨定位（PI-SEC-07） | P3（SEC-06） | 同一代碼位 |
| 8 | 五個創建端點返 200 | P2（PI-DATA-01） | P3（DATA-01） | 行號完全一致（850/857/864/871/878）；兩邊都指出佢係測試全紅成因 |
| 9 | revision 讀改寫非原子（無 DB 級守護） | P2（PI-DATA-03） | P3（DATA-03） | 同一窗口描述；兩邊都確認字段級合併令「唔會靜默丟數據」 |
| 10 | 上傳失敗殘留孤兒檔案 | P3（PI-DATA-07） | P3（OPS-04） | 同一路徑（`app.py:1360-1412`） |
| 11 | Google Fonts 外鏈 | P3（PI-FE-04） | P3（FE-06） | `static/index.html:9-11` |
| 12 | 新功能零測試覆蓋 | P2（PI-TEST-02） | P2（TEST-02） | Claude 補充「唯一綠燈嘅 test_merge_logic 測嘅係運行時死代碼」——核實：`app.py`/`models.py`/前端確實都不 import `merge_logic`，**同意，呢個觀察比 Pi 更尖銳** |

### 2.2 淨係 Pi 搵到（Claude 盲區）—— 5 項

| # | 發現 | 評級 | 證據 |
|---|------|------|------|
| 1 | **SESSION_SECRET 喺生產容器完全缺席**——每次重啟全員登出＋CSRF 全失效（並直接反駁 Claude SEC-10 嘅「SESSION_SECRET 存在」陳述，見 2.4） | P2 | `docker inspect` env 鍵名單：DB_PASSWORD/SHARED_PASSWORD 在、`grep -c "^SESSION_SECRET"` = 0；`app.py:130` fallback `secrets.token_hex(32)` |
| 2 | `make_child`/`create_resource` `parse_field` ValueError 未捕 → 垃圾 datetime 得 500 而非 400 | P3 | `app.py:617, 1235` vs `apply_entity_changes` 有 catch（`app.py:563-565`） |
| 3 | `restore_audit` 對 update_links／archive 類審計記錄一律 400（before_json 含 `session_ids`/`archived_at` 等非 allowlist 鍵） | P3 | `app.py:1203-1213`＋`app.py:538-540`＋`app.js:488`「按此记录恢复」按鈕必敗 |
| 4 | `resolve_change` conflict 過渡無審計 | P3 | `app.py:1148-1156` |
| 5 | requirements.txt 未釘版本（构建不可重現）；另環境衛生：生產 host 有第三方 `http.server 8601 --bind 0.0.0.0`（cwd `/home/jc/cft`，已排除洩漏本 repo） | P3 | `requirements.txt:1-6`；`ss -tlnp`＋`/proc/1098899/cwd`＋404 探測 |

### 2.3 淨係 Claude 搵到（Pi 逐一複核）—— 7 項，全部裁定屬實

| # | Claude 發現 | Pi 複核裁定 | 複核證據 |
|---|------------|------------|----------|
| 1 | DATA-02：`/archive` 完全繞過 `_revision` 衝突檢測 | **屬實，同意 P2**。Pi 原本將佢摺入 PI-DATA-03 籠統描述，Claude 獨立拎出係更準確嘅定位——archive 係唯一無守護嘅寫端點，與並發 PATCH 撞 revision 號會令 FieldRevision stale 偵測出現盲區 | `app.py:826-843` 全程無 `_revision`；前端 `archiveProject()`（`app.js:751-755`）只送 `{confirm:true}`，連欄位都冇帶 |
| 2 | DATA-04：reschedule 連鎖改動節點/任務有 FieldRevision 無 audit_log | **屬實，同意 P3** | `app.py:942-956` 逐 node 平移＋FieldRevision，無 write_audit；`app.py:958-960` `needs_review=True` 無審計；只有 session 一筆 `reschedule_confirmed`（`app.py:961-962`） |
| 3 | DATA-05：reject_change 審計 before/after 記法誤導（記錄「好似已生效」） | **屬實，同意 P3** | `app.py:1140-1141` reject 路徑 `after={field: new_value}`，但值從未寫入，需靠 `action` 欄位分辨 |
| 4 | DATA-06：restore 無 `_revision` 守護（非關鍵字段直接覆蓋） | **屬實，同意 P3**；與 Pi-DATA-05（同端點另一角度：某類記錄直接 400）互補，兩個都真 | `app.py:1211-1212` 無 expected_revision；非關鍵字段走 direct-write 分支 |
| 5 | SEC-07：無 ProxyFix——一旦上 TLS 反代，Origin 檢查會令全部寫請求 403 | **屬實，同意 P3（預埋斷裂）**。Pi 曾注意到 `request.host_url` 依賴 Host/scheme 但無展開；Claude 推理正確：Werkzeug `host_url` 用 `wsgi.url_scheme`（http），瀏覽器 Origin（https）→ 不等 → 403（`app.py:151-155`），而 `deploy/nginx-test-proxy.example.conf` 已設 `X-Forwarded-Proto` 但 app 唔讀 | `app.py:26` 無 proxy_fix import；`app.py:151-155` |
| 6 | OPS-01：Werkzeug dev server（`app.run`）做生產入口 | **屬實，同意 P2** | `Dockerfile:13` `CMD ["python","app.py","serve"]` → `app.py:1558` `app.run(threaded=True)`；dev server 無生產硬化，與 SEC-01 修復（TLS 後併發模式改變）互相阻塞 |
| 7 | FE-05：前端硬編碼 Asia/Shanghai 而後端 TZ 可配 | **屬實，同意 P3** | `app.js:61` `BUSINESS_TZ`、`app.js:842` `+08:00` vs `app.py:58` `APP_TIMEZONE` env；生產兩邊一致故暫無實害 |

### 2.4 分歧與爭議

| 爭議點 | Pi 立場 | Claude 立場 | 裁定 |
|--------|---------|------------|------|
| **SESSION_SECRET 喺生產容器是否存在** | **不存在**（`docker inspect` env 全鍵名枚舉＋`grep -c "^SESSION_SECRET"`=0；DB_PASSWORD/SHARED_PASSWORD 均在獨缺佢） | SEC-10 稱「生產容器鍵名單確認存在」 | **Pi 勝——Claude 呢個事實陳述錯誤**。後果：SECRET_KEY fallback 每進程隨機（`app.py:130`），每次重啟/重部署全員登出＋CSRF 全失效。呢個係有實證嘅 P2 運維發現（PI-DATA-02）。建議 Claude 報告勘誤 |
| sample-data.json 評級 | P1（疊加 0.0.0.0 即全 LAN 免認證可讀真實業務數據） | P2 | 事實零分歧，純嚴重度判斷。Pi 維持 P1（組合暴露面），但接受 P2 為合理下界；修復動作兩邊一致（移出 static＋重建鏡像） |
| IntegrityError detail 評級 | 初評 P2 | P3（需登入先見） | 採納 P3 |
| 201 bug 評級 | P2（因令測試門禁失效，係 TEST-01 嘅直接成因） | P3（單看係契約 cosmetic，但捆綁 TEST-01 見 P1 效應） | 兩邊其實同意「捆綁效應」；獨立嚴重度 P3、捆綁後升級——共識 |
| `/api/logout` 無 login_required | 未立項（視為冇害：session.clear 冪等＋CSRF 仍生效） | 記錄為「安全」註 | 無實質分歧 |

---

## Part 3：三個指定複核項裁定

### 複核 1：SEC-01（0.0.0.0 暴露）——**裁定：屬實（P1）**

Pi 獨立實測（未參考 Claude 前完成）：
- `docker inspect event-time-v041 --format '{{.HostConfig.PortBindings}}'` → `map[8097/tcp:[{0.0.0.0 8600}]]`——host 側綁定所有介面，偏離 repo `compose.yaml:19` 嘅 `127.0.0.1:${HOST_PORT:-8601}`。
- `ss -tlnp`：8600 LISTEN 於 `0.0.0.0`（docker-proxy）。
- 同容器 `COOKIE_SECURE=0`（基線應為 1），`app.py:137` 因此 cookie 無 Secure；登入密碼明文 POST（`app.py:695-706`）。
- 補充釐清（避免過度指控）：`app.py:1556`／`compose.yaml:14` 嘅 `ACTIVITY_HOST=0.0.0.0` 係**容器內**綁定，本身正常；真正問題係 **host PortBinding 用咗 0.0.0.0**（生產實際 compose／run 參數偏離倉庫）。

### 複核 2：TEST-01（test_editor_regression import 爆從未跑過）——**裁定：屬實（P1），且 Claude 根因分析正確並更深**

Pi 三層獨立驗證：
1. 本機實跑：`python3 -m unittest discover -s tests` → loader ERROR（`ModuleNotFoundError: No module named 'flask'`，`tests/test_editor_regression.py:12` 先爆）——套件當下完全跑唔到。
2. Claude 指出嘅更根本根因，Pi 已核實：`tests/test_editor_regression.py:13` `from models import db, ...`——**`models.py`（407 行，全文精讀）從未定義 `db`**（`db = SQLAlchemy(...)` 在 `app.py:124`）。即使裝好 Flask，呢行都係 `ImportError`。Claude 呢個根因比 Pi 初步發現嘅「flask 缺失」更本質——**雙層斷裂，任修一層都仲係紅**。
3. Claude 嘅對照實驗結論（修 import 後 4/4 敗於 `200 != 201`；放寬斷言後 8/8 綠）與 Pi 純代碼推理完全吻合：`tests/test_editor_regression.py:44-46` 斷言 201 vs `app.py:850/857/864/871/878` 實返 200；`git show 674afbd:app.py` 證實測試提交當刻 bug 已在。
**結論**：674afbd 聲稱嘅 R1 回歸覆蓋自創建起為零；修 `from app import db`＋五個 201 後套件應可全綠（Claude 實驗二佐證）。列為下次部署硬門禁。

### 複核 3：SEC-03（sample-data.json 免登入公開）——**裁定：屬實（Pi 評 P1／Claude 評 P2）**

Pi 獨立實測：`curl http://127.0.0.1:8600/static/sample-data.json`（無任何 cookie）→ **200，18,420 bytes，content-type application/json**。內容核實：22 個真實項目（含真名「洪湾渔港安全生产方案」等）＋18 個任務＋內部人名（JC、DDme、Fantasy、Mr.Y、付姐、任雪）；已掃描**無**電話/郵箱/密碼類欄位。`static/` 由 Flask 靜態路由直接伺服（`app.py:128`），不經鑑權；檔案自 758277e 入庫後零代碼引用（V0.3 遺留）；`Dockerfile:9` 將佢帶入生產鏡像。修復：移出 `static/`（如 `migration-source/`，已 gitignore）＋重建鏡像。

---

## 總體結論

# **PASS_WITH_FIXES**

### Pi 統計（獨立審計口徑）
- **P0 = 0**
- **P1 = 3**：PI-SEC-01（0.0.0.0 生產暴露）、PI-SEC-02/TEST-01（回歸套件從未運行）、PI-SEC-03（sample-data.json 免登入公開）
- **P2 = 7**：PI-SEC-04（無防爆破）、PI-DATA-01（五端點 201→200）、PI-DATA-02（SESSION_SECRET 缺席）、PI-DATA-03（revision 非原子）、PI-SEC-05（409 detail 洩漏，覆核後採 P3）、PI-SEC-06（health 洩漏，覆核後採 P3）、PI-SEC-07（operator 偽冒，覆核後採 P3）＋PI-TEST-02（零覆蓋）——即 P2 實際 5 項＋3 項下調 P3
- **P3 = 7**＋覆核下調 3 項＝10 項（PI-DATA-04/05/06/07、PI-FE-04、PI-OPS-01/02＋SEC-05/06/07）
- **PASS 級正向核驗 = 8**：CSRF 全覆蓋、上傳/穿越防護鏈、esc() 無 XSS 活路、quick-add 異常路徑、operator encode、競態鏈路、事務/級聯/審計完整性（含 d4c8a93 修復完整）、容器加固/備份腳本

### 共識／分歧摘要
- **互相印證 12 項**（含全部三個複核項——兩個審計員獨立實測同一事實）
- **Pi 獨有 5 項**（最重要：SESSION_SECRET 生產缺席——並反駁 Claude SEC-10 一處事實錯誤；其餘：parse_field 500、restore 400、conflict 無審計、依賴未釘版本＋host 衛生）
- **Claude 獨有 7 項，Pi 複核後全部裁定屬實同意**（archive 無 revision 守護、reschedule 連鎖審計缺口、reject 審計語義、restore 無守護、ProxyFix 預埋 403、dev server 生產、TZ 硬編碼）
- **評級分歧 3 處**（sample-data P1 vs P2；detail/health 洩漏 P2 vs P3——Pi 覆核後採納 Claude 較低評級；201 bug 捆綁效應兩邊本已同意）
- **事實爭議 1 處**：SESSION_SECRET 存在性——Pi 有直接 docker inspect 實證（缺席），Claude 陳述有誤，建議其報告勘誤

### 修復順序（合併兩份審計）
1. **立即（零代碼）**：生產改 `127.0.0.1` 綁定＋TLS 反代＋`COOKIE_SECURE=1`（反代前先加 ProxyFix，SEC-07）；移走 sample-data.json 重建鏡像；`.env` 補 `SESSION_SECRET`。
2. **一小時內**：`tests/test_editor_regression.py:13` 改 `from app import db`＋修五個 201（`app.py:850/857/864/871/878`）→ 8 測試全綠，設為部署門禁。
3. **本週**：登入限速＋失敗審計；`/archive` 補 `_revision`；換 gunicorn/waitress。
4. **排期**：其餘 P3（parse_field 400、restore 兩項、reject/conflict 審計語義、孤兒檔案清理、字體自托管、依賴釘版、TZ 注入）＋ TEST-02 補測（優先 d4c8a93 回歸與創建端點契約）。

*本報告全部證據可複現：git@d66cf97 工作副本只讀審計＋生產端只讀 GET 實測；除本檔案外零寫入。*
