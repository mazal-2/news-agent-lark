import asyncio
import tomllib
from datetime import datetime
from typing import List, Dict, Optional, Any
import httpx
import feedparser
from trafilatura import extract, fetch_url
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径，以便导入 anews.utils
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from anews.utils import db

# 导入模块 (如上)

# 常量定义
CONFIG_PATH = "config.toml"
TIMEOUT = 30.0
MAX_CONCURRENT = 10

def load_config(config_path: str) -> List[str]:
    """
    从TOML配置文件中读取RSS URL列表

    返回:
        包含RSS URL的列表，如果文件不存在或格式错误则返回空列表
    """
    try:
        with open(config_path, 'rb') as f:
            config = tomllib.load(f)

        # 支持两种格式：[rss]下的urls，或者顶层的rss_urls
        urls = None
        if 'rss' in config and 'urls' in config['rss']:
            urls = config['rss']['urls']
        elif 'rss_urls' in config:
            urls = config['rss_urls']

        if isinstance(urls, list):
            return [url for url in urls if isinstance(url, str)]
        else:
            print(f"警告: 配置文件中未找到有效的RSS URL列表 (rss.urls 或 rss_urls)")
            return []
    except FileNotFoundError:
        print(f"警告: 配置文件不存在: {config_path}")
        return []
    except tomllib.TOMLDecodeError as e:
        print(f"警告: 配置文件解析失败: {e}")
        return []
    except Exception as e:
        print(f"警告: 读取配置文件时出错: {e}")
        return []

