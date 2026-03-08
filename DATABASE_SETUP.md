# 数据库设置指南

## 已完成的实现

已完成基于 asyncpg 的数据库操作模块 `src/anews/utils/db.py`，主要功能包括：

1. **连接池管理**：自动初始化和关闭连接池
2. **新闻条目增删改查**：支持插入、更新、查询、删除操作
3. **URL 去重**：使用 PostgreSQL 的 `ON CONFLICT` 机制，以 URL 为唯一标识
4. **异步支持**：所有函数均为 `async/await` 风格
5. **错误处理**：完整的 try...except 错误处理
6. **集成到 RSS 抓取**：在 `src/news/get_rss.py` 的 `main()` 函数末尾自动保存到数据库

## 数据库配置

环境变量配置（`.env` 文件）：

```env
# PostgreSQL
PG_HOST=localhost
PG_PORT=5432
PG_USER=news_user
PG_PASSWORD=dev_strong_9527
PG_DB=news_db
```

## 安装和设置 PostgreSQL

### 在 Windows 上安装 PostgreSQL

1. **下载并安装 PostgreSQL**
   - 访问 [PostgreSQL 官网](https://www.postgresql.org/download/windows/)
   - 下载安装程序并运行
   - 安装时记住设置的密码（建议使用 `postgres`）

2. **启动 PostgreSQL 服务**
   - 打开 "Services"（服务）应用
   - 找到 "postgresql-x64-xx" 服务
   - 确保服务状态为 "Running"

3. **创建数据库和用户**
   使用 pgAdmin 或命令行：
   ```sql
   -- 以 postgres 用户登录
   psql -U postgres

   -- 创建数据库
   CREATE DATABASE news_db;

   -- 创建用户
   CREATE USER news_user WITH PASSWORD 'dev_strong_9527';

   -- 授予权限
   GRANT ALL PRIVILEGES ON DATABASE news_db TO news_user;

   -- 退出
   \q
   ```

### 在 macOS 上安装 PostgreSQL

```bash
# 使用 Homebrew 安装
brew install postgresql

# 启动服务
brew services start postgresql

# 创建数据库和用户
psql postgres
```

然后执行上述 SQL 语句。

### 在 Linux (Ubuntu/Debian) 上安装 PostgreSQL

```bash
# 安装
sudo apt update
sudo apt install postgresql postgresql-contrib

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 切换到 postgres 用户
sudo -i -u postgres

# 创建数据库和用户
psql -c "CREATE DATABASE news_db;"
psql -c "CREATE USER news_user WITH PASSWORD 'dev_strong_9527';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE news_db TO news_user;"
```

## 测试数据库连接

运行测试脚本：

```bash
python test_db.py
```

如果连接成功，将显示：
```
============================================================
测试数据库连接
============================================================
[OK] 数据库连接池初始化成功
[OK] 表创建/验证成功
...
```

## 数据库表结构

```sql
CREATE TABLE news_entries (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    published TIMESTAMP WITH TIME ZONE,
    source TEXT,
    content TEXT,
    summary TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_news_url ON news_entries(url);
CREATE INDEX idx_news_published ON news_entries(published);
CREATE INDEX idx_news_status ON news_entries(status);
CREATE INDEX idx_news_created_at ON news_entries(created_at);
```

## 主要 API 函数

```python
# 初始化/关闭连接池
await db.init_db()
await db.close_db()

# 插入/更新新闻条目（URL 去重）
await db.upsert_news_entry(entry)

# 更新新闻内容
await db.update_news_content(url, content)

# 更新摘要
await db.update_news_summary(url, summary)

# 更新状态
await db.update_news_status(url, status)

# 查询新闻
await db.get_news_by_url(url)
await db.get_pending_news(limit=100)
await db.get_recent_news(limit=50)

# 统计
await db.count_news()

# 删除
await db.delete_news_by_url(url)
```

## 故障排除

### 1. 连接被拒绝
- 确保 PostgreSQL 服务正在运行
- 检查防火墙设置，确保端口 5432 开放
- 验证用户名和密码

### 2. 数据库/用户不存在
- 运行上述 SQL 语句创建数据库和用户
- 确保用户有正确的权限

### 3. 其他错误
- 查看日志文件中的详细错误信息
- 检查 `.env` 文件中的配置
- 确保 asyncpg 已正确安装

## 下一步

1. 启动 PostgreSQL 服务
2. 运行 `python test_db.py` 测试连接
3. 运行 `python -m src.news.get_rss` 测试完整的 RSS 抓取和数据库保存

数据库连接成功后，每次运行 RSS 抓取都会自动将新闻保存到 PostgreSQL 数据库中。