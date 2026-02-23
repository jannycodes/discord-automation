from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .models import Ad, AdTarget, Channel, PLAN_LIMITS, PlanLimits, SendLog, SendStatus, Server, User


class LimitError(ValueError):
    """Raised when a plan limit is violated."""


class NotFoundError(ValueError):
    """Raised when an entity cannot be found."""


@dataclass(slots=True)
class InMemoryStore:
    users: dict[int, User] = field(default_factory=dict)
    servers: dict[int, Server] = field(default_factory=dict)
    channels: dict[int, Channel] = field(default_factory=dict)
    ads: dict[int, Ad] = field(default_factory=dict)
    ad_targets: list[AdTarget] = field(default_factory=list)
    send_logs: list[SendLog] = field(default_factory=list)

    _next_ad_id: int = 1

    def next_ad_id(self) -> int:
        ad_id = self._next_ad_id
        self._next_ad_id += 1
        return ad_id


class AdService:
    def __init__(self, store: InMemoryStore):
        self.store = store

    def _limits_for(self, user_id: int) -> PlanLimits:
        user = self.store.users.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return PLAN_LIMITS[user.plan]

    def _user_ads(self, user_id: int) -> Iterable[Ad]:
        return (ad for ad in self.store.ads.values() if ad.user_id == user_id)

    def create_ad(
        self,
        *,
        user_id: int,
        content: str,
        embed_json: str | None,
        interval_seconds: int,
        channel_ids: list[int],
    ) -> Ad:
        limits = self._limits_for(user_id)

        ads_count = sum(1 for _ in self._user_ads(user_id))
        if ads_count >= limits.max_ads:
            raise LimitError(f"Max ads reached: {limits.max_ads}")

        if interval_seconds < limits.min_interval_seconds:
            raise LimitError(
                f"Interval too short for plan: minimum {limits.min_interval_seconds} seconds"
            )

        if not channel_ids:
            raise ValueError("At least one target channel is required")

        server_ids = {self._channel(channel_id).server_id for channel_id in channel_ids}
        if len(server_ids) > limits.max_servers:
            raise LimitError(f"Max servers reached: {limits.max_servers}")

        ad = Ad(
            id=self.store.next_ad_id(),
            user_id=user_id,
            content=content,
            embed_json=embed_json,
            interval_seconds=interval_seconds,
            active=False,
            last_sent_at=None,
        )
        self.store.ads[ad.id] = ad
        self.store.ad_targets.extend(AdTarget(ad_id=ad.id, channel_id=channel_id) for channel_id in channel_ids)
        return ad

    def start_ad(self, ad_id: int) -> Ad:
        ad = self._ad(ad_id)
        ad.active = True
        return ad

    def pause_ad(self, ad_id: int) -> Ad:
        ad = self._ad(ad_id)
        ad.active = False
        return ad

    def delete_ad(self, ad_id: int) -> None:
        self._ad(ad_id)
        del self.store.ads[ad_id]
        self.store.ad_targets = [target for target in self.store.ad_targets if target.ad_id != ad_id]

    def record_log(
        self,
        *,
        ad_id: int,
        channel_id: int,
        status: SendStatus,
        timestamp: datetime,
        error: str | None,
        scheduled_for: datetime,
        attempt: int,
    ) -> None:
        self.store.send_logs.append(
            SendLog(
                ad_id=ad_id,
                channel_id=channel_id,
                timestamp=timestamp,
                status=status,
                error=error,
                scheduled_for=scheduled_for,
                attempt=attempt,
            )
        )

    def ad_targets(self, ad_id: int) -> list[Channel]:
        channel_ids = [target.channel_id for target in self.store.ad_targets if target.ad_id == ad_id]
        return [self._channel(channel_id) for channel_id in channel_ids]

    def due_ads(self, now: datetime) -> list[Ad]:
        due: list[Ad] = []
        for ad in self.store.ads.values():
            if not ad.active:
                continue
            if ad.last_sent_at is None:
                due.append(ad)
                continue
            elapsed = (now - ad.last_sent_at).total_seconds()
            if elapsed >= ad.interval_seconds:
                due.append(ad)
        return due

    def _ad(self, ad_id: int) -> Ad:
        ad = self.store.ads.get(ad_id)
        if ad is None:
            raise NotFoundError(f"Ad {ad_id} not found")
        return ad

    def _channel(self, channel_id: int) -> Channel:
        channel = self.store.channels.get(channel_id)
        if channel is None:
            raise NotFoundError(f"Channel {channel_id} not found")
        return channel
