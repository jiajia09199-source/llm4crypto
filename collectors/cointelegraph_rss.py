"""
Cointelegraph RSS 新闻采集

安装：
pip install feedparser

运行：
python cointelegraph_rss.py
"""

import feedparser
import re
import sys
import os
from datetime import datetime
from typing import List, Dict

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import Message, save_messages


# ==================== RSS 配置 ====================

MAIN_RSS_URL = "https://cointelegraph.com/rss"

# 这些分类RSS目前大部分已经失效
# 保留备用，不强制使用
CATEGORY_RSS = {
    "bitcoin": "https://cointelegraph.com/tags/bitcoin/rss",
    "ethereum": "https://cointelegraph.com/tags/ethereum/rss",
    "defi": "https://cointelegraph.com/tags/defi/rss",
    "nft": "https://cointelegraph.com/tags/nft/rss",
}


# ==================== 提取代币 ====================

TOKEN_MAP = {
    "BTC": ["BITCOIN", "BTC"],
    "ETH": ["ETHEREUM", "ETH"],
    "SOL": ["SOLANA", "SOL"],
    "BNB": ["BNB", "BINANCE"],
    "XRP": ["XRP", "RIPPLE"],
    "ADA": ["CARDANO", "ADA"],
    "DOGE": ["DOGECOIN", "DOGE"],
    "AVAX": ["AVALANCHE", "AVAX"],
    "DOT": ["POLKADOT", "DOT"],
    "LINK": ["CHAINLINK", "LINK"],
    "UNI": ["UNISWAP", "UNI"],
    "PEPE": ["PEPE"],
    "ARB": ["ARBITRUM", "ARB"],
    "OP": ["OPTIMISM", "OP"],
    "MATIC": ["POLYGON", "MATIC"],
}


def extract_tokens(text: str):
    text = text.upper()

    tokens = []

    for symbol, keywords in TOKEN_MAP.items():
        for kw in keywords:
            if kw in text:
                tokens.append(symbol)
                break

    return list(dict.fromkeys(tokens))


# ==================== RSS解析 ====================

def parse_feed(url: str):

    try:

        print(f"[Cointelegraph]解析 RSS: {url}")

        feed = feedparser.parse(url)

        if feed.bozo:
            print(f"RSS异常: {feed.bozo_exception}")

        print(
            f"[Cointelegraph]Feed标题: {feed.feed.get('title', 'Unknown')}"
        )

        print(
            f"[Cointelegraph]返回新闻数: {len(feed.entries)}"
        )

        articles = []

        for entry in feed.entries:

            published = ""

            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(
                    *entry.published_parsed[:6]
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

            summary = entry.get("summary", "")

            summary = re.sub(
                r"<[^>]+>",
                "",
                summary
            )

            articles.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": summary,
                "published": published,
            })

        return articles

    except Exception as e:

        print("解析失败:", e)

        return []


# ==================== 主采集 ====================

def fetch_news(include_categories=False):
    """入口：采集并保存"""
    print("=" * 50)
    print("[Cointelegraph] 开始采集...")

    all_articles = []
    # 主RSS
    main_articles = parse_feed(MAIN_RSS_URL)

    all_articles.extend(main_articles)

    print(
        f"[Cointelegraph]主RSS获得 {len(main_articles)} 条"
    )

    # 分类RSS（失败不影响主流程）
    if include_categories:

        for name, url in CATEGORY_RSS.items():

            try:

                cat_articles = parse_feed(url)

                print(
                    f"{name}: {len(cat_articles)} 条"
                )

                all_articles.extend(cat_articles)

            except Exception as e:

                print(
                    f"{name} RSS失败: {e}"
                )

    messages = []

    for article in all_articles:
        content = (
            f"{article['title']}\n\n{article['summary']}"
            if article['summary']
            else article['title']
        )

        full_text = (
                article['title']
                + " "
                + article['summary']
        )

        tokens = extract_tokens(full_text)

        msg = Message(
            source="cointelegraph",
            content=content,
            timestamp=article["published"],
            author="Cointelegraph",
            url=article["link"],
            mentioned_tokens=tokens,
            extra={
                "source_type": "rss",
                "news_source": "Cointelegraph",
                "title": article["title"],
                "summary": article["summary"],
            }
        )

        messages.append(msg)

    return messages


# ==================== 保存
# ====================

def collect_and_save():

    messages = fetch_news(
        include_categories=False
    )

    save_messages(
        messages,
        "cointelegraph.json"
    )

    return messages

if __name__ == "__main__":
    collect_and_save()