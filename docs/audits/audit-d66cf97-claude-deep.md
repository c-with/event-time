# EVENT-TIME-AUDIT-03：d66cf97 深度只讀審計報告

- **審計基準**：HEAD `d66cf97`（branch `ui/bento-redesign`）；生產容器 `event-time-v041` 鏡像 sha256 `4e56a05f8f12…` 已核對等於本倉 `event-time:d66cf97` 標籤 → **生產即審計基準，無版本漂移**。
- **審計範圍**：`e6b8de7..d66cf97` 全部 23 個 commit（任務書寫 8 個，實際區間 23 個），重點深挖 `f4d19b4..d66cf97`（R1 修復＋bento UI＋quick-add＋operator 修復）。
- **方法**：全文精讀 `app.py`(1562 行)/`models.py`(407)/`static/app.js`(875)/`static/index.html`/`styles.css` 外掃；全部 41 條路由逐條枚舉核對 CSRF/鑑權；`db_schema.sql` 與 models 級聯全量比對；運維腳本逐行；生產端**只讀**實測（GET `/health`、GET static、`docker inspect` 非機密鍵）；測試套件在一次性容器內以 repo read-only 掛載執行（本機無 Flask 環境，容器內副本作兩個受控實驗，repo 零改動）。
- **紅線遵守**：零修改、零 commit/push/deploy、對 8600 只發 GET、未讀取任何密碼/token 值（`.env` 只查存在性——repo 內無 `.env`；容器 env 只列鍵名＋兩個非機密值 `COOKIE_SECURE`/`HOST_PORT`）。

---

## 執行摘要

| 維度 | 結論 |
| --- | --- |
| A 安全 | 核心機制（CSRF、會話、路徑穿越、上傳）**設計良好且覆蓋完整**；但**生產部署偏離 repo 基線**（0.0.0.0＋純 HTTP＋COOKIE_SECURE=0）構成最主要風險 |
| B 數據完整性 | 事務邊界、字段級合併、審計 append-only 均落實；`d4c8a93` 修復完整；小缺口在 archive 無 revision 守護與 revision 計數器非原子 |
| C 前端 | `esc()` 覆蓋近乎完整無 XSS 活路；quick-add `pendingModalRestore` 異常路徑逐一推演無洩漏/雙重觸發；operator encode 修復完整 |
| D 運維 | 容器加固（read-only rootfs、no-new-privileges、tmpfs noexec）**實測落實**；備份腳本品質好；最大債是 Werkzeug dev server 跑生產 |
| E 測試 | **最重炸彈：`test_editor_regression.py` 自創建起從未運行過**（import 爆），674afbd 聲稱的 R1 回歸覆蓋是虛假安全感；實驗證明修一行 import 後 4/4 測試因已知的 201 bug 失敗，再放寬斷言則 8/8 全綠 |

**總體評級：PASS_WITH_FIXES**（無 P0；兩個 P1 均為可快速修復的部署衛生與測試債，不需數據遷移）

**統計：P0=0，P1=2，P2=5，P3=12**（另 8 項 PASS 級正向核驗）

---

## A. 安全

### SEC-01 [P1] Production network exposure deviates from repo baseline: 0.0.0.0 + plain HTTP + COOKIE_SECURE=0

**位置/證據**（生產實測，非推測）：
```
$ docker inspect event-time-v041 --format '{{json .HostConfig.PortBindings}}'
{"8097/tcp":[{"HostIp":"0.0.0.0","HostPort":"8600"}]}
$ docker inspect … | grep ^COOKIE_SECURE
COOKIE_SECURE=0
```
而 repo 基線 `compose.yaml:20` 明確 `127.0.0.1:${HOST_PORT:-8601}:8097`、`compose.yaml:18` `COOKIE_SECURE: "${COOKIE_SECURE:-1}"`、`.env.example:8` `COOKIE_SECURE=1`。生產配置繞過了倉庫設計的「只綁 localhost＋反代 TLS」安全意圖（部署偏移，生產 WS 的實際 compose 與 repo 不一致）。

**影響**：登入共享密碼以 JSON 明文 POST（`app.py:694-706`）、session cookie 無 Secure 標記（`app.py:137` `SESSION_COOKIE_SECURE` 因 env=0 而關閉）且全程純 HTTP。任何同網段主機（尤其活動場地共享 Wi-Fi——本系統的典型使用場景）可嗅探憑證或劫持會話。`SESSION_COOKIE_HTTPONLY=True`（`app.py:135`）與 `SameSite=Lax`（`app.py:136`）只防 XSS/CSRF 側信道，防唔到網絡竊聽。

**建議修復**：生產改回 `127.0.0.1` 綁定＋HTTPS 反代（`deploy/nginx-test-proxy.example.conf` 已有模板），`COOKIE_SECURE=1`；過渡期用防火牆限制 8600 只允許辦公網段；將生產 compose 差異回填入倉庫避免再次漂移。

### SEC-02 [P2] No brute-force protection or login attempt auditing on /api/login

