"""服务事项超期口径：页面展示、动作拦截与统计汇总共用的同一份判断。

「什么叫超期」只在这里定义，别处一律调用，不再各自重写：

- 已办结、已退回的事项不再参与超期判断，历史办结事项不会被新口径标成超期；
- 响应时限缺失或写法认不出来时不算超期，但要给出一句说明，空结果也照此办理；
- 其余事项按「当前时刻晚于响应时限」判定超期；只写日期的时限宽限到当日 23:59:59。
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Iterable, Mapping

TERMINAL_STATUSES = ("已办结", "已退回")

DATE_ONLY_FORMATS = ("%Y-%m-%d", "%Y/%m/%d")
DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


def parse_deadline(raw: Any) -> datetime | None:
    """把响应时限解析成具体时刻；缺失或认不出来的写法一律按未设置处理。"""
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    for fmt in DATE_ONLY_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return datetime.combine(parsed.date(), time(23, 59, 59))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ":" not in text:
        parsed = datetime.combine(parsed.date(), time(23, 59, 59))
    return parsed


def evaluate_overdue(entry: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """对一条服务事项给出超期结论：机器标记、短标签与一句人类可读的说明。"""
    now = now or datetime.now()
    status = str(entry.get("status") or "").strip()
    if status in TERMINAL_STATUSES:
        return {
            "overdue": False,
            "label": "不判超期",
            "note": f"事项已处于「{status}」，按统一口径不再参与超期判断",
            "deadline": None,
        }
    deadline = parse_deadline(entry.get("响应时限"))
    if deadline is None:
        return {
            "overdue": False,
            "label": "未设时限",
            "note": "未设置可识别的响应时限，按统一口径不参与超期判断",
            "deadline": None,
        }
    deadline_text = deadline.isoformat(sep=" ", timespec="minutes")
    if now > deadline:
        return {
            "overdue": True,
            "label": "已超期",
            "note": f"已超过响应时限 {(now - deadline).days} 天",
            "deadline": deadline_text,
        }
    return {
        "overdue": False,
        "label": "时限内",
        "note": f"距响应时限还有 {(deadline - now).days} 天",
        "deadline": deadline_text,
    }


def summarize_entries(
    rows: Iterable[Mapping[str, Any]], *, now: datetime | None = None
) -> dict[str, int]:
    """统计汇总与列表、动作用同一份口径数超期，保证条数与事项状态对得上。"""
    moment = now or datetime.now()
    summary = {"待受理事项": 0, "办理中事项": 0, "超时未办结": 0}
    for row in rows:
        status = str(row.get("status") or "").strip()
        if status == "待受理":
            summary["待受理事项"] += 1
        elif status == "办理中":
            summary["办理中事项"] += 1
        if evaluate_overdue(row, now=moment)["overdue"]:
            summary["超时未办结"] += 1
    return summary
