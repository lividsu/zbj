import os
import sys
import argparse
sys.path.append(os.path.dirname(__file__))
from lark_bot.api import MessageApiClient
from dotenv import load_dotenv
from llm.chat_client import ChatHandler

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="可选测试：发送图片/发送文本/AI回复并发送")
    parser.add_argument("--send-image", action="store_true", help="发送图片到群")
    parser.add_argument("--send-text", action="store_true", help="发送文本到群")
    parser.add_argument("--ai", action="store_true", help="调用 chat.get_ai_response 并将回复发送到群")
    parser.add_argument("--image", type=str, default=os.path.join(os.path.dirname(__file__), "1.png"), help="图片路径")
    parser.add_argument("--text", type=str, default="哈哈哈", help="发送的文本内容")
    parser.add_argument("--ai-model", type=str, choices=["gemini", "openai", "deepseek"], default="gemini", help="AI模型类型")
    parser.add_argument("--ai-input", type=str, default="你好，来一段简短的自我介绍", help="AI输入内容")
    args = parser.parse_args()

    app_id = os.getenv("APP_ID")
    app_secret = os.getenv("APP_SECRET")
    lark_host = os.getenv("LARK_HOST", "https://open.feishu.cn")
    chat_id = os.getenv("TEST_CHAT_ID")

    if not app_id or not app_secret or not chat_id:
        print("APP_ID/APP_SECRET/TEST_CHAT_ID 未设置")
        sys.exit(1)

    client = MessageApiClient(app_id, app_secret, lark_host)

    if not (args.send_image or args.send_text or args.ai):
        print("未选择任何操作。使用 --send-image、--send-text 或 --ai")
        sys.exit(0)

    if args.send_image:
        if not os.path.exists(args.image):
            print(f"图片不存在: {args.image}")
            sys.exit(1)
        image_key = client.upload_image(args.image)
        client.send_image_with_chat_id(chat_id, image_key)
        print(f"已发送图片到群: {chat_id}")

    if args.send_text:
        client.send_text_with_chat_id(chat_id, args.text)
        print(f"已发送文本到群: {chat_id}")

    if args.ai:
        chat_handler = ChatHandler(model_type=args.ai_model)
        print(f"input is {args.ai_input}")
        ai_reply = chat_handler.get_ai_response(args.ai_input)
        print(f"AI回复: {ai_reply}")
        print(f"type is {type(ai_reply)}")
        client.send_text_with_chat_id(chat_id, ai_reply)
        print(f"已发送AI回复到群: {chat_id}")

if __name__ == "__main__":
    main()