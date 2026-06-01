"""
数据清洗与预处理模块

清洗步骤：
1. 去除纯表情消息
2. 去除纯标点消息
3. 去除广告（综合评分机制）
4. 模糊去重（余弦相似度，覆盖同平台和跨平台）
5. 代币提取（三层匹配 + CoinGecko 代币列表）
6. URL 清洗
7. 信息熵过滤（过滤低信息量消息）
8. 去除短文本（跳过 Coindar 事件数据）
"""
import hashlib
import re
import json
import math
import requests
from collections import Counter
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import Message, DATA_DIR, save_messages


# ==================== 1. 去除纯表情消息 ====================

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)


def is_emoji_only(text: str) -> bool:
    """判断消息是否为纯表情"""
    cleaned = EMOJI_PATTERN.sub("", text).strip()
    return len(cleaned) == 0


# ==================== 2. 去除纯标点消息 ====================

def is_punctuation_only(text: str) -> bool:
    """过滤纯标点符号消息"""
    cleaned = EMOJI_PATTERN.sub("", text).strip()
    import string
    no_punct = cleaned.translate(str.maketrans("", "", string.punctuation + "。，！？、；：""''（）【】…—"))
    no_punct = no_punct.replace(" ", "").replace("\n", "").replace("\t", "")
    return len(no_punct) == 0 and len(cleaned) > 0


# ==================== 3. 去除广告 ====================

AD_KEYWORDS_HIGH = [
    "guaranteed profit", "100x", "1000x",
    "send btc to", "send eth to",
    "free airdrop",
]
AD_KEYWORDS_MEDIUM = [
    "join now", "sign up", "register now", "click here",
    "limited time offer", "act now", "don't miss",
    "earn daily", "passive income",
    "dm me", "dm for",
    "promo code", "referral",
    "deposit bonus", "sign up now", "vip",
    "no kyc",
]

URL_DENSITY_PATTERN = re.compile(r'https?://\S+|t\.me/\S+|discord\.gg/\S+', re.IGNORECASE)


def calc_link_density(text: str) -> float:
    """计算链接密度"""
    if not text:
        return 0.0
    links = URL_DENSITY_PATTERN.findall(text)
    link_chars = sum(len(link) for link in links)
    return link_chars / len(text)


def calc_emoji_density(text: str) -> float:
    """计算表情密度"""
    if not text:
        return 0.0
    emojis = EMOJI_PATTERN.findall(text)
    emoji_chars = sum(len(e) for e in emojis)
    return emoji_chars / len(text)


def is_advertisement(text: str) -> bool:
    """综合评分判断广告"""
    score = 0
    text_lower = text.lower()

    for kw in AD_KEYWORDS_HIGH:
        if kw in text_lower:
            score += 3
    for kw in AD_KEYWORDS_MEDIUM:
        if kw in text_lower:
            score += 1

    if calc_link_density(text) > 0.2:
        score += 2

    if calc_emoji_density(text) > 0.15:
        score += 1
    if calc_emoji_density(text) > 0.3:
        score += 2

    if text == text.upper() and text.count("!") >= 3 and len(text) > 20:
        score += 2

    return score >= 4


# ==================== 4. 去重 ====================

# **********精确去重（MD5）***********
#减少计算
def deduplicate(messages: list[Message]) -> list[Message]:
    """
    基于内容 hash 去重
    相同内容只保留第一条（最早出现的）
    """
    seen_hashes = set()
    unique_messages = []

    for msg in messages:
        # 对内容做归一化后再 hash（去除首尾空格、统一小写）
        normalized = msg.content.strip().lower()
        content_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()

        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique_messages.append(msg)

    removed = len(messages) - len(unique_messages)
    if removed > 0:
        print(f"  [精确去重] 移除 {removed} 条重复内容")

    return unique_messages