**位置**：`app.py:694-706`。
**證據**：login 直接 `check_password_hash`（werkzeug scrypt），全倉無任何 rate limiter / 失敗計數 / 鎖定（grep 無 flask-limiter 等）；失敗登入不寫 `audit_log`（`write_audit` 調用點全在業務寫路徑）。錯誤訊息統一「账号或密码不正确」不洩漏用戶存在性（好），但僅靠密碼強度（init 時強制 ≥14 位，`app.py:1505-1506`）硬扛。
**影響**：結合 SEC-01（0.0.0.0 直連），同網段可無限速撞密碼；且撞庫嘗試無審計痕跡。
**建議修復**：per-IP＋全局限速／失敗退避；失敗登入記 audit（actor=來源 IP）。

### SEC-03 [P2] /static/sample-data.json serves real business data without authentication

**位置**：`static/sample-data.json`（V0.3 導出樣本，628 行）。
**證據**（生產實測）：`GET http://127.0.0.1:8600/static/sample-data.json` → **HTTP 200，18,420 bytes，無需登入**。內容為 22 個真實項目（「洪湾渔港安全生产方案」「澳门青年实习计划」等真實名稱＋日期）與 7 個真實人員名（JC、DDme、Fantasy、Mr.Y、Source、付姐、任雪）。Flask static 路由（`app.py:128` `static_folder="static"`）不經 `login_required`。
**影響**：完全繞過登入門檻取得客戶項目名單、排期與內部人員名。0.0.0.0 下整個 LAN 可讀。
**建議修復**：將該檔移出 `static/`（入 `docs/` 或 `data/`），重建鏡像；若屬 V0.3 遷移中間產物，歸檔到 `migration-source/`（已 gitignore）。

### SEC-04 [P3] /health leaks raw DB exception detail and stack fingerprint unauthenticated

**位置**：`app.py:684-692`。
**證據**：`return jsonify(ok=False, error=str(exc)[:200]), 503` — 原始驅動異常字串（可含 DB 主機/埠/錯誤語義）直接對外；正常時回 `database=postgresql, version=0.4.1`（技術棧指紋）。生產實測 `GET /health` → `{"database":"postgresql","ok":true,"version":"0.4.1"}` 無需登入。
**影響**：低（監控價值 vs 淺洩漏）；DB 故障時對外網暴露連線錯誤細節。
**建議修復**：對外只回 `ok:false`，細節進 `app.logger`；或 health 加內網限制。

### SEC-05 [P3] IntegrityError 409 returns raw DB error detail (and frontend toast doesn't show it either)

**位置**：`app.py:172-175` — `detail=str(error.orig)[:240]`（含約束名/表名/值片段）。
**影響**：登入後可見的淺洩漏；同時是任務書已知 UX 問題（前端 toast 唔顯示 detail）——兩頭唔討好：洩漏咗但用戶睇唔到。
**建議修復**：detail 換成結構化欄位（如 `{"constraint": "fk"}`），原文入 log；前端揀選顯示友好訊息。一併解決已知 UX 問題。

### SEC-06 [P3] X-Operator-Name is an unauthenticated, spoofable audit actor

**位置**：`app.py:203-217`；`app.js:99-111`（localStorage 任改）。
**影響**：共享單賬號模型下所有審計追責（`audit_log.actor`、`ChangeRequest.proposed_by`）依賴客戶端誠實申報。這是設計取捨而非漏洞，但應在文檔明示「operator 名非強身份證明」。
**建議修復**：接受現狀＋文檔聲明；或長遠把登入賬號與 operator 並存記錄。

### SEC-07 [P3] Missing ProxyFix will 403 all writes the moment an HTTPS reverse proxy is enabled

**位置**：`app.py:26`（無 `werkzeug.middleware.proxy_fix` import）；`app.py:151-155`（Origin 直比 `request.host_url`）；`deploy/nginx-test-proxy.example.conf`（設 `X-Forwarded-Proto` 但 app 不讀）。
**影響**：一旦按 repo 基線計劃上 TLS 反代（SEC-01 的正確修法），`host_url` 仍為 `http://…`，瀏覽器 Origin `https://…` → 所有帶 Origin 的寫請求 403「跨站请求被拒绝」。屬部署斷裂預埋。
**建議修復**：加 `ProxyFix(x_for=1, x_proto=1, x_host=1)`，由 env 開關（`PROXY_FIX=1`），上反代前先改。

### SEC-08 [PASS] CSRF 覆蓋完整（逐端點枚舉核驗）

**證據**：`app.py:146-160` before_request 攔截所有 `/api/*` 的 POST/PUT/PATCH/DELETE（唯一豁免 `/api/login`——登入 CSRF 在共享單賬號下無實害）。枚舉全部 41 條路由（見附錄）：**所有**寫路由都在 `/api/` 下；`/`、`/health`、`/share/<token>` 均為 GET；無任何漏網端點。Token 比較用 `hmac.compare_digest`（`app.py:158`）✓；SameSite=Lax＋token 雙保險 ✓；登入時輪換 csrf_token＋`session.clear()` 防 fixation（`app.py:701-703`）✓。修復 import 後 `test_missing_csrf_cannot_edit` 實測通過（403）。

