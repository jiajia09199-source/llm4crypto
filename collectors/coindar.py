"""
数据源 1: Coindar 事件日历采集（替代 CoinMarketCal）
文档: https://coindar.org/en/api

由于 CoinMarketCal API 注册受限（邮件服务故障），使用功能相同的 Coindar 平台替代。
两者都是加密货币事件日历，采集的数据类型一致：事件标题、涉及代币、事件日期、事件分类。
"""
import requests
import time
from datetime import datetime, timedelta
import sys, os
from config import COINDAR_API_TOKEN

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import Message, save_messages

# Coindar URL
COINDAR_BASE_URL = "https://coindar.org/api/v2"


def fetch_coin_list() -> dict:
    """获取代币列表，建立 coin_id -> symbol/name 映射"""
    try:
        resp = requests.get(
            f"{COINDAR_BASE_URL}/coins",
            params={"access_token": COINDAR_API_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json()
        coin_map = {}
        for c in coins:
            coin_map[str(c.get("id", ""))] = {
                "symbol": c.get("symbol", ""),
                "name": c.get("name", ""),
            }
        print(f"[Coindar] 获取代币列表: {len(coin_map)} 个代币")
        return coin_map
    except Exception as e:
        print(f"[Coindar] 获取代币列表失败: {e}")
        return {}


def fetch_tag_list() -> dict:
    """获取标签列表，建立 tag_id -> tag_name 映射"""
    try:
        resp = requests.get(
            f"{COINDAR_BASE_URL}/tags",
            params={"access_token": COINDAR_API_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        tags = resp.json()
        tag_map = {str(t.get("id", "")): t.get("name", "") for t in tags}
        print(f"[Coindar] 获取标签列表: {len(tag_map)} 个标签")
        return tag_map
    except Exception as e:
        print(f"[Coindar] 获取标签列表失败: {e}")
        return {}


def fetch_events(max_pages: int = 5) -> list[Message]:
    """获取近期加密货币事件"""
    coin_map = fetch_coin_list()
    tag_map = fetch_tag_list()
    time.sleep(1)

    all_messages = []
    today = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")#这里可以修改数据获取的时间范围

    for page in range(1, max_pages + 1):
        params = {
            "access_token": COINDAR_API_TOKEN,
            "page": page,
            "page_size": 100,
            "filter_date_start": today,
            "sort_by": "date_start",
            "order_by": 0,
        }

        try:
            resp = requests.get(
                f"{COINDAR_BASE_URL}/events",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            events = resp.json()
        except Exception as e:
            print(f"[Coindar] 第{page}页请求失败: {e}")
            break

        if not events:
            print(f"[Coindar] 第{page}页无数据，停止翻页")
            break

        for event in events:
            caption = event.get("caption", "")
            date_start = event.get("date_start", "")
            coin_id = str(event.get("coin_id", ""))
            source_url = event.get("source", "")
            important = event.get("important", False)
            source_reliable = event.get("source_reliable", False)

            # 代币 ID -> 符号
            coin_info = coin_map.get(coin_id, {})
            symbol = coin_info.get("symbol", "")
            coin_name = coin_info.get("name", "")
            tokens = [symbol] if symbol else []

            # 标签 ID -> 名称
            tag_ids = event.get("tags", "")
            if isinstance(tag_ids, str):
                tag_names = [tag_map.get(t.strip(), "") for t in tag_ids.split(",") if t.strip()]
            else:
                tag_names = []
            tag_names = [t for t in tag_names if t]

            # 拼接内容
            content = caption
            if coin_name and coin_name not in caption:
                content = f"[{coin_name}] {caption}"

            msg = Message(
                source="coindar",
                content=content,
                timestamp=date_start,
                author="Coindar",
                url=source_url,
                mentioned_tokens=tokens,
                extra={
                    "coin_id": coin_id,
                    "coin_name": coin_name,
                    "tags": tag_names,
                    "important": important,
                    "source_reliable": source_reliable,
                },
            )
            all_messages.append(msg)

        print(f"[Coindar] 第{page}页: {len(events)} 条事件")
        time.sleep(1)

    return all_messages


def collect_and_save():
    """采集并保存"""
    print("=" * 50)
    print("[Coindar] 开始采集事件数据...")

    if not COINDAR_API_TOKEN:
        print("[Coindar] 未配置 API Token")
        return []

    messages = fetch_events()

    if messages:
        save_messages(messages, "coindar.json")
    else:
        print("[Coindar] 未获取到数据，请检查 API Token")

    print(f"[Coindar] 完成，共 {len(messages)} 条")
    return messages


if __name__ == "__main__":
    results = collect_and_save()