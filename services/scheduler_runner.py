"""
Scheduler runner — checks for due posts and posts them via X API.
Called by Vercel Cron every minute hitting /api/cron/post.
"""

import time, logging
from datetime import datetime, timedelta
from threading import Lock

from config import LOCAL_TZ, MAX_RETRIES, RETRY_BACKOFF, RETRYABLE_CODES, POST_DELAY
from db import get_db, now_utc, new_id
from services.xapi import get_valid_token, post_tweet
from services.notifications import notify

log = logging.getLogger(__name__)
post_lock = Lock()


def run_scheduler():
    with post_lock:
        try:
            with get_db() as conn:
                now_local_str = datetime.now(LOCAL_TZ).strftime('%Y-%m-%dT%H:%M:%S')

                pending = conn.execute(
                    """SELECT * FROM posts
                       WHERE (status='pending' AND scheduled_time<=?)
                          OR (status='retrying' AND next_retry<=?)
                       ORDER BY scheduled_time""",
                    (now_local_str, now_utc().isoformat())
                ).fetchall()

                posted_count = 0
                for p in pending:
                    p = dict(p)
                    slot = p['account_slot']

                    if posted_count > 0:
                        time.sleep(POST_DELAY)

                    retry_num = (p.get('retry_count') or 0) + 1
                    log.info("Posting id=%s account=%s (attempt %d/%d)",
                             p['id'][:8], slot, retry_num, MAX_RETRIES)

                    token, err = get_valid_token(slot)
                    if err:
                        conn.execute(
                            "UPDATE posts SET status='failed',error_msg=? WHERE id=?",
                            (err, p['id']))
                        conn.commit()
                        notify(f"Post failed (no token): {p['text'][:80]}… → {err}", 'error')
                        continue

                    tweet_id, err, status_code = post_tweet(token, p['text'])

                    if err:
                        retry_count = (p.get('retry_count') or 0) + 1

                        if status_code in RETRYABLE_CODES and retry_count < MAX_RETRIES:
                            backoff = RETRY_BACKOFF[min(retry_count - 1, len(RETRY_BACKOFF) - 1)]
                            next_retry = (now_utc() + timedelta(seconds=backoff)).isoformat()
                            conn.execute(
                                "UPDATE posts SET status='retrying',retry_count=?,next_retry=?,error_msg=? WHERE id=?",
                                (retry_count, next_retry, err, p['id']))
                            conn.commit()
                            log.warning("  Retry %d/%d in %ds: %s",
                                        retry_count, MAX_RETRIES, backoff, err)
                            continue

                        conn.execute(
                            "UPDATE posts SET status='failed',retry_count=?,error_msg=? WHERE id=?",
                            (retry_count, err, p['id']))
                        conn.commit()
                        log.error("  Post failed permanently: %s", err)
                        notify(f"Post FAILED ({retry_count} attempts): "
                               f"{p['text'][:80]}… → {err}", 'error')
                        continue

                    if p.get('reply_text'):
                        _, rerr, _ = post_tweet(token, p['reply_text'], reply_to_id=tweet_id)
                        if rerr:
                            log.warning("  Reply failed: %s", rerr)
                            notify(f"Thread reply failed: {rerr}", 'warning')

                    conn.execute(
                        "UPDATE posts SET status='posted',posted_at=?,tweet_id=?,retry_count=0 WHERE id=?",
                        (now_utc().isoformat(), tweet_id, p['id'])
                    )

                    if p['recurring'] and p['recurring'] != 'none':
                        days   = 7 if p['recurring'] == 'weekly' else 14
                        new_dt = datetime.fromisoformat(p['scheduled_time']) + timedelta(days=days)
                        conn.execute(
                            '''INSERT INTO posts
                               (id,account_slot,type,text,reply_text,notes,
                                scheduled_time,recurring,status,project,rating,stage,created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (new_id(), slot, p['type'], p['text'], p['reply_text'],
                             p['notes'], new_dt.isoformat(), p['recurring'], 'pending',
                             p['project'], p['rating'], p['stage'], now_utc().isoformat())
                        )
                    conn.commit()
                    posted_count += 1
                    log.info("  ✓ Posted tweet %s", tweet_id)

        except Exception:
            log.exception("Scheduler error")