### SEC-09 [PASS] 路徑穿越／文件上傳防護鏈完整

**證據**：
- 下載雙保險：`app.py:1420-1421`（document_content）與 `app.py:1464-1465`（public_share）都 `Path(path).resolve()` 後驗 `DATA_DIR in p.parents`；儲存檔名一律伺服器生成 uuid（`app.py:1268`），不用戶檔名。
- PDF magic bytes `raw.startswith(b"%PDF")`（`app.py:1270-1271`）；圖片一律經 PIL 解碼重編碼（`app.py:1302-1334`）——polyglot 載荷會被重編碼消解；HEIC 經 pillow-heif 註冊。
- `secure_filename`（`app.py:1377`）；副檔名白名單 `ALLOWED_EXT`（`app.py:66`）；單檔 100MB／批量 250MB＋`MAX_CONTENT_LENGTH`（`app.py:64-65, 134`）＋413 handler。
- 分享 token：`secrets.token_urlsafe(32)` 只存 sha256（`app.py:1436-1437`），有過期＋撤銷＋`allow_download` 門（`app.py:1461-1466`）。
- 小注（資源消耗，不另立項）：`app.py:1364` `sum(len(f.read()) for f in files)` 先整批讀入記憶測總量再逐檔重讀——250MB 上限下峰值記憶可觀，建議改流式／按 `content_length` 預檢。

### SEC-10 [PASS] 會話與認證機制健全（除 SEC-01/02 已列項）

`SESSION_COOKIE_HTTPONLY` ✓（`app.py:135`）；`SECRET_KEY` 優先取 `SESSION_SECRET`（`app.py:130`，生產容器鍵名單確認存在；fallback 隨機值的副作用只是重啟即登出，非安全問題）；`login_required` 每請求驗 user 存在＋active（`app.py:190-201`）；`/api/me` 無csrf_token 時補發（`app.py:719-720`）；logout `session.clear()` 徹底（`app.py:708-711`）；無 CORS 頭（同源封閉）✓。share_links 端點全部 `@login_required`（建立/撤銷/列表，`app.py:1426-1476`），無「假設角色分離」的授權缺口——共享單賬號模型下語義一致。

> ### 勘誤（2026-10-23，EVENT-TIME-AUDIT-03-VERIFY 補記）
>
> 上段「生產容器鍵名單確認存在（SESSION_SECRET）」為**錯誤事實陳述**，由 Pi 交叉審計實證反駁（`audit-d66cf97-pi-cross.md` PI-DATA-02／§2.4 分歧裁定）：`docker inspect event-time-v041` env 全鍵名枚舉顯示 `DB_PASSWORD`/`SHARED_PASSWORD` 均在、**獨缺 `SESSION_SECRET`**（`grep -c "^SESSION_SECRET"` = 0）。本人原審計對此鍵並無 docker inspect 直接證據，「存在」屬無實證支撐的斷言，作廢。
>
> **正確事實**：生產容器缺 `SESSION_SECRET`，`app.py:130` fallback `secrets.token_hex(32)` 每進程隨機生效——每次重啟/重部署全員登出＋CSRF token 全失效（營運衝擊 P2，即 Pi 報告 PI-DATA-02；密碼學上隨機 fallback 並非弱化，故非安全漏洞）。
>
> SEC-10 的 PASS 結論（會話機制*設計*健全）不變；變嘅係「部署已設定該鍵」呢句陳述。後續處理：b30188e 已喺 `app.py:130` 上方加註釋記錄此取捨（刻意零行為改動），真正修復喺部署側 `.env` 補鍵後重啟——屬主控部署動作，唔係代碼修復。

---

## B. 數據完整性

### DATA-01 [P3] Five child-create endpoints return 200 instead of 201 (known bug, confirmed + impact bounded)

**位置**：`app.py:850`（sessions）、`app.py:857`（time-nodes）、`app.py:864`（work-packages）、`app.py:871`（requirements）、`app.py:878`（tasks）。
**證據**：統一寫法 `return jsonify(session=result) if status == 201 else (jsonify(result), status)` — 201 分支裸返回 Response，Flask 預設狀態碼 200。`make_child` 明明正確返回 `(serialize_entity(...), 201)`（`app.py:678`）。容器內實測：4/4 回歸測試 `assertEqual(200 != 201)` 失敗（見 TEST-01）。
**影響**：REST 契約斷裂。前端 `res.ok` 判斷不受影響（200 也是 ok），功能無損；但任何按 201 判斷的集成/遷移腳本會誤判，且它正是令 674afbd 測試全紅的直接原因。
**建議修復**：五處改為 `return jsonify(session=result), status`；修復後已知 UX 問題清單可劃走一項。
**已知問題優先級評估**：單獨看是 P3（契約 Cosmetic）；與 TEST-01 疊加效應見該項。

