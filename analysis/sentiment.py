"""
LLM 情绪分析模块

功能：
1. 读取清洗后的消息数据
2. 调用 LLM 对每条消息进行结构化分析：
3. 保存分析结果

"""
import json
import time
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import Message, DATA_DIR

# ==================== LLM API 配置 ====================
LLM_API_KEY = "tp-cvigmfv2x24rmjq4o0vu7ho5riu22rme83hoeramdu9m3taa"
LLM_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
LLM_MODEL = "mimo-v2.5-pro"

# ==================== Prompt 模板 ====================

ANALYSIS_PROMPT = """你是一个加密货币市场分析师。请对以下消息进行结构化分析。

消息内容：
{content}

消息来源：{source}
消息时间：{timestamp}
作者：{author}

请严格按以下 JSON 格式返回分析结果（不要返回任何其他内容）：
{{
    "is_crypto_related": true/false,
    "tokens": ["代币符号列表，如 BTC, ETH"],
    "sentiment": "bullish/bearish/neutral",
    "sentiment_score": 0.0到1.0之间的数值(0=极度看跌, 0.5=中性, 1.0=极度看涨),
    "time_horizon": "short-term/medium-term/long-term",
    "importance": 1到10的整数,
    "message_type": "news/analysis/opinion/announcement/rumor",
    "credibility": 1到10的整数(1=纯情绪无依据, 10=有数据/官方来源支撑),
    "summary": "一句话总结该消息的核心信息",
    "reasoning": "简要说明判断依据"
}}

说明：
- time_horizon: short-term=24小时内影响, medium-term=1周内影响, long-term=1个月以上影响
- importance: 1=无关紧要, 5=一般关注, 10=重大事件
- 如果消息与加密货币无关，is_crypto_related 设为 false，其他字段仍需填写
- message_type: news=新闻报道, analysis=技术分析, opinion=个人观点, announcement=官方公告, rumor=传闻
- credibility: 1=纯情绪无依据, 5=有一定逻辑但缺乏来源, 10=有数据支撑或官方来源"""


# ==================== 批量分析 Prompt ====================

BATCH_PROMPT = """你是一个加密货币市场分析师。请对以下多条消息逐一进行结构化分析。

{messages_block}

请严格按以下 JSON 格式返回分析结果数组（不要返回任何其他内容）：
[
    {{
        "message_index": 0,
        "is_crypto_related": true/false,
        "tokens": ["代币符号列表"],
        "sentiment": "bullish/bearish/neutral",
        "sentiment_score": 0.0到1.0之间的数值,
        "time_horizon": "short-term/medium-term/long-term",
        "importance": 1到10的整数,
        "message_type": "news/analysis/opinion/announcement/rumor",
        "credibility": 1到10的整数(1=纯情绪无依据, 10=有数据/官方来源支撑),
        "summary": "一句话总结",
        "reasoning": "判断依据"
    }},
    ...
]"""


# ==================== LLM 调用函数 ====================
def call_llm(prompt: str) -> str:
    """通用 LLM 调用（兼容所有 OpenAI 接口格式的 API）"""
    if not LLM_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except ImportError:
        print("  [LLM] 请安装 openai: pip install openai")
        return ""
    except Exception as e:
        print(f"  [LLM] 调用失败: {e}")
        return ""

# ==================== 基于规则的后备分析 ====================

# 看涨/看跌关键词
BULLISH_KEYWORDS = [
    "bullish", "moon", "pump", "rally", "breakout", "ath", "all-time high",
    "surged", "soared", "upgrade", "launch", "partnership", "adoption",
    "institutional", "accumulation", "inflows", "buy", "long",
    "看涨", "利好", "突破", "新高", "暴涨", "上线",
]

BEARISH_KEYWORDS = [
    "bearish", "dump", "crash", "drop", "sell", "short", "liquidation",
    "hack", "exploit", "vulnerability", "sec", "lawsuit", "ban",
    "delist", "unlock", "outflows", "fear", "panic", "scam",
    "看跌", "利空", "暴跌", "下架", "清算", "监管",
]


def rule_based_analysis(msg: Message) -> dict:
    """无 LLM API 时的后备分析方案：基于关键词规则"""
    content_lower = msg.content.lower()

    # 情绪判断
    bull_score = sum(1 for kw in BULLISH_KEYWORDS if kw in content_lower)
    bear_score = sum(1 for kw in BEARISH_KEYWORDS if kw in content_lower)

    if bull_score > bear_score:
        sentiment = "bullish"
        sentiment_score = min(0.5 + bull_score * 0.1, 1.0)
    elif bear_score > bull_score:
        sentiment = "bearish"
        sentiment_score = max(0.5 - bear_score * 0.1, 0.0)
    else:
        sentiment = "neutral"
        sentiment_score = 0.5

    # 重要性评分（基于互动量和来源）
    importance = 3  # 基础分
    if msg.followers > 1000000:
        importance += 3
    elif msg.followers > 100000:
        importance += 2
    elif msg.followers > 10000:
        importance += 1

    total_engagement = msg.likes + msg.retweets + msg.replies
    if total_engagement > 10000:
        importance += 2
    elif total_engagement > 1000:
        importance += 1

    importance = min(importance, 10)

    # 时间尺度
    time_horizon = "short-term"
    long_term_keywords = ["etf", "regulation", "halving", "upgrade", "roadmap", "2027", "2028"]
    medium_term_keywords = ["unlock", "airdrop", "launch", "listing", "fork"]
    if any(kw in content_lower for kw in long_term_keywords):
        time_horizon = "long-term"
    elif any(kw in content_lower for kw in medium_term_keywords):
        time_horizon = "medium-term"

    return {
        "is_crypto_related": True,
        "tokens": msg.mentioned_tokens,
        "sentiment": sentiment,
        "sentiment_score": round(sentiment_score, 2),
        "time_horizon": time_horizon,
        "importance": importance,
        "message_type": "opinion",
        "credibility": 5,
        "summary": msg.content[:100],
        "reasoning": f"基于规则分析: 看涨词{bull_score}个, 看跌词{bear_score}个",
    }


