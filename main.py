"""
一键运行全部流程
用法:
  python main.py              # 运行全部（采集+清洗+分析+可视化）
  python main.py collect      # 只跑采集
  python main.py clean        # 只跑清洗
  python main.py analyze      # 只跑分析+可视化
"""
import sys
import importlib


def run(module_path, func_name, step_name):
    """运行单个步骤，出错不中断"""
    try:
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        func()
        print(f"[{step_name}] 完成")
    except Exception as e:
        print(f"[{step_name}] 失败: {e}")
        print(f"  跳过，继续下一步...\n")


def collect():
    """步骤1: 数据采集"""
    print("\n" + "=" * 60)
    print("步骤 1/3: 数据采集")
    print("=" * 60)

    # 原有采集器
    run("collectors.telegram_listener", "collect_and_save", "Telegram")
    run("collectors.coindar", "collect_and_save", "Coindar")
    run("collectors.twitter_scraper", "collect_and_save", "Twitter")

    # 新增 RSS 采集器
    run("collectors.cointelegraph_rss", "collect_and_save", "Cointelegraph")
    run("collectors.coindesk_rss", "collect_and_save", "CoinDesk")


def clean():
    """步骤2: 数据清洗"""
    print("\n" + "=" * 60)
    print("步骤 2/3: 数据清洗")
    print("=" * 60)
    run("processing.cleaner", "load_and_clean", "清洗")


def analyze():
    """步骤3: 情绪分析 + 价格对比 + 可视化"""
    print("\n" + "=" * 60)
    print("步骤 3/3: LLM 情绪分析 + 价格对比")
    print("=" * 60)
    run("analysis.sentiment", "run_analysis", "情绪分析")
    run("analysis.price_compare", "run_comparison", "价格对比")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target == "all":
        collect()
        clean()
        analyze()
    elif target == "collect":
        collect()
    elif target == "clean":
        clean()
    elif target == "analyze":
        analyze()
    else:
        print("用法: python main.py [all|collect|clean|analyze]")


if __name__ == "__main__":
    main()