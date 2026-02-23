from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from .models import PendingRetry, SchedulerResult, SendStatus
from .service import AdService


class DiscordSender(Protocol):
    def send(self, *, channel_id: str, content: str, embed_json: str | None) -> None:
        """Send a message to Discord. Raise an exception on failure."""


@dataclass(slots=True)
class Scheduler:
    service: AdService
    sender: DiscordSender
    retry_base_seconds: int = 60
    max_retries: int = 3
    _pending_retries: list[PendingRetry] = field(default_factory=list)
    _idempotency_keys: set[tuple[int, int, datetime]] = field(default_factory=set)

    def tick(self, now: datetime) -> SchedulerResult:
        result = SchedulerResult()
        for ad in self.service.due_ads(now):
            result.processed_ads += 1
            self._process_ad_send(ad_id=ad.id, scheduled_for=now, attempt=1, now=now, result=result)
            ad.last_sent_at = now

        self._process_retries(now=now, result=result)
        return result

    def _process_ad_send(
        self,
        *,
        ad_id: int,
        scheduled_for: datetime,
        attempt: int,
        now: datetime,
        result: SchedulerResult,
    ) -> None:
        ad = self.service.store.ads[ad_id]
        for channel in self.service.ad_targets(ad_id):
            key = (ad_id, channel.id, scheduled_for)
            if key in self._idempotency_keys:
                result.skipped += 1
                result.messages.append(
                    f"Skipped duplicate send for ad={ad_id}, channel={channel.id}, run={scheduled_for.isoformat()}"
                )
                self.service.record_log(
                    ad_id=ad_id,
                    channel_id=channel.id,
                    status=SendStatus.SKIPPED,
                    timestamp=now,
                    error="duplicate_send_prevented",
                    scheduled_for=scheduled_for,
                    attempt=attempt,
                )
                continue

            try:
                self.sender.send(
                    channel_id=channel.discord_channel_id,
                    content=ad.content,
                    embed_json=ad.embed_json,
                )
                self._idempotency_keys.add(key)
                self.service.record_log(
                    ad_id=ad_id,
                    channel_id=channel.id,
                    status=SendStatus.SUCCESS,
                    timestamp=now,
                    error=None,
                    scheduled_for=scheduled_for,
                    attempt=attempt,
                )
                result.sent += 1
            except Exception as exc:  # noqa: BLE001
                self.service.record_log(
                    ad_id=ad_id,
                    channel_id=channel.id,
                    status=SendStatus.FAILED,
                    timestamp=now,
                    error=str(exc),
                    scheduled_for=scheduled_for,
                    attempt=attempt,
                )
                result.failed += 1
                self._schedule_retry(
                    ad_id=ad_id,
                    channel_id=channel.id,
                    scheduled_for=scheduled_for,
                    attempt=attempt,
                    now=now,
                    result=result,
                )

    def _schedule_retry(
        self,
        *,
        ad_id: int,
        channel_id: int,
        scheduled_for: datetime,
        attempt: int,
        now: datetime,
        result: SchedulerResult,
    ) -> None:
        if attempt >= self.max_retries:
            result.retry_exhausted += 1
            return

        delay = self.retry_base_seconds * (2 ** (attempt - 1))
        self._pending_retries.append(
            PendingRetry(
                ad_id=ad_id,
                channel_id=channel_id,
                scheduled_for=scheduled_for,
                next_retry_at=now + timedelta(seconds=delay),
                attempt=attempt + 1,
                max_retries=self.max_retries,
            )
        )
        result.retry_scheduled += 1

    def _process_retries(self, *, now: datetime, result: SchedulerResult) -> None:
        still_pending: list[PendingRetry] = []
        due = [retry for retry in self._pending_retries if retry.next_retry_at <= now]
        still_pending.extend(retry for retry in self._pending_retries if retry.next_retry_at > now)

        for retry in due:
            ad = self.service.store.ads.get(retry.ad_id)
            if ad is None or not ad.active:
                result.skipped += 1
                continue

            channel = self.service.store.channels.get(retry.channel_id)
            if channel is None:
                result.skipped += 1
                continue

            key = (retry.ad_id, retry.channel_id, retry.scheduled_for)
            if key in self._idempotency_keys:
                result.skipped += 1
                continue

            try:
                self.sender.send(
                    channel_id=channel.discord_channel_id,
                    content=ad.content,
                    embed_json=ad.embed_json,
                )
                self._idempotency_keys.add(key)
                self.service.record_log(
                    ad_id=retry.ad_id,
                    channel_id=retry.channel_id,
                    status=SendStatus.SUCCESS,
                    timestamp=now,
                    error=None,
                    scheduled_for=retry.scheduled_for,
                    attempt=retry.attempt,
                )
                result.sent += 1
            except Exception as exc:  # noqa: BLE001
                self.service.record_log(
                    ad_id=retry.ad_id,
                    channel_id=retry.channel_id,
                    status=SendStatus.FAILED,
                    timestamp=now,
                    error=str(exc),
                    scheduled_for=retry.scheduled_for,
                    attempt=retry.attempt,
                )
                result.failed += 1
                self._schedule_retry(
                    ad_id=retry.ad_id,
                    channel_id=retry.channel_id,
                    scheduled_for=retry.scheduled_for,
                    attempt=retry.attempt,
                    now=now,
                    result=result,
                )

        self._pending_retries = still_pending
