from __future__ import annotations

import json
import re
from typing import Iterable

from .util import clean_value, norm_text, now_iso

TYPE_LABELS = {
    "character": "人物",
    "faction": "势力",
    "nation": "国家",
    "region": "地区",
    "location": "地点",
    "item": "物品",
    "event": "事件",
    "rule": "规则",
    "term": "名词",
    "other": "其他",
}
TYPE_ORDER = list(TYPE_LABELS)

TYPE_ALIASES = {
    "人物": "character", "角色": "character", "npc": "character", "character": "character",
    "势力": "faction", "组织": "faction", "阵营": "faction", "faction": "faction",
    "国家": "nation", "国度": "nation", "王国": "nation", "帝国": "nation", "nation": "nation",
    "地区": "region", "区域": "region", "大陆": "region", "region": "region",
    "地点": "location", "场景": "location", "location": "location",
    "物品": "item", "道具": "item", "装备": "item", "item": "item",
    "事件": "event", "剧情": "event", "event": "event",
    "规则": "rule", "机制": "rule", "设定": "rule", "rule": "rule",
    "名词": "term", "术语": "term", "概念": "term", "term": "term",
    "其他": "other", "other": "other",
}


class PatchError(Exception):
    pass


def empty_canon() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "entities": {},
        "conflicts": {},
        "questions": {},
        "meta": {"conflict_seq": 0, "question_seq": 0},
    }


def normalize_type(value: object) -> str:
    text = norm_text(value)
    return TYPE_ALIASES.get(text, "other")


def entity_key(etype: str, name: str) -> str:
    return f"{etype}:{norm_text(name)}"


def find_key(canon: dict, name: str) -> str | None:
    target = norm_text(name)
    if not target:
        return None
    for key, ent in canon.get("entities", {}).items():
        if norm_text(ent.get("name")) == target:
            return key
        if any(norm_text(alias) == target for alias in ent.get("aliases", [])):
            return key
    return None


def _merge_sources(*groups: Iterable[int]) -> list[int]:
    result: set[int] = set()
    for group in groups:
        for value in group or []:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
    return sorted(result)


def _clean_sources(value: object, allowed: set[int]) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part for part in re.split(r"[,，\s]+", value) if part]
    elif not isinstance(value, (list, tuple, set)):
        value = [value]
    result: set[int] = set()
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number in allowed:
            result.add(number)
    return sorted(result)


def values_equal(left: str, right: str) -> bool:
    return norm_text(left) == norm_text(right)


def _find_open_conflict(canon: dict, key: str, field: str) -> dict | None:
    for conflict in canon.get("conflicts", {}).values():
        if (conflict.get("status") == "open"
                and conflict.get("key") == key
                and conflict.get("field") == field):
            return conflict
    return None


def _new_conflict(canon: dict, key: str, ent: dict, field: str,
                  values: list[dict], now: str) -> dict:
    seq = int(canon["meta"].get("conflict_seq", 0)) + 1
    canon["meta"]["conflict_seq"] = seq
    cid = f"C-{seq:02d}"
    conflict = {
        "id": cid,
        "key": key,
        "entity": ent["name"],
        "field": field,
        "values": values,
        "question": f"{ent['name']}的{field}应该取哪个值？",
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "resolved": None,
    }
    canon["conflicts"][cid] = conflict
    return conflict


