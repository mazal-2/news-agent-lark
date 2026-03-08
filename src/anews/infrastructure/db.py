"""
数据库操作模块，基于 asyncpg 实现异步 PostgreSQL 操作。

主要功能：
1. 连接池管理
2. 新闻条目的增删改查
3. 使用 ON CONFLICT 机制以 URL 为唯一标识去重
"""

import os
import asyncpg
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(r"D:\projects\news-agent-lark\.env")

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    # 查找项目根目录下的 .env 文件
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"已加载环境变量文件: {env_path}")
    else:
        print(f"未找到环境变量文件: {env_path}")
except ImportError:
    # python-dotenv 未安装，跳过
    pass

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 从环境变量读取数据库配置
PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "zxy20030926"
PG_DB = "postgres"

# 打印数据库配置（调试用）
logger.debug(f"数据库配置: host={PG_HOST}, port={PG_PORT}, user={PG_USER}, db={PG_DB}")

# 数据库连接池
_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """初始化数据库连接池"""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                host=PG_HOST,
                port=PG_PORT,
                user=PG_USER,
                password=PG_PASSWORD,
                database=PG_DB,
                min_size=1,
                max_size=10,
                command_timeout=60,
            )
            logger.info("Database connection pool initialized successfully")

            # 创建表（如果不存在）
            await create_tables()
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {e}")
            raise


