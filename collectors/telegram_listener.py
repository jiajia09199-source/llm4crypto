"""
数据源 3: Telegram 频道/群组消息采集
使用 Telethon 库 (https://github.com/LonamiWebs/Telethon)
安装: pip install telethon

采集内容：
- 公开频道/群组的历史消息
- 消息内容、发送时间、发送者
- 实时监听新消息

使用前需要:
1. 访问 https://my.telegram.org 登录
2. 点击 "API development tools"
3. 创建应用，获取 api_id 和 api_hash
4. 填入 config.py
"""
import asyncio
import re
import sys, os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    TELEGRAM_CHANNELS,
    Message, save_messages,
)

try:
    from telethon import TelegramClient, events
except ImportError:
    print("请先安装: pip install telethon")
    sys.exit(1)

# 匹配代币符号
TOKEN_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')


def extract_tokens(text: str) -> list[str]:
    """从消息中提取代币符号"""
    return list(set(TOKEN_PATTERN.findall(text)))


async def fetch_channel_history(
    client: TelegramClient,
    channel: str,
    limit: int = 100,
    days: int = 7,
) -> list[Message]:
    """
    获取指定频道/群组的历史消息
    channel: 频道用户名，如 "binance_announcements"
    limit: 最多获取多少条
    days: 获取最近几天的消息
    """
    messages = []
    offset_date = datetime.now() - timedelta(days=days)

    print(f"[Telegram] 获取 @{channel} 最近{days}天的消息 (最多{limit}条)")

    try:
        entity = await client.get_entity(channel)

        async for msg in client.iter_messages(
            entity,
            limit=limit,
            offset_date=offset_date,
            reverse=False,
        ):
            # 跳过无文本消息（纯图片/视频等）
            if not msg.text:
                continue

            sender_name = ""
            if msg.sender:
                sender_name = getattr(msg.sender, "username", "") or \
                              getattr(msg.sender, "first_name", "") or ""

            m = Message(
                source="telegram",
                content=msg.text,
                timestamp=msg.date.isoformat() if msg.date else datetime.now().isoformat(),
                author=sender_name,
                url=f"https://t.me/{channel}/{msg.id}",
                mentioned_tokens=extract_tokens(msg.text),
                likes=0,
                extra={
                    "message_id": msg.id,
                    "channel": channel,
                    "views": msg.views or 0,
                    "forwards": msg.forwards or 0,
                    "has_media": msg.media is not None,
                },
            )
            messages.append(m)

    except Exception as e:
        print(f"[Telegram] @{channel} 采集失败: {e}")

    print(f"[Telegram]   -> {len(messages)} 条消息")
    return messages


async def listen_realtime(client: TelegramClient, channels: list[str], duration: int = 60):
    """
    实时监听频道新消息
    duration: 监听多少秒后自动停止
    """
    collected = []

    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        text = event.message.text or ""
        if not text:
            return

        sender = await event.get_sender()
        sender_name = getattr(sender, "username", "") if sender else ""

        m = Message(
            source="telegram",
            content=text,
            timestamp=event.message.date.isoformat(),
            author=sender_name,
            mentioned_tokens=extract_tokens(text),
            extra={
                "message_id": event.message.id,
                "realtime": True,
            },
        )
        collected.append(m)
        print(f"  [实时] @{sender_name}: {text[:80]}...")

    print(f"\n[Telegram] 开始实时监听 {len(channels)} 个频道，持续 {duration} 秒...")
    await asyncio.sleep(duration)

    # 移除监听器
    client.remove_event_handler(handler)
    print(f"[Telegram] 实时监听结束，收到 {len(collected)} 条新消息")
    return collected


async def collect_all() -> list[Message]:
    """完整采集流程"""
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print("[Telegram] 未配置 API，请在 config.py 中设置 TELEGRAM_API_ID 和 TELEGRAM_API_HASH")
        return []

    # 创建客户端（首次运行会要求输入手机号和验证码）
    import socks
    client = TelegramClient(
        "telegram_session",
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        proxy=(socks.SOCKS5, '127.0.0.1', 31446)
    )
    await client.start(phone=TELEGRAM_PHONE if TELEGRAM_PHONE else None)

    all_messages = []

    # 1. 获取各频道的历史消息
    print("\n--- 历史消息采集 ---")
    for channel in TELEGRAM_CHANNELS:
        msgs = await fetch_channel_history(client, channel, limit=40, days=3)
        all_messages.extend(msgs)
        await asyncio.sleep(1)

    # 2. 实时监听（可选，默认监听60秒）
    # 如果不需要实时监听，注释掉下面两行
    # realtime_msgs = await listen_realtime(client, TELEGRAM_CHANNELS, duration=60)
    # all_messages.extend(realtime_msgs)

    await client.disconnect()
    return all_messages


def collect_and_save():
    """入口：采集并保存"""
    print("=" * 50)
    print("[Telegram] 开始采集...")
    messages = asyncio.run(collect_all())
    if messages:
        save_messages(messages, "telegram.json")
    else:
        print("[Telegram] 未获取到数据，请检查 API 配置")
    print(f"[Telegram] 完成，共 {len(messages)} 条")
    return messages


if __name__ == "__main__":
    results = collect_and_save()