### DATA-02 [P2] /archive bypasses _revision conflict detection entirely

**位置**：`app.py:826-843`。
**證據**：`archive_project` 直接 `project.revision += 1` 寫入（`app.py:838-840`），全程不接收/不比對 `_revision`，與 `apply_entity_changes`（`app.py:546-557`）和 `patch_with_links`（`app.py:986-995`）的樂觀鎖路徑不一致。
**影響**：與並發 PATCH 同時發生時，兩邊各自把 revision 從 N 推到 N+1 → revision 號碰撞、FieldRevision 序列交錯，令後續 stale 偵測（`FieldRevision.revision > expected`，`app.py:550-552`）出現盲區。業務上歸檔與編輯衝突的窗口小，但這是唯一完全無守護的寫端點。
**建議修復**：archive 接收 `_revision` 比對（前端 `archiveProject` 有 `state.project.revision` 可帶），或改 DB 端原子 `UPDATE … WHERE revision=:expected`。

### DATA-03 [P3] Revision counter is application-level read-modify-write (non-atomic)

**位置**：`app.py:545`（讀 `entity_revision(obj)`）→ `app.py:583-585`（`obj.revision = current_revision + 1`）；`resolve_change` 同款（`app.py:1161-1164`）。
**影響**：兩個並發 PATCH 可同讀 revision=N 各寫 N+1。字段級合併設計下業務衝突有 FieldRevision 兜底（`later_revision` 查詢會抓到同字段後寫），**不會靜默丟數據**，但 revision 號會重複、變更歷史亂序。屬設計已知限制，建議文檔化或改 ORM `version_id_col`。
**建議修復**：低成本方案——`UPDATE … SET revision=revision+1 RETURNING revision`；或接受＋文檔。

### DATA-04 [P3] Reschedule cascade mutates nodes/tasks with FieldRevision but no audit_log entries

**位置**：`app.py:942-956`（跟隨場次的 time_node 被平移＋revision+1＋FieldRevision，但無 `write_audit`）；`app.py:958-960`（`task.needs_review=True` 無審計）；只有 session 本身有一筆 `reschedule_confirmed`（`app.py:961-962`）。
**影響**：審計鏈對「點解呢個節點時間變咗／任務被標複核」需靠推理關聯，與「人工改過嘅數據可完整追溯」原則有落差。
**建議修復**：受影響 node/task 聚合記入同一筆 audit 的 after（如 `{"moved_nodes": [...ids], "flagged_tasks": [...ids]}`）。

### DATA-05 [P3] reject_change audit entry records before/after as if the change was applied

**位置**：`app.py:1140-1141` — 駁回路徑 `write_audit(..., before={field: old_value}, after={field: new_value})`，與 confirm 路徑（`app.py:1171-1172`）記法相同，但駁回時值根本未寫入。
**影響**：事後只讀 before/after 欄位會誤以為提案值已生效（需靠 `action="reject_change"` 區分，欄位語義錯誤）。
**建議修復**：reject 審計的 after 記當前實際值或空物件。

### DATA-06 [P3] restore_audit applies field restores without _revision guard on non-critical fields

**位置**：`app.py:1211-1212` — `apply_entity_changes(..., before_json, critical_confirmed=False)` 不帶 `expected_revision`；`before_json` 亦無 `_revision` 鍵。
**影響**：關鍵字段有 ChangeRequest 提案流程兜底 ✓；但非關鍵字段（notes、owner、description 等）恢復是無衝突檢測的直接覆蓋，可靜默蓋掉並發修改。屬恢復語義的設計取捨，建議至少彈窗提示。
**建議修復**：restore 帶當前 `_revision` 走正常衝突檢測。

### DATA-07 [PASS] 事務邊界與 rollback 完整性

- `patch_with_links`（`app.py:974-1061`，f4d19b4/8afff1a 修復核心）：先全量驗證（關係循環、跨項目、ID 合法性）→ `apply_entity_changes(commit=False)` → 連結變更 → 單一 `commit`；`except Exception: rollback; raise`（`app.py:1059-1061`）；status≠200 路徑先 rollback 再返回（`app.py:1017-1019`）✓。
- `errorhandler(IntegrityError)` 有 rollback（`app.py:174`）✓；`health` 失敗 rollback（`app.py:691`）✓；`make_child` 驗證失敗 rollback（`app.py:660, 667, 673`）✓；上傳逐文件 commit＋失敗 rollback（`app.py:1401-1406`）✓。
- 小衛生項（併入此條）：`errorhandler(Exception)`（`app.py:183-188`）無顯式 rollback，靠 Flask-SQLAlchemy teardown `session.remove()` 兜底——實務上安全（錯誤後無後續代碼跑），但與 IntegrityError handler 風格不一致，建議補一行。`apply_entity_changes` 中 `parse_field` 中途 400（`app.py:563-565`）時 session 可能已有 flush 過的 ChangeRequest——同樣靠 teardown 丟棄，無持久化風險。
- **實證**：修 import＋放寬斷言後 `test_task_edit_and_relations_are_atomic`、`test_invalid_relationship_does_not_save_valid_scalar`、`test_stale_relationship_edit_is_rejected` 全部通過——R1 的原子性/stale 拒絕行為真實正確。

