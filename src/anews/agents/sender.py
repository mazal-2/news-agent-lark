import os
import json
from typing import Optional, Any
from lark_oapi.ws import Client
from lark_oapi import EventDispatcherHandler, Client as LarkClient
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, P2ImMessageReceiveV1,CreateMessageRequestBody
import uuid
from langchain_core.messages import HumanMessage


# 飞书应用配置
APP_ID = "cli_a92f29aba3f8dceb"
APP_SECRET = "nSwbglr5ft7HpPMbpiAxNdPkG5qRuKUW"
VERIFICATION_TOKEN = "MAyGkXEcNIvOLd3aZ0FZkQMksFsHSGWe"
ENCRYPT_KEY = "mazal-2"

# 创建 REST 客户端用于发送消息
lark_client = LarkClient.builder() \
    .app_id(APP_ID) \
    .app_secret(APP_SECRET) \
    .build()


def send_message(chat_id: str, message: str, msg_type: str = "text") -> bool:
    """
    发送消息到飞书群聊
    # 想办法
    Args:
        chat_id: 群聊ID
        message: 消息内容
        msg_type: 消息类型，支持 "text" 或 "post"（富文本）

    Returns:
        bool: 发送是否成功
    """
    try:
        if msg_type == "text":
            # 创建文本消息
            content = json.dumps({"text": message})
        elif msg_type == "post":
            # 创建富文本消息
            content = message  # 假设message已经是符合格式的JSON字符串
        else:
            print(f"不支持的消息类型: {msg_type}")
            return False

        # 调用飞书API发送消息
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type(msg_type) \
                .content(content) \
                .uuid(str(uuid.uuid4())) \
                .build()) \
            .build()

        # 3. 发起请求
        resp = lark_client.im.v1.message.create(request)
# 这个没问题
        if resp.success():
            print(f"消息发送成功: {resp.data.message_id}")
            return True
        else:
            print(f"消息发送失败: {resp.code}, {resp.msg}")
            return False

    except Exception as e:
        print(f"发送消息时出错: {e}")
        return False


def handle_receive_message(event: P2ImMessageReceiveV1) -> None:
    """
    处理接收到的消息
    """
    print(f"\n🔔 [收到原始事件通知] LogID: {event.header.event_id if event.header else 'N/A'}")
    try:
        if not event or not event.event or not event.event.message:
            print("收到空事件或消息")
            return

        # 2. 提取消息核心信息 (直接访问属性)
        message = event.event.message
        chat_id = message.chat_id
        content_str = message.content
        
        # 3. 提取发送者 ID (处理嵌套对象)
        # 注意：在自建应用中，如果没有给权限，user_id 可能是 None，通常建议使用 open_id
        sender = event.event.sender
        sender_id = "unknown"
        if sender and sender.sender_id:
            sender_id = sender.sender_id.open_id or "unknown"
        # 4. 解析消息内容 (JSON 字符串转字典)
        content_dict = {}
        try:
            content_dict = json.loads(content_str)
        except Exception:
            content_dict = {"text": content_str}

        text_content = content_dict.get("text", "")
        print(f"✅ 收到消息！群: {chat_id} | 发送者: {sender_id} | 内容: {text_content}")

        from anews.utils.handler import should_handle_message
        need_reply, clean_text = should_handle_message(message,text_content)

        if not need_reply:
            return
       
        #from anews.agents.main_agent import generate_response
        #reply_text = generate_response(messages=text_content) # 这里只能暂时回答单次对话
        from anews.agents.work_flow_rag import graph

        initial_input = {
            "messages":[HumanMessage(content=text_content)],
            "clean_text":clean_text,
            'response_type':None,
            'final_reply':None
        } # 不需要将这个State示例化么？
        
        thread_id = f'group_{chat_id}_user_{sender_id}'
        try:
            result = graph.invoke(  
                input=initial_input,
                config={'configurable':{'thread_id':thread_id}}
            )

        # reply_message 优化这个reply_need（should handle message）的逻辑，然后再可以做一个分流来整理这个回复的内容
            reply_text = result.get("final_reply","抱歉没能理解您的意思")
            send_message(chat_id, reply_text) # 在此处再进行补充
        except Exception as e:
            print(chat_id,"抱歉，处理过程出现了一点问题，请稍后再试")
            # TODO: 这里可以添加AI回复的逻辑，调用其他模块生成新闻摘要

    except Exception as e:
        # 打印完整的堆栈跟踪有助于调试
        import traceback
        print(f"❌ 处理消息时出错:\n{traceback.format_exc()}")


# 创建事件处理器
event_handler = EventDispatcherHandler.builder("", VERIFICATION_TOKEN) \
    .register_p2_im_message_receive_v1(handle_receive_message) \
    .build()

# 创建WebSocket客户端
ws_client = Client(
    app_id=APP_ID,
    app_secret=APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG
)


def start_bot():
    """
    启动飞书机器人
    """
    print("启动飞书机器人...")
    try:
        ws_client.start()
    except KeyboardInterrupt:
        print("机器人停止")
    except Exception as e:
        print(f"机器人启动失败: {e}")


def send_daily_news(chat_id: str, news_content: str):
    """
    发送每日财经新闻

    Args:
        chat_id: 群聊ID
        news_content: 新闻内容（由其他模块生成）
    """
    print(f"向群 {chat_id} 发送每日财经新闻")

    # 可以在这里格式化新闻内容
    formatted_news = f"📊 每日财经早报 📊\n\n{news_content}\n\n---\n数据来源：多家财经媒体"

    success = send_message(chat_id, formatted_news)
    return success


if __name__ == "__main__":
    # 启动机器人
    start_bot()