async def fetch_feed(client: httpx.AsyncClient, url: str, timeout: float) -> Optional[str]:
    """
    异步抓取单个RSS feed

    返回:
        RSS feed的文本内容，如果抓取失败则返回None
        # 返回原文本内容，但这里面的url应该是多个
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = await client.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()  # 如果状态码不是2xx，抛出HTTPStatusError
        return response.text
    except httpx.TimeoutException:
        print(f"警告: 请求超时 ({timeout}s): {url}")
        return None
    except httpx.HTTPStatusError as e:
        print(f"警告: HTTP错误 {e.response.status_code}: {url}")
        return None
    except Exception as e:
        print(f"警告: 抓取feed时出错: {e}")
        return None 
    

def parse_feed(feed_text: str, source_url: str) -> List[Dict]:
    """
    解析feed文本并提取条目 

    返回:
        包含条目信息的字典列表
    """
    if not feed_text:
        print(f"警告: 空的feed文本，源: {source_url}")
        return []

    try:
        parsed_feed = feedparser.parse(feed_text)
        # 这里面的feedparser.parse能够读取一个url，而这个parse读到url后自身就能够parse这里面rss的内容，即每一个entry，,entry带有title,link,description等属性
        # 检查解析错误
        if parsed_feed.bozo:
            print(f"警告: 解析feed时出错 (源: {source_url}): {parsed_feed.bozo_exception}")

        # 检查是否有条目
        if not parsed_feed.entries:
            print(f"信息: feed中没有条目 (源: {source_url})")
            return []

        entries = []
        for entry in parsed_feed.entries:
            entry_info = extract_entry_info(entry, source_url)
            if entry_info:
                entries.append(entry_info)

        print(f"成功解析 {len(entries)} 个条目 (源: {source_url})")
        return entries

    except Exception as e:
        print(f"警告: 解析feed时发生异常 (源: {source_url}): {e}")
        return []

def extract_entry_info(entry, source_url: str) -> Optional[Dict]:
    """
    从单个entry中提取结构化信息，即parse_
    
    返回:
        包含条目信息的字典，如果缺少必要信息则返回None
    """
    # 提取链接
    link = entry.get("link") # url属性
    if not link:
        return None

    # 提取标题
    title = entry.get("title", "无标题")
    if not title or title == "无标题":
        # 尝试从其他字段获取标题
        title = entry.get("description", "无标题")[:100]  # 截断描述作为标题

    # 提取发布时间
    published_str = entry.get("published", entry.get("updated", entry.get("date")))
    published_dt = format_datetime(published_str) if published_str else None

    # 提取源名称（从URL或feed信息中）
    # 这里简单使用源URL，后续可以改进为提取域名
    source = source_url

    return {
        "title": str(title).strip(),
        "link": str(link).strip(),
        "published": published_dt,
        "source": source,
        "published_str": published_str,  # 保留原始字符串用于调试
        "content": None,  # 占位，后续可以填充全文内容
        "summary":None,
        "status":"pending"
    } 

def format_datetime(published_str: str) -> Optional[datetime]:
    """
    将各种时间格式转换为datetime对象

    返回:
        datetime对象，如果无法解析则返回None
    """
    if not published_str:
        return None

    # 常见RSS日期格式
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',  # RFC 822 with timezone
        '%a, %d %b %Y %H:%M:%S %Z',  # RFC 822 with timezone name
        '%a, %d %b %Y %H:%M:%S',     # RFC 822 without timezone
        '%Y-%m-%dT%H:%M:%S%z',       # ISO 8601 with timezone
        '%Y-%m-%dT%H:%M:%S.%f%z',    # ISO 8601 with microseconds and timezone
        '%Y-%m-%dT%H:%M:%SZ',        # ISO 8601 UTC
        '%Y-%m-%dT%H:%M:%S',         # ISO 8601 without timezone
        '%Y-%m-%d %H:%M:%S',         # Simple datetime
        '%Y-%m-%d',                  # Date only
        '%d %b %Y %H:%M:%S',         # Alternative format
    ]

    for fmt in formats:
        try:
            # 处理时区格式中的特殊情况
            if fmt.endswith('%z'):
                # 处理时区格式如 +0800 或 +08:00
                dt_str = published_str.replace(':', '') if ':' in published_str and published_str[-3] == ':' else published_str
                return datetime.strptime(dt_str, fmt)
            else:
                return datetime.strptime(published_str, fmt)
        except (ValueError, AttributeError):
            continue

    print(f"警告: 无法解析日期格式: {published_str}")
    return None

def deduplicate_entries(entries: List[Dict], key: str = "link") -> List[Dict]:
    """
    根据指定字段去重，保留最新版本
    实现思路即利用判断entry当前的link是否在其中，如果没有则直接保存，如果有则比较发布时间，保留更新的那个

    需要优化的点：
    1，应该查看去标题相似度,如果标题相似度很高但链接不同，也可以认为是同一条新闻，保留发布时间更新的那个
    返回:
        去重后的条目列表，保留每个唯一键的最新版本
    """
    seen = {}

    for entry in entries:
        # 检查键是否存在
        if key not in entry:
            continue
# 读取每个条目的连接，并使用它作为去重的键
        entry_key = entry[key]
        existing_entry = seen.get(entry_key)
# 如果之前没有见过这个键，直接保存
        if existing_entry is None:
            # 第一次见到这个键，直接保存
            seen[entry_key] = entry
        else:
            # 比较发布时间，保留更新的
            existing_published = existing_entry.get("published")
            current_published = entry.get("published")

            # 如果当前条目有发布时间且现有条目没有，或者当前发布时间更晚
            if current_published is not None: # 当前条目有发布时间
                if existing_published is None or current_published > existing_published:
                    seen[entry_key] = entry # 更新为当前条目
            # 如果当前条目没有发布时间，但现有条目有，则保留现有条目
            elif existing_published is not None:
                # 现有条目有发布时间，当前条目没有，保留现有条目
                pass
            else:
                # 两个条目都没有发布时间，保留第一个遇到的
                pass

    return list(seen.values()) # 返回去重后的条目列表

def print_entries(entries: List[Dict], limit: int = 30) -> None:
    """
    格式化打印条目

    参数:
        entries: 条目字典列表
        limit: 最大打印数量，默认30
    """
    if not entries:
        print("没有找到任何条目")
        return

    # 1. 按发布时间降序排序（没有时间的排到最后）
    def get_sort_key(entry):
        published = entry.get("published")
        # 如果有发布时间，返回发布时间（最新排前面）
        # 如果没有发布时间，返回一个很旧的日期，使其排到最后
        return published if published is not None else datetime.min

    sorted_entries = sorted(entries, key=get_sort_key, reverse=True)

    # 2. 取前limit个条目
    entries_to_print = sorted_entries[:limit]

    print(f"\n{'='*80}")
    print(f"最新 {len(entries_to_print)} 条新闻 (共 {len(entries)} 条)")
    print(f"{'='*80}\n")

    # 3. 遍历打印
    for i, entry in enumerate(entries_to_print, 1):
        # 格式化时间
        published_dt = entry.get("published")
        if published_dt:
            time_str = published_dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = "N/A"

        # 截断标题
        title = entry.get("title", "无标题")
        if len(title) > 80:
            title = title[:77] + "..."

        # 获取链接和来源
        link = entry.get("link", "")
        source = entry.get("source", "")

        # 提取域名作为简短的来源显示
        import urllib.parse
        try:
            source_domain = urllib.parse.urlparse(source).netloc
            if not source_domain and source:
                source_domain = source[:30]
        except:
            source_domain = source[:30] if source else "未知"

        # 4. 使用固定宽度列对齐
        # 第一行：编号、时间、标题
        print(f"{i:>3}. [{time_str:<19}] {title}")

        # 第二行：缩进显示链接和来源
        print(f"    链接: {link}")
        print(f"    来源: {source_domain}")
        print()  # 空行分隔

import random
import time
import sys
from typing import Optional
import trafilatura

def get_full_content(url: str) -> Optional[str]:
    """
    从给定 URL 提取文章正文（纯文本），使用 trafilatura 库。
    如果提取失败或内容太短，返回 None。

    返回:
        提取到的正文（str），或 None（失败/空/太短）
    """
    # 随机延迟 3-5 秒，防止被网站封 IP
    delay = random.uniform(3, 5)
    time.sleep(delay)

    try:
        # 1. 下载网页
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            print(f"Error: Failed to download URL: {url}", file=sys.stderr)
            return None

        # 2. 提取正文
        text = trafilatura.extract(
            downloaded,
            include_links=False,
            include_tables=False,
            include_images=False,
            no_fallback=True,
            output_format="txt"
        ) # output_format能够规定应该输出什么格式的文本

        if text is None:
            print(f"Error: Failed to extract content from: {url}", file=sys.stderr)
            return None

        # 清理空白字符
        cleaned_text = text.strip()

        # 3. 检查内容长度
        if len(cleaned_text) < 80:
            print(f"Warning: Content too short ({len(cleaned_text)} chars) from: {url}", file=sys.stderr)
            return None

        print(f"Successfully extracted {len(cleaned_text)} chars from: {url}", file=sys.stderr)
        return cleaned_text

    except Exception as e:
        print(f"Error extracting content from {url}: {e}", file=sys.stderr)
        return None

# =====================================
#          下一步要做的事情
# =====================================

async def save_news_to_db(entry: dict) -> bool:
    '''
    将一条新闻（已经有 content 的）保存到 PostgreSQL
    如果 url 已存在，则跳过（或更新）

    Args:
        entry: 新闻条目字典，包含 title、link、published、source、content 等字段

    Returns:
        bool: 保存是否成功
    '''
    try:
        # 保存基础元数据
        success = await db.upsert_news_entry(entry)
        if not success:
            print(f"警告: 保存基础元数据失败 - {entry.get('title', '无标题')[:50]}...")
            return False

        # 如果条目有内容，更新内容字段
        if entry.get("content"):
            content_success = await db.update_news_content(entry["link"], entry["content"])
            if not content_success:
                print(f"警告: 更新内容失败 - {entry.get('title', '无标题')[:50]}...")
                # 这里不返回 False，因为基础元数据已经保存成功

        print(f"成功保存新闻: {entry.get('title', '无标题')[:50]}...")
        return True

    except Exception as e:
        print(f"保存新闻到数据库时出错 - {entry.get('title', '无标题')[:50]}...: {e}")
        return False


async def save_news_batch(entries: list) -> dict:
    '''
    批量保存新闻条目到数据库

    Args:
        entries: 新闻条目字典列表

    Returns:
        dict: 统计信息，包含 saved_count, content_updated_count, error_count
    '''
    saved_count = 0
    content_updated_count = 0
    error_count = 0

    for entry in entries:
        try:
            success = await db.upsert_news_entry(entry)
            if success:
                saved_count += 1

                # 如果条目有内容，更新内容字段
                if entry.get("content"):
                    content_success = await db.update_news_content(entry["link"], entry["content"])
                    if content_success:
                        content_updated_count += 1
            else:
                error_count += 1
                print(f"警告: 保存条目失败 - {entry.get('title', '无标题')[:50]}...")

        except Exception as e:
            error_count += 1
            print(f"警告: 处理条目时出错 - {entry.get('title', '无标题')[:50]}...: {e}")

    return {
        "saved_count": saved_count,
        "content_updated_count": content_updated_count,
        "error_count": error_count
    }

async def main() -> None:
    """
    主协程：协调整个抓取流程

    伪代码：
    1. 调用load_config()获取URL列表
    2. 创建httpx.AsyncClient()，设置公共请求头
    3. 创建任务列表：每个URL对应一个fetch_feed()任务
    4. 使用asyncio.gather()并发执行
    5. 收集所有结果（过滤None值）
    6. 对每个成功抓取的feed，调用parse_feed()
    7. 合并所有条目
    8. 调用deduplicate_entries()去重
    9. 调用print_entries()打印结果
    10. 统计并打印：成功/失败的feed数量，总条目数
    """
    print("开始抓取RSS新闻...")

    # 1. 加载配置
    urls = load_config(CONFIG_PATH)
    if not urls:
        print("错误: 没有找到RSS URL，请检查配置文件")
        return

    print(f"找到 {len(urls)} 个RSS源")

    # 2. 创建异步客户端
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # 使用信号量控制并发数
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def fetch_with_semaphore(client, url):
        async with semaphore:
            return await fetch_feed(client, url, TIMEOUT)

    async with httpx.AsyncClient(headers=headers) as client:
        # 3. 创建任务列表
        print(f"开始并发抓取，最大并发数: {MAX_CONCURRENT}")
        tasks = [fetch_with_semaphore(client, url) for url in urls]
# client； 这里面的semaphore函数函数获取的仅仅是rrs的url，而这个函数里面调用了fetch_feed函数，fetch_feed函数里面才是真正的抓取rss内容的函数
        # 4. 并发执行， 对多个rss源进行抓取，获取每个rss源的文本内容
        results = await asyncio.gather(*tasks, return_exceptions=False)

    # 5. 收集结果
    successful_feeds = []
    failed_feeds = []

    for url, result in zip(urls, results):
        if result is None:
            failed_feeds.append(url)
        else:
            successful_feeds.append((url, result))

    print(f"\n抓取完成:")
    print(f"  成功: {len(successful_feeds)} 个源")
    print(f"  失败: {len(failed_feeds)} 个源")

    if failed_feeds:
        print("失败的源:")
        for url in failed_feeds:
            print(f"  - {url}")

    # 6. 解析成功的feed
    all_entries = []
    for url, feed_text in successful_feeds:
        entries = parse_feed(feed_text, url)
        all_entries.extend(entries) # 对html/xml文本进行解析，提取出其中的条目，并将所有条目合并到一个列表中

    if not all_entries:
        print("错误: 没有成功解析到任何新闻条目")
        return

    print(f"\n解析完成，共获得 {len(all_entries)} 个原始条目")

    # 7. 合并所有条目（已在上一步完成）
    # 8. 去重
    unique_entries = deduplicate_entries(all_entries)
    print(f"去重后剩余 {len(unique_entries)} 个条目")

    # 9. 提取正文内容
    print(f"\n开始提取正文内容...")
    MAX_CONTENT_CONCURRENT = 5  # 控制并发数，避免被封IP

    # 初始化content字段
    for entry in unique_entries:
        entry["content"] = None 

    # 创建信号量控制并发
    content_semaphore = asyncio.Semaphore(MAX_CONTENT_CONCURRENT)

    async def fetch_content(entry): # 异步调用获取每个条目的链接，并使用get_full_content函数提取正文内容
        async with content_semaphore:
            url = entry["link"]
            try:
                # 在线程池中运行同步函数，避免阻塞事件循环
                content = await asyncio.to_thread(get_full_content, url)
                # 检查内容长度是否满足要求（至少100字符）
                if content and len(content) >= 100:
                    entry["content"] = content
                    return True
                else:
                    entry["content"] = None
                    return False
            except Exception as e:
                print(f"Error fetching content for {url}: {e}", file=sys.stderr)
                entry["content"] = None
                return False

    # 创建所有任务
    tasks = [fetch_content(entry) for entry in unique_entries]
    # 最后返回的unique_entries就是所有的parse后面的数据
    # 跟踪进度
    completed = 0
    successful = 0
    total = len(tasks)

    # 使用asyncio.as_completed逐个等待任务完成，以便显示进度
    print(f"正在提取 {total} 篇文章的正文，最大并发数: {MAX_CONTENT_CONCURRENT}")

    for future in asyncio.as_completed(tasks):
        try:
            success = await future
            completed += 1 # 这里面的是处理过的entry数量，完成则是cp，在这基础上再分成功/失败
            if success:
                successful += 1

            # 每处理10条打印一次进度
            if completed % 10 == 0 or completed == total:
                print(f"  进度: {completed}/{total}，成功: {successful}")
        except Exception as e:
            completed += 1
            print(f"  任务异常: {e}")

    print(f"\n正文提取完成:")
    print(f"  成功提取: {successful} 篇")
    print(f"  提取失败: {total - successful} 篇")

    # 过滤掉没有内容的条目（可选）
    # entries_with_content = [entry for entry in unique_entries if entry["content"] is not None]
    # print(f"  有内容的条目: {len(entries_with_content)} 个")

    # 9. 打印结果
    print_entries(unique_entries, limit=30)

    # 10. 保存到数据库
    print(f"\n{'='*60}")
    print("开始保存到数据库...")

    try:
        # 初始化数据库连接
        await db.init_db()

        # 使用批量保存函数
        stats = await save_news_batch(unique_entries)

        print(f"数据库保存完成:")
        print(f"  成功保存: {stats['saved_count']} 条")
        print(f"  内容更新: {stats['content_updated_count']} 条")
        print(f"  失败: {stats['error_count']} 条")

        # 打印数据库统计
        counts = await db.count_news()
        print(f"数据库统计:")
        print(f"  总条目数: {counts['total']}")
        print(f"  待处理: {counts['pending']}")
        print(f"  有内容: {counts['with_content']}")

    except Exception as e:
        print(f"数据库操作失败: {e}")
    finally:
        # 关闭数据库连接池
        await db.close_db()

    # 11. 最终统计
    print(f"\n{'='*60}")
    print("最终统计:")
    print(f"  RSS源总数: {len(urls)}")
    print(f"  成功抓取: {len(successful_feeds)}")
    print(f"  抓取失败: {len(failed_feeds)}")
    print(f"  原始条目数: {len(all_entries)}")
    print(f"  去重后条目数: {len(unique_entries)}")
    print(f"{'='*60}")




# 程序入口
if __name__ == "__main__":
    asyncio.run(main())
