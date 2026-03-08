import asyncio
import os
from datetime import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from anews.infrastructure.db import get_recent_news,count_news,init_db
from collections import defaultdict
"""
1,每天八点半启动get_rss里面的集成函数，即抓取rss里面的新闻并实现信息储存；
2,信息储存后调用news_processor.py里面的batch_process函数实现ai对新闻的概要、分类以及重要性评分
3,每日9：00定时开启sender.py里面的send_daily_news的函数，发送财经新闻

"""
# scheduler.py
from zoneinfo import ZoneInfo
# 导入你的核心功能
from scripts.get_rss import main as fetch_rss_main          # 抓取 + 入库
from anews.agents.news_processor import process_pending_batch    # AI 处理 pending 新闻
from scripts.sender import send_daily_news                  # 发送早报

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("scheduler")

# 你的飞书群聊 ID（可以从环境变量读取，或写死用于测试）
DAILY_CHAT_ID = "oc_d2cd18ae5ac8d2d961be4b06e976182c"   # ← 替换成真实的群聊ID

# 北京时间（飞书主要用户在中国大陆）
BEIJING_TZ = ZoneInfo("Asia/Shanghai")

async def job_fetch_rss():
    logger.info("═══════ 开始执行每日RSS抓取 ═══════")
    try:
        await fetch_rss_main()
        logger.info("RSS抓取 & 入库 完成")
    except Exception as e:
        logger.exception("RSS抓取任务异常")

async def job_process_news():
    logger.info("═══════ 开始执行待处理新闻AI分析 ═══════")
    try:
        stats = await process_pending_batch(limit=20)   # 可调批次大小
        logger.info(f"AI处理完成：{stats}")
    except Exception as e:
        logger.exception("新闻AI处理任务异常")

async def job_send_morning_news():
    logger.info("═══════ 开始发送每日财经早报 ═══════")
    try:
        # 这里你需要自己实现“生成早报文本”的逻辑
        # 可以从数据库读取当天/最近 processed 的高重要性新闻
        morning_content = await generate_morning_news_content()  # ← 你要补这个函数
        
        success = send_daily_news(
            chat_id=DAILY_CHAT_ID,
            news_content=morning_content
        )
        logger.info(f"早报发送{'成功' if success else '失败'}")
    except Exception as e:
        logger.exception("早报发送任务异常")


async def generate_morning_news_content() -> str:
    """
    生成分区版每日早报：
    1. 调用已修改的 get_recent_news（只取 processed）
    2. 按 field（领域）分组
    3. 每个领域只取 importance 最高的前 5 条
    """
    from anews.infrastructure.db import get_recent_news   # 确保导入你修改后的函数

    news_list = await get_recent_news(limit=50)   # 取足够多，后面再截 Top5

    # ==================== 按 field 分组 + 排序 ====================
    grouped: dict[str, list[dict]] = defaultdict(list)
    
    for item in news_list:
        field = item.get("field", "其他").strip()
        grouped[field].append(item)

    # 对每个分组按 importance 降序排序
    for field in grouped:
        grouped[field].sort(key=lambda x: x.get("importance", 0), reverse=True)

    # ==================== 构建美观早报文本 ====================
    lines = ["📈 今日财经早报（AI精选 · 分领域版）\n"]

    for field, items in grouped.items():
        top5 = items[:5]                      # 每个领域最多取 5 条
        if not top5:
            continue

        lines.append(f"🔹 【{field}】")        # 分区标题
        for i, item in enumerate(top5, 1):
            title = item.get("title", "无标题")[:58]
            summary = item.get("summary", "暂无摘要")[:110]
            source = item.get("source", "?").split("/")[-1]   # 只显示域名更简洁
            importance = item.get("importance", 0)

            lines.append(
                f"   {i}. {title}\n"
                f"      {summary}\n"
                f"      重要性：{'★' * int(importance)}  来源：{source}"
            )
        lines.append("")   # 分区之间空一行

    # 兜底文案
    if len(lines) <= 2:
        return "今日暂无已处理的财经新闻～ 请稍后查看"

    lines.append("—— 数据来源于多家权威财经媒体，由 AI 自动分类 + 重要性评分")
    final_text = "\n".join(lines)
    # 粗估 UTF-8 字节长度（JSON 后还会更大）
    if len(final_text.encode('utf-8')) > 18000:  # 留足余量给 JSON 包装
        # 简单粗暴截断：保留开头 + 结尾提示
        final_text = final_text[:15000] + "\n\n……（今日新闻较多，已自动截断，请查看更多详情）\n" + final_text[-2000:]
    
    return final_text



async def main():
    scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)
    
    # 每天 08:30 抓取最新RSS
    scheduler.add_job(
        job_fetch_rss,
        trigger=CronTrigger(hour=8, minute=20),
        id="daily_fetch_rss",
        name="每日RSS抓取 & 入库",
        replace_existing=True
    )
    
    # 每天 08:45 开始AI处理（给抓取留15分钟缓冲）
    scheduler.add_job(
        job_process_news,
        trigger=CronTrigger(hour=8, minute=30),
        id="daily_process_news",
        name="每日待处理新闻AI分析",
        replace_existing=True
    )
    
    # 每天 09:00 发送早报
    scheduler.add_job(
        job_send_morning_news,
        trigger=CronTrigger(hour=9, minute=00),
        id="daily_send_news",
        name="每日财经早报群发",
        replace_existing=True
    )
    
    logger.info("定时任务已注册，开始运行调度器...")
    scheduler.start()
    
    # 保持事件循环运行
    try:
        await asyncio.sleep(3600 * 24 * 365)  # 运行一年（实际可使用 while True）
    except (KeyboardInterrupt, asyncio.CancelledError):
        scheduler.shutdown()
        logger.info("调度器已关闭")


if __name__ == "__main__":
    asyncio.run(main())
