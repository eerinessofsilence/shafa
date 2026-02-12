import json
from typing import Optional

from data.const import API_URL
from main_no_playwright import (
    _base_headers,
    _get_csrftoken_from_cookies,
    _load_shafa_cookies,
    _request_json,
)
from utils.logging import log

MY_CLOTHES_PRODUCTS_FEED_QUERY = """
query WEB_MyClothesProductsFeed(
  $first: Int
  $after: String
  $orderBy: String
  $catalogSlug: String
  $productsType: ProfileProductTypeEnum
) {
  viewer {
    id
    products: viewerProducts(
      first: $first
      after: $after
      orderBy: $orderBy
      catalogSlug: $catalogSlug
      productsType: $productsType
    ) {
      edges {
        node {
          id
          ...productCardFeedData
          statusTitle
          isProcessingMultipleAction
          isOutOfStock
          promotion {
            promotionName
            validUntil
            __typename
          }
          freePushupAvailable
          fillRatio
          priceDeviation
          __typename
        }
        __typename
      }
      pageInfo {
        endCursor
        hasNextPage
        total
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment productCardFeedData on Product {
  id
  url
  thumbnail
  name
  price
  oldPrice
  statusTitle
  discountPercent
  ...productLikes
  brand {
    id
    name
    __typename
  }
  catalogSlug
  isNew
  sizes {
    id
    name
    __typename
  }
  size
  saleLabel {
    status
    date
    price
    __typename
  }
  seller {
    id
    __typename
  }
  freeDeliveryServices
  isUkrainian
  ownerHasRecentActivity
  tags
  rating
  ratingAmount
  isViewed
  createdAt
  sellingCondition
  collectionsTags
  sourceImport
  __typename
}

fragment productLikes on Product {
  likes
  isLiked
  __typename
}
"""


def get_my_clothes_products_feed(
    first: int = 16,
    order_by: str = "1",
    catalog_slug: str = "",
    products_type: str = "ACTIVE",
    after: Optional[str] = None,
) -> dict:
    if first < 1:
        raise ValueError("first must be >= 1")

    cookies = _load_shafa_cookies()
    if not cookies:
        log("ERROR", "No saved cookies. Log in via main.py first.")
        return {}

    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")

    payload = {
        "operationName": "WEB_MyClothesProductsFeed",
        "variables": {
            "catalogSlug": catalog_slug,
            "productsType": products_type,
            "first": first,
            "orderBy": order_by,
            "after": after,
        },
        "query": MY_CLOTHES_PRODUCTS_FEED_QUERY,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": "https://shafa.ua/uk/my/clothes",
    }

    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    errors = data.get("errors") or []
    if errors:
        log("ERROR", f"GraphQL errors: {errors}")
        return {"errors": errors}

    return data.get("data", {}).get("viewer", {}).get("products") or {}


def main() -> None:
    raw_cursor = input("after cursor (optional): ").strip()
    feed = get_my_clothes_products_feed(after=raw_cursor or None)
    if not feed:
        return

    errors = feed.get("errors") or []
    if errors:
        print(f"Feed errors: {errors}")
        return

    edges = feed.get("edges") or []
    page_info = feed.get("pageInfo") or {}
    total = page_info.get("total")
    has_next = page_info.get("hasNextPage")
    end_cursor = page_info.get("endCursor")
    print(f"Fetched: {len(edges)} | total: {total} | hasNextPage: {has_next}")
    if end_cursor:
        print(f"endCursor: {end_cursor}")


if __name__ == "__main__":
    main()
