"""服务保障业务规则：状态流转、字段校验与筛选口径都收在这里。

超期判断不在本文件另写一套，统一走 app.services.overdue 里的共用口径，
列表展示、动作拦截与统计汇总看到的结论因此始终一致。
"""
from __future__ import annotations

from typing import Any

from app.services.overdue import TERMINAL_STATUSES, evaluate_overdue, summarize_entries
from app.store import store

MODULE = "service"
REQUIRED_FIELDS = ["事项编号", "服务对象", "服务类别"]
OPTIONAL_FIELDS = ["响应时限", "受理人员", "完成时刻", "评价结果"]
STATUS_ORDER = ["待受理", "办理中", "已办结", "已退回"]
ACTION_RULES = {"受理事项": "办理中", "确认办结": "已办结", "退回事项": "已退回"}
NEGATIVE_ACTIONS = []
EMPTY_RESULT_NOTE = "当前筛选条件下没有服务事项，列表与超期统计按同一口径均为空"


class ServiceService:
    def _filtered(self, keyword: str | None, status: str | None) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("事项编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    @staticmethod
    def _available_actions(entry: dict[str, Any]) -> list[str]:
        """已办结、已退回的事项按同一口径不再提供可执行动作。"""
        if str(entry.get("status") or "").strip() in TERMINAL_STATUSES:
            return []
        return list(ACTION_RULES)

    def _annotate(self, row: dict[str, Any]) -> dict[str, Any]:
        """给列表行挂上超期结论与可执行动作；只读不改，原数据保持原样。"""
        verdict = evaluate_overdue(row)
        return {
            **row,
            "overdue": verdict["overdue"],
            "超期状态": verdict["label"],
            "超期说明": verdict["note"],
            "可执行动作": self._available_actions(row),
        }

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered(keyword, status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._annotate(row) for row in rows[start:start + size]], total

    def summarize(self, *, keyword: str | None = None, status: str | None = None) -> dict[str, int]:
        """统计汇总与列表走同一批筛选结果、同一份超期口径。"""
        return summarize_entries(self._filtered(keyword, status))

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._annotate(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["事项状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"服务事项 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于服务保障可执行范围"
        status = str(entry.get("status") or "").strip()
        if status in TERMINAL_STATUSES:
            return None, f"服务事项已处于「{status}」，按统一口径不再执行「{action}」"
        verdict = evaluate_overdue(entry)
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["事项状态"] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"服务事项已{action}"
        if verdict["overdue"]:
            message += f"（执行前{verdict['note']}）"
        return self._annotate(entry), message