### DATA-08 [PASS] 級聯刪除配置 vs 業務預期：一致且休眠

全 API **無任何 DELETE 路由**（41 條路由枚舉確認）——級聯配置只影響直接 DB 操作。關鍵配置符合「人工數據不被靜默刪除」原則：`clients→projects.client_id` SET NULL＋`client_snapshot` 保留（`models.py:152-153`）；`work_packages.supplier_id` SET NULL（`models.py:225`）；`time_nodes.work_package_id`／`tasks.work_package_id`／`requirement_items.work_package_id` SET NULL（`models.py:199, 274, 248`）。唯一 CASCADE 刪人工數據的位：`contacts` 隨 client/supplier 級聯刪（`models.py:77-78`，ORM 側 `cascade="all, delete-orphan"` `models.py:56, 69`）——但無 API 觸發，僅直接 DB 刪除時生效，建議 ops runbook 註明。`db_schema.sql` 與 `models.py` 的 ondelete 全量比對**一致無漂移**（23 張表對齊）。

### DATA-09 [PASS] 審計日誌 append-only；寫路徑不漏記

無任何 API 修改/刪除 AuditLog 舊記錄（僅 insert＋query，`app.py:1194-1201`）；`restore_audit` 只讀舊記錄、經新變更流程生效（`app.py:1203-1213`）✓。所有業務寫路徑（create/patch/archive/reschedule/confirm/reject/upload/share/revoke）的 `write_audit` 與數據變更同事務 commit——commit 失敗則審計與數據一起回滾，不會出現「有審計無數據」或反向 ✓。缺口僅 DATA-04（reschedule 連鎖影響）與登入事件不記審計（SEC-02）。

### DATA-10 [PASS] d4c8a93（client_id="" → NULL）修復完整性核驗：完整

**證據**：`create_project` 手工組裝 fields 路徑已修（`app.py:795-797`）；其餘所有入口都經 `parse_field`（`app.py:267-268`）——FK 字段 `""` 統一轉 None（`make_child` `app.py:617`、`create_resource` `app.py:1235`、`apply_entity_changes` 經 `parse_field` `app.py:563`）。`cover_document_id`/`evidence_document_id` 故意例外保留 `""`（非 FK、String(36) 列，`models.py:157, 285`）語義一致。同類欄位（supplier_id/venue_space_id/work_package_id/session_id/space_id）無同款炸彈。**無殘留路徑**。
附註：此修復無回歸測試（見 TEST-02）。

---

## C. 前端正確性

### FE-01 [PASS] esc() 覆蓋逐變數點算：無 XSS 活路（附衛生建議）

**方法**：`static/app.js` 全部 innerHTML 模板字串中的 `${…}` 插值逐個點算（約 40 個模板位）。
**結論**：所有用戶可控文本（name/title/notes/owner/actor/label/subtitle/resolution_note/JSON.stringify(after) 等）全部經 `esc()`（`app.js:46-48`），包括屬性上下文（`value="…"`、`title="…"`、`data-*="…"`、`url`）。`toast()` 用 `textContent`（`app.js:95`）✓；`page-title` 用 `textContent`（`app.js:384`）✓。
**剩餘未 esc 插值**（全部目前安全，屬縱深防禦缺口，記錄不立項）：
1. 伺服器生成 UUID（`app.js:321` `data-session-id="${s.id}"`、`app.js:375` `data-id="${p.id}"` 等）——uuid4 字符集不可能是引號；但若 API 未來被第三方寫入則失守。
2. `fmtDate`/`fmtDateTime` 輸出（`app.js:339, 348, 375, 415, 419, 423, 433, 446, 449` 等）——安全依賴後端 DateTime 列型別強制；`fmtDateTime` 對非法值有 `String(value).replace('T',' ')` 直通分支（`app.js:58`）。
**建議修復**（P3 衛生）：約定「模板插值一律 esc() 包裹」——把 UUID 與 fmt* 輸出也包上，成本零、杜絕未來回歸。

### FE-02 [PASS] quick-add `pendingModalRestore` 異常路徑全推演：無洩漏、無雙重觸發