def _add_field(canon: dict, key: str, ent: dict, field: str, value: str,
               sources: list[int], now: str, stats: dict) -> None:
    field = field.strip()[:80]
    if not field:
        return
    current = ent["fields"].get(field)
    if current is None:
        ent["fields"][field] = {
            "value": value,
            "sources": sources,
            "conflict_ids": [],
        }
        ent["updated_at"] = now
        stats["fields_added"] += 1
        return

    if values_equal(current["value"], value):
        current["sources"] = _merge_sources(current.get("sources", []), sources)
        return

    conflict = _find_open_conflict(canon, key, field)
    if conflict is None:
        conflict = _new_conflict(
            canon, key, ent, field,
            [
                {"value": current["value"], "sources": current.get("sources", [])},
                {"value": value, "sources": sources},
            ],
            now,
        )
        ids = current.setdefault("conflict_ids", [])
        if conflict["id"] not in ids:
            ids.append(conflict["id"])
        stats["conflicts_new"] += 1
        return

    matched = None
    for item in conflict["values"]:
        if values_equal(item["value"], value):
            matched = item
            break
    if matched is not None:
        matched["sources"] = _merge_sources(matched.get("sources", []), sources)
        stats["conflicts_extended"] += 1
    else:
        conflict["values"].append({"value": value, "sources": sources})
        stats["conflicts_extended"] += 1
    conflict["updated_at"] = now
    ids = current.setdefault("conflict_ids", [])
    if conflict["id"] not in ids:
        ids.append(conflict["id"])


