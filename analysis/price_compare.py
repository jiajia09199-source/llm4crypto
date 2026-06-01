"""
情绪 vs 价格对比 + 可视化模块

功能：
1. 从情绪分析结果中提取涉及的代币
2. 调用 CoinGecko 免费 API 获取代币价格数据
3. 汇总每个代币的情绪得分与价格变化
4. 按代币类别分组分析
5. 计算情绪与价格的相关性
6. 生成可视化图表

CoinGecko Demo API:
- 免费，无需 API Key
- 限制: 约 30 次/分钟
"""
import json
import math
import time
import requests
from datetime import datetime, timezone
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import DATA_DIR

# 可视化输出目录
VIS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "visualization")
os.makedirs(VIS_DIR, exist_ok=True)


# ==================== CoinGecko API ====================

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

TOKEN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
    "LINK": "chainlink", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "ARB": "arbitrum", "OP": "optimism",
    "RENDER": "render-token", "NEAR": "near", "FIL": "filecoin",
    "AAVE": "aave", "PEPE": "pepe", "POL": "matic-network",
    "SUI": "sui", "SEI": "sei-network", "INJ": "injective-protocol",
}

# 代币类别分组
TOKEN_CATEGORIES = {
    "Major": ["BTC", "ETH"],
    "Exchange": ["BNB"],
    "Layer1": ["SOL", "ADA", "AVAX", "SUI", "SEI", "NEAR", "DOT", "ATOM"],
    "DeFi": ["UNI", "AAVE", "LINK", "INJ"],
    "Meme": ["DOGE", "PEPE"],
    "Layer2": ["ARB", "OP"],
    "Others": ["XRP", "LTC", "RENDER", "FIL", "POL"],
}
# ==================== 时间衰减配置 ====================
# 半衰期（小时）：消息权重降到 0.5 所需的时间
FRESHNESS_HALF_LIFE = {
    "twitter": 6,      # 推文生命周期最短
    "telegram": 12,    # 频道公告稍长
    "coindar": 48,     # 事件日历影响周期最长
    "cointelegraph": 12,  # RSS 新闻
    "coindesk": 12,       # RSS 新闻
    "default": 24,     # 默认半衰期
}

def get_token_category(symbol):
    for category, tokens in TOKEN_CATEGORIES.items():
        if symbol.upper() in tokens:
            return category
    return "其他"