逐路徑核驗（`app.js:530-598, 480-517`）：
- **二級 POST 失敗**：錯誤留在二級 modal 錯誤欄＋按鈕復位（`app.js:502-507`），`pendingModalRestore` 保持；重試成功或取消都正確回收一級表單 ✓。
- **Escape**（`app.js:859`）/ **backdrop 點擊**（`app.js:510`）/ **取消按鈕**：全部經 `requestCloseModal` → dirty 檢查（initialSnapshot 比對，`app.js:536-542`）→ `closeModal` → restore 重建一級表單 ✓。
- **雙重觸發防護**：`closeModal` 先取出並置 null 再執行 restore（`app.js:532-534`）——連續兩次 closeModal 第二次是純清空 ✓；restore 內的 `openModal` 不觸碰 `pendingModalRestore`，無遞歸 ✓。
- **值保全**：`triggerQuickAdd` 快取全部 live 值（checkbox/multiple 分支齊全，`app.js:570-576`）＋ initialSnapshot 基線；restore 後基線還原（`app.js:596`）令「未保存守護」語義連續（新建資源已選入 → 表單 dirty → 誤關有提示）✓。
- **資源列表刷新失敗**：`delete state.resources[kind]` 後 `ensureResource` 失敗有 toast 警告＋手動 push 選項 fallback（`app.js:584-585, 592`）✓。
- **`field.options` 原位變異**（`app.js:591`）：作用於 cfg.fields 原物件，openModal 重渲染即生效 ✓。
- UX 註：二級 modal 乾淨時按 Escape 會「返回一級表單」而非全部關閉——符合巢式語義，非 bug。
**結論**：d66cf97 新機制在各關閉路徑下不丟用戶草稿、不殘留鉤子、不重複觸發。僅有既有通病：hashchange 導航時 modal 不關（任何 modal 皆有，非 quick-add 特有）。

### FE-03 [PASS] 競態防護：修訂號鏈路閉合

日曆拖拽帶 `data-revision`（`app.js:831`）→ reschedule POST 帶 `_revision`（`app.js:822, 850`）→ 伺服器 409（`app.py:931-933`）✓。`cycleTask` 帶 `_revision`＋`confirm_critical`（`app.js:681`）✓。全部編輯表單 PATCH 帶 `_revision`（`app.js:605, 633, 644, 653, 662, 673, 690, 724`）✓。長開 modal 後提交 → 409 → 錯誤留在 modal 內資料不丟（`app.js:502-507`）✓。兩個 quick-add 並發在 UI 上不可能（單 modal 佔據 modalRoot）✓。stale 關係編輯拒絕（8afff1a）實測通過（409）✓。

### FE-04 [PASS] operator name encode 修復完整，同類位排查無殘留

`app.js:123` `headers.set('X-Operator-Name', encodeURIComponent(operator))`；後端 `app.py:206-211` 條件 unquote（僅 `%` 存在時；`urllib.parse.unquote` 對非法 escape 原樣保留，舊客戶端含 `%` 的 ASCII 名不會被誤解碼）。全前端排查：非 ASCII 入 header 的位置只有這一處（`X-CSRF-Token` 為 ASCII token；`api()` 是唯一 fetch 封裝）✓。服務端截斷 `[:160]` 防 header 溢出（`app.py:217`）✓。

### FE-05 [P3] Frontend hardcodes Asia/Shanghai while backend TZ is env-configurable

**位置**：`app.js:61`（`BUSINESS_TZ = 'Asia/Shanghai'`）、`app.js:842`（拖拽 `+08:00` 硬編碼）；`app.py:58`（`TZ` 由 `APP_TIMEZONE` env）。生產 `APP_TIMEZONE=Asia/Shanghai`（實測）兩邊一致 ✓。
**影響**：改 env 即漂移（拖拽改期會錯時區）。目前無實害，屬配置耦合債。
**建議修復**：由 `/health` 或模板注入業務時區到前端。

### FE-06 [P3] index.html depends on Google Fonts CDN

**位置**：`static/index.html:21-23`。
**影響**：內網/離線場館環境字體加載失敗（有系統字體 fallback，視覺降級）；用戶 IP 對 Google 洩漏。與「場地網絡不可靠」的使用場景相悖。
**建議修復**：字體自托管入 static/，或直接刪除外鏈用系統字體棧。

---

## D. 運維/部署

### OPS-01 [P2] Werkzeug development server (app.run) is the production entrypoint

**位置**：`Dockerfile:13` `CMD ["python","app.py","serve"]` → `app.py:1556-1558` `app.run(host, port, threaded=True)`。R1 索引（`docs/audits/README.md` P1-06）標「未改」——**屬實**。
**影響**：dev server 未經生產硬化（無請求超時治理、無 worker 進程模型、Werkzeug 官方明示 not for production）。目前 RestartCount=0、health ok（實測），單進程小併發勉強可用；但這是生產穩定性與 SEC-01 修復（TLS 終結後併發模式改變）的技術債前置。
**建議修復**：gunicorn（sync worker，留意大上傳 timeout）或 waitress；保留 `/health` 供 compose healthcheck。

### OPS-02 [PASS] 容器加固實測落實（非紙面配置）

生產 `docker inspect` 實測：`ReadonlyRootfs=true` ✓、`SecurityOpt=["no-new-privileges:true"]` ✓、專用非 root UID 1000 ✓、鏡像 sha `4e56a05f…` == `event-time:d66cf97` 標籤（生產代碼即審計基準）✓、`RestartCount=0`、`StartedAt 2026-10-23T00:13`、health 200 ✓。compose 基線另有 tmpfs `/tmp` noexec,nosuid（`compose.yaml:34-35`）✓；`.dockerignore` 排除 `.env`/`data`/`backups`——秘密不進鏡像 ✓；repo 目錄無 `.env`（實測）✓。註：應用暫存目錄 `/data/tmp` 在持久 volume 內而非 tmpfs——配合 OPS-04 的殘留問題。

