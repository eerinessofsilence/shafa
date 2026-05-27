import threading


_PRODUCT_PIPELINE_GUARD = threading.Lock()
_PRODUCT_PIPELINE_SERIAL_LOCK = threading.Lock()
_PRODUCT_PIPELINE_ACTIVE_COUNT = 0


def enter_product_pipeline() -> None:
    global _PRODUCT_PIPELINE_ACTIVE_COUNT
    _PRODUCT_PIPELINE_SERIAL_LOCK.acquire()
    with _PRODUCT_PIPELINE_GUARD:
        _PRODUCT_PIPELINE_ACTIVE_COUNT += 1


def exit_product_pipeline() -> None:
    global _PRODUCT_PIPELINE_ACTIVE_COUNT
    with _PRODUCT_PIPELINE_GUARD:
        _PRODUCT_PIPELINE_ACTIVE_COUNT = max(0, _PRODUCT_PIPELINE_ACTIVE_COUNT - 1)
    _PRODUCT_PIPELINE_SERIAL_LOCK.release()


def is_product_pipeline_active() -> bool:
    with _PRODUCT_PIPELINE_GUARD:
        return _PRODUCT_PIPELINE_ACTIVE_COUNT > 0
