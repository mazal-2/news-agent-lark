# 这里可以当作初次简单的筛选
def should_handle_message(message, text_content: str) -> tuple[bool, str | None]:
    """
    判断当前消息是否需要机器人处理，并返回清理后的文本
    message是一整条信息，里面包括了chat_id,sender这些元数据，text_content是就是message.content的内容，是一字符串
    返回:
        (是否需要处理, 清理后的纯文本 or None)
    """
    content_lower = text_content.lower()

    # ------------------- 触发条件 -------------------
    has_mention = message.mentions is not None and len(message.mentions) > 0
    has_keyword = any(kw in content_lower for kw in [
        "早报", "新闻", "资讯", "财经", "总结", "今天", "热点",
        "机器人", "@机器人", "请问", "帮我查", "告诉我"
    ])  # 可继续扩展

    if not (has_mention or has_keyword):
        return False, None

    # ------------------- 清理 @ 符号 -------------------
    clean_text = text_content
    if has_mention:
        for mention in message.mentions or []:
            clean_text = clean_text.replace(mention.key, "").strip()

    # 可以再做第二步清理：去掉多余空格、换行符等
    clean_text = " ".join(clean_text.split())

    return True, clean_text

"""
def generate_reponse_type(message)

    收到message, 以及text_content后，由agent判断这其内容应该流向哪个langgraph.Node,输出财报（generate_report）、日常回答(solve_problem)等多个内容
"""