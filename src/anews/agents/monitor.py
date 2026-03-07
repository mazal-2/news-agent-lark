from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

# 1. 定义结构化数据模型
class IsNeeded(BaseModel):
    is_needed: bool = Field(
        ..., 
        description="是否需要回复。如果用户提到新闻、资讯、热点或直接@机器人，设为 True；否则为 False。"
    )
    query: str = Field(
        default="", 
        description="如果 is_needed 为 True，提取具体的关键词；否则返回空字符串。"
    )
    response_needed: str = Field(
        default="",
        description="如果 is_needed 为 True，生成针对用户输入的回复内容；否则返回空字符串。"
    )
    

def main():
    # 2. 初始化模型（建议设置 temperature=0 保证判断稳定）
    llm = ChatOllama(model='qwen3:8b', temperature=0)

    # 3. 将模型与结构化输出绑定
    # 这一步是关键，它会自动处理 JSON 解析
    structured_llm = llm.with_structured_output(IsNeeded)

    # 4. 定义 Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "你是一个飞书群聊过滤助手。你的任务是判断用户的输入是否需要机器人介入回复。并生成回复\n"
            "判断标准：\n"
            "1. 包含关键词：新闻、资讯、热点、消息。\n"
            "2. 包含询问天气的请求或计算请求。\n"
            "3. 用户表现出明显的提问意图。"
        )),
        ("human", "{user_message}") # 这里定义的变量名是 user_message
    ])

    # 5. 构建链
    chain = prompt | structured_llm

    test_cases = [
        "今天天气怎么样？",
        "1+1等于几？",
        "你是谁？",
        "现在几点了？",
    ]

    for i, user_input in enumerate(test_cases):
        print(f"测试 #{i} │ 输入: {user_input}")
        try:
            # 6. 调用时，键名必须与 Prompt 中的变量名一致
            result = chain.invoke({"user_message": user_input})
            
            # 此时 result 直接就是 IsNeeded 对象
            print(f"结果   │ 需要回复: {result.is_needed} | 提取内容: {result.query} | 所生成回复：{result.response_needed}")
            
        except Exception as e:
            print(f"× 调用失败: {e}")
        print("-" * 50)

if __name__ == "__main__":
    main()