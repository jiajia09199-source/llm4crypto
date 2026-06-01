"""
数据源 2: Twitter / X 推文采集
使用 twscrape 库 (https://github.com/vladkens/twscrape)
安装: pip install twscrape

采集内容：
a. KOL / 项目方 / 交易所账号的推文
   - 推文内容、发布时间、作者、粉丝数
   - 转发数 / 点赞数 / 回复数
   - 提及的代币
b. 关键词搜索 ($BTC, $ETH, $SOL)
"""

import asyncio
import re
import sys, os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    TWITTER_USERNAME, TWITTER_PASSWORD,
    TWITTER_EMAIL, TWITTER_EMAIL_PASSWORD,
    TWITTER_KOLS, TWITTER_KEYWORDS,
    Message, save_messages,
)

try:
    from twscrape import API, gather
except ImportError:
    print("请先安装: pip install twscrape")
    sys.exit(1)

# 匹配 $BTC, $ETH 等代币符号
TOKEN_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')


def extract_tokens(text: str) -> list[str]:
    """从推文中提取代币符号"""
    return list(set(TOKEN_PATTERN.findall(text)))


async def setup_api() -> API:
    """初始化 twscrape 并登录"""
    api = API("accounts.db")

    # 检查是否已有账号
    accounts = await api.pool.accounts_info()
    has_active = any(a.get("active") for a in accounts) if accounts else False

    if not has_active:
        if not TWITTER_USERNAME:
            print("[Twitter] 未配置账号，请在 config.py 中设置")
            return None
        print(f"[Twitter] 添加账号 {TWITTER_USERNAME} ...")
        await api.pool.add_account(
            TWITTER_USERNAME, TWITTER_PASSWORD,
            TWITTER_EMAIL, TWITTER_EMAIL_PASSWORD,
            cookies="your_ct0_cookie_here; your_auth_token_here",
        )
        await api.pool.login_all()
        print("[Twitter] 登录成功")

    return api


def tweet_to_message(tweet, author_override: str = "") -> Message:
    """将 twscrape 的 Tweet 对象转为统一的 Message"""
    username = author_override or (tweet.user.username if tweet.user else "")
    return Message(
        source="twitter",
        content=tweet.rawContent,
        timestamp=tweet.date.isoformat() if tweet.date else datetime.now().isoformat(),
        author=username,
        url=f"https://x.com/{username}/status/{tweet.id}",
        mentioned_tokens=extract_tokens(tweet.rawContent),
        likes=tweet.likeCount or 0,
        retweets=tweet.retweetCount or 0,
        replies=tweet.replyCount or 0,
        followers=tweet.user.followersCount if tweet.user else 0,
        extra={
            "tweet_id": tweet.id,
            "views": tweet.viewCount or 0,
            "lang": tweet.lang or "",
        },
    )


async def search_by_keyword(api: API, keyword: str, limit: int = 20) -> list[Message]:
    """b. 关键词搜索，如 $BTC"""
    print(f"[Twitter] 搜索关键词: {keyword}")
    messages = []
    try:
        tweets = await gather(api.search(keyword, limit=limit))
        messages = [tweet_to_message(t) for t in tweets]
    except Exception as e:
        print(f"[Twitter] 搜索 '{keyword}' 失败: {type(e).__name__}: {e}")
    print(f"[Twitter]   -> {len(messages)} 条推文")
    return messages


async def get_user_tweets(api: API, username: str, limit: int = 10) -> list[Message]:
    """a. 获取指定 KOL/交易所 的推文"""
    print(f"[Twitter] 获取 @{username} 的推文")
    messages = []
    try:
        user = await api.user_by_login(username)
        if not user:
            print(f"[Twitter]   -> 未找到用户 @{username}")
            return []
        tweets = await gather(api.user_tweets(user.id, limit=limit))
        messages = [tweet_to_message(t, username) for t in tweets]
        # 补充粉丝数
        for m in messages:
            m.followers = user.followersCount or 0
    except Exception as e:
        print(f"[Twitter] @{username} 失败: {type(e).__name__}: {e}")
    print(f"[Twitter]   -> {len(messages)} 条推文")
    return messages


async def collect_all() -> list[Message]:
    """完整采集流程"""
    api = await setup_api()
    if not api:
        return []

    all_messages = []

    # b. 关键词搜索
    print("\n--- 关键词搜索 ---")
    for kw in TWITTER_KEYWORDS:
        msgs = await search_by_keyword(api, kw)
        all_messages.extend(msgs)
        await asyncio.sleep(2)  # 控制频率

    # a. KOL 推文
    print("\n--- KOL 推文 ---")
    for user in TWITTER_KOLS:
        msgs = await get_user_tweets(api, user)
        all_messages.extend(msgs)
        await asyncio.sleep(2)

    return all_messages


def collect_and_save():
    """入口：采集并保存"""
    print("=" * 50)
    print("[Twitter] 开始采集...")
    messages = asyncio.run(collect_all())
    if messages:
        save_messages(messages, "twitter.json")
    else:
        print("[Twitter] 未获取到数据，请检查账号配置")
    print(f"[Twitter] 完成，共 {len(messages)} 条")
    return messages


if __name__ == "__main__":
    results = collect_and_save()
