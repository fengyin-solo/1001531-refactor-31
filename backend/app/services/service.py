"""服务保障业务规则：状态流转、字段校验、筛选与超期口径都收在这里。

超期判定只有 :func:`evaluate_overdue` 一份实现，列表展示、动作拦截与
统计汇总都必须经它取得结论，避免各写一套导致口径漂移。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "service"
REQUIRED_FIELDS = ["事项编号", "服务对象", "服务类别"]
LIMIT_FIELD = "响应时限"
FINISH_FIELD = "完成时刻"
STATUS_ORDER = ["待受理", "办理中", "已办结", "已退回"]
ACTION_RULES = {"受理事项": "办理中", "确认办结": "已办结", "退回事项": "已退回"}
# 终态：历史已办结、已退回的事项不再追溯超期，避免新口径翻旧账。
CLOSED_STATUSES = {"已办结", "已退回"}
NEGATIVE_ACTIONS = []

# 展示/统计共用的口径说明，空结果与时限缺失都引用同一份措辞。
OVERDUE_NOTE = "已超过响应时限且尚未办结"
MISSING_LIMIT_NOTE = "响应时限缺失或无法识别，暂不判定超期"
CLOSED_NOTE = "事项已办结/退回，不再判定超期"
EMPTY_NOTE = "当前筛选条件下没有服务事项"
OVERDUE_BLOCK_NOTE = "该事项已超过响应时限，请先退回或走逾期处置，不能再受理"

_DEADLINE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)


def parse_deadline(value: Any) -> datetime | None:
    """把响应时限解析为可比较的时刻；解析不出来时返回 None（视为时限缺失）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def evaluate_overdue(
    entry: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """服务事项超期口径（全系统唯一一份）。

    规则：
    1. 已办结、已退回的终态事项一律不判超期 —— 历史数据不因新口径翻旧账；
    2. 响应时限缺失或无法解析时不判超期，说明里写明原因；
    3. 其余在办事项（待受理、办理中）以当前时刻与响应时限比较，时限已到即超期。

    返回 ``(是否超期, 说明)``，调用方不得再自行比较日期。
    """
    moment = now or datetime.now()
    status = str(entry.get("status") or "")
    if status in CLOSED_STATUSES:
        return False, CLOSED_NOTE
    deadline = parse_deadline(entry.get(LIMIT_FIELD))
    if deadline is None:
        return False, MISSING_LIMIT_NOTE
    if deadline < moment:
        return True, OVERDUE_NOTE
    return False, f"响应时限 {deadline.strftime('%Y-%m-%d %H:%M')} 前办结即可"


def serialize_entry(
    entry: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """给条目附上统一口径的超期标记与说明；列表和明细共用，不回写存量数据。"""
    serialized = dict(entry)
    overdue, note = evaluate_overdue(entry, now=now)
    serialized["超期"] = overdue
    serialized["时限说明"] = note
    return serialized


class ServiceService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("事项编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status)
        total = len(rows)
        # 同一页内用同一个“现在”，保证行标记与统计口径严格一致。
        moment = datetime.now()
        start = max(page - 1, 0) * size
        page_rows = [serialize_entry(row, now=moment) for row in rows[start:start + size]]
        return page_rows, total

    def summarize(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> dict[str, int]:
        """统计汇总：待受理、办理中、超期未办结全部来自同一过滤集、同一口径。"""
        rows = self._filter_rows(keyword=keyword, status=status)
        moment = datetime.now()
        return {
            "待受理事项": sum(1 for row in rows if row.get("status") == "待受理"),
            "办理中事项": sum(1 for row in rows if row.get("status") == "办理中"),
            "超时未办结": sum(1 for row in rows if evaluate_overdue(row, now=moment)[0]),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return serialize_entry(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + [LIMIT_FIELD, "受理人员"]:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return serialize_entry(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"服务事项 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于服务保障可执行范围"

        # 动作拦截与列表展示同用 evaluate_overdue：在办事项一旦超期即拦下受理。
        overdue, note = evaluate_overdue(entry)
        if action == "受理事项" and overdue:
            return None, OVERDUE_BLOCK_NOTE

        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target not in CLOSED_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "确认办结":
            entry[FINISH_FIELD] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result = serialize_entry(entry)
        if action == "确认办结" and note == OVERDUE_NOTE:
            return result, "服务事项已确认办结；该事项办理期间已超期，已如实标注"
        return result, f"服务事项已{action}"
