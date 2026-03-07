from typing import Optional

from controller.data_controller import register_product_failure
from data.const import MAX_PRODUCT_CREATE_ATTEMPTS
from utils.logging import log


def summarize_graph_errors(errors: list[dict]) -> str:
    parts: list[str] = []
    for err in errors:
        field = str(err.get("field") or "").strip() or "unknown"
        messages = err.get("messages") or []
        codes = [
            str(message.get("code") or "").strip()
            for message in messages
            if str(message.get("code") or "").strip()
        ]
        texts = [
            str(message.get("message") or "").strip()
            for message in messages
            if str(message.get("message") or "").strip()
        ]
        details: list[str] = []
        if codes:
            details.append(",".join(dict.fromkeys(codes)))
        if texts:
            details.append(" | ".join(dict.fromkeys(texts)))
        if details:
            parts.append(f"{field}: {'; '.join(details)}")
        else:
            parts.append(field)
    summary = " / ".join(parts)
    return summary[:500] if summary else "unknown"


def handle_retryable_product_failure(
    *,
    message_id: int,
    channel_id: Optional[int],
    failure_reason: str,
    detail_message: str,
    detail_level: str = "ERROR",
) -> tuple[int, bool]:
    log(detail_level, detail_message)
    attempts, skipped = register_product_failure(
        message_id,
        failure_reason=failure_reason,
        channel_id=channel_id,
    )
    if skipped:
        log(
            "WARN",
            "Пропускаю товар после лимита попыток. "
            f"message_id={message_id}. Попыток: {attempts}. Причина: {failure_reason}.",
        )
        return attempts, True
    retries_left = max(0, MAX_PRODUCT_CREATE_ATTEMPTS - attempts)
    log(
        "WARN",
        "Повторю этот товар позже. "
        f"message_id={message_id}. Осталось ретраев: {retries_left}. "
        f"Причина: {failure_reason}.",
    )
    return attempts, False
