from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class AdMetricRecord:
    platform: str
    date: date
    campaign_id: str | None
    campaign_name: str | None
    adset_id: str | None
    adset_name: str | None
    ad_id: str | None
    ad_name: str | None
    spend: float
    impressions: int
    clicks: int
    link_clicks: int | None
    reach: int | None
    frequency: float | None
    purchases: float
    revenue_rep: float


class AdPlatformConnector(ABC):
    """Meta now; Google Ads later. Both implement this."""

    @abstractmethod
    def fetch_ad_metrics(
        self, brand_id: str, creds: dict, start: date, end: date
    ) -> list[AdMetricRecord]: ...


@dataclass
class OrderRecord:
    order_id: str
    created_at: str          # ISO-8601 string
    gross_value: float
    payment_method: str      # 'cod' | 'prepaid'
    status: str              # 'confirmed' | 'delivered' | 'cancelled' | 'returned'
    items: list[dict]        # [{product_id, quantity, unit_price}]


class EcommerceConnector(ABC):
    """Shopify now; other platforms later."""

    @abstractmethod
    def fetch_orders(
        self, brand_id: str, creds: dict, start: date, end: date
    ) -> list[OrderRecord]: ...

    @abstractmethod
    def fetch_products(self, brand_id: str, creds: dict) -> list[dict]: ...
