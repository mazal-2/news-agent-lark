from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel,Field
from typing import Literal,TypedDict,Annotated
from langgraph.graph import StateGraph,END
from langchain_core.messages import BaseMessage,HumanMessage,AIMessage

llm = ChatOllama(model="qwen3:8b",temperature=0.2)

class AgentState(TypedDict):
    message:Annotated[list[BaseMessage],"add"]
    clean_text:str
    response_type:Literal["news",'chat','ignore']
    final_reply:str  # 





