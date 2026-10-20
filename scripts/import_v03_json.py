#!/usr/bin/env python3
"""Non-destructive, review-first importer for an explicitly exported V0.3 state JSON.

This is not a direct live-SQLite migration. Export/backup the source first, inspect the report,
then run this importer against the isolated V0.4.1 database.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, date, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app, db, init_database  # noqa: E402
from models import (  # noqa: E402
    Project, EventSession, WorkPackage, RequirementItem, Task, TimeNode,
    Client, Contact, Supplier, Venue, VenueSpace, VenueEquipment,
    ChangeRequest, AuditLog, new_id, utcnow,
)
from sqlalchemy import select

TZ = ZoneInfo("Asia/Shanghai")


def parse_dt(value, end_of_day=False):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(raw)
        except ValueError:
            try:
                d = date.fromisoformat(raw[:10])
                result = datetime.combine(d, time(23, 59) if end_of_day else time.min)
            except ValueError:
                return None
    return result.replace(tzinfo=TZ) if result.tzinfo is None else result


def phase_from_old(status):
    value = str(status or "")
    if any(x in value for x in ("归档", "已完成", "完成验收")): return "已完成"
    if any(x in value for x in ("取消", "作废")): return "已取消"
    if any(x in value for x in ("收尾", "已交", "等下一步")): return "收尾"
    if any(x in value for x in ("现场", "执行中")): return "现场执行"
    if any(x in value for x in ("筹备", "待制作", "制作中", "待确认")): return "筹备执行"
    return "新登记"


def requirement_status(old):
    value = str(old or "")
    if "验收" in value or "已完成" in value: return "已验收"
    if "已交付" in value or "已交" in value: return "已交付"
    if "已确认" in value: return "已确认"
    if "待确认" in value or "等待资料" in value: return "待确认"
    return "待澄清"


def task_status(old):
    value = str(old or "")
    if "完成" in value: return "已完成"
    if "阻塞" in value or "卡住" in value: return "阻塞"
    if "制作中" in value or "进行中" in value: return "进行中"
    if "确认" in value or "验收" in value: return "待确认/待验收"
    return "待办"


def unwrap_state(value):
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        value = value["data"]
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象")
    if "events" not in value and isinstance(value.get("state"), dict):
        value = value["state"]
    return value


def main():
    parser = argparse.ArgumentParser(description="Import an exported V0.3 JSON into the normalized V0.4.1 schema")
    parser.add_argument("json_file", help="Path to a manually exported V0.3 JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print counts without writing")
    parser.add_argument("--allow-nonempty", action="store_true", help="Allow importing into a DB that already has projects")
    args = parser.parse_args()
    path = Path(args.json_file)
    if not path.is_file():
        parser.error(f"文件不存在：{path}")
    try:
        state = unwrap_state(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        parser.error(f"无法读取 JSON：{exc}")
    events = state.get("events", []) or []
    old_tasks = state.get("tasks", []) or []
    packages = state.get("workPackages", state.get("work_packages", [])) or []
    suppliers = state.get("suppliers", []) or []
    venues = state.get("venues", []) or []
    assets = state.get("assets", []) or []
    print("V0.3 JSON import preview")
    print(f"  events -> projects/sessions: {len(events)}")
    print(f"  work packages: {len(packages)}")
    print(f"  legacy task/material rows -> requirement + review task: {len(old_tasks)}")
    print(f"  suppliers: {len(suppliers)} | venues: {len(venues)} | assets/equipment: {len(assets)}")
    if args.dry_run:
        print("DRY RUN: no database writes performed")
        return 0

    app = create_app()
    with app.app_context():
        init_database(app, seed_demo=False)
        existing = db.session.scalar(select(Project.id).limit(1))
        if existing and not args.allow_nonempty:
            raise SystemExit("目标数据库已有项目。为防止误混数据，默认拒绝导入；确认后显式添加 --allow-nonempty。")
        project_by_old_event = {}
        package_by_old_id = {}
        supplier_by_old_id = {}
        client_by_name = {}
        venue_by_old_id = {}
        space_by_old_id = {}
        created = {"projects":0,"sessions":0,"packages":0,"requirements":0,"tasks":0,"time_nodes":0,"clients":0,"suppliers":0,"venues":0,"spaces":0,"equipment":0}

        for old in suppliers:
            old_id = str(old.get("id") or new_id())
            obj = Supplier(name=str(old.get("name") or "旧版供应商（待核）"),
                           service_category=str(old.get("serviceCategory") or old.get("service_category") or ""),
                           notes="[V0.3 导入] " + str(old.get("notes") or ""))
            db.session.add(obj); db.session.flush(); supplier_by_old_id[old_id] = obj.id; created["suppliers"] += 1

        for old in venues:
            old_id = str(old.get("id") or new_id())
            venue = Venue(name=str(old.get("name") or "旧版场地（待核）"), address=str(old.get("address") or ""),
                          notes="[V0.3 导入] " + str(old.get("notes") or ""), verified_status="待核实")
            db.session.add(venue); db.session.flush(); venue_by_old_id[old_id] = venue.id; created["venues"] += 1
            if any(old.get(k) for k in ("building", "floor", "room")):
                parent = None
                for label, name in (("楼栋", old.get("building")), ("楼层", old.get("floor")), ("厅室", old.get("room"))):
                    if not name: continue
                    space = VenueSpace(venue_id=venue.id, parent_space_id=parent, name=str(name), space_type=label,
                                       floor_label=str(name) if label == "楼层" else "", details="[V0.3 导入] 原始空间层级字段待核实", verified_status="待核实")
                    db.session.add(space); db.session.flush(); parent=space.id; created["spaces"] += 1
                space_by_old_id[old_id] = parent

        for old in assets:
            name = str(old.get("name") or "旧版设备/资产（待核）")
            obj = VenueEquipment(name=name, category=str(old.get("category") or ""),
                ownership="场地固定" if old.get("fixed") else "自有资产", physical_dimensions=str(old.get("dimensions") or ""),
                source_text=json.dumps(old, ensure_ascii=False), verified_status="待核实")
            db.session.add(obj); created["equipment"] += 1

        for old in events:
            old_id = str(old.get("id") or new_id())
            name = str(old.get("title") or old.get("name") or "旧版未命名项目（待核）")
            client_name = str(old.get("client") or old.get("clientName") or "").strip()
            client_id = None
            if client_name:
                if client_name not in client_by_name:
                    client = Client(name=client_name, notes="[V0.3 导入] 由旧记录自动建立，需核实")
                    db.session.add(client); db.session.flush(); client_by_name[client_name] = client.id; created["clients"] += 1
                client_id = client_by_name[client_name]
            owners = old.get("owners") or []
            project = Project(name=name, client_id=client_id, client_snapshot=client_name,
                owner="、".join(map(str, owners)) if isinstance(owners, list) else str(owners),
                phase=phase_from_old(old.get("status")), description="[V0.3 导入] " + str(old.get("notes") or ""))
            db.session.add(project); db.session.flush(); project_by_old_event[old_id] = project.id; created["projects"] += 1
            start = parse_dt(old.get("startDate") or old.get("starts_at"))
            end = parse_dt(old.get("endDate") or old.get("ends_at"), end_of_day=True)
            mode = str(old.get("dateMode") or old.get("date_mode") or ("fixed" if start else "undated"))
            if mode in {"window", "alternatives"}:
                s = EventSession(project_id=project.id, title=name, date_mode="window", window_start=start, window_end=end,
                    location_text=str(old.get("place") or ""), status="日期窗口", notes="[V0.3 导入] 原始择日/备选日期，需人工核实")
                db.session.add(s); created["sessions"] += 1
            elif start:
                s = EventSession(project_id=project.id, title=name, starts_at=start, ends_at=end, date_mode="fixed",
                    location_text=str(old.get("place") or ""), status="暂定" if "待" in str(old.get("status") or "") else "已确认",
                    notes="[V0.3 导入] " + str(old.get("notes") or ""))
                db.session.add(s); created["sessions"] += 1

        # Legacy work packages are preserved as packages, with supplier association when known.
        for old in packages:
            old_id = str(old.get("id") or new_id())
            event_id = str(old.get("eventId") or old.get("event_id") or "")
            project_id = project_by_old_event.get(event_id)
            if not project_id:
                continue
            supplier_id = supplier_by_old_id.get(str(old.get("supplierId") or old.get("supplier_id") or ""))
            obj = WorkPackage(project_id=project_id, supplier_id=supplier_id,
                name=str(old.get("name") or "旧版工作包（待核）"), status=str(old.get("status") or "待指派"),
                description="[V0.3 导入] " + str(old.get("description") or old.get("notes") or ""),
                contact_snapshot=str(old.get("contact") or old.get("contactName") or ""),
                responsibility=str(old.get("responsibility") or ""), acceptance_criteria=str(old.get("acceptanceCriteria") or ""),
                planned_entry_at=parse_dt(old.get("plannedEntryAt") or old.get("planned_entry_at")),
                planned_strike_at=parse_dt(old.get("plannedStrikeAt") or old.get("planned_strike_at")))
            db.session.add(obj); db.session.flush(); package_by_old_id[old_id] = obj.id; created["packages"] += 1

        orphan_project = None
        for old in old_tasks:
            old_id = str(old.get("id") or new_id())
            event_id = str(old.get("eventId") or old.get("event_id") or "")
            project_id = project_by_old_event.get(event_id)
            if not project_id:
                if not orphan_project:
                    orphan_project = Project(name="旧版未关联事项（迁移待核）", phase="新登记",
                        description="[V0.3 导入] 旧版记录没有关联到可识别的活动；请人工归属。")
                    db.session.add(orphan_project); db.session.flush(); created["projects"] += 1
                project_id = orphan_project.id
            package_id = package_by_old_id.get(str(old.get("workPackageId") or old.get("work_package_id") or ""))
            name = str(old.get("name") or old.get("title") or "旧版事项（待核）")
            source = json.dumps(old, ensure_ascii=False, sort_keys=True)
            req = RequirementItem(project_id=project_id, work_package_id=package_id, name=name,
                source_text=source, specification=str(old.get("spec") or old.get("specification") or ""),
                quantity_text=str(old.get("quantity") or ""), intended_use=str(old.get("intendedUse") or ""),
                location_text=str(old.get("location") or ""), owner=str(old.get("owner") or ""),
                status=requirement_status(old.get("status")), acceptance_criteria=str(old.get("acceptanceCriteria") or ""))
            db.session.add(req); created["requirements"] += 1
            due = parse_dt(old.get("dueDate") or old.get("due_at"), end_of_day=True)
            task = Task(project_id=project_id, work_package_id=package_id, name=f"迁移复核：{name}", source_text=source,
                status="待办", owner=str(old.get("owner") or ""), responsible_party=str(old.get("contact") or ""), due_at=due,
                notes="旧版将物料/事项与执行任务混在同一条记录中。请核对后拆分为正确的需求项与执行任务。\n"
                      + "旧版状态：" + str(old.get("status") or "未记录") + "；旧版依赖：" + str(old.get("dependency") or "未记录"),
                needs_review=True)
            db.session.add(task); created["tasks"] += 1

        # Keep a source-level audit marker so the import can be traced without treating it as production truth.
        db.session.add(AuditLog(actor="system-import", action="import_v03_json", entity_type="", entity_id="",
            before_json=None, after_json=created, source_ref=str(path.name)))
        db.session.commit()
        print("IMPORT PASS — source JSON was imported into normalized records; review flags are intentional.")
        for key, value in created.items(): print(f"  {key}: {value}")
        print("Important: this does not copy attachment binaries or import the live SQLite WAL database. Use the separate backup/restore procedure for production migration.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
