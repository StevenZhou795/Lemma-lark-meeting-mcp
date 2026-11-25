"""Prepare official Lark MCP create/update bodies from local metadata.

No network calls. The AI extracts tasks; this script only validates field mappings.
"""
import argparse
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UTC8 = timezone(timedelta(hours=8))


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(v.get("text", "") for v in value if isinstance(v, dict))
    return ""


def normal_text(value):
    return re.sub(r"\s+", " ", text_value(value)).strip()


def date_value(value):
    if value is None:
        return None
    require(isinstance(value, str), "deadline 必须是 ISO 日期/日期时间或 null")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        date = datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), time(), UTC8)
    else:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(date.tzinfo is not None, "日期时间必须带时区，不使用电脑的时区")
    return int(date.timestamp() * 1000)


def option_names(field):
    return {o["name"] for o in (field.get("property") or {}).get("options", [])}


def label_value(field, value):
    require(value in option_names(field), f"{field['field_name']} 没有该标签：{value}")
    return [value] if field["type"] == 4 else value


def owner_values(task, mapping, field):
    candidates = task.get("owner_candidates")
    if candidates is None:
        candidates = [task.get("owner_candidate")]
    require(isinstance(candidates, list) and bool(candidates), "缺少负责人候选列表")
    aliases = mapping.get("owner_aliases", {})
    resolved = []
    for candidate in candidates:
        require(isinstance(candidate, str) and bool(candidate.strip()), "负责人候选必须是非空姓名")
        name, visited = candidate, set()
        while name in aliases:
            require(name not in visited, "负责人别名映射存在循环")
            visited.add(name)
            name = aliases[name]
            require(isinstance(name, str) and bool(name.strip()), "负责人别名目标必须是非空姓名")
        owner = mapping.get("owners", {}).get(name)
        require(owner and owner.get("verified") is True, f"负责人身份未核实：{candidate}")
        value = owner.get("value")
        if field["type"] == 11:
            require(isinstance(value, str) and value.startswith("ou_"), f"人员字段需要本应用下的 open_id：{candidate}")
        else:
            require(value in option_names(field), f"{field['field_name']} 没有该人员标签：{value}")
        if value not in resolved:
            resolved.append(value)
    if field["type"] == 11:
        require((field.get("property") or {}).get("multiple") is not False or len(resolved) == 1,
                "当前人员字段不支持多位负责人")
        return [{"id": value} for value in resolved]
    if field["type"] == 4:
        return resolved
    require(len(resolved) == 1, "单选负责人字段不能写入多位负责人")
    return resolved[0]


def canonical(value, field):
    kind = field["type"]
    if kind == 1:
        return normal_text(value)
    if kind == 11:
        return sorted(v["id"] for v in (value or []))
    if kind == 4:
        return sorted(value or [])
    if kind == 5:
        return int(value) if value is not None else None
    return value


