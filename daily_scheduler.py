"""
daily_scheduler.py — Runs BlogBoard article generation automatically every day.

Usage:
    python daily_scheduler.py                  # Runs at 6:00 AM IST daily
    python daily_scheduler.py --hour 8         # Runs at 8:00 AM IST daily
    python daily_scheduler.py --interval 12    # Runs every 12 hours

Keep this script running in the background. It will:
  1. Generate 1 tutorial article (auto-rotating across domains)
  2. Generate 1 AI news article
  3. Sync from R2 to local web folder
  4. Sleep until the next scheduled time
"""

import sys
import time
import schedule
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT_DIR / ".env")
except ImportError:
    pass

import os
import sentry_sdk
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)


def daily_job():
    """Generate today's articles and sync to local."""
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).strftime("%Y-%m-%d")
    now = datetime.now(ist).strftime("%H:%M:%S")

    print(f"\n{'='*60}")
    print(f"  📝 Daily generation triggered at {now} IST")
    print(f"  Date: {today}")
    print(f"{'='*60}")

    try:
        from blogboard.graph.graph import build_graph

        # 1. Generate tutorial article (auto-selects least updated domain)
        print("\n[1/2] Generating tutorial article...")
        graph = build_graph()
        state = {"date": today, "dry_run": False}
        config = {"configurable": {"thread_id": f"daily-tutorial-{today}"}}
        result = graph.invoke(state, config=config)
        print(f"  ✅ Tutorial: {result.get('title', '?')} ({result.get('domain', '?')})")

        # 2. Generate AI News article
        print("\n[2/2] Generating AI News article...")
        graph2 = build_graph()
        state2 = {"date": today, "dry_run": False, "domain": "ainews"}
        config2 = {"configurable": {"thread_id": f"daily-ainews-{today}"}}
        result2 = graph2.invoke(state2, config=config2)
        print(f"  ✅ AI News: {result2.get('title', '?')}")

        # 3. Sync R2 to local
        print("\n📥 Syncing articles from R2 to local...")
        from bulk_generate import sync_r2_to_local
        sync_r2_to_local()
        print("✅ Sync complete!")

    except Exception as e:
        print(f"  ❌ Error during daily generation: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  ⏰ Next run scheduled. Waiting...")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BlogBoard Daily Scheduler")
    parser.add_argument("--hour", type=int, default=6, help="Hour to run (IST, 24h format). Default: 6")
    parser.add_argument("--minute", type=int, default=0, help="Minute to run. Default: 0")
    parser.add_argument("--interval", type=int, default=None, help="Run every N hours instead of at a fixed time")
    parser.add_argument("--run-now", action="store_true", help="Run immediately on startup, then continue scheduling")
    args = parser.parse_args()

    # Convert IST time to UTC for scheduling
    # schedule library uses local time, so we just use the IST time directly
    if args.interval:
        schedule.every(args.interval).hours.do(daily_job)
        print(f"📅 Scheduled to run every {args.interval} hours")
    else:
        run_time = f"{args.hour:02d}:{args.minute:02d}"
        schedule.every().day.at(run_time).do(daily_job)
        print(f"📅 Scheduled to run daily at {run_time} IST")

    if args.run_now:
        print("🚀 Running immediately...")
        daily_job()

    print("⏰ Scheduler is running. Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n👋 Scheduler stopped.")
