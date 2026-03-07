from langchain_community.chat_models import ChatOpenAI
from dotenv import load_dotenv
import os
from langchain.agents import create_agent
import datetime
load_dotenv()

dp_key = os.getenv("DEEPSEEK_API_KEY")
dp_url = "https://api.deepseek.com"
llm = ChatOpenAI(model="DeepSeek-V3.2", temperature=0.7, max_tokens=2048)

system_prompt = f"""
现在是{datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}。
你是一位优秀的助理，在飞书上和同事们交流，帮助同事们解决问题
...
"""

agent = create_agent(llm=llm, system_prompt=system_prompt, tools=[web_search,run_rag_flow,create_calendar_event_tool])

def generate_response(messages) -> str:
    result = agent.invoke({"message":messages})
    return result['messages'][-1].content

