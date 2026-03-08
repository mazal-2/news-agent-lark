"""
调用agent完成新闻摘要处
"""
from langchain_ollama import ChatOllama
from typing import Dict,Optional,Literal
import json
import asyncio
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel,Field
from anews.infrastructure.db import get_one_pending_news,update_news_analysis
from loguru import logger
from langchain_deepseek import ChatDeepSeek

class NewsAnalysis(BaseModel):
    summary: str = Field(..., description="50字以内深度摘要，必须包含关键数据")
    field: Literal[
        "国内宏观",
        "产业新闻",
        "公司动态",
        "国外宏观",
        "海外公司",
        "社会/其他"
    ] = Field(...)
    importance: float = Field(..., ge=0.0, le=5.0, description="0.0~5.0，步进0.5")

llm_dp = ChatDeepSeek(model="deepseek-chat",temperature=0.15)
llm = ChatOllama(model="qwen3:8b")
system_prompt = """
# Role
你是一位资深的财经新闻分析专家“小白”。你擅长从宏观政策、产业趋势和公司财报中提取核心逻辑，并能敏锐识别突发事件对产业链的潜在冲击。

# Task
请对接收的新闻标题和正文完成以下任务：
1. **深度摘要 (100字以内)**：
   - **数据驱动**：必须包含核心数值（金额、百分比、伤亡/受灾数等）。
   - **背景对比**：若文中提到对比数据（如“罕见”、“创纪录”、“同比增减”），必须体现。
   - **逻辑串联**：用“因果关系”或“影响路径”串联数据，而非简单的罗列。

2. **多维分类 (Field)**：
   若新闻不属于以下 5 类，请统一归类为“**社会/其他**”：
   - 国内宏观 / 国外宏观
   - 产业新闻 / 公司动态 / 海外公司
   - **社会/其他**：突发自然灾害、娱乐民生等与经济研究弱相关的资讯。

3. **重要性评分 (0.0-5.0)**：
   - 评分标准：0.5 为步进。
   - **加分项**：涉及半导体、新能源汽车(NEV)、AI 基础设施、关键供应链中断。
   - **减分项**：虽有伤亡但未触及核心工业区或宏观政策的局部突发事件。

# Constraints
- 必须且只能输出标准的 JSON 格式。
- 严禁包含任何 Markdown 代码块（如 ```json ）或多余的解释文字。
"""

prompt = ChatPromptTemplate.from_messages([("system",system_prompt),("human","标题：{title}\n正文：{content}")])

analyzer = prompt | llm.with_structured_output(NewsAnalysis)


async def summarize_and_update_news() -> bool:
    """
    主处理函数：取一条 pending 新闻 → 调用 LLM 分析 → 更新数据库
    返回是否成功处理了一条（用于循环判断是否继续）
    """
    entry = await get_one_pending_news()
    if not entry:
        return False

    url = entry["url"]
    title = entry.get("title", "")
    content = entry.get("content") or title  # 如果没正文，用标题兜底

    try:
        # 调用 LLM
        analysis: NewsAnalysis = await analyzer.ainvoke({
            "title": title,
            "content": content[:8000]  # 防止超长，qwen3:8b 上下文有限
        })

        # 准备更新数据
        update_data = {
            "summary": analysis.summary.strip(),
            "field": analysis.field,
            "importance": analysis.importance,
        }

        # 调用你已有的 update_news_analysis 函数
        success = await update_news_analysis(url, update_data)

        if success:
            logger.success(
                f"新闻分析完成并入库 | url={url} | "
                f"field={analysis.field} | importance={analysis.importance} | "
                f"摘要={analysis.summary[:40]}..."
            )
            return True
        else:
            logger.warning(f"数据库更新失败: {url}")
            return False

    except Exception as e:
        logger.exception(f"分析新闻失败 url={url}")
        # 可选：标记为 failed 状态，避免重复尝试
     #  await update_news_status(url, "failed")  # 如果你有这个函数
        return False

async def process_pending_batch(limit=30):
    processed = 0
    while processed < limit:
        success = await summarize_and_update_news()
        if not success:
            break
        processed += 1
        await asyncio.sleep(0.5)  # 防止打满模型限速
    return processed

async def test_processor():
    success = await process_pending_batch(limit=10)
    print("本次处理是否成功:", success)


if __name__ == "__main__":
    asyncio.run(test_processor())