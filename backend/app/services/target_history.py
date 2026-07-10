"""Effective-dated target snapshots.

Targets change over time (the dietician adjusts them as labs come back), but a
past day should always be judged against the targets that were in effect THEN —
same principle as nutrition being snapshotted on feeds at write time.

Storage: FAMILY#<fid> / TARGETHIST#<baby_id>#<YYYY-MM-DD>. Each snapshot says
"from this local day onward, these were the targets". Editing targets writes a
snapshot effective today; the first-ever edit also backfills the previous
targets as the baseline so history before the change stays correct.
"""

from datetime import date, datetime, time, timezone

from app.models.baby import Baby, Targets
from app.repo import family_items, keys
from app.services.tz import effective_day

# Sorts before any real date; covers all days before targets were first edited.
BASELINE_DATE = "0001-01-01"


def record_change(
    family_id: str,
    baby_id: str,
    old: Targets,
    new: Targets,
    tz_name: str,
    day_start: time = time.min,
    effective_from: date | None = None,
) -> None:
    if new == old:
        return
    prefix = f"TARGETHIST#{baby_id}#"
    if not family_items.list_by_prefix(family_id, prefix):
        _put_snapshot(family_id, baby_id, BASELINE_DATE, old)
    today = effective_day(datetime.now(timezone.utc), tz_name, day_start)
    # A plan change often predates the edit (the dietician called days ago),
    # but can't start in the future — the live targets apply from now.
    when = min(effective_from or today, today)
    _put_snapshot(family_id, baby_id, when.isoformat(), new)


def list_periods(family_id: str, baby_id: str) -> list[dict]:
    snaps = family_items.list_by_prefix(family_id, f"TARGETHIST#{baby_id}#")
    snaps.sort(key=lambda s: s["effective_date"])
    return [
        {"effective_date": s["effective_date"], "targets": s.get("targets") or {}}
        for s in snaps
    ]


def delete_period(family_id: str, baby_id: str, effective_date: str) -> bool:
    sk = keys.target_hist_sk(baby_id, effective_date)
    if family_items.get(family_id, sk) is None:
        return False
    family_items.delete(family_id, sk)
    return True


def targets_for_day(family_id: str, baby: Baby, day: date) -> Targets:
    """The targets in effect on a given local day. Days on or after the newest
    snapshot use the live baby targets (authoritative for "now")."""
    snaps = family_items.list_by_prefix(family_id, f"TARGETHIST#{baby.id}#")
    if not snaps:
        return baby.targets
    snaps.sort(key=lambda s: s["effective_date"])
    if day.isoformat() >= snaps[-1]["effective_date"]:
        return baby.targets
    chosen = None
    for s in snaps:
        if s["effective_date"] <= day.isoformat():
            chosen = s
    return Targets.model_validate(chosen["targets"]) if chosen else baby.targets


def _put_snapshot(
    family_id: str, baby_id: str, effective_date: str, targets: Targets
) -> None:
    family_items.put(
        family_id,
        keys.target_hist_sk(baby_id, effective_date),
        {
            "baby_id": baby_id,
            "effective_date": effective_date,
            "targets": targets.model_dump(mode="json"),
            "recorded_at": keys.iso_z(datetime.now(timezone.utc)),
        },
    )
