"""
全局配置：API Key 和统一数据模型
所有密钥请替换为你自己的，或通过环境变量设置
"""
import os
import json
from dataclasses import dataclass, field, asdict

# ==================== API 配置 ====================

# Coindar (https://coindar.org 注册获取)
COINDAR_API_TOKEN = "your_coindar_api_token_here"

# Twitter / X 账号 (用于 twscrape)
TWITTER_USERNAME = "your_twitter_username_here"
TWITTER_PASSWORD = "your_twitter_password_here"
TWITTER_EMAIL = "your_twitter_email_here"
TWITTER_EMAIL_PASSWORD = "your_twitter_email_password_here"

# Telegram (https://my.telegram.org 申请，免费)
TELEGRAM_API_ID = 0  # your_telegram_api_id_here
TELEGRAM_API_HASH = "your_telegram_api_hash_here"
TELEGRAM_PHONE = "your_telegram_phone_here"

# ==================== 采集参数 ====================

# Twitter 关注的 KOL
TWITTER_KOLS = [
    # 项目创始人
    "VitalikButerin",
    # 交易所
    "binance",
    # 新闻媒体
    "WuBlockchain",
    # 链上资金流
    "lookonchain",
    # 巨鲸转账监控
    "whale_alert",
    # 市场观点
    "saylor",
]

# Twitter 搜索关键词
TWITTER_KEYWORDS = ["$BTC", "$ETH", "$SOL","$BNB","$XRP", "$DOGE",]

# Telegram 监听的群组/频道 (用户名或链接)
TELEGRAM_CHANNELS = [
    "binance_announcements",   # 币安公告
    "crypto",                  # 加密货币综合
    "Bitcoin",                 # 比特币频道
    "OKXAnnouncements",        # OKX 公告
    "whale_alert_io",          # 巨鲸监控
]

# ==================== 路径 ====================

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


# ==================== 统一数据模型 ====================

@dataclass
class Message:
    """所有数据源统一的消息格式"""
    source: str              # "coinmarketcal" / "twitter" / "telegram"
    content: str             # 消息内容
    timestamp: str           # ISO 格式时间
    author: str = ""
    url: str = ""
    mentioned_tokens: list = field(default_factory=list)
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    followers: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def save_messages(messages: list[Message], filename: str):
    """保存消息列表到 data/ 目录"""
    filepath = os.path.join(DATA_DIR, filename)
    data = [m.to_dict() for m in messages]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[保存] {len(data)} 条数据 -> {filepath}")
