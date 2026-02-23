from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"


@dataclass(slots=True)
class PlanLimits:
    max_ads: int
    max_servers: int
    min_interval_seconds: int


PLAN_LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(max_ads=2, max_servers=3, min_interval_seconds=3600),
    Plan.PRO: PlanLimits(max_ads=25, max_servers=50, min_interval_seconds=300),
}


@dataclass(slots=True)
class User:
    id: int
    discord_id: str
    plan: Plan


@dataclass(slots=True)
class Server:
    id: int
    discord_server_id: str
    name: str


@dataclass(slots=True)
class Channel:
    id: int
    discord_channel_id: str
    server_id: int


@dataclass(slots=True)
class Ad:
    id: int
    user_id: int
    content: str
    embed_json: Optional[str]
    interval_seconds: int
    active: bool = False
    last_sent_at: Optional[datetime] = None


@dataclass(slots=True)
class AdTarget:
    ad_id: int
    channel_id: int


class SendStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class SendLog:
    ad_id: int
    channel_id: int
    timestamp: datetime
    status: SendStatus
    error: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    attempt: int = 1


@dataclass(slots=True)
class PendingRetry:
    ad_id: int
    channel_id: int
    scheduled_for: datetime
    next_retry_at: datetime
    attempt: int = 1
    max_retries: int = 3


@dataclass(slots=True)
class SchedulerResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retry_scheduled: int = 0
    retry_exhausted: int = 0
    processed_ads: int = 0
    messages: list[str] = field(default_factory=list)
