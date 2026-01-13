def extract_text_from_response(resp) -> str:
    """
    从 Ark / OpenAI Responses API 中安全提取最终文本
    """
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    return c.text
    return ""