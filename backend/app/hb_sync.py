"""Scheduled Huckleberry sync Lambda (EventBridge, every 30 minutes).

Same code bundle as the API, separate function: Firestore reads across
families don't fit interactive request budgets, and a sync failure must
never take the API down with it.
"""

import json
import logging

from app.services.huckleberry import sync_all_connections

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)


def handler(event, context):
    results = sync_all_connections()
    log.info("Huckleberry sync finished: %s", json.dumps(results, default=str))
    return {"synced": len(results), "results": results}