def get_current_prices(symbols):
    ids = []
    symbol_to_id = {}
    for s in symbols:
        s_upper = s.upper()
        if s_upper in TOKEN_MAP:
            ids.append(TOKEN_MAP[s_upper])
            symbol_to_id[TOKEN_MAP[s_upper]] = s_upper
    if not ids:
        return {}
    params = {
        "ids": ",".join(ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }
    try:
        resp = requests.get(f"{COINGECKO_BASE_URL}/simple/price", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        for cg_id, symbol in symbol_to_id.items():
            if cg_id in data:
                result[symbol] = {
                    "price": data[cg_id].get("usd", 0),
                    "change_24h": data[cg_id].get("usd_24h_change", 0),
                    "volume_24h": data[cg_id].get("usd_24h_vol", 0),
                    "market_cap": data[cg_id].get("usd_market_cap", 0),
                }
        return result
    except requests.RequestException as e:
        print(f"[CoinGecko] 价格获取失败: {e}")
        return {}


def get_price_history(symbol, days=7):
    s_upper = symbol.upper()
    if s_upper not in TOKEN_MAP:
        return []
    cg_id = TOKEN_MAP[s_upper]
    try:
        resp = requests.get(
            f"{COINGECKO_BASE_URL}/coins/{cg_id}/market_chart",
            params={"vs_currency": "usd", "days": days}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [{"timestamp": datetime.fromtimestamp(ts / 1000).isoformat(), "price": round(p, 2)}
                for ts, p in data.get("prices", [])]
    except requests.RequestException as e:
        print(f"[CoinGecko] {symbol} 历史价格获取失败: {e}")
        return []


def get_freshness(source: str, hours_ago: float) -> float:
    """计算时间新鲜度（指数衰减）"""
    half_life = FRESHNESS_HALF_LIFE.get(source, FRESHNESS_HALF_LIFE["default"])
    freshness = 2 ** (-hours_ago / half_life)
    return max(freshness, 0.01)  # 最小值截断至 0.01


# ==================== 情绪汇总分析 ====================
def aggregate_sentiment(sentiment_results: list[dict]) -> dict:
    """按代币汇总情绪数据，计算等权和影响力加权情绪得分"""
    token_data = {}

    for r in sentiment_results:
        tokens = r.get("tokens", [])
        sentiment = r.get("sentiment", "neutral")
        score = r.get("sentiment_score", 0.5)
        importance = r.get("importance", 5)
        msg_type = r.get("message_type", "opinion")
        credibility = r.get("credibility", 5)
        source = r.get("source", "")
        extra = r.get("extra", {}) if isinstance(r.get("extra"), dict) else {}
        followers = r.get("followers", 0)
        likes = r.get("likes", 0)
        retweets = r.get("retweets", 0)
        replies = r.get("replies", 0)

        # 计算外部分（按数据源类型）
        if source == "twitter":
            views = extra.get("views", 0)
            ext = math.log(1 + followers) * (1 + math.log(1 + likes + retweets + replies + views))
            external_score = min(ext / 20, 1.0)
        elif source == "telegram":
            views = extra.get("views", 0)
            forwards = extra.get("forwards", 0)
            ext = math.log(1 + views) * (1 + math.log(1 + forwards))
            external_score = min(ext / 15, 1.0)
        elif source == "coindar":
            is_reliable = 1.0 if str(extra.get("source_reliable", "")).lower() == "true" else 0.5
            is_important = 1.5 if str(extra.get("important", "")).lower() == "true" else 1.0
            external_score = min(is_reliable * is_important, 1.0)
        elif source in ("cointelegraph", "coindesk"):
            external_score = 0.7
        else:
            external_score = 0.5

        # 内容分
        content_score = (credibility * importance) / 100

        # 时间新鲜度（指数衰减）
        try:
            msg_time = datetime.fromisoformat(r.get("timestamp", ""))
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            hours_ago = (datetime.now(timezone.utc) - msg_time).total_seconds() / 3600
            freshness = get_freshness(source, hours_ago)
        except:
            freshness = 0.5


        # Final influence = freshness × (0.4 × external + 0.6 × content)
        influence = freshness * (0.4 * external_score + 0.6 * content_score)

        influence = max(influence, 0.01)

        for token in tokens:
            token_upper = token.upper()
            if token_upper not in token_data:
                token_data[token_upper] = {
                    "scores": [], "importances": [], "credibilities": [],
                    "influences": [], "weighted_scores": [],
                    "bullish": 0, "bearish": 0, "neutral": 0, "total": 0,
                    "message_types": {},
                }
            td = token_data[token_upper]
            td["scores"].append(score)
            td["importances"].append(importance)
            td["credibilities"].append(credibility)
            td["influences"].append(influence)
            td["weighted_scores"].append(score * influence)
            td["total"] += 1
            td["message_types"][msg_type] = td["message_types"].get(msg_type, 0) + 1
            if sentiment == "bullish":
                td["bullish"] += 1
            elif sentiment == "bearish":
                td["bearish"] += 1
            else:
                td["neutral"] += 1

    for token, td in token_data.items():
        td["avg_score"] = round(sum(td["scores"]) / len(td["scores"]), 3)
        td["avg_importance"] = round(sum(td["importances"]) / len(td["importances"]), 1)
        td["avg_credibility"] = round(sum(td["credibilities"]) / len(td["credibilities"]), 1)
        td["category"] = get_token_category(token)

        # 影响力加权情绪得分
        total_weight = sum(td["influences"])
        td["weighted_avg_score"] = round(sum(td["weighted_scores"]) / total_weight, 3) if total_weight > 0 else td["avg_score"]

        if td["avg_score"] > 0.6:
            td["label"] = "偏看涨"
        elif td["avg_score"] < 0.4:
            td["label"] = "偏看跌"
        else:
            td["label"] = "中性"

    return token_data

# ==================== 可视化 ====================

def setup_plot_style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.sans-serif': ['SimHei', 'Microsoft YaHei', 'Arial', 'DejaVu Sans'],
        'axes.unicode_minus': False,
        'figure.facecolor': '#FAFAFA',
        'axes.facecolor': '#FAFAFA',
        'axes.edgecolor': '#CCCCCC',
        'axes.grid': True,
        'grid.alpha': 0.3,
        'grid.color': '#CCCCCC',
        'axes.spines.top': False,
        'axes.spines.right': False,
        'font.size': 11,
    })


def generate_visualizations(token_data, prices, sentiment_results):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[可视化] 请安装 matplotlib: pip install matplotlib")
        return

    setup_plot_style()

    valid_tokens = [t for t in token_data if t in prices and token_data[t]["total"] >= 3]
    valid_tokens.sort(key=lambda t: token_data[t]["total"], reverse=True)
    if not valid_tokens:
        print("[可视化] 无足够数据生成图表")
        return

    COLORS = {
        "bullish": "#5B9BD5",
        "bearish": "#ED7D31",
        "neutral": "#A5A5A5",
        "Major": "#4472C4",
        "Exchange": "#ED7D31",
        "Layer1": "#70AD47",
        "DeFi": "#7B7FB5",
        "Meme": "#FFC000",
        "Layer2": "#5B9BD5",
        "Others": "#A5A5A5",
    }

    # ===== 图1: 各代币情绪分布 =====
    top_tokens = valid_tokens[:12]
    fig, ax = plt.subplots(figsize=(13, 6))
    x = range(len(top_tokens))
    width = 0.25
    bars_bull = ax.bar([i - width for i in x], [token_data[t]["bullish"] for t in top_tokens],
                       width, label="Bullish", color=COLORS["bullish"], alpha=0.85, edgecolor="white")
    bars_neut = ax.bar(x, [token_data[t]["neutral"] for t in top_tokens],
                       width, label="Neutral", color=COLORS["neutral"], alpha=0.85, edgecolor="white")
    bars_bear = ax.bar([i + width for i in x], [token_data[t]["bearish"] for t in top_tokens],
                       width, label="Bearish", color=COLORS["bearish"], alpha=0.85, edgecolor="white")
    for bars in [bars_bull, bars_neut, bars_bear]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 1, str(int(h)),
                        ha="center", va="bottom", fontsize=8, color="#666666")
    ax.set_xlabel("Token", fontsize=11)
    ax.set_ylabel("Number of Messages", fontsize=11)
    ax.set_title("Sentiment Distribution by Token (Top 12)", fontsize=15, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(top_tokens, fontweight="bold", fontsize=10)
    ax.legend(fontsize=10, framealpha=0.9)
    plt.tight_layout()
    plt.savefig(os.path.join(VIS_DIR, "sentiment_distribution.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[可视化] 图1 已保存 -> sentiment_distribution.png")

    # ===== 图2: 按代币类别分组对比 =====
    # ===== 图2: 按代币类别分组对比（等权 + 加权 + 价格）=====
    category_data = {}
    for token in valid_tokens:
        td = token_data[token]
        cat = td["category"]
        if cat not in category_data:
            category_data[cat] = {
                "equal_scores": [],  # 等权得分
                "weighted_scores": [],  # 加权得分
                "changes": [],
                "counts": 0,
                "credibilities": []
            }
        category_data[cat]["equal_scores"].append(td["avg_score"])
        category_data[cat]["weighted_scores"].append(td["weighted_avg_score"])
        category_data[cat]["changes"].append(prices[token]["change_24h"])
        category_data[cat]["counts"] += td["total"]
        category_data[cat]["credibilities"].append(td["avg_credibility"])

    categories = []
    cat_equal_scores = []
    cat_weighted_scores = []
    cat_avg_changes = []
    cat_counts = []
    cat_colors = []
    for cat, cd in sorted(category_data.items(), key=lambda x: x[1]["counts"], reverse=True):
        categories.append(cat)
        cat_equal_scores.append(round(sum(cd["equal_scores"]) / len(cd["equal_scores"]), 3))
        cat_weighted_scores.append(round(sum(cd["weighted_scores"]) / len(cd["weighted_scores"]), 3))
        cat_avg_changes.append(round(sum(cd["changes"]) / len(cd["changes"]), 2))
        cat_counts.append(cd["counts"])
        cat_colors.append(COLORS.get(cat, "#546E7A"))

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 6))

    # 左图：等权情绪得分
    bars1 = ax1.barh(categories, cat_equal_scores, color=cat_colors, alpha=0.85, edgecolor="white", height=0.6)
    ax1.axvline(x=0.5, color="#999999", linestyle="--", linewidth=0.8)
    for i, (score, count) in enumerate(zip(cat_equal_scores, cat_counts)):
        ax1.text(score + 0.01, i, f"{score:.2f} ({count}msg)", va="center", fontsize=10, color="#333333")
    ax1.set_xlabel("Equal Weight Score", fontsize=11)
    ax1.set_title("Sentiment by Category (Equal Weight)", fontsize=13, fontweight="bold")
    ax1.set_xlim(0, 1)

    # 中图：加权情绪得分
    bars2 = ax2.barh(categories, cat_weighted_scores, color=cat_colors, alpha=0.85, edgecolor="white", height=0.6)
    ax2.axvline(x=0.5, color="#999999", linestyle="--", linewidth=0.8)
    for i, (score, count) in enumerate(zip(cat_weighted_scores, cat_counts)):
        ax2.text(score + 0.01, i, f"{score:.2f} ({count}msg)", va="center", fontsize=10, color="#333333")
    ax2.set_xlabel("Weighted Score", fontsize=11)
    ax2.set_title("Sentiment by Category (Weighted)", fontsize=13, fontweight="bold")
    ax2.set_xlim(0, 1)

    # 右图：价格变化
    bar_colors_change = [COLORS["bullish"] if c > 0 else COLORS["bearish"] for c in cat_avg_changes]
    bars3 = ax3.barh(categories, cat_avg_changes, color=bar_colors_change, alpha=0.85, edgecolor="white", height=0.6)
    ax3.axvline(x=0, color="#999999", linestyle="-", linewidth=0.8)
    for i, change in enumerate(cat_avg_changes):
        if abs(change) < 0.5:
            ax3.text(change + 0.3, i, f"{change:+.1f}%", va="center", fontsize=10, color="#333333")
        elif change < 0:
            ax3.text(change - 0.1, i, f"{change:+.1f}%", va="center", fontsize=10, color="#333333", ha="right")
        else:
            ax3.text(change + 0.1, i, f"{change:+.1f}%", va="center", fontsize=10, color="#333333")
    ax3.set_xlabel("24h Price Change (%)", fontsize=11)
    ax3.set_title("Price Change by Category", fontsize=13, fontweight="bold")

    fig.suptitle("Token Category Analysis: Equal Weight vs Weighted Sentiment vs Price", fontsize=15, fontweight="bold",
                 y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(VIS_DIR, "category_analysis.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[可视化] 图2 已保存 -> category_analysis.png")

    # ===== 各代币情绪得分 vs 价格变化（等权 + 加权）=====
    top_compare = valid_tokens[:15]
    x = range(len(top_compare))
    scores_vals_equal = [token_data[t]["avg_score"] for t in top_compare]
    scores_vals_weighted = [token_data[t]["weighted_avg_score"] for t in top_compare]
    changes_vals = [prices[t]["change_24h"] for t in top_compare]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True,
                                        gridspec_kw={"height_ratios": [1, 1, 1], "hspace": 0.08})

    # 上图：等权情绪得分
    ax1.bar(x, scores_vals_equal, color="#5B9BD5", alpha=0.85, edgecolor="white", width=0.6)
    for i, s in enumerate(scores_vals_equal):
        ax1.text(i, s + 0.02, f"{s:.2f}", ha="center", fontsize=8, color="#333333")
    ax1.set_ylabel("Equal Weight Score", fontsize=11)
    ax1.set_ylim(0, 1)
    ax1.axhline(y=0.5, color="#999999", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.set_title("Sentiment Score vs Price Change by Token (Top 15)", fontsize=15, fontweight="bold", pad=10)

    # 中图：加权情绪得分
    ax2.bar(x, scores_vals_weighted, color="#70AD47", alpha=0.85, edgecolor="white", width=0.6)
    for i, s in enumerate(scores_vals_weighted):
        ax2.text(i, s + 0.02, f"{s:.2f}", ha="center", fontsize=8, color="#333333")
    ax2.set_ylabel("Weighted Score", fontsize=11)
    ax2.set_ylim(0, 1)
    ax2.axhline(y=0.5, color="#999999", linestyle="--", linewidth=0.8, alpha=0.5)

    # 下图：价格变化
    bar_colors = ["#70AD47" if c >= 0 else "#ED7D31" for c in changes_vals]
    ax3.bar(x, changes_vals, color=bar_colors, alpha=0.85, edgecolor="white", width=0.6)
    for i, c in enumerate(changes_vals):
        offset = 0.3 if c >= 0 else -0.3
        ax3.text(i, c + offset, f"{c:+.1f}%", ha="center", fontsize=8, color="#333333")
    ax3.set_ylabel("24h Price Change (%)", fontsize=11)
    ax3.axhline(y=0, color="#999999", linestyle="-", linewidth=0.8)
    ax3.set_xticks(x)
    ax3.set_xticklabels(top_compare, fontweight="bold", fontsize=10)

    plt.tight_layout()
    plt.savefig(os.path.join(VIS_DIR, "token_sentiment_vs_price.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[可视化] 已保存 -> token_sentiment_vs_price.png")


# ==================== 生成报告 ====================

def generate_report(token_data, prices, sentiment_results):
    lines = []
    lines.append("=" * 60)
    lines.append("LLM 情绪分析 vs 实际价格变化 对比报告")
    lines.append("=" * 60)

    valid = [(t, td) for t, td in token_data.items() if t in prices and td["total"] >= 3]
    valid.sort(key=lambda x: x[1]["total"], reverse=True)

    total_messages = sum(td["total"] for _, td in valid)
    lines.append(f"\n涉及代币: {len(valid)} 个")
    lines.append(f"分析消息: {total_messages} 条\n")

    for token, td in valid:
        p = prices[token]
        lines.append(f"--- {token} [{td['category']}] ---")
        lines.append(f"  当前价格: ${p['price']:,.2f} | 24h变化: {p['change_24h']:+.2f}%")
        lines.append(f"  平均情绪得分: {td['avg_score']} ({td['label']})")
        lines.append(f"  加权情绪得分: {td['weighted_avg_score']} (结合可信度与重要性加权)")
        lines.append(f"  平均可信度: {td['avg_credibility']}/10")
        lines.append(f"  消息分布: {td['total']} 条 (看涨 {td['bullish']} / 看跌 {td['bearish']} / 中性 {td['neutral']})")
        lines.append(f"  平均重要性: {td['avg_importance']}/10")
        lines.append("")

    lines.append("=" * 60)
    lines.append("按代币类别分析")
    lines.append("=" * 60)

    category_stats = {}
    for token, td in valid:
        cat = td["category"]
        if cat not in category_stats:
            category_stats[cat] = {"scores": [], "changes": [], "total": 0, "credibilities": []}
        category_stats[cat]["scores"].append(td["avg_score"])
        category_stats[cat]["changes"].append(prices[token]["change_24h"])
        category_stats[cat]["total"] += td["total"]
        category_stats[cat]["credibilities"].append(td["avg_credibility"])

    for cat, cs in sorted(category_stats.items(), key=lambda x: x[1]["total"], reverse=True):
        avg_s = round(sum(cs["scores"]) / len(cs["scores"]), 3)
        avg_c = round(sum(cs["changes"]) / len(cs["changes"]), 2)
        avg_cr = round(sum(cs["credibilities"]) / len(cs["credibilities"]), 1)
        lines.append(f"\n{cat}: {cs['total']} 条消息")
        lines.append(f"  平均情绪: {avg_s} | 平均涨跌幅: {avg_c:+.2f}% | 平均可信度: {avg_cr}/10")

    lines.append("\n" + "=" * 60)
    lines.append("整体分析")
    lines.append("=" * 60)

    if valid:
        all_scores = [td["avg_score"] for _, td in valid]
        all_changes = [prices[t]["change_24h"] for t, _ in valid]
        overall_avg_score = round(sum(all_scores) / len(all_scores), 3)

        n = len(all_scores)
        if n >= 3:
            mean_s = sum(all_scores) / n
            mean_c = sum(all_changes) / n
            cov = sum((s - mean_s) * (c - mean_c) for s, c in zip(all_scores, all_changes)) / n
            std_s = (sum((s - mean_s) ** 2 for s in all_scores) / n) ** 0.5
            std_c = (sum((c - mean_c) ** 2 for c in all_changes) / n) ** 0.5
            correlation = round(cov / (std_s * std_c), 3) if std_s > 0 and std_c > 0 else 0
        else:
            correlation = 0

        total_bullish = sum(td["bullish"] for _, td in valid)
        total_bearish = sum(td["bearish"] for _, td in valid)
        total_neutral = sum(td["neutral"] for _, td in valid)

        lines.append(f"\n整体平均情绪得分: {overall_avg_score}")
        lines.append(f"情绪分布: 看涨 {total_bullish} / 看跌 {total_bearish} / 中性 {total_neutral}")
        lines.append(f"情绪与价格相关系数: {correlation}")

        if correlation > 0.3:
            lines.append("\n结论: 情绪得分与价格变化呈正相关，社区情绪在一定程度上反映了市场走势。")
        elif correlation < -0.3:
            lines.append("\n结论: 情绪得分与价格变化呈负相关，存在\"反向指标\"现象——社区过度乐观时价格反而下跌。")
        else:
            lines.append("\n结论: 情绪得分与价格变化相关性较弱，短期价格受多种因素影响，单一社交媒体情绪信号不足以预测走势。")

        type_stats = {}
        for r in sentiment_results:
            mt = r.get("message_type", "opinion")
            type_stats[mt] = type_stats.get(mt, 0) + 1
        lines.append(f"\n消息类型分布:")
        for mt, count in sorted(type_stats.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {mt}: {count} 条 ({count/len(sentiment_results)*100:.1f}%)")

        lines.append("\n可能的改进方向:")
        lines.append("  1. 加权高影响力账号的情绪（粉丝数 > 100K 的 KOL）")
        lines.append("  2. 综合多天数据观察情绪趋势变化而非单一时间点快照")
        lines.append("  3. 结合链上数据（交易量、巨鲸转账）增强信号")
        lines.append("  4. 区分消息类型（新闻 vs 个人观点 vs 分析）给予不同权重")
        lines.append("  5. 对高可信度消息赋予更大权重")

    lines.append("=" * 60)
    return "\n".join(lines)


# ==================== 主流程 ====================

def run_comparison():
    print("=" * 50)
    print("[价格对比] 开始...")

    sentiment_file = os.path.join(DATA_DIR, "sentiment_results.json")
    if not os.path.exists(sentiment_file):
        print(f"[价格对比] 未找到 {sentiment_file}，请先运行情绪分析模块")
        return

    with open(sentiment_file, "r", encoding="utf-8") as f:
        sentiment_results = json.load(f)

    print(f"[价格对比] 加载 {len(sentiment_results)} 条情绪分析结果")

    token_data = aggregate_sentiment(sentiment_results)
    print(f"[价格对比] 涉及代币: {sorted(token_data.keys())}")

    print("[价格对比] 获取价格数据...")
    prices = get_current_prices(list(token_data.keys()))
    if not prices:
        print("[价格对比] 未获取到价格数据")
        return

    for symbol, data in sorted(prices.items()):
        print(f"  {symbol}: ${data['price']:,.2f} ({data['change_24h']:+.2f}%)")

    comparison_data = []
    for token, td in token_data.items():
        if token in prices:
            comparison_data.append({
                "token": token, "category": td["category"],
                "avg_sentiment_score": td["avg_score"], "sentiment_label": td["label"],
                "avg_credibility": td["avg_credibility"],
                "bullish": td["bullish"], "bearish": td["bearish"], "neutral": td["neutral"],
                "total_messages": td["total"], "avg_importance": td["avg_importance"],
                "price_usd": prices[token]["price"], "change_24h": prices[token]["change_24h"],
            })
    comparison_data.sort(key=lambda x: x["total_messages"], reverse=True)

    output_file = os.path.join(DATA_DIR, "price_comparison.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, ensure_ascii=False, indent=2)
    print(f"\n[价格对比] 详细数据已保存 -> {output_file}")

    print("\n[价格对比] 获取历史价格...")
    history = {}
    top_tokens = sorted(prices.keys(), key=lambda t: token_data.get(t, {}).get("total", 0), reverse=True)[:5]
    for token in top_tokens:
        history[token] = get_price_history(token, days=7)
        if history[token]:
            print(f"  {token}: {len(history[token])} 个数据点")
        time.sleep(5)

    history_file = os.path.join(DATA_DIR, "price_history.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"[价格对比] 历史价格已保存 -> {history_file}")

    report = generate_report(token_data, prices, sentiment_results)
    print(f"\n{report}")

    report_file = os.path.join(DATA_DIR, "comparison_report.txt")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[价格对比] 报告已保存 -> {report_file}")

    print("\n[可视化] 生成图表...")
    generate_visualizations(token_data, prices, sentiment_results)
    print("[可视化] 完成")


if __name__ == "__main__":
    run_comparison()