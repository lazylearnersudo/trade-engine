import logging
import threading

from modules.execution import execute, reconcile
from modules.strategy import scheduled_slot
from shared.config import settings
from shared.db import pool

logger = logging.getLogger("trade.scheduler")


def tick():
    with pool.connection() as conn:
        conn.execute(
            "UPDATE trade.quotes SET updated_at=now() WHERE symbol IN ('NIFTYBEES','GOLDBEES')"
        )
        items = conn.execute(
            "SELECT * FROM trade.strategies WHERE enabled AND schedule_time IS NOT NULL"
        ).fetchall()
    for item in items:
        slot = scheduled_slot(item, grace_minutes=settings.schedule_grace_minutes)
        if slot:
            execute(item["id"], slot, {"id": "scheduler", "role": "SUPERUSER"})


class Scheduler:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="strategy-scheduler", daemon=True)

    def run(self):
        while not self.stop_event.wait(10):
            try:
                tick()
            except Exception:
                logger.error('{"event":"scheduler_tick_failed"}')

    def start(self):
        reconcile()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=15)
