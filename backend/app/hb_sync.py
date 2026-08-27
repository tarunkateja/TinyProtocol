"""Scheduled sync Lambda (EventBridge, every 30 minutes): Huckleberry +
MyChart.

Same code bundle as the API, separate function: Firestore reads across
families don't fit interactive request budgets, and a sync failure must
never take the API down with it.
"""

import asyncio
import json
import logging

from app.services.huckleberry import sync_all_connections
from app.services.mychart import sync_all_connections as mychart_sync_all

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)


def handler(event, context):
    results = sync_all_connections()
    log.info("Huckleberry sync finished: %s", json.dumps(results, default=str))
    try:
        mc_results = asyncio.run(mychart_sync_all())
        log.info("MyChart sync finished: %s", json.dumps(mc_results, default=str))
    except Exception:  # a MyChart failure must never break the HB sync
        log.exception("MyChart sync pass failed")
        mc_results = []
    return {"synced": len(results), "results": results, "mychart": mc_results}