# **********模糊去重（余弦相似度）***********
def fuzzy_deduplicate(messages: list[Message], similarity_threshold: float = 0.85) -> list[Message]:
    """
    模糊去重：使用余弦相似度检测内容相似的消息
    覆盖同平台精确重复和跨平台措辞不同但内容相似的情况
    相似度超过阈值时，保留互动量最高的那条
    """
    def tokenize(text):
        clean = EMOJI_PATTERN.sub("", text).lower()
        clean = re.sub(r'https?://\S+', '', clean)
        clean = re.sub(r'[^\w\s]', ' ', clean)
        return clean.split()

    def cosine_similarity(tokens_a, tokens_b):
        all_words = set(tokens_a + tokens_b)
        if not all_words:
            return 0.0
        vec_a = Counter(tokens_a)
        vec_b = Counter(tokens_b)
        dot = sum(vec_a[w] * vec_b[w] for w in all_words)
        norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def engagement(msg):
        return msg.likes + msg.retweets + msg.replies

    tokenized = [(msg, tokenize(msg.content)) for msg in messages]
    removed_indices = set()

    for i in range(len(tokenized)):
        if i in removed_indices:
            continue
        for j in range(i + 1, len(tokenized)):
            if j in removed_indices:
                continue
            msg_i, tokens_i = tokenized[i]
            msg_j, tokens_j = tokenized[j]

            sim = cosine_similarity(tokens_i, tokens_j)
            if sim >= similarity_threshold:
                if engagement(msg_i) >= engagement(msg_j):
                    removed_indices.add(j)
                else:
                    removed_indices.add(i)
                    break

    unique = [msg for idx, (msg, _) in enumerate(tokenized) if idx not in removed_indices]
    removed = len(messages) - len(unique)
    if removed > 0:
        print(f"  [模糊去重] 移除 {removed} 条相似内容（含跨平台重复）")
    return unique


# ==================== 5. 代币提取 ====================

BUILTIN_TOKENS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
    "DOT", "MATIC", "LINK", "UNI", "ATOM", "LTC", "ARB", "OP",
    "APT", "SUI", "SEI", "TIA", "INJ", "FET", "RENDER", "NEAR",
    "FIL", "AAVE", "MKR", "CRV", "SNX", "COMP", "PEPE", "WIF",
    "BONK", "SHIB", "FLOKI", "POL", "IMX", "SAND", "MANA", "AXS",
}

WORD_PATTERN = re.compile(r"\b([A-Z]{2,10})\b")


def fetch_coingecko_token_list() -> set:
    """从 CoinGecko 获取完整代币 symbol 列表"""
    try:
        print("  [代币列表] 从 CoinGecko 获取...")
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/list",
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json()
        symbols = {c["symbol"].upper() for c in coins}
        print(f"  [代币列表] 获取到 {len(symbols)} 个代币")
        return symbols
    except Exception as e:
        print(f"  [代币列表] CoinGecko 请求失败: {e}，使用内置列表")
        return BUILTIN_TOKENS


def extract_tokens(text: str, valid_tokens: set) -> list[str]:
    """从文本中提取提及的代币符号（三层匹配）"""
    found = set()

    common_words = {
        "THE", "AND", "FOR", "NOT", "BUT", "ALL", "CAN", "HAS", "HER",
        "WAS", "ONE", "OUR", "OUT", "ARE", "HIS", "HOW", "ITS", "MAY",
        "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "GET", "LET",
        "SAY", "SHE", "TOO", "USE", "NFT", "CEO", "SEC", "ETF", "API",
        "USD", "EUR", "JPY", "ATH", "ATL", "APR", "APY", "TVL", "DEX",
        "IMO", "ACC", "VIP", "WAR", "PRE", "STATE", "IN", "ON", "AT",
        "UP", "SO", "IF", "OR", "NO", "GO", "DO", "BE", "BY", "TO",
        "AI", "US", "AN", "AS", "IS", "IT", "OF", "AM", "PM",
        "GOLD", "OIL", "GAS", "CAD", "GBP", "JUST", "BACK",
    }

    # 1. 匹配 $BTC 格式（大小写兼容）
    cashtags = re.findall(r'\$([A-Za-z]{2,10})\b', text)
    for tag in cashtags:
        upper_tag = tag.upper()
        if upper_tag in valid_tokens and upper_tag not in common_words:
            found.add(upper_tag)

    # 2. 匹配大写单词与代币列表交集
    words = WORD_PATTERN.findall(text)
    for word in words:
        if word in valid_tokens and word not in common_words:
            found.add(word)

    # 3. 匹配代币全名
    name_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "cardano": "ADA", "dogecoin": "DOGE", "ripple": "XRP",
        "chainlink": "LINK", "polkadot": "DOT", "avalanche": "AVAX",
        "arbitrum": "ARB", "uniswap": "UNI", "litecoin": "LTC",
    }
    text_lower = text.lower()
    for name, symbol in name_map.items():
        if name in text_lower:
            found.add(symbol)

    return sorted(found)


# ==================== 6. URL 清洗 ====================

URL_CLEAN_PATTERN = re.compile(r'https?://[^\s,，。!！?？\)）]+')


