"""Read-only access to the GA-1 Facebook support-group corpus.

The corpus is built and curated offline in the `ga1-community` repo, then
exported as a small SQLite file to S3. This module downloads it once per Lambda
container and answers two very different kinds of question:

  * ``search_community``    - narrative: what did families actually say
  * ``community_practices`` - countable: how many described a given practice

Keeping those separate is deliberate. Retrieval sees a handful of threads, so it
cannot honestly count anything; the practice rows were extracted from every
thread, so they can. Blurring the two is how "3 of the threads I read" silently
becomes "3 families in the group".

PRIVACY: author names were one-way hashed at ingest and never stored. This is
other families' medical discussion, currently for the two parents' own use only
- see the "Before publishing" section of the ga1-community README before this
goes to any other user.
"""

import json
import os
import sqlite3
import threading

import boto3

GROUP_SLUG = "GlutaricAcidemia1"
CORPUS_KEY = "community/corpus-app.sqlite"
LOCAL_PATH = "/tmp/corpus-app.sqlite"  # noqa: S108 - Lambda's writable scratch

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def is_configured() -> bool:
    return bool(os.environ.get("DOCS_BUCKET"))


def _connect() -> sqlite3.Connection | None:
    """Download the corpus once per container, then reuse the connection."""
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:
            return _conn
        bucket = os.environ.get("DOCS_BUCKET")
        if not bucket:
            return None
        if not os.path.exists(LOCAL_PATH):
            try:
                boto3.client("s3").download_file(bucket, CORPUS_KEY, LOCAL_PATH)
            except Exception:
                # No corpus uploaded yet is a normal state, not an error: the
                # assistant should carry on answering from the baby's own logs.
                return None
        _conn = sqlite3.connect(LOCAL_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        return _conn


def permalink(post_id: str) -> str:
    return f"https://www.facebook.com/groups/{GROUP_SLUG}/permalink/{post_id}/"


def _fts_query(terms: list[str]) -> str:
    """Build a tolerant FTS5 OR-query, dropping anything that would be a syntax error."""
    cleaned = []
    for t in terms:
        t = "".join(ch for ch in t if ch.isalnum() or ch in " -").strip()
        for word in t.split():
            if len(word) > 2:
                cleaned.append(f'"{word}"')
    return " OR ".join(dict.fromkeys(cleaned))


def search(query: str, keywords: list[str] | None = None, max_threads: int = 6) -> str:
    """Find discussion threads relevant to a question, with citable permalinks.

    The app backend has no embedding model, so retrieval is keyword-based. The
    assistant compensates by passing synonyms in `keywords` - that is far more
    effective here than any single-phrase match, because parents write "jabs",
    "shots" and "immunisations" for the same thing.
    """
    conn = _connect()
    if conn is None:
        return json.dumps({"error": "community corpus unavailable"})

    terms = [query] + (keywords or [])
    match = _fts_query(terms)
    if not match:
        return json.dumps({"threads": []})

    # bm25() is an FTS5 auxiliary function: it is only valid in a plain MATCH
    # query, not inside an aggregate or a subquery SQLite may flatten. So rank
    # the individual chunks in SQL and group them into threads in Python.
    hits = conn.execute(
        """
        SELECT post_id, bm25(search_fts) AS rank
        FROM search_fts WHERE search_fts MATCH ?
        ORDER BY rank LIMIT 400
        """,
        (match,),
    ).fetchall()

    scored: dict[str, dict[str, float]] = {}
    for h in hits:
        agg = scored.setdefault(h["post_id"], {"hits": 0, "best": 0.0})
        agg["hits"] += 1
        agg["best"] = min(agg["best"], h["rank"])  # bm25 is negative: lower is better

    rows = sorted(
        ({"post_id": pid, **agg} for pid, agg in scored.items()),
        key=lambda r: (-r["hits"], r["best"]),
    )[:max_threads]

    threads = []
    for r in rows:
        post = conn.execute(
            "SELECT post_id, text, created_at, comment_count FROM posts WHERE post_id = ?",
            (r["post_id"],),
        ).fetchone()
        if post is None:
            continue
        comments = conn.execute(
            "SELECT text, created_at, parent_id FROM comments WHERE post_id = ? ORDER BY created_at LIMIT 40",
            (r["post_id"],),
        ).fetchall()
        threads.append({
            "post_id": post["post_id"],
            "date": post["created_at"],
            "url": permalink(post["post_id"]),
            "post": (post["text"] or "")[:1200],
            "total_comments": post["comment_count"],
            "comments": [(c["text"] or "")[:600] for c in comments],
        })

    total_threads = conn.execute("SELECT COUNT(*) n FROM posts").fetchone()["n"]
    return json.dumps({
        "threads_returned": len(threads),
        "threads": threads,
        "corpus_size_note": (
            f"The searchable corpus holds {total_threads} threads that have comments, "
            "drawn from 8830 posts crawled from the group (2008-2026). Only threads on "
            "topics crawled so far have their comments; the rest are post text only."
        ),
        "note": (
            "Parent anecdotes from a private GA-1 support group, not medical advice. "
            "You are seeing only the threads retrieved for this question - never "
            "describe these as counts of the whole group. If asked 'how many posts "
            "about X', do not answer from the number returned here: it is a retrieval "
            "limit, not a total."
        ),
    })


def practices(
    topic: str = "vaccination",
    phase: str | None = None,
    vaccine: str | None = None,
    outcome: str | None = None,
) -> str:
    """Aggregate structured practice reports extracted from every thread.

    Unlike `search`, these counts cover the whole extracted set, so they can be
    stated as numbers - with the selection-bias caveat that always rides along.
    """
    conn = _connect()
    if conn is None:
        return json.dumps({"error": "community corpus unavailable"})

    sql = "SELECT * FROM practices WHERE topic = ?"
    args: list[object] = [topic]
    if outcome:
        sql += " AND outcome = ?"
        args.append(outcome)
    rows = conn.execute(sql, args).fetchall()

    if vaccine:
        rows = [r for r in rows if vaccine in json.loads(r["vaccine_types"] or "[]")]
    if not rows:
        return json.dumps({"reports": 0, "note": f"no extracted practices for topic '{topic}'"})

    post_ids = {r["post_id"] for r in rows}

    def tally(phase_name: str) -> list[dict]:
        """Count on the canonical label, not the raw phrasing.

        Semantic clustering happens offline during export because there is no
        embedding model here. Counting raw strings would split one 37-family
        practice across rows of 6, 3 and 1 and make every finding look rarer
        than it is.
        """
        counts: dict[str, int] = {}
        for row in conn.execute(
            "SELECT post_id, canonical FROM practice_items WHERE topic = ? AND phase = ?",
            (topic, phase_name),
        ):
            if row["post_id"] not in post_ids:
                continue  # respect the vaccine/outcome filters applied above
            key = row["canonical"]
            if key:
                counts[key] = counts.get(key, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:25]
        return [{"practice": k, "reports": v} for k, v in top]

    # Be explicit about what each count covers. "threads" here means threads that
    # yielded a structured practice report - narrower than "threads about this
    # topic", because sympathy replies and opinions extract to nothing. Returning
    # the bare number invited the model to answer "how many posts are there about
    # vaccination?" with it, which is a different and smaller question.
    corpus_posts = conn.execute(
        "SELECT COUNT(*) n FROM posts WHERE post_id IN "
        "(SELECT DISTINCT post_id FROM practices WHERE topic = ?)",
        (topic,),
    ).fetchone()["n"]

    payload: dict[str, object] = {
        "topic": topic,
        "reports": len(rows),
        "distinct_families": len({r["speaker"] for r in rows if r["speaker"]}),
        "threads_with_extracted_practices": len({r["post_id"] for r in rows}),
        "scope_note": (
            f"{corpus_posts} threads on '{topic}' produced at least one structured "
            "practice report. That is NOT the number of posts about this topic in "
            "the group: threads that are only sympathy, agreement or opinion extract "
            "to nothing and are excluded. If asked how many posts exist on a topic, "
            "say you can only report how many were crawled and extracted, and give "
            "these figures with that qualification rather than presenting them as a "
            "total."
        ),
    }

    if phase in (None, "before"):
        payload["before"] = tally("before")
    if phase in (None, "during"):
        payload["during"] = tally("during")
    if phase in (None, "after"):
        payload["after"] = tally("after")
    if phase is None:
        payload["observations"] = tally("observations")
        outcomes: dict[str, int] = {}
        for r in rows:
            if r["outcome"]:
                outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        payload["outcomes"] = dict(sorted(outcomes.items(), key=lambda kv: -kv[1]))
        payload["premedication_examples"] = [
            r["premedication"] for r in rows if r["premedication"]
        ][:15]
        payload["diet_changes"] = [r["diet_change"] for r in rows if r["diet_change"]][:15]
        payload["schedule_changes"] = [
            r["schedule_change"] for r in rows if r["schedule_change"]
        ][:15]

    payload["serious_outcomes"] = [
        {"outcome": r["outcome"], "quote": r["quote"], "url": permalink(r["post_id"])}
        for r in rows
        if r["outcome"] in ("metabolic_crisis", "hospitalised", "high_fever")
    ][:12]

    payload["caveat"] = (
        "These count what families WROTE in these threads, not how often anything "
        "happens. Parents post about strong opinions and bad outcomes far more than "
        "routine ones. Valid for 'this practice exists and N families described it'; "
        "NOT valid as a percentage of GA-1 families, and never as an incidence rate. "
        "Near-identical practices may also appear as separate rows, so related lines "
        "should be read together."
    )
    return json.dumps(payload)