# ==================== 解析 LLM 返回 ====================

def parse_llm_response(response_text: str) -> dict | list | None:
    """解析 LLM 返回的 JSON"""
    if not response_text:
        return None

    # 清理可能的 markdown 代码块标记
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [LLM] JSON 解析失败: {e}")
        return None


# ==================== 主分析流程 ====================

def analyze_single(msg: Message) -> dict:
    """分析单条消息"""
    prompt = ANALYSIS_PROMPT.format(
        content=msg.content,
        source=msg.source,
        timestamp=msg.timestamp,
        author=msg.author,
    )

    response = call_llm(prompt)
    result = parse_llm_response(response)

    if result:
        return result
    else:
        return rule_based_analysis(msg)


def analyze_batch(messages: list[Message], batch_size: int = 5) -> list[dict]:
    """
    批量分析消息（节省 API 调用次数）
    每次发 batch_size 条给 LLM 一起分析
    """
    all_results = []

    for i in range(0, len(messages), batch_size):
        batch = messages[i:i + batch_size]

        # 构建批量消息文本
        messages_block = ""
        for idx, msg in enumerate(batch):
            messages_block += f"\n--- 消息 {idx} ---\n"
            messages_block += f"来源: {msg.source}\n"
            messages_block += f"时间: {msg.timestamp}\n"
            messages_block += f"作者: {msg.author}\n"
            messages_block += f"内容: {msg.content}\n"

        prompt = BATCH_PROMPT.format(messages_block=messages_block)
        response = call_llm(prompt)
        results = parse_llm_response(response)

        if results and isinstance(results, list):
            for idx, msg in enumerate(batch):
                if idx < len(results):
                    result = results[idx]
                else:
                    result = rule_based_analysis(msg)
                result["original_content"] = msg.content
                result["source"] = msg.source
                result["timestamp"] = msg.timestamp
                result["author"] = msg.author
                all_results.append(result)
        else:
            for msg in batch:
                result = rule_based_analysis(msg)
                result["original_content"] = msg.content
                result["source"] = msg.source
                result["timestamp"] = msg.timestamp
                result["author"] = msg.author
                all_results.append(result)

        print(f"  [分析] 已处理 {min(i + batch_size, len(messages))}/{len(messages)} 条")
        time.sleep(1)

    return all_results


def run_analysis():
    """主入口：读取清洗后数据 -> 分析 -> 保存结果"""
    print("=" * 50)
    print("[情绪分析] 开始...")

    # 读取清洗后的数据
    cleaned_file = os.path.join(DATA_DIR, "cleaned_all.json")
    if not os.path.exists(cleaned_file):
        print(f"[情绪分析] 未找到 {cleaned_file}，请先运行清洗模块")
        return []

    with open(cleaned_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = [Message(**d) for d in data]
    print(f"[情绪分析] 加载 {len(messages)} 条消息")

    # 判断使用哪种分析方式
    if LLM_API_KEY:
        print("[情绪分析] 使用LLM批量分析")
        results = analyze_batch(messages, batch_size=5)
    else:
        print("[情绪分析] 未配置 LLM API Key，使用基于规则的分析")
        results = []
        for msg in messages:
            result = rule_based_analysis(msg)
            result["original_content"] = msg.content
            result["source"] = msg.source
            result["timestamp"] = msg.timestamp
            result["author"] = msg.author
            results.append(result)
        print(f"  [分析] 已处理 {len(results)}/{len(messages)} 条")

    # 保存结果
    output_file = os.path.join(DATA_DIR, "sentiment_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[情绪分析] 结果已保存 -> {output_file}")

    # 打印统计
    bullish = sum(1 for r in results if r.get("sentiment") == "bullish")
    bearish = sum(1 for r in results if r.get("sentiment") == "bearish")
    neutral = sum(1 for r in results if r.get("sentiment") == "neutral")
    avg_importance = sum(r.get("importance", 0) for r in results) / len(results) if results else 0

    print(f"\n[统计]")
    print(f"  看涨: {bullish} 条 | 看跌: {bearish} 条 | 中性: {neutral} 条")
    print(f"  平均重要性: {avg_importance:.1f}/10")

    return results


if __name__ == "__main__":
    results = run_analysis()
