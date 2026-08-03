"""
daily_auto_generate.py — Automatic daily article generation + sync.

This script is called by GitHub Actions every day at 6:00 AM IST.
It uses the LangGraph News Agent to generate 2 AI news articles based on
real-world current events, then syncs all articles from R2 to the local web folder.
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


def prune_excess_articles(max_total=60):
    """
    Ensures that the total number of articles across all domains does not exceed max_total.
    If it does, the OLDEST articles are removed from R2 Storage and local filesystem, 
    and the corresponding domain's articles.json is updated.
    """
    from blogboard.services.storage import R2StorageService
    storage = R2StorageService()
    
    all_categories = ["ml", "dl", "nlp", "cv", "genai", "ainews", "statistics"]
    all_articles = []
    
    # 1. Collect all articles from R2
    for cat in all_categories:
        articles = storage.get_articles_json(cat)
        for article in articles:
            article['_cat'] = cat  # Keep track of which category this belongs to
            all_articles.append(article)
            
    if len(all_articles) <= max_total:
        logger.info(f"  ✅ Total articles ({len(all_articles)}) is within limit ({max_total}). No pruning needed.")
        return

    def parse_date(date_str):
        try:
            return datetime.strptime(date_str.strip(), "%B %d, %Y")
        except:
            return datetime.min

    # 2. Sort all articles by date (oldest first). 
    all_articles.sort(key=lambda x: parse_date(x.get("date", "")))
    
    # 3. Determine how many to delete
    excess_count = len(all_articles) - max_total
    articles_to_delete = all_articles[:excess_count]
    
    logger.info(f"  🗑️ Pruning {excess_count} oldest articles to maintain limit of {max_total}...")
    
    # 4. Group deletions by category and remove from R2 and Local
    web_dir = ROOT_DIR / "blogboard" / "web"
    cat_to_remaining = {}
    
    for cat in all_categories:
        cat_to_remaining[cat] = [a for a in storage.get_articles_json(cat)]
        
    for article in articles_to_delete:
        cat = article['_cat']
        file_key = article.get("file", "")
        article_id = article.get("id", "")
        
        # Remove from R2
        if file_key:
            storage.delete_object(file_key)
            
            # Remove locally so git removes it
            local_path = web_dir / file_key
            if local_path.exists():
                local_path.unlink()
                
        # Remove from the remaining list for this category
        cat_to_remaining[cat] = [a for a in cat_to_remaining[cat] if a.get("id") != article_id]
        logger.info(f"    - Deleted '{article.get('title')}' (from {cat}, {article.get('date')})")
        
    # 5. Save updated articles.json to R2 for affected categories
    deleted_cats = set(a['_cat'] for a in articles_to_delete)
    for cat in deleted_cats:
        storage.save_articles_json(cat, cat_to_remaining[cat])
        logger.info(f"    - Updated {cat}/articles.json in R2")



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

    # 1. Generate first AI News article (Research & Breakthroughs focus)
    logger.info("\n[1/2] Generating AI News article (Research & Breakthroughs)...")
    try:
        graph = build_graph()
        state = {"date": today, "dry_run": False, "domain": "ainews", "topic": "Latest AI Research & Breakthroughs"}
        config = {"configurable": {"thread_id": f"auto-ainews-research-{today}"}}
        result = generate_with_retry(graph, state, config)
        logger.info(f"  ✅ AI News (Research): {result.get('title', '?')}")
    except Exception as e:
        logger.error(f"  ❌ AI News (Research) generation failed: {e}")
        traceback.print_exc()

    # Wait before next generation to avoid rate limits
    logger.info("  ⏳ Waiting 60s before next generation...")
    time.sleep(60)

    # 2. Generate second AI News article (Industry & Products focus)
    logger.info("\n[2/2] Generating AI News article (Industry & Products)...")
    try:
        graph2 = build_graph()
        state2 = {"date": today, "dry_run": False, "domain": "ainews", "topic": "AI Industry News & Product Launches"}
        config2 = {"configurable": {"thread_id": f"auto-ainews-industry-{today}"}}
        result2 = generate_with_retry(graph2, state2, config2)
        logger.info(f"  ✅ AI News (Industry): {result2.get('title', '?')}")
    except Exception as e:
        logger.error(f"  ❌ AI News (Industry) generation failed: {e}")
        traceback.print_exc()

    # 3. Prune old articles if over limit
    logger.info("\n🧹 Checking article limits...")
    try:
        prune_excess_articles(60)
    except Exception as e:
        logger.error(f"❌ Pruning failed: {e}")
        traceback.print_exc()

    # 4. Sync everything from R2 to local
    logger.info("\n📥 Syncing articles from R2 to local web folder...")
    try:
        sync_r2_to_local()
        logger.info("✅ Sync complete!")
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        traceback.print_exc()

    # 5. Git operations are handled by the GitHub Action workflow
    logger.info("\n🚀 GitHub Action will handle commit and push.")

    logger.info(f"\n{'='*60}")
    logger.info(f"  🎉 Daily generation finished at {datetime.now(ist).strftime('%H:%M:%S')} IST")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