def _as_field_map(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if name:
                    result[str(name)] = item.get("value")
        return result
    return {}


def apply_patch(canon: dict, patch: object, allowed_ids: set[int], now: str) -> dict:
    """把模型输出的 patch 合并进 canon。只接受 allowed_ids 里的来源编号。"""
    if not isinstance(patch, dict):
        raise PatchError("patch 不是 JSON 对象")

    canon.setdefault("entities", {})
    canon.setdefault("conflicts", {})
    canon.setdefault("questions", {})
    canon.setdefault("meta", {"conflict_seq": 0, "question_seq": 0})
    canon["meta"].setdefault("conflict_seq", 0)
    canon["meta"].setdefault("question_seq", 0)

    stats = {
        "added": 0,
        "updated": 0,
        "fields_added": 0,
        "conflicts_new": 0,
        "conflicts_extended": 0,
        "questions": 0,
        "dropped": 0,
    }

    entities = patch.get("entities") or []
    if isinstance(entities, dict):
        entities = list(entities.values())
    if not isinstance(entities, list):
        entities = []

    for raw in entities:
        if not isinstance(raw, dict):
            stats["dropped"] += 1
            continue
        etype = normalize_type(raw.get("type"))
        name = clean_value(raw.get("name"), 60)
        sources = _clean_sources(raw.get("source_ids") or raw.get("sources"), allowed_ids)
        if not name or not sources:
            stats["dropped"] += 1
            continue

        key = find_key(canon, name)
        is_new = key is None
        if is_new:
            key = entity_key(etype, name)
            suffix = 2
            while key in canon["entities"]:
                key = f"{entity_key(etype, name)}-{suffix}"
                suffix += 1
            canon["entities"][key] = {
                "type": etype,
                "name": name,
                "aliases": [],
                "fields": {},
                "relations": [],
                "sources": [],
                "created_at": now,
                "updated_at": now,
            }
            stats["added"] += 1
        else:
            stats["updated"] += 1

        ent = canon["entities"][key]
        ent["sources"] = _merge_sources(ent.get("sources", []), sources)
        ent["updated_at"] = now

        aliases = raw.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            alias = clean_value(alias, 60)
            if not alias:
                continue
            if find_key(canon, alias) not in (None, key):
                continue
            if alias != ent["name"] and alias not in ent["aliases"]:
                ent["aliases"].append(alias)

        for field, value in _as_field_map(raw.get("fields")).items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                cleaned = clean_value(item)
                if cleaned:
                    _add_field(canon, key, ent, str(field), cleaned, sources, now, stats)

        relations = raw.get("relations") or []
        if isinstance(relations, dict):
            relations = [relations]
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            target = clean_value(rel.get("to") or rel.get("target"), 60)
            kind = clean_value(rel.get("kind") or rel.get("type"), 40) or "关联"
            if not target:
                continue
            exists = any(
                norm_text(item.get("to")) == norm_text(target)
                and norm_text(item.get("kind")) == norm_text(kind)
                for item in ent["relations"]
            )
            if not exists:
                ent["relations"].append({
                    "to": target,
                    "kind": kind,
                    "sources": sources,
                })

    # 模型自己报告的同批冲突（不同消息说法不一致时，单靠字段合并发现不了）
    conflicts = patch.get("conflicts") or []
    if isinstance(conflicts, dict):
        conflicts = list(conflicts.values())
    if isinstance(conflicts, list):
        for raw in conflicts:
            if not isinstance(raw, dict):
                continue
            key = find_key(canon, raw.get("entity") or "")
            field = clean_value(raw.get("field"), 80)
            values = raw.get("values") or []
            if isinstance(values, str):
                values = [values]
            sources = _clean_sources(raw.get("source_ids"), allowed_ids)
            if not key or not field or len(values) < 2:
                continue
            ent = canon["entities"][key]
            for item in values:
                if isinstance(item, dict):
                    value_sources = _clean_sources(item.get("source_ids"), allowed_ids) or sources
                    item = item.get("value")
                else:
                    value_sources = sources
                cleaned = clean_value(item)
                if cleaned and value_sources:
                    _add_field(canon, key, ent, field, cleaned, value_sources, now, stats)
            conflict = _find_open_conflict(canon, key, field)
            if conflict is not None:
                question = clean_value(raw.get("question"), 200)
                if question:
                    conflict["question"] = question
                conflict["updated_at"] = now

    questions = patch.get("open_questions") or []
    if isinstance(questions, dict):
        questions = list(questions.values())
    if isinstance(questions, str):
        questions = [questions]
    existing = {norm_text(q.get("text")) for q in canon["questions"].values()}
    for raw in questions:
        if isinstance(raw, dict):
            text = clean_value(raw.get("text") or raw.get("question"), 300)
            sources = _clean_sources(raw.get("source_ids"), allowed_ids)
        else:
            text = clean_value(raw, 300)
            sources = []
        if not text or norm_text(text) in existing:
            continue
        seq = int(canon["meta"].get("question_seq", 0)) + 1
        canon["meta"]["question_seq"] = seq
        qid = f"Q-{seq:02d}"
        canon["questions"][qid] = {
            "id": qid,
            "text": text,
            "sources": sources,
            "status": "open",
            "created_at": now,
        }
        existing.add(norm_text(text))
        stats["questions"] += 1

    canon["updated_at"] = now
    return stats


def open_conflicts(canon: dict) -> list[dict]:
    return sorted(
        (c for c in canon.get("conflicts", {}).values() if c.get("status") == "open"),
        key=lambda c: c.get("id", ""),
    )


def open_questions(canon: dict) -> list[dict]:
    return sorted(
        (q for q in canon.get("questions", {}).values() if q.get("status") == "open"),
        key=lambda q: q.get("id", ""),
    )


def resolve_conflict(canon: dict, conflict_id: str, value: str, who: int, now: str) -> dict:
    cid = str(conflict_id or "").strip().upper()
    conflict = canon.get("conflicts", {}).get(cid)
    if conflict is None:
        raise ValueError(f"没有找到冲突 {cid}")
    if conflict.get("status") != "open":
        raise ValueError(f"{cid} 已经裁决过了")
    chosen = None
    for item in conflict.get("values", []):
        if values_equal(item.get("value", ""), value):
            chosen = item
            break
    if chosen is None:
        options = " / ".join(v.get("value", "") for v in conflict.get("values", []))
        raise ValueError(f"「{value}」不在 {cid} 的候选值里。可选：{options}")

    key = conflict.get("key")
    ent = canon.get("entities", {}).get(key)
    if ent is None:
        raise ValueError(f"{cid} 对应的实体已不存在，无法裁决")
    field = conflict["field"]
    current = ent["fields"].get(field, {})
    other_ids = [
        x for x in current.get("conflict_ids", [])
        if x != cid and canon.get("conflicts", {}).get(x, {}).get("status") == "open"
    ]
    if values_equal(current.get("value", ""), chosen["value"]):
        sources = current.get("sources", [])
    else:
        sources = chosen.get("sources", [])
    ent["fields"][field] = {
        "value": chosen["value"],
        "sources": _merge_sources(sources),
        "conflict_ids": other_ids,
    }
    ent["updated_at"] = now
    conflict["status"] = "resolved"
    conflict["updated_at"] = now
    conflict["resolved"] = {"value": chosen["value"], "by": int(who), "at": now}
    canon["updated_at"] = now
    return conflict


def search(canon: dict, query: str, limit: int = 5) -> list[str]:
    target = norm_text(query)
    if not target:
        return []
    scored: list[tuple[int, str]] = []
    for key, ent in canon.get("entities", {}).items():
        score = 0
        name = norm_text(ent.get("name"))
        if name == target:
            score = 100
        elif any(norm_text(a) == target for a in ent.get("aliases", [])):
            score = 90
        elif target in name:
            score = 70
        elif any(target in norm_text(a) for a in ent.get("aliases", [])):
            score = 60
        else:
            for value in ent.get("fields", {}).values():
                if target in norm_text(value.get("value")):
                    score = 40
                    break
        if score:
            scored.append((score, key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [key for _, key in scored[:limit]]


def remove_entity(canon: dict, key: str) -> dict | None:
    """删除一个条目，并清掉指向它的关系和冲突。调用方负责快照和保存。"""
    entities = canon.get("entities", {})
    ent = entities.get(key)
    if not ent:
        return None
    names = {norm_text(ent.get("name"))}
    names.update(norm_text(alias) for alias in ent.get("aliases", []))
    del entities[key]

    conflicts = canon.get("conflicts", {})
    for cid, conflict in list(conflicts.items()):
        if conflict.get("key") == key or norm_text(conflict.get("entity")) in names:
            del conflicts[cid]

    for other in entities.values():
        other["relations"] = [
            rel for rel in other.get("relations", [])
            if norm_text(rel.get("to")) not in names
        ]
    return ent


def add_question(canon: dict, text: str, sources: list[int] | None = None) -> dict:
    """手动加一条待定问题；不经过模型。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("待定内容为空")
    questions = canon.setdefault("questions", {})
    meta = canon.setdefault("meta", {})
    existing = []
    for qid in questions:
        if str(qid).upper().startswith("Q-"):
            try:
                existing.append(int(str(qid)[2:]))
            except ValueError:
                continue
    seq = max([int(meta.get("question_seq", 0)), *existing, 0]) + 1
    meta["question_seq"] = seq
    qid = f"Q-{seq:02d}"
    now = now_iso()
    question = {
        "id": qid,
        "text": text,
        "sources": sorted({int(s) for s in (sources or [])}),
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    questions[qid] = question
    canon["updated_at"] = now
    return question


def remove_question(canon: dict, question_id: str) -> dict | None:
    """手动删除一条待定问题；不经过模型。"""
    qid = str(question_id or "").strip().upper()
    questions = canon.get("questions", {})
    if qid in questions:
        removed = questions.pop(qid)
        canon["updated_at"] = now_iso()
        return removed
    return None


def _source_text(sources: Iterable[int]) -> str:
    values = sorted({int(s) for s in sources or []})
    return "、".join(f"#{s}" for s in values)


def render_card(canon: dict, key: str) -> str:
    ent = canon["entities"][key]
    label = TYPE_LABELS.get(ent.get("type"), "其他")
    lines = [f"【{label}】{ent['name']}"]
    if ent.get("aliases"):
        lines.append("别名：" + "、".join(ent["aliases"]))
    for field, item in ent.get("fields", {}).items():
        suffix = ""
        if item.get("conflict_ids"):
            suffix = " ⚠️ " + "、".join(item["conflict_ids"])
        source = _source_text(item.get("sources"))
        source_text = f"（{source}）" if source else ""
        lines.append(f"{field}：{item['value']}{source_text}{suffix}")
    for rel in ent.get("relations", []):
        source = _source_text(rel.get("sources"))
        source_text = f"（{source}）" if source else ""
        lines.append(f"关系：{rel['kind']} → {rel['to']}{source_text}")
    if ent.get("sources"):
        lines.append(f"来源：{_source_text(ent['sources'])}")
    return "\n".join(lines)


def render_full(canon: dict, group_id: int | None = None) -> str:
    entities = canon.get("entities", {})
    title = f"# 设定库 · 群 {group_id}" if group_id else "# 设定库"
    lines = [title, ""]
    lines.append(f"> 更新于 {canon.get('updated_at') or '（尚未整理）'} · 条目 {len(entities)}")
    lines.append("")

    for etype in TYPE_ORDER:
        group = [e for e in entities.values() if e.get("type") == etype]
        if not group:
            continue
        lines.append(f"## {TYPE_LABELS[etype]}")
        lines.append("")
        for ent in sorted(group, key=lambda e: e.get("name", "")):
            lines.append(f"### {ent['name']}")
            if ent.get("aliases"):
                lines.append(f"- 别名：{'、'.join(ent['aliases'])}")
            for field, item in ent.get("fields", {}).items():
                mark = ""
                if item.get("conflict_ids"):
                    mark = " ⚠️ " + "、".join(item["conflict_ids"])
                source = _source_text(item.get("sources"))
                source_text = f"（{source}）" if source else ""
                lines.append(f"- {field}：{item['value']}{source_text}{mark}")
            for rel in ent.get("relations", []):
                source = _source_text(rel.get("sources"))
                source_text = f"（{source}）" if source else ""
                lines.append(f"- 关系：{rel['kind']} → {rel['to']}{source_text}")
            lines.append("")

    conflicts = open_conflicts(canon)
    if conflicts:
        lines.append("## 待裁决")
        lines.append("")
        for c in conflicts:
            values = " / ".join(f"{v['value']}（{_source_text(v.get('sources'))}）"
                                for v in c.get("values", []))
            lines.append(f"- **{c['id']}** {c['entity']} · {c['field']}：{values}")
            if c.get("question"):
                lines.append(f"  - {c['question']}")
        lines.append("")

    questions = open_questions(canon)
    if questions:
        lines.append("## 待补完")
        lines.append("")
        for q in questions:
            suffix = f"（{_source_text(q.get('sources'))}）" if q.get("sources") else ""
            lines.append(f"- **{q['id']}** {q['text']}{suffix}")
        lines.append("")

    if not entities and not conflicts and not questions:
        lines.append("（空）")
    return "\n".join(lines).rstrip() + "\n"


def render_summary(stats: dict, canon: dict, remaining: int = 0) -> str:
    lines = [
        "📚 本轮整合完成",
        f"新增 {stats['added']} · 更新 {stats['updated']} · 新字段 {stats['fields_added']}"
        f" · 新冲突 {stats['conflicts_new']} · 待补 {stats['questions']}",
    ]
    if not any(stats.get(key, 0) for key in
               ("added", "updated", "fields_added", "conflicts_new", "questions")):
        return ("这一轮没有抽取到有效设定。可能是素材里没有明确事实，"
                "或者模型没有按格式输出；可以换个说法再试，或看 logs/bot.log。")
    conflicts = open_conflicts(canon)
    if conflicts:
        lines.append("")
        for c in conflicts[:3]:
            values = " / ".join(v["value"] for v in c.get("values", []))
            lines.append(f"⚠️ {c['id']} {c['entity']}·{c['field']}：{values}")
        if len(conflicts) > 3:
            lines.append(f"……还有 {len(conflicts) - 3} 条，发「待定」查看")
        lines.append("")
        first = conflicts[0]
        values = " / ".join(v["value"] for v in first.get("values", []))
        lines.append(f"回复「裁决 {first['id']} {first['values'][0]['value']}」定稿（可选：{values}）")
    if remaining:
        lines.append(f"还有 {remaining} 条未整合，继续发「整合」。")
    if stats["dropped"]:
        lines.append(f"另有 {stats['dropped']} 条素材缺少有效来源编号，被丢弃。")
    return "\n".join(lines)


def render_pending(canon: dict, limit: int = 10) -> str:
    conflicts = open_conflicts(canon)
    questions = open_questions(canon)
    if not conflicts and not questions:
        return "✅ 没有待裁决或待补完的事项。"
    lines = []
    if conflicts:
        lines.append(f"⚖️ 待裁决（{len(conflicts)}）")
        for c in conflicts[:limit]:
            values = " / ".join(f"{v['value']}（{_source_text(v.get('sources'))}）"
                                for v in c.get("values", []))
            lines.append(f"{c['id']} {c['entity']}·{c['field']}：{values}")
            if c.get("question"):
                lines.append(f"   {c['question']}")
        if len(conflicts) > limit:
            lines.append(f"……还有 {len(conflicts) - limit} 条")
    if questions:
        if lines:
            lines.append("")
        lines.append(f"❓ 待补完（{len(questions)}）")
        for q in questions[:limit]:
            suffix = f"（{_source_text(q.get('sources'))}）" if q.get("sources") else ""
            lines.append(f"{q['id']} {q['text']}{suffix}")
        if len(questions) > limit:
            lines.append(f"……还有 {len(questions) - limit} 条")
    return "\n".join(lines)


def canon_size(canon: dict) -> int:
    return len(json.dumps(canon, ensure_ascii=False))


def render_digest(canon: dict, max_chars: int = 10_000) -> str:
    """给聊天/评价用的紧凑摘要，不把整份 canon 塞给模型。"""
    entities = canon.get("entities", {})
    conflicts = open_conflicts(canon)
    questions = open_questions(canon)
    if not entities and not conflicts and not questions:
        return "（设定库还是空的）"

    counts: dict[str, int] = {}
    for ent in entities.values():
        etype = ent.get("type", "other")
        counts[etype] = counts.get(etype, 0) + 1

    lines: list[str] = []
    summary = "、".join(
        f"{TYPE_LABELS.get(etype, etype)} {counts[etype]}"
        for etype in TYPE_ORDER if counts.get(etype)
    )
    if summary:
        lines.append(f"共 {len(entities)} 个条目：{summary}")

    for etype in TYPE_ORDER:
        group = [e for e in entities.values() if e.get("type") == etype]
        for ent in sorted(group, key=lambda e: e.get("name", "")):
            fields = list(ent.get("fields", {}).items())[:4]
            desc = "；".join(
                f"{name}={item.get('value')}" for name, item in fields
            )
            line = f"[{TYPE_LABELS[etype]}] {ent.get('name')}"
            if ent.get("aliases"):
                line += f"（别名：{'、'.join(ent['aliases'])}）"
            if desc:
                line += f"：{desc}"
            if any(item.get("conflict_ids") for _, item in ent.get("fields", {}).items()):
                line += " ⚠有冲突"
            lines.append(line)

    if conflicts:
        lines.append("")
        lines.append("待裁决：")
        for conflict in conflicts[:8]:
            values = " / ".join(v.get("value", "") for v in conflict.get("values", []))
            lines.append(f"- {conflict['id']} {conflict['entity']}·{conflict['field']}：{values}")
        if len(conflicts) > 8:
            lines.append(f"- ……另有 {len(conflicts) - 8} 条")

    if questions:
        lines.append("")
        lines.append("待补完：")
        for question in questions[:6]:
            lines.append(f"- {question['text']}")
        if len(questions) > 6:
            lines.append(f"- ……另有 {len(questions) - 6} 条")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n……（设定库摘要已截断）"
    return text
