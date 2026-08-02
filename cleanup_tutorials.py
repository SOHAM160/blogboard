"""
cleanup_tutorials.py — One-time script to remove all old tutorial articles
from R2 and locally, keeping only ainews (real-world) articles.
"""
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(dotenv_path=ROOT_DIR / ".env")

from blogboard.services.storage import R2StorageService

def main():
    storage = R2StorageService()
    web_dir = ROOT_DIR / "blogboard" / "web"
    
    # These are the tutorial categories to wipe (NOT ainews)
    tutorial_categories = ["ml", "dl", "nlp", "cv", "genai", "statistics"]
    
    for cat in tutorial_categories:
        print(f"\n🗑️  Cleaning category: {cat}")
        articles = storage.get_articles_json(cat)
        
        if not articles:
            print(f"  (empty, skipping)")
            continue
            
        for article in articles:
            file_key = article.get("file", "")
            title = article.get("title", "?")
            
            # Delete .md from R2
            if file_key:
                storage.delete_object(file_key)
                print(f"  ❌ R2 deleted: {file_key} ({title})")
                
                # Delete locally
                local_path = web_dir / file_key
                if local_path.exists():
                    local_path.unlink()
                    print(f"  ❌ Local deleted: {local_path.name}")
        
        # Save empty articles.json to R2
        storage.save_articles_json(cat, [])
        print(f"  ✅ Cleared {cat}/articles.json in R2 ({len(articles)} articles removed)")
        
        # Save empty articles.json locally
        local_json = web_dir / "blogs" / cat / "articles.json"
        if local_json.exists():
            with open(local_json, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            print(f"  ✅ Cleared local {cat}/articles.json")
    
    print(f"\n{'='*50}")
    print(f"✅ All tutorial articles removed!")
    print(f"Only ainews (real-world) articles remain.")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
