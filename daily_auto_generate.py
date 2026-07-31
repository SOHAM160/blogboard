"""
daily_auto_generate.py — Automatic daily article generation + sync.

This script is called by Windows Task Scheduler every day.
It uses LangGraph AI Agents to generate 1 tutorial article (auto-rotating domains) 
and 1 AI news article, then syncs all articles from R2 to the local web folder.
"""

import sys
import os
import json
import time
import logging
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup paths
ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Setup logging to file
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"daily_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT_DIR / ".env")
except ImportError:
    pass

# Sentry
import sentry_sdk
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)


def sync_r2_to_local():
    """Download all articles.json and .md files from R2 to local web folder."""
    from blogboard.services.storage import R2StorageService

    storage = R2StorageService()
    web_dir = ROOT_DIR / "blogboard" / "web"
    all_categories = ["ml", "dl", "nlp", "cv", "genai", "ainews", "statistics"]

    for cat in all_categories:
        cat_dir = web_dir / "blogs" / cat
        cat_dir.mkdir(parents=True, exist_ok=True)

        articles = storage.get_articles_json(cat)
        if articles:
            json_path = cat_dir / "articles.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(articles, f, indent=2, ensure_ascii=False)
            logger.info(f"  📄 {cat}/articles.json ({len(articles)} articles)")

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
            logger.info(f"  ⏭️  {cat} — no articles yet")


def generate_with_retry(graph, state, config, max_retries=3, delay=60):
    """Try to generate an article, retrying on rate limit errors."""
    for attempt in range(max_retries):
        try:
            result = graph.invoke(state, config=config)
            return result
        except Exception as e:
            error_str = str(e)
            if "rate_limit" in error_str.lower() and attempt < max_retries - 1:
                logger.warning(f"  ⚠️ Rate limited. Retry {attempt+2}/{max_retries} in {delay}s...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                raise


def main():
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).strftime("%B %d, %Y").replace(" 0", " ") # Keep format like 'August 1, 2026'
    now_str = datetime.now(ist).strftime("%H:%M:%S")

    logger.info(f"{'='*60}")
    logger.info(f"  📝 BlogBoard Daily Auto-Generate (LangGraph AI)")
    logger.info(f"  Date: {today}  |  Time: {now_str} IST")
    logger.info(f"{'='*60}")

    from blogboard.graph.graph import build_graph

    # 1. Generate tutorial article (auto-selects least recently updated domain)
    logger.info("\n[1/2] Generating AI tutorial article...")
    try:
        graph = build_graph()
        state = {"date": today, "dry_run": False}
        config = {"configurable": {"thread_id": f"auto-tutorial-{today}"}}
        result = generate_with_retry(graph, state, config)
        logger.info(f"  ✅ AI Tutorial: {result.get('title', '?')} ({result.get('domain', '?')})")
    except Exception as e:
        logger.error(f"  ❌ AI Tutorial generation failed: {e}")
        traceback.print_exc()

    # Wait before next generation to avoid rate limits
    logger.info("  ⏳ Waiting 60s before next generation...")
    time.sleep(60)

    # 2. Generate AI News article
    logger.info("\n[2/2] Generating AI News article...")
    try:
        graph2 = build_graph()
        state2 = {"date": today, "dry_run": False, "domain": "ainews"}
        config2 = {"configurable": {"thread_id": f"auto-ainews-{today}"}}
        result2 = generate_with_retry(graph2, state2, config2)
        logger.info(f"  ✅ AI News: {result2.get('title', '?')}")
    except Exception as e:
        logger.error(f"  ❌ AI News generation failed: {e}")
        traceback.print_exc()

    # 3. Sync everything from R2 to local
    logger.info("\n📥 Syncing articles from R2 to local web folder...")
    try:
        sync_r2_to_local()
        logger.info("✅ Sync complete!")
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        traceback.print_exc()

    logger.info(f"\n{'='*60}")
    logger.info(f"  🎉 Daily generation finished at {datetime.now(ist).strftime('%H:%M:%S')} IST")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
