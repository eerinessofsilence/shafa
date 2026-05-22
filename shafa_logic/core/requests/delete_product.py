def delete_product(product_id: str) -> None:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise ValueError("product_id is required")
    raise RuntimeError(
        "Удаление товара на Shafa пока не реализовано в API-слое. "
        "Передай свой delete_product_func в delete_old_telegram_products."
    )