def clean_urls(text: str) -> str:
    """将消息中的 URL 替换为 [link]"""
    return URL_CLEAN_PATTERN.sub("[link]", text).strip()


# ==================== 7. 信息熵过滤 ====================

def calc_entropy(text: str) -> float:
    """计算文本信息熵，衡量内容丰富度"""
    text_clean = EMOJI_PATTERN.sub("", text).strip().lower()
    if len(text_clean) < 5:
        return 0.0
    counter = Counter(text_clean)
    length = len(text_clean)
    entropy = 0.0
    for count in counter.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 3)


def is_low_entropy(text: str, threshold: float = 2.0) -> bool:
    """信息熵低于阈值的消息为低质量内容"""
    return calc_entropy(text) < threshold


# ==================== 8. 短文本过滤 ====================

def is_too_short(text: str, min_length: int = 10) -> bool:
    """过滤无信息量的短文本"""
    cleaned = EMOJI_PATTERN.sub("", text).strip()
    return len(cleaned) < min_length


# ==================== 主清洗流程 ====================

def clean_messages(messages: list[Message]) -> list[Message]:
    """完整清洗流程：8 步"""
    print(f"\n[清洗] 开始处理 {len(messages)} 条消息...")
    original_count = len(messages)

    valid_tokens = fetch_coingecko_token_list()

    # 步骤 1: 去除纯表情消息
    cleaned = []
    emoji_removed = 0
    for msg in messages:
        if is_emoji_only(msg.content):
            emoji_removed += 1
        else:
            cleaned.append(msg)
    print(f"  [纯表情] 移除 {emoji_removed} 条")

    # 步骤 2: 去除纯标点消息
    non_punct = []
    punct_removed = 0
    for msg in cleaned:
        if is_punctuation_only(msg.content):
            punct_removed += 1
        else:
            non_punct.append(msg)
    print(f"  [纯标点] 移除 {punct_removed} 条")

    # 步骤 3: 去除广告
    non_ad = []
    ad_removed = 0
    for msg in non_punct:
        if is_advertisement(msg.content):
            ad_removed += 1
        else:
            non_ad.append(msg)
    print(f"  [广告] 移除 {ad_removed} 条")

    # 步骤 4: 模糊去重
    unique =deduplicate(non_ad)
    unique = fuzzy_deduplicate(unique)

    # 步骤 5: 代币提取
    enriched_count = 0
    for msg in unique:
        if not msg.mentioned_tokens:
            tokens = extract_tokens(msg.content, valid_tokens)
            if tokens:
                msg.mentioned_tokens = tokens
                enriched_count += 1
    print(f"  [代币提取] 为 {enriched_count} 条消息补充了代币标签")

    # 步骤 6: URL 清洗
    for msg in unique:
        msg.content = clean_urls(msg.content)
    print(f"  [URL清洗] 已将所有链接替换为 [link]")

    # 步骤 7: 信息熵过滤（跳过 Coindar）
    non_low_entropy = []
    entropy_removed = 0
    for msg in unique:
        if msg.source != "coindar" and is_low_entropy(msg.content):
            entropy_removed += 1
        else:
            non_low_entropy.append(msg)
    print(f"  [信息熵] 移除 {entropy_removed} 条低信息量消息")

    # 步骤 8: 去除短文本（跳过 Coindar）
    non_short = []
    short_removed = 0
    for msg in non_low_entropy:
        if msg.source != "coindar" and is_too_short(msg.content):
            short_removed += 1
        else:
            non_short.append(msg)
    print(f"  [短文本] 移除 {short_removed} 条")

    # 总结
    total_removed = original_count - len(non_short)
    print(f"[清洗] 完成: {original_count} -> {len(non_short)} 条 (移除 {total_removed} 条)")

    return non_short


def load_and_clean():
    """从 data/ 加载所有原始数据，清洗后保存"""
    all_messages = []

    raw_files = [
        "coindar.json",
        "twitter.json",
        "telegram.json",
        "coindesk.json",
        "cointelegraph.json",
    ]

    for filename in raw_files:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"[跳过] {filename} 不存在")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for d in data:
            all_messages.append(Message(**d))
        print(f"[加载] {filename}: {len(data)} 条")

    if not all_messages:
        print("[清洗] 没有找到任何数据文件，请先运行采集模块")
        return []

    cleaned = clean_messages(all_messages)
    save_messages(cleaned, "cleaned_all.json")

    return cleaned


if __name__ == "__main__":
    results = load_and_clean()