def prepare(args):
    target = load(ROOT / "target.json")
    drafts = load(ROOT / "task-drafts.json")
    mapping = load(args.mapping)
    schema = load(args.schema)
    existing = load(args.existing)
    for snapshot in (schema, existing):
        require(snapshot.get("complete") is True, "快照必须确认所有分页已读取，并标记 complete=true")
        for key in ("app_token", "table_id"):
            require(snapshot.get(key) == target[key], f"快照目标 {key} 与 target.json 不一致")
    require(isinstance(schema.get("fields"), list), "schema.json 需要 fields 数组")
    require(isinstance(existing.get("records"), list), "existing-records.json 需要 records 数组")
    by_id = {f["field_id"]: f for f in schema["fields"]}
    fields = {}
    expected_types = {"task": {1}, "owner": {3, 4, 11}, "priority": {3, 4}, "deadline": {5}, "project": {3, 4}}
    for role, types in expected_types.items():
        field = by_id.get(mapping.get("fields", {}).get(role))
        require(field is not None, f"未映射真实字段 ID：{role}")
        require(field["type"] in types, f"{role} 字段类型不支持：{field['type']}")
        fields[role] = field
    require(len({f['field_id'] for f in fields.values()}) == len(expected_types), "各字段必须分别映射，不能复用字段 ID")
    project_options_to_create = mapping.get("project_options_to_create", [])
    require(isinstance(project_options_to_create, list) and all(isinstance(value, str) and value.strip() for value in project_options_to_create),
            "project_options_to_create 必须是明确允许新增的 Project 标签名称数组")
    allowed_new_projects = set(project_options_to_create)
    start_date_policy = mapping.get("start_date_policy", "omit")
    require(start_date_policy in {"omit", "processing_day"}, "start_date_policy 仅支持 omit 或 processing_day")
    start_field = None
    if start_date_policy == "processing_day":
        start_field = by_id.get(mapping.get("fields", {}).get("start_date"))
        require(start_field is not None and start_field["type"] == 5, "以后启用处理当天日期时，需要映射真实 start_date 日期字段")
        require(start_field["field_id"] not in {f["field_id"] for f in fields.values()}, "start_date 不能与其他字段映射相同")
    selected = mapping.get("selected_task_ids", [])
    require(isinstance(selected, list) and bool(selected), "请先选定本次任务 selected_task_ids")
    require(len(selected) == len(set(selected)), "selected_task_ids 包含重复 ID")
    by_task = {task["id"]: task for task in drafts["tasks"]}
    require(all(t in by_task for t in selected), "所选任务 ID 不在草稿中")
    records, updates, skipped, blocked, source_ids, update_source_ids = [], [], [], [], [], []
    new_project_options, processed_update_ids = set(), set()
    by_record_id = {r["record_id"]: r for r in existing["records"] if r.get("record_id")}
    existing_rows = [r.get("fields", {}) for r in existing["records"]]
    seen = list(existing_rows)
    for task_id in selected:
        draft = by_task[task_id]
        task = {**draft, **mapping.get("task_overrides", {}).get(task_id, {})}
        try:
            require(task.get("decision_status") == "action", "原文仅是建议/待决议，需要先确定是否成为任务")
            require(draft.get("evidence"), "缺少原文证据")
            title = task.get("task", "").strip()
            require(bool(title), "任务文字为空")
            record_id = task.get("record_id")
            mapped_record_id = mapping.get("existing_record_ids", {}).get(task_id)
            updating = record_id is not None or mapped_record_id is not None
            if updating:
                require(mapping.get("allow_update_existing_records") is True, "更新已有记录需要 allow_update_existing_records=true")
                require(isinstance(record_id, str) and bool(record_id) and record_id == mapped_record_id,
                        "草稿 record_id 必须与 existing_record_ids 中本任务的记录 ID 完全一致")
                require(record_id in by_record_id, "待更新的记录 ID 不在完整快照中")
                require(record_id not in processed_update_ids, "本批多个任务指向同一更新记录，需先合并")
            owner_field = fields["owner"]
            owner_value = owner_values(task, mapping, owner_field)
            priority = mapping.get("priorities", {}).get(task.get("priority_suggestion"))
            require(isinstance(priority, str) and bool(priority), "未映射 priority 建议到真实标签")
            project = task.get("project")
            require(isinstance(project, str) and bool(project.strip()), "缺少明确的 Project 分组")
            project = mapping.get("projects", {}).get(project, project)
            require(isinstance(project, str) and bool(project.strip()), "Project 映射必须是非空标签名称")
            project_field = fields["project"]
            new_project = project not in option_names(project_field)
            require(not new_project or project in allowed_new_projects,
                    f"Project 没有该标签且未明确允许创建：{project}")
            values = {
                fields["task"]["field_name"]: title,
                owner_field["field_name"]: owner_value,
                fields["priority"]["field_name"]: label_value(fields["priority"], priority),
                project_field["field_name"]: [project] if project_field["type"] == 4 else project,
            }
            deadline = date_value(task.get("deadline"))
            if deadline is not None:
                values[fields["deadline"]["field_name"]] = deadline
            if updating:
                current = by_record_id[record_id].get("fields", {})
                processed_update_ids.add(record_id)
                # Compare only supplied fields: an unknown deadline never clears one.
                equal = all(canonical(current.get(f["field_name"]), f) == canonical(values[f["field_name"]], f)
                            for f in fields.values() if f["field_name"] in values)
                if equal:
                    skipped.append({"id": task_id, "record_id": record_id, "reason": "所选字段已与目标更新记录一致"})
                    continue
                updates.append({"record_id": record_id, "fields": values})
                update_source_ids.append(task_id)
                if new_project:
                    new_project_options.add(project)
                # Reflect this scheduled update in the in-memory duplicate lookup.
                current.update(values)
                continue
            matches = [r for r in seen if normal_text(r.get(fields["task"]["field_name"])) == normal_text(title)]
            if matches:
                equivalent = any(all(canonical(r.get(f["field_name"]), f) == canonical(values.get(f["field_name"]), f) for f in fields.values()) for r in matches)
                if equivalent:
                    skipped.append({"id": task_id, "reason": "所选字段与快照或本批已有记录一致"})
                else:
                    blocked.append({"id": task_id, "reason": "已有同名任务但字段不同，需人工判断，不自动覆盖或追加"})
                continue
            if start_field is not None:
                values[start_field["field_name"]] = date_value(datetime.now(UTC8).date().isoformat())
            records.append({"fields": values})
            source_ids.append(task_id)
            seen.append(values)
            if new_project:
                new_project_options.add(project)
        except (ValueError, TypeError) as error:
            blocked.append({"id": task_id, "reason": str(error)})
    require(len(records) + len(updates) <= 100, "请将新增和更新合计分成每批不超过 100 条，再生成 payload")
    return {
        "status": "local_payload_only_not_written",
        "path": {k: target[k] for k in ("app_token", "table_id")},
        "params": {"user_id_type": "open_id"},
        "body": {"records": records},
        "source_task_ids": source_ids,
        "update_body": {"records": updates},
        "update_source_task_ids": update_source_ids,
        "new_project_options": sorted(new_project_options),
        "skipped": skipped,
        "blocked": blocked,
        "warning": "精确查重不等于语义查重；写入前刷新完整快照，写入后读回核对。",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--existing", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        payload = prepare(args)
        # Exclusive create prevents accidental overwrite of an earlier import receipt/payload.
        with Path(args.output).open("x", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
        print(f"仅本地生成：可新增 {len(payload['body']['records'])}，可更新 {len(payload['update_body']['records'])}，重复/无需更新 {len(payload['skipped'])}，待处理 {len(payload['blocked'])}")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"未生成 payload：{error}\n")


if __name__ == "__main__":
    main()