async def close_db():
    """关闭数据库连接池"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("数据库连接池已关闭")


@asynccontextmanager
async def get_connection():
    """获取数据库连接的上下文管理器"""
    if _pool is None:
        await init_db()

    async with _pool.acquire() as connection:
        yield connection


async def create_tables():
    """创建新闻表（如果不存在）"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS news_entries (
        id SERIAL PRIMARY KEY,
        url TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        published TIMESTAMP WITH TIME ZONE,
        source TEXT,
        content TEXT,
        summary TEXT,
        status TEXT DEFAULT 'pending',
        field TEXT,
        importance INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """

    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_news_url ON news_entries(url);",
        "CREATE INDEX IF NOT EXISTS idx_news_published ON news_entries(published);",
        "CREATE INDEX IF NOT EXISTS idx_news_status ON news_entries(status);",
        "CREATE INDEX IF NOT EXISTS idx_news_created_at ON news_entries(created_at);"
    ]

    try:
        async with get_connection() as conn:
            # 创建表
            await conn.execute(create_table_sql)
            logger.info("表创建/验证成功")

            # 创建索引
            for sql in create_indexes_sql:
                try:
                    await conn.execute(sql)
                    logger.debug(f"索引创建成功: {sql}")
                except Exception as e:
                    logger.warning(f"创建索引失败 (可能已存在): {sql}, 错误: {e}")

    except Exception as e:
        logger.error(f"创建表失败: {e}")
        raise


async def upsert_news_entry(entry: Dict[str, Any]) -> bool:
    """
    插入或更新新闻条目（基于 URL 去重）

    使用 PostgreSQL 的 ON CONFLICT 机制，当 URL 冲突时更新其他字段。

    Args:
        entry: 新闻条目字典，包含以下字段：
            - title: 标题
            - link: URL（唯一标识）
            - published: 发布时间（datetime 对象）
            - source: 来源
            - content: 正文内容（可选）
            - summary: 摘要（可选）
            - status: 状态（默认 'pending'）

    Returns:
        bool: 操作是否成功
    """
    required_fields = ["title", "link"]
    for field in required_fields:
        if field not in entry:
            logger.error(f"缺少必要字段: {field}")
            return False

    sql = """
    INSERT INTO news_entries (
        url, title, published, source, content, summary, status, field, importance
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (url) DO UPDATE SET
        title = EXCLUDED.title,
        published = EXCLUDED.published,
        source = EXCLUDED.source,
        content = COALESCE(EXCLUDED.content, news_entries.content),
        summary = COALESCE(EXCLUDED.summary, news_entries.summary),
        status = EXCLUDED.status,
        field = COALESCE(EXCLUDED.field,news_entries.field),
        importance = COALESCE(EXCLUDED.importance,news_entries.importance),
        updated_at = NOW()
    RETURNING id;
    """

    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(
                sql,
                entry["link"],  # $1: url
                entry["title"],  # $2: title
                entry.get("published"),  # $3: published
                entry.get("source"),  # $4: source
                entry.get("content"),  # $5: content
                entry.get("summary"),  # $6: summary
                entry.get("status", "pending"),  # $7: status
                entry.get("field"),
                entry.get("importance")
            )

            if result:
                logger.debug(f"成功插入/更新新闻条目，ID: {result['id']}, URL: {entry['link']}")
                return True
            else:
                logger.error(f"插入/更新新闻条目失败，无返回ID")
                return False

    except Exception as e:
        logger.error(f"数据库操作失败 (upsert_news_entry): {e}")
        return False


async def update_news_content(url: str, content: str) -> bool:
    """
    更新新闻条目的正文内容

    Args:
        url: 新闻条目的 URL
        content: 正文内容

    Returns:
        bool: 操作是否成功
    """
    sql = """
    UPDATE news_entries
    SET content = $1, updated_at = NOW()
    WHERE url = $2
    RETURNING id;
    """

    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(sql, content, url)
            if result:
                logger.debug(f"成功更新新闻内容，ID: {result['id']}, URL: {url}")
                return True
            else:
                logger.warning(f"未找到 URL 对应的新闻条目: {url}")
                return False

    except Exception as e:
        logger.error(f"数据库操作失败 (update_news_content): {e}")
        return False


async def update_news_summary(url: str, summary: str) -> bool:
    """
    更新新闻条目的摘要

    Args:
        url: 新闻条目的 URL
        summary: 摘要内容

    Returns:
        bool: 操作是否成功
    """
    sql = """
    UPDATE news_entries
    SET summary = $1, updated_at = NOW()
    WHERE url = $2
    RETURNING id;
    """

    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(sql, summary, url)
            if result:
                logger.debug(f"成功更新新闻摘要，ID: {result['id']}, URL: {url}")
                return True
            else:
                logger.warning(f"未找到 URL 对应的新闻条目: {url}")
                return False

    except Exception as e:
        logger.error(f"数据库操作失败 (update_news_summary): {e}")
        return False


async def update_news_status(url: str, status: str) -> bool:
    """
    更新新闻条目的状态

    Args:
        url: 新闻条目的 URL
        status: 新状态（如 'pending', 'processed', 'failed'）

    Returns:
        bool: 操作是否成功
    """
    sql = """
    UPDATE news_entries
    SET status = $1, updated_at = NOW()
    WHERE url = $2
    RETURNING id;
    """

    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(sql, status, url)
            if result:
                logger.debug(f"成功更新新闻状态，ID: {result['id']}, URL: {url}, 状态: {status}")
                return True
            else:
                logger.warning(f"未找到 URL 对应的新闻条目: {url}")
                return False

    except Exception as e:
        logger.error(f"数据库操作失败 (update_news_status): {e}")
        return False


async def get_news_by_url(url: str) -> Optional[Dict[str, Any]]:
    """
    根据 URL 获取新闻条目

    Args:
        url: 新闻条目的 URL

    Returns:
        Optional[Dict]: 新闻条目字典，如果未找到则返回 None
    """
    sql = """
    SELECT id, url, title, published, source, content, summary, status, field, importance created_at, updated_at
    FROM news_entries
    WHERE url = $1;
    """
# sql命令+fetchrow能够将后面的参数填入到url
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(sql, url)
            if row:
                return dict(row)
            else:
                return None

    except Exception as e:
        logger.error(f"数据库操作失败 (get_news_by_url): {e}")
        return None


async def get_pending_news(limit: int = 100) -> List[Dict[str, Any]]:
    """
    获取待处理的新闻条目

    Args:
        limit: 返回条目的最大数量

    Returns:
        List[Dict]: 新闻条目字典列表
    """
    sql = """
    SELECT id, url, title, published, source, content, summary, status,field, importance created_at, updated_at
    FROM news_entries
    WHERE status = 'pending'
    ORDER BY published DESC NULLS LAST, created_at DESC
    LIMIT $1;
    """

    try:
        async with get_connection() as conn:
            rows = await conn.fetch(sql, limit)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"数据库操作失败 (get_pending_news): {e}")
        return []


async def get_recent_news(limit: int = 50) -> List[Dict[str, Any]]:
    """
    获取最近的新闻条目

    Args:
        limit: 返回条目的最大数量

    Returns:
        List[Dict]: 新闻条目字典列表
    """
    sql = """
    SELECT id, url, title, published, source, content, summary, 
           status, field, importance, created_at, updated_at
    FROM news_entries
    WHERE status = 'processed'                    -- ← 新增：只取 AI 处理过的
    ORDER BY published DESC NULLS LAST, 
             importance DESC NULLS LAST,          -- 新增：同一天按重要性排序
             created_at DESC
    LIMIT $1;
    """

    try:
        async with get_connection() as conn:
            rows = await conn.fetch(sql, limit)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"数据库操作失败 (get_recent_news): {e}")
        return []


async def delete_news_by_url(url: str) -> bool:
    """
    根据 URL 删除新闻条目

    Args:
        url: 新闻条目的 URL

    Returns:
        bool: 操作是否成功
    """
    sql = "DELETE FROM news_entries WHERE url = $1 RETURNING id;"

    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(sql, url)
            if result:
                logger.info(f"成功删除新闻条目，ID: {result['id']}, URL: {url}")
                return True
            else:
                logger.warning(f"未找到 URL 对应的新闻条目: {url}")
                return False

    except Exception as e:
        logger.error(f"数据库操作失败 (delete_news_by_url): {e}")
        return False


async def count_news() -> Dict[str, int]:
    """
    统计新闻条目数量

    Returns:
        Dict[str, int]: 各类统计数量
    """
    sql_total = "SELECT COUNT(*) as count FROM news_entries;"
    sql_pending = "SELECT COUNT(*) as count FROM news_entries WHERE status = 'pending';"
    sql_with_content = "SELECT COUNT(*) as count FROM news_entries WHERE content IS NOT NULL AND content != '';"

    try:
        async with get_connection() as conn:
            total = await conn.fetchval(sql_total)
            pending = await conn.fetchval(sql_pending)
            with_content = await conn.fetchval(sql_with_content)

            return {
                "total": total or 0,
                "pending": pending or 0,
                "with_content": with_content or 0,
                "processed": (total or 0) - (pending or 0)
            }

    except Exception as e:
        logger.error(f"数据库操作失败 (count_news): {e}")
        return {"total": 0, "pending": 0, "with_content": 0, "processed": 0}


# 异步上下文管理器，用于管理数据库连接生命周期
@asynccontextmanager
async def db_session():
    """
    数据库会话上下文管理器

    示例用法:
    ```python
    async with db_session():
        await upsert_news_entry(entry)
        await update_news_content(entry["link"], content)
    ```
    """
    try:
        await init_db()
        yield
    finally:
        await close_db()


async def update_news_analysis(url: str, analysis: Dict[str, Any]) -> bool:
    """
    接收 AI Agent 生成的结构化分析结果，一次性更新数据库中的分析字段并标记处理完成。

    输入参数 (Args):
        url (str): 
            新闻条目的唯一标识符（URL）。用于定位需要更新的数据库行。
        analysis (Dict[str, Any]): 
            由 AI Agent 解析得到的 JSON 字典，必须包含以下键：
            - "summary" (str): 100字以内的摘要，需包含新闻核心数据（如 NEV 销量或财务百分比）。
            - "field" (str): 领域分类，仅限“国内宏观”、“产业新闻”、“公司动态”、“国外宏观”、“海外公司”之一。
            - "importance" (float/int): 重要性评分，范围 0-5，支持 0.5 步进。

    返回结果 (Returns):
        bool: 
            - True: 成功找到该 URL 并更新了字段，且 status 已变为 'processed'。
            - False: 未找到该 URL，或数据库操作发生异常。

    处理逻辑:
        1. 使用 URL 作为 $4 占位符进行精确匹配。
        2. 将 AI 提供的摘要、领域和分值分别填入 $1, $2, $3。
        3. 自动将 status 字段从 'pending' 修改为 'processed'，无需人工干预。
        4. 自动刷新 updated_at 时间戳为当前时间。
    """
    sql = """
    UPDATE news_entries
    SET 
        summary = $1, 
        field = $2, 
        importance = $3, 
        status = 'processed',  -- 在这里直接写死或传参，标记为已处理
        updated_at = NOW()
    WHERE url = $4
    RETURNING id;
    """
    try:
        async with get_connection() as conn:
            result = await conn.fetchrow(
                sql, 
                analysis.get("summary"), 
                analysis.get("field"), 
                analysis.get("importance"), 
                url
            )
            if result:
                logger.info(f"AI 分析回填成功: {url}")
                return True
            return False
    except Exception as e:
        logger.error(f"回填 AI 分析时数据库报错: {e}")
        return False


# 测试函数
async def test_db_operations():
    """测试数据库操作"""
    try:
        await init_db()

        # 测试插入
        test_entry = {
            "title": "测试新闻标题",
            "link": "https://example.com/test-news",
            "published": datetime.now(),
            "source": "测试源",
            "content": "测试正文内容",
            "summary": "测试摘要",
            "status": "pending",
            "field":"海外宏观",
            "importance":"3"
        }

        print("测试插入新闻条目...")
        success = await upsert_news_entry(test_entry)
        print(f"插入结果: {'成功' if success else '失败'}")

        # 测试查询
        print("\n测试查询新闻条目...")
        news = await get_news_by_url(test_entry["link"])
        if news:
            print(f"查询成功: ID={news['id']}, 标题={news['title']}")
        else:
            print("查询失败")

        # 测试更新内容
        print("\n测试更新内容...")
        success = await update_news_content(test_entry["link"], "更新的正文内容")
        print(f"更新内容结果: {'成功' if success else '失败'}")

        # 测试统计
        print("\n测试统计...")
        counts = await count_news()
        print(f"统计结果: {counts}")

        # 清理测试数据
        print("\n清理测试数据...")
        success = await delete_news_by_url(test_entry["link"])
        print(f"删除结果: {'成功' if success else '失败'}")

        await close_db()

    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        await close_db()

async def get_one_pending_news() -> dict | None:
    """
    从 news_entries 表中取一条 status = 'pending' 的新闻（通常按发布时间倒序取最早未处理的）
    返回完整的 entry 字典，或 None（没有待处理新闻）
    不需要输出参数，会自动选取pending的一条新闻
    """
    sql = """
    SELECT id, url, title, published, source, content, summary, status, field, importance, created_at, updated_at
    FROM news_entries
    WHERE status = 'pending'
    ORDER BY published DESC NULLS LAST, created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;   -- 防止并发重复处理
    """

    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(sql)
            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"获取待处理新闻失败: {e}")
        return None

"""
if __name__ == "__main__":
    # 直接运行此文件时执行测试
    asyncio.run(test_db_operations())
"""