### OPS-03 [PASS] 備份腳本品質好（含驗證與保留策略）

`scripts/backup.sh`：經既有 postgres 容器 dump（不另起 DB）✓；`pg_restore --list` 驗證 dump 可讀 ✓；SHA256 清單 ✓；`trap` 清 .tmp ✓；保留 7 日/4 週且每條清理管線 `|| true` 護欄（30aa106 修復）✓；密碼僅經 `docker exec -e PGPASSWORD` 進程 env 短暫存在（可接受）。`scripts/restore-test.sh`：臨時庫＋`DROP … FORCE` cleanup trap ✓、7 核心表＋項目數斷言 ✓。
**缺口**（P3，併入此條）：不驗 `data-*.tar.gz` 文件包的恢復與 documents↔DB 交叉一致性；無異地副本自動化（install-cron 只 echo 提示）；`.env`（SESSION_SECRET/DB_PASSWORD）不在備份範圍——災難恢復時全員登出＋需人工改庫密碼。建議 runbook 補異地副本步驟。

### OPS-04 [P3] Upload failure paths orphan files on disk; no tmp cleanup

**位置**：`app.py:1273-1292`（先寫盤後 insert）；`app.py:1404-1406`（insert/commit 失敗 rollback 但不刪已寫文件）；`/data/tmp` 的 `.tmp` 中間文件在異常中斷時殘留，無清理任務。R1 索引 P2-08「未改」屬實（記憶體預讀部分見 SEC-09 附註）。
**建議修復**：失敗路徑 best-effort unlink；cron 清理 `/data/tmp` 超過 24h 的 `.tmp`。

### OPS-05 [PASS] Health check covers DB liveness; container orchestration coherent

`/health` 執行 `SELECT 1`（`app.py:687`）真實探活 ✓；DB 失敗返 503＋rollback ✓；compose healthcheck 30s×3 合理 ✓。注意：`restart: unless-stopped` 只看退出碼——DB 長期故障時容器持續 running-but-unhealthy，不會自癒，監控需盯 health 狀態而非進程存在（記錄於此，不立項）。信息洩漏面見 SEC-04。

---

## E. 測試債

### TEST-01 [P1] test_editor_regression.py has never run since creation — broken import voids all R1 regression coverage

**位置**：`tests/test_editor_regression.py:13` — `from models import db, Project, Task, RequirementItem, TaskDependency, FieldRevision`。
**證據**：
1. `models.py` 全歷史（僅 758277e 一個 commit）**從未 export `db`**——`db` 定義在 `app.py:124`。import 即 `ImportError`。
2. 本機/容器實測 `python -m unittest discover -s tests`：`test_editor_regression` loader ERROR，4 個回歸測試**零執行**（merge_logic 4 個通過）。
3. **受控實驗一**（容器內副本 sed 修 import 為 `from app import db`）：4/4 失敗於 `AssertionError: 200 != 201`——撞正 DATA-01。
4. **受控實驗二**（再放寬狀態碼斷言為 `assertIn((200,201))`）：**8/8 全部通過**——證明 674afbd 想覆蓋的原子性、無效關係零寫入、stale 409、CSRF 403 行為本身全部正確。
**影響**：commit 674afbd 訊息「cover task relation edits, atomic errors, stale revision and CSRF」實際覆蓋為零——R1 修復至今只有人肉驗證；且 DATA-01（201 bug）本應在當時就被測試攔下。`tests/__pycache__` 有該檔 .pyc（編譯於 import 嘗試）不能證明曾通過。
**建議修復**：一行改 `from app import db`；配合修 DATA-01 後 8 個測試直接全綠。**將「測試套件全綠」設為下一次部署的硬門禁**（現時任何 CI 若只看 exit code 應已標紅——需確認部署流程真的有跑）。

### TEST-02 [P2] New feature surface has zero test coverage; only passing tests exercise dead code

**證據**：`tests/` 僅 2 個文件。`grep quickAdd|theme|operator tests/` 零命中——quick-add（d66cf97）、theme 三態（8884575）、operator encode、bento UI、`d4c8a93` client_id 修復（DATA-10，無回歸保護）、409 detail、reschedule 流程、上傳/分享/撤銷、restore_audit、search、resources CRUD 全部無測試。而唯一穩定通過的 `test_merge_logic.py` 測的 `merge_logic.py` 是**運行時死代碼**（`app.py`/`models.py`/前端均不 import，V0.3 遺物）。
**影響**：R1 索引 P1-07「未改」屬實且惡化——測試資產的「綠燈」與生產代碼路徑完全脫節。
**建議修復**：優先補（1）d4c8a93 回歸（`client_id=""`）；（2）五個創建端點狀態碼契約；（3）上傳＋分享 smoke（含 413/400 路徑）；（4）quick-add 後端資源創建路徑（前端部分至少手動清單）。`merge_logic.py` 若確認棄用可移至 `scripts/` 或刪除（連同其測試），避免虚假覆蓋感。

