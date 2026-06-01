"""
CoinDesk新闻采集
"""

import feedparser
import re
import sys
import os
from datetime import datetime

sys.path.append(
    os.path.dirname(
        os.path.dirname(__file__)
    )
)

from config import Message, save_messages


# ==========================
# RSS源
# ==========================

COINDESK_RSS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
)
# ==========================
# 代币提取
# ==========================

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
    "ATOM": ["COSMOS", "ATOM"],
    "LTC": ["LITECOIN", "LTC"],
    "FIL": ["FILECOIN", "FIL"],
    "APT": ["APTOS", "APT"],
    "SUI": ["SUI"],
}
def extract_tokens(text):

    text = text.upper()

    tokens = []

    for symbol, keywords in TOKEN_MAP.items():

        for kw in keywords:

            if kw in text:

                tokens.append(symbol)

                break

    return list(dict.fromkeys(tokens))


# ==========================
# RSS解析
# ==========================
import requests
import feedparser


def parse_rss():

    print("[CoinDesk] 解析RSS...")

    headers = {
        "User-Agent":
        "Mozilla/5.0"
    }

    r = requests.get(
        COINDESK_RSS,
        headers=headers,
        timeout=20
    )

    print(
        f"[CoinDesk] HTTP状态码: {r.status_code}"
    )

    feed = feedparser.parse(
        r.content
    )

    print(
        f"[CoinDesk] RSS标题: "
        f"{feed.feed.get('title','Unknown')}"
    )

    print(
        f"[CoinDesk] RSS返回: "
        f"{len(feed.entries)} 条"
    )

    articles = []

    for entry in feed.entries:

        published = ""

        if (
            hasattr(
                entry,
                "published_parsed"
            )
            and
            entry.published_parsed
        ):
            published = datetime(
                *entry.published_parsed[:6]
            ).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        summary = entry.get(
            "summary",
            ""
        )

        summary = re.sub(
            r"<[^>]+>",
            "",
            summary
        )

        articles.append({
            "title":
                entry.get(
                    "title",
                    ""
                ),
            "link":
                entry.get(
                    "link",
                    ""
                ),
            "summary":
                summary,
            "published":
                published,
        })

    return articles

# ==========================
# 新闻采集
# ==========================

def fetch_news():

    articles = parse_rss()

    messages = []

    for article in articles:
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
            source="coindesk",
            content=content,
            timestamp=article["published"],
            author="CoinDesk",
            url=article["link"],
            mentioned_tokens=tokens,
            extra={
                "source_type": "rss",
                "title": article["title"],
                "summary": article["summary"],
            },
        )

        messages.append(msg)

    return messages


# ==========================
# 保存
# ==========================

def collect_and_save():

    print("=" * 50)

    print(
        "[CoinDesk] 开始采集..."
    )

    messages = fetch_news()

    if messages:

        save_messages(
            messages,
            "coindesk.json"
        )

    else:

        print(
            "[CoinDesk] 未获取到数据"
        )

    return messages


# ==========================
# main
# ==========================

if __name__ == "__main__":
    collect_and_save()