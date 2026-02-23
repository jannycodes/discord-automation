from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from src.autoadv.models import Plan, User, Server, Channel
from src.autoadv.scheduler import Scheduler
from src.autoadv.service import AdService, InMemoryStore, LimitError


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail_once_channels: set[str] = set()

    def send(self, *, channel_id: str, content: str, embed_json: str | None) -> None:
        if channel_id in self.fail_once_channels:
            self.fail_once_channels.remove(channel_id)
            raise RuntimeError("temporary error")
        self.sent.append((channel_id, content))


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        self.store.users[1] = User(id=1, discord_id="u_1", plan=Plan.PRO)
        self.store.servers[1] = Server(id=1, discord_server_id="s_1", name="Guild 1")
        self.store.channels[1] = Channel(id=1, discord_channel_id="c_1", server_id=1)
        self.store.channels[2] = Channel(id=2, discord_channel_id="c_2", server_id=1)
        self.service = AdService(self.store)
        self.sender = FakeSender()
        self.scheduler = Scheduler(service=self.service, sender=self.sender, retry_base_seconds=30, max_retries=3)

    def test_send_due_ad(self) -> None:
        ad = self.service.create_ad(
            user_id=1,
            content="hello",
            embed_json=None,
            interval_seconds=300,
            channel_ids=[1, 2],
        )
        self.service.start_ad(ad.id)

        now = datetime(2026, 1, 1, 12, 0, 0)
        result = self.scheduler.tick(now)

        self.assertEqual(result.processed_ads, 1)
        self.assertEqual(result.sent, 2)
        self.assertEqual(len(self.store.send_logs), 2)

    def test_retry_failed_channel(self) -> None:
        ad = self.service.create_ad(
            user_id=1,
            content="hello",
            embed_json=None,
            interval_seconds=300,
            channel_ids=[1],
        )
        self.service.start_ad(ad.id)
        self.sender.fail_once_channels.add("c_1")

        now = datetime(2026, 1, 1, 12, 0, 0)
        first = self.scheduler.tick(now)
        self.assertEqual(first.failed, 1)
        self.assertEqual(first.retry_scheduled, 1)

        second = self.scheduler.tick(now + timedelta(seconds=30))
        self.assertEqual(second.sent, 1)

    def test_free_plan_limits_interval(self) -> None:
        self.store.users[2] = User(id=2, discord_id="u_2", plan=Plan.FREE)

        with self.assertRaises(LimitError):
            self.service.create_ad(
                user_id=2,
                content="promo",
                embed_json=None,
                interval_seconds=120,
                channel_ids=[1],
            )


if __name__ == "__main__":
    unittest.main()