---

## 已知問題清單複核（任務書指定）

| 已知問題 | 複核結論 | 評級 |
| --- | --- | --- |
| 五個創建端點 jsonify 201 實返 200 | 屬實，五處定位 `app.py:850/857/864/871/878`；實測重現；前端 `res.ok` 不受影響，純契約斷裂；但它係 TEST-01 全紅的直接成因，建議與測試修復捆綁處理 | DATA-01（P3，捆綁效應見 TEST-01 P1） |
| IntegrityError 409 detail 前端 toast 不顯示 | 屬實（後端給了 `detail`，前端 `err.message` 只取 `error` 欄位 `app.js:131`）；與 SEC-05 洩漏面同源，建議一併改結構化 detail＋前端顯示 | 併入 SEC-05（P3） |
| client_id="" 曾引 FK 409（已修 d4c8a93） | **修復完整**（DATA-10）：手工組裝路徑已修，其餘入口全經 `parse_field` 統一 `""`→None；同類欄位無殘留 | PASS；缺回歸測試（TEST-02） |

---

## 生產實測記錄（全部只讀）

| 探測 | 結果 |
| --- | --- |
| `GET http://127.0.0.1:8600/health` | `{"database":"postgresql","ok":true,"version":"0.4.1"}`（無需登入） |
| `GET /`、`GET /static/app.js` | 200（靜態資源無鑑權，預期） |
| `GET /static/sample-data.json` | **200，18,420 bytes，含真實業務數據**（SEC-03） |
| `docker inspect event-time-v041` | 鏡像 `4e56a05f…`（=d66cf97）✓；PortBindings `0.0.0.0:8600`（SEC-01）；`COOKIE_SECURE=0`（SEC-01）；ReadonlyRootfs/no-new-privileges ✓（OPS-02）；RestartCount=0 |
| `.env` 存在性 | repo 目錄無 `.env` ✓（生產在 WS 部署目錄，未讀取） |
| 端口掃描/滲透 | **未執行**（紅線遵守）；僅被動讀上述端點 |

## 附錄：41 條路由核對表（CSRF／鑑權）

GET（無 CSRF 需求）：`/`、`/health`、`/share/<token>` 公開；`/api/me` 半公開（未登入返 `authenticated:false`）；其餘 `/api/dashboard|projects|projects/<id>|calendar|change-requests|audit|resources/<kind>|documents|documents/<id>/content|shares|search` 全部 `@login_required` ✓。
POST/PATCH（19 條）：全部位於 `/api/*`，除 `/api/login` 外全部經 before_request CSRF＋Origin 檢查 ✓；全部業務寫路由 `@login_required` ✓（`/api/logout` 無 login_required，冊碌操作，安全）。
DELETE/PUT：**零條**（呼應 DATA-08）。

---

## 總體評級與統計

# **PASS_WITH_FIXES**

- **P0 = 0**
- **P1 = 2**：SEC-01（生產明文暴露偏離基線）、TEST-01（回歸測試從未運行）
- **P2 = 5**：SEC-02（登入無防爆破）、SEC-03（sample-data 公開真實數據）、DATA-02（archive 無 revision 守護）、OPS-01（dev server 跑生產）、TEST-02（新功能零覆蓋＋唯一綠燈測死代碼）
- **P3 = 12**：SEC-04、SEC-05、SEC-06、SEC-07、DATA-01、DATA-03、DATA-04、DATA-05、DATA-06、FE-05、FE-06、OPS-04
- **PASS 級正向核驗 = 8**：SEC-08（CSRF 全覆蓋）、SEC-09（穿越/上傳防護）、SEC-10（會話機制）、DATA-07（事務邊界）、DATA-08（級聯一致休眠）、DATA-09（審計 append-only）、DATA-10（d4c8a93 完整）、FE-01~04（esc/quick-add/競態/encode）、OPS-02/03/05（加固/備份/健康）

**修復順序建議**：
1. 立即（唔使改代碼）：生產改 `127.0.0.1` 綁定＋TLS 反代＋`COOKIE_SECURE=1`（先加 ProxyFix，SEC-07）；移走 sample-data.json 重建鏡像。
2. 一小時內：`tests/test_editor_regression.py:13` 改 `from app import db`＋修五個 201 → 8 測試全綠，設為部署門禁。
3. 本週：SEC-02 限速、DATA-02 archive revision、OPS-01 換 WSGI server。
4. 排期：其餘 P3 與 TEST-02 補測。

*審計方法與證據均可複現：git@d66cf97 工作副本；測試實驗於一次性 `python:3.12-slim` 容器（repo 以 `:ro` 掛載）執行，本倉除本報告外零寫入。*
