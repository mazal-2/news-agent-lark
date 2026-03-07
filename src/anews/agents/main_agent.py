from langchain_community.chat_models import ChatOpenAI
from langchain_ollama import ChatOllama
from dotenv import load_dotenv
import os
from langchain.agents import create_agent
import datetime
# load_dotenv()

#dp_key = os.getenv("DEEPSEEK_API_KEY")
#dp_url = "https://api.deepseek.com"
# llm = ChatOpenAI(model="DeepSeek-V3.2", temperature=0.7, max_tokens=2048)
llm_qw = ChatOllama(model="qwen3:8b",)

system_prompt = f"""
现在是{datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}。
你是一位优秀的助理，在飞书上和同事们交流，帮助同事们解决问题，当同事们向你提问问题的时候，你的回答会尽量在解决对方疑惑的同时保持简洁，鉴于其在飞书群上的对话并不会太长。
如果有任务过于复杂，你可以简要回答的基础上，向提问者推荐深入解决问题的其他途径。
每次回答的内容尽量保持在200字以内

"""

agent = create_agent(model=llm_qw, system_prompt=system_prompt) # tools=[web_search,run_rag_flow,create_calendar_event_tool])

def generate_response(messages) -> str:
    result = agent.invoke({"messages":messages})
    return result['messages'][-1].content

"""
question = "你知道CPA这么考试的科目有哪些吗？有过一定财务基础的人在3个月内有希望通过吗？"
response = generate_response(question)
print(response)
"""
