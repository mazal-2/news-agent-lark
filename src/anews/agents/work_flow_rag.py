from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel,Field
from typing import Literal,TypedDict,Annotated
from langgraph.graph import StateGraph,END
from langchain_core.messages import BaseMessage,HumanMessage,AIMessage
from langgraph.checkpoint.memory import MemorySaver

llm = ChatOllama(model="qwen3:8b",temperature=0.2)

class AgentState(TypedDict):
    message:Annotated[list[BaseMessage],"add"]
    clean_text:str
    response_type:Literal["news",'chat','ignore']
    final_reply:str  


def classify_response_type(state:AgentState) -> AgentState:  
    """
    输入当前状态，对变量进行处理并且返回下一个状态作为结果，在每个节点上会对这个AgentState的Dict进行处理？ 然后某个节点的
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是飞书群聊意图分类器。
根据用户消息判断最合适的回复类型，只输出以下之一：
- "news"    ：用户想要财经新闻、早报、资讯、总结、热点等
- "chat"    ：普通聊天、问答、闲聊、吐槽等
- "ignore"  ：纯表情、刷屏、无意义、辱骂、不需要机器人回复

用户消息：{clean_text}"""),
        ("human", "{clean_text}")
    ])

    chain = prompt | llm
    
    response = chain.invoke({"clean_text": state["clean_text"]})
    type_str = response.content.strip().lower()

    valid_types = {"news", "chat", "ignore"}
    response_type = type_str if type_str in valid_types else "chat"  # 默认兜底

    return {"response_type": response_type}

# 节点2：新闻分支处理（这里可以接你的 RSS / DB / RAG 逻辑）
def handle_news(state: AgentState) -> AgentState:
    # 伪代码：实际替换成你的新闻获取逻辑,这里面的reply需要进行调整;还未设计
    reply = f"今日财经早报（模拟）\n1. xx股票涨停\n2. xx新闻摘要\n\n来源：你的数据库"
    
    # 未来可以 await get_latest_news_summary() 或 run_rag 等
    return {"final_reply": reply}

def handle_chat(state:AgentState) -> AgentState:
    from anews.agents.main_agent import generate_response
    reply = generate_response(state['clean_text'])
    return {'final_reply':reply}

# 3. 条件路由函数
# ────────────────────────────────────────────────
def route_after_classify(state: AgentState) -> Literal["news", "chat", "end"]:
    t = state["response_type"]
    if t == "news":
        return "news"
    elif t == "chat":
        return "chat"
    else:
        return "end"   # ignore 直接结束
    
# 4，各个节点进行组装

workflow = StateGraph(state_schema=AgentState)
workflow.add_node("classify",classify_response_type)
workflow.add_node("news",handle_news)
workflow.add_node("chat",handle_chat)

workflow.set_entry_point("classify") # 定义第一个节点
workflow.add_conditional_edges(      # 添加条件节点，三个参数分别是source, path, path_map, 即能够从source节点出发，而后添加path，path这个函数输出的结果能够由下方的path_map进行映射到对应的下一个节点
    "classify",
    route_after_classify,
    {
        "news":"news",
        "chat":"chat",
        "end":END
    }
) 

workflow.add_edge("news",END)
workflow.add_edge("chat",END)

memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)
# 对这个graph对象进行invoke


