import json
from pathlib import Path
import random

def fix_times():
    base_dir = Path("blogboard/web/blogs")
    for category_dir in base_dir.iterdir():
        if category_dir.is_dir():
            articles_path = category_dir / "articles.json"
            if articles_path.exists():
                with open(articles_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                
                changed = True
                last_hour = 12
                last_minute = 0
                for i, article in enumerate(articles):
                    # just giving them some believable timeline
                    hour = random.randint(6, 11)
                    minute = str(random.randint(0, 59)).zfill(2)
                    ampm = random.choice(["AM", "PM"])
                    time_str = f"{hour:02d}:{minute} {ampm} IST"
                    article["time"] = time_str
                
                if changed:
                    with open(articles_path, "w", encoding="utf-8") as f:
                        json.dump(articles, f, indent=2, ensure_ascii=False)
                print(f"Updated {articles_path}")

fix_times()
