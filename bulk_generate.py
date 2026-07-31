"""
bulk_generate.py — Backfill BlogBoard with articles for all categories over the past N days.

Usage:
    python bulk_generate.py                    # Generate 30 days × all categories
    python bulk_generate.py --days 7           # Generate 7 days × all categories
    python bulk_generate.py --domains ml dl    # Only specific domains
    python bulk_generate.py --per-day 1        # 1 tutorial + 1 ainews per day (default)

Each day generates:
  - 1 tutorial article (rotates across: ml, dl, nlp, cv, genai, statistics)
  - 1 AI news article (ainews)
"""

import argparse
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).parent / "blogboard"
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

from blogboard.graph.graph import build_graph
from langgraph.checkpoint.memory import InMemorySaver


# All tutorial domains (excluding ainews which has its own agent)
TUTORIAL_DOMAINS = ["ml", "dl", "nlp", "cv", "genai", "statistics"]


def generate_one(domain: str, date_str: str, thread_id: str):
    """Generate a single article for a given domain and date."""
    # Build a fresh graph for each invocation to avoid state conflicts
    graph = build_graph()

    initial_state = {
        "date": date_str,
        "dry_run": False,
    }

    if domain == "ainews":
        initial_state["domain"] = "ainews"

    else:
        # Force the tutorial agent to pick a specific domain
        # We do this by pre-setting the domain in state
        initial_state["domain"] = domain

    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = graph.invoke(initial_state, config=config)
        title = final_state.get("title", "?")
        md_path = final_state.get("md_path", "?")
        print(f"  ✅ [{domain}] {date_str} → {title}")
        print(f"     File: {md_path}")
        return True
    except Exception as e:
        print(f"  ❌ [{domain}] {date_str} → FAILED: {e}")
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Bulk-generate BlogBoard articles for backfilling",
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of past days to backfill (default: 30)",
    )
    parser.add_argument(
        "--domains", nargs="*", default=None,
        help=f"Specific domains to generate. Choices: {TUTORIAL_DOMAINS + ['ainews']}. Default: all",
    )
    parser.add_argument(
        "--skip-ainews", action="store_true",
        help="Skip AI news generation (only tutorials)",
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Start date (YYYY-MM-DD). Default: today minus --days",
    )
    args = parser.parse_args()

    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).date()

    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = today - timedelta(days=args.days - 1)

    # Build list of dates from start to today
    dates = []
    current = start
    while current <= today:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    # Determine domains
    if args.domains:
        tutorial_domains = [d for d in args.domains if d != "ainews"]
        include_ainews = "ainews" in args.domains and not args.skip_ainews
    else:
        tutorial_domains = TUTORIAL_DOMAINS[:]
        include_ainews = not args.skip_ainews

    # Build generation plan: rotate tutorial domains across days
    plan = []
    for i, date_str in enumerate(dates):
        # Rotate through tutorial domains (if any)
        if tutorial_domains:
            domain = tutorial_domains[i % len(tutorial_domains)]
            plan.append((domain, date_str))

        # Also generate ainews for each day
        if include_ainews:
            plan.append(("ainews", date_str))

    total = len(plan)
    print(f"\n{'='*60}")
    print(f"  BlogBoard — Bulk Article Generator")
    print(f"  Date range  : {dates[0]} → {dates[-1]} ({len(dates)} days)")
    print(f"  Domains     : {tutorial_domains}" + (" + ainews" if include_ainews else ""))
    print(f"  Total jobs  : {total}")
    print(f"{'='*60}\n")

    success = 0
    failed = 0

    for idx, (domain, date_str) in enumerate(plan, 1):
        print(f"\n[{idx}/{total}] Generating {domain} article for {date_str}...")
        thread_id = f"bulk-{domain}-{date_str}"

        ok = generate_one(domain, date_str, thread_id)
        if ok:
            success += 1
        else:
            failed += 1

        # Delay to avoid Groq rate limiting (free tier)
        if idx < total:
            print("  ⏳ Waiting 30s to avoid rate limits...")
            time.sleep(30)

    print(f"\n{'='*60}")
    print(f"  🎉 Bulk generation complete!")
    print(f"  Success : {success}/{total}")
    print(f"  Failed  : {failed}/{total}")
    print(f"{'='*60}\n")

    # After bulk generation, sync articles from R2 to local web folder
    print("📥 Syncing articles from R2 to local web folder...")
    sync_r2_to_local()
    print("✅ Sync complete! Serve with: python -m http.server 8000 --directory blogboard/web")


def sync_r2_to_local():
    """Download all articles.json and .md files from R2 to the local web folder."""
    from blogboard.services.storage import R2StorageService

    storage = R2StorageService()
    web_dir = ROOT_DIR / "blogboard" / "web"
    all_categories = ["ml", "dl", "nlp", "cv", "genai", "ainews", "statistics"]

    for cat in all_categories:
        cat_dir = web_dir / "blogs" / cat
        cat_dir.mkdir(parents=True, exist_ok=True)

        # Download articles.json
        articles = storage.get_articles_json(cat)
        if articles:
            json_path = cat_dir / "articles.json"
            import json
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(articles, f, indent=2, ensure_ascii=False)
            print(f"  📄 {cat}/articles.json ({len(articles)} articles)")

            # Download each .md file
            for article in articles:
                file_key = article.get("file", "")
                if file_key:
                    md_content = storage.get_object(file_key)
                    if md_content:
                        md_path = web_dir / file_key
                        md_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(md_content)
        else:
            print(f"  ⏭️  {cat} — no articles yet")


if __name__ == "__main__":
    main()
