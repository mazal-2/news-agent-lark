
# 飞书财经早报 & 群聊机器人（练习版）

基于飞书开放平台 + 大语言模型的个人练习项目  
主要实现：每日财经新闻抓取 → AI摘要 → 定时推送早报 + 群内智能回复

### 当前功能

- 从多个 RSS 源抓取财经新闻 → 去重 → 存入 PostgreSQL
- 使用本地大模型（Ollama qwen3:8b）对待处理新闻生成：
  - 50–100 字摘要
  - 领域分类（国内宏观/产业新闻/公司动态/国外宏观/海外公司/社会其他）
  - 重要性评分（0.0–5.0）
- 每天定时向指定飞书群推送「分区版财经早报」
- 支持群内 @机器人 进行自然语言对话（查新闻、问答、闲聊等）

### 项目结构（当前状态）

```
news-agent-lark/
├── scripts/                        # 独立运行的入口脚本
│   ├── get_rss.py                 # 抓取 + 入库
│   ├── daily_finance_brief.py     # 定时任务（抓取→处理→推送）
│   └── sender.py                  # 飞书机器人（WebSocket 长连接）
├── src/anews/
│   ├── agents/                    # LLM 相关逻辑
│   │   ├── main_agent.py
│   │   ├── monitor.py
│   │   ├── news_processor.py
│   │   └── work_flow_rag.py       # 群聊意图路由（langgraph）
│   ├── infrastructure/
│   │   └── db.py                  # 数据库操作（asyncpg）
│   └── utils/
│       └── handler.py             # 消息预处理（是否需要回复）
├── config.toml                    # RSS 源列表
├── .env                           # 飞书凭证 + 数据库连接
├── Dockerfile / docker-compose.yml
├── pyproject.toml / uv.lock
└── README.md
```

### 快速运行指南

#### 1. 环境准备

```bash
# 激活虚拟环境
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 确保依赖已安装（uv 或 pip）
uv sync    # 推荐（如果用了 uv）
# 或 pip install -r requirements.txt
```

#### 2. 配置（必须修改）

**.env**（飞书 + 数据库）

```ini
# 飞书应用凭证（必填）
LARK_APP_ID=cli_xxx
LARK_APP_SECRET=xxx
LARK_VERIFICATION_TOKEN=xxx
LARK_ENCRYPT_KEY=xxx

# PostgreSQL（建议 docker 跑）
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=你的密码
PG_DB=postgres
```

**config.toml**（RSS源，可增删）

```toml
[rss]
urls = [
  "https://rsshub.app/36kr/newsflashes",
  "https://rsshub.app/sina/finance",
  "https://rsshub.app/wallstreetcn/news",
  # ...
]
```

#### 3. 初始化数据库（只需一次）

```bash
# 方法一：直接运行 db.py（会自动创建表）
python src/anews/infrastructure/db.py

# 方法二：或手动执行建表（见 db.py 里的 create_tables 函数）
```

#### 4. 运行方式（选一种或组合）

**A. 只启动群聊机器人**

```bash
python scripts/sender.py
```

**B. 只执行一次新闻抓取 & 入库**

```bash
python scripts/get_rss.py
```

**C. 启动定时任务（抓取 → AI 处理 → 推送早报）**

```bash
# 默认定时：8:20 抓取 → 8:30 处理 → 9:00 发送（北京时间）
python scripts/daily_finance_brief.py
```

### 注意事项

- 群聊 ID 目前硬编码在 `daily_finance_brief.py` 中（变量 `DAILY_CHAT_ID`），请改为真实群 ID
- 大模型依赖本地 Ollama（qwen3:8b），请提前启动 ollama serve
- 首次运行建议先手动跑一次 `get_rss.py` + `news_processor.py` 确认数据流正常

这是一个练习项目，结构和代码都还在迭代中
```