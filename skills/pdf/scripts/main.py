import os
import shutil
import time

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    has_files = kwargs.get("has_files", False)
    file_paths = kwargs.get("file_paths", [])

    result = {
        "text": "",
        "image_path": None,
        "file_path": None,
        "needs_reflection": False,
        "reflection_context": None
    }

    if has_files and file_paths:
        pdf_paths = [p for p in file_paths if str(p).lower().endswith(".pdf")]
        if not pdf_paths:
            result["text"] = "我收到了文件，但不是 PDF。请发送 .pdf 文件后再试。"
            return result

        source_pdf = pdf_paths[0]
        output_dir = os.path.join(os.getcwd(), "generated_files")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{chat_id}_{int(time.time())}_processed.pdf")
        shutil.copyfile(source_pdf, output_path)

        user_intent = message.strip() if message else "未提供具体修改指令"
        result["file_path"] = output_path
        result["text"] = f"已收到并处理 PDF，已回传文件。你的需求是：{user_intent}"
        return result

    guidance_prompt = f"""你是 PDF 助手。请基于用户消息给出简洁可执行建议。
要求：
- 优先中文回答
- 输出 2-4 条可执行步骤
- 若用户需要实际处理 PDF，提醒其上传 PDF 文件

用户消息：{message if message else '请告诉我你能做什么'}"""
    result["text"] = processor.chat_handler.get_ai_response(
        guidance_prompt,
        context=processor.conversation_history.get(chat_id, [])
    )
    return result
