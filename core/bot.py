import os
import time
import logging
import threading
from config import config
from core.dependencies import message_api_client, message_processor
from llm.humanized_responses import designer

def download_image(message_id, image_key):
    """下载图片并返回本地路径"""
    try:
        image_path = message_api_client.download_image_from_message(message_id, image_key)
        print(f"图片已下载到: {image_path}")
        return image_path
    except Exception as e:
        logging.error(f"下载图片失败: {e}")
        return None

def download_images(message_id, image_keys):
    """下载多张图片并返回本地路径列表"""
    image_paths = []
    for image_key in image_keys:
        path = download_image(message_id, image_key)
        if path:
            image_paths.append(path)
    return image_paths

def download_file(message_id, file_key, file_name=None):
    """下载文件并返回本地路径"""
    try:
        file_path = message_api_client.download_file_from_message(message_id, file_key, file_name=file_name)
        print(f"文件已下载到: {file_path}")
        return file_path
    except Exception as e:
        logging.error(f"下载文件失败: {e}")
        return None

def download_files(message_id, file_items):
    """下载多文件并返回本地路径列表"""
    file_paths = []
    for item in file_items:
        file_key = item.get("file_key")
        file_name = item.get("file_name")
        if not file_key:
            continue
        path = download_file(message_id, file_key, file_name=file_name)
        if path:
            file_paths.append(path)
    return file_paths

def send_response(chat_id, response_dict):
    """发送AI响应(可能包含文字、图片和/或文件)"""
    text_response = response_dict.get("text", "")
    image_path = response_dict.get("image_path")
    file_path = response_dict.get("file_path") or response_dict.get("pdf_path")
    
    # 如果有生成的图片，先发送图片
    if image_path and os.path.exists(image_path):
        try:
            message_api_client.send_png_with_chat_id(chat_id, image_path)
            print(f"✅ 图片已发送: {image_path}")
        except Exception as e:
            logging.error(f"发送图片失败: {e}")
            text_response = (text_response or "") + "\n\n(图片发送失败了😢)"

    if file_path and os.path.exists(file_path):
        try:
            message_api_client.send_file_with_chat_id(chat_id, file_path)
            print(f"✅ 文件已发送: {file_path}")
        except Exception as e:
            logging.error(f"发送文件失败: {e}")
            text_response = (text_response or "") + "\n\n(文件发送失败了😢)"
    
    # 发送文字响应
    if text_response:
        message_api_client.send_text_with_chat_id(chat_id, text_response)
        print(f"✅ 文字响应已发送")

def perform_reflection_and_retry(chat_id, reflection_context, reference_image_paths=None):
    """执行反思并决定是否重试"""
    try:
        print(f"=" * 60)
        print(f"🔍 开始执行反思流程")
        print(f"=" * 60)
        
        # 进行反思
        reflection_result = message_processor.reflect_and_decide(reflection_context)
        
        # 发送反思结果的文字回复
        reflection_message = reflection_result.get("text", "")
        if reflection_message:
            message_api_client.send_text_with_chat_id(chat_id, reflection_message)
        
        if reflection_result.get('should_retry'):
            # 触发重试
            optimization_message = reflection_result['optimization_message']
            
            if reference_image_paths:
                print(f"🔄 带参考图片的优化重试")
                def retry_with_images():
                    time.sleep(1)
                    response_dict = message_processor.process_image_message(
                        optimization_message, 
                        chat_id, 
                        reference_image_paths
                    )
                    send_response(chat_id, response_dict)
                    
                    if response_dict.get("needs_reflection") and response_dict.get("reflection_context"):
                        perform_reflection_and_retry(
                            chat_id, 
                            response_dict["reflection_context"],
                            reference_image_paths
                        )
                threading.Thread(target=retry_with_images, daemon=True).start()
            else:
                print(f"🔄 纯文字优化重试")
                def retry_text_gen():
                    time.sleep(1)
                    response_dict = message_processor.process_text_message(
                        optimization_message, 
                        chat_id
                    )
                    send_response(chat_id, response_dict)
                    
                    if response_dict.get("needs_reflection") and response_dict.get("reflection_context"):
                        perform_reflection_and_retry(
                            chat_id, 
                            response_dict["reflection_context"],
                            None
                        )
                threading.Thread(target=retry_text_gen, daemon=True).start()
            
    except Exception as e:
        logging.error(f"反思流程出错: {e}")
        print(f"❌ 反思流程出错: {e}")

def handle_text_only(chat_id, user_message):
    """处理纯文字消息"""
    start_time = time.time()
    print(f"📝 处理纯文字消息: {user_message[:100]}...")
    
    response_dict = message_processor.process_text_message(user_message, chat_id)
    
    print(f"⏱️ AI处理时间: {time.time() - start_time:.2f}秒")
    send_response(chat_id, response_dict)
    
    if response_dict.get("needs_reflection") and response_dict.get("reflection_context"):
        print("🔍 检测到需要反思的图片生成任务")
        threading.Thread(
            target=perform_reflection_and_retry,
            args=(chat_id, response_dict["reflection_context"], None),
            daemon=True
        ).start()

def handle_with_images(chat_id, message_id, image_keys, user_message):
    """处理带图片的消息"""
    start_time = time.time()
    print(f"📷 处理带图片的消息: text='{user_message[:50] if user_message else ''}...', 图片数量={len(image_keys)}")
    
    image_paths = download_images(message_id, image_keys)
    if not image_paths:
        message_api_client.send_text_with_chat_id(chat_id, designer.get_image_gen_failed())
        return
    
    print(f"✅ 成功下载 {len(image_paths)} 张图片")
    
    response_dict = message_processor.process_image_message(user_message, chat_id, image_paths)
    
    print(f"⏱️ AI处理时间: {time.time() - start_time:.2f}秒")
    send_response(chat_id, response_dict)
    
    if response_dict.get("needs_reflection") and response_dict.get("reflection_context"):
        print("🔍 检测到需要反思的图片生成/编辑任务")
        threading.Thread(
            target=perform_reflection_and_retry,
            args=(chat_id, response_dict["reflection_context"], image_paths),
            daemon=True
        ).start()

def handle_with_image(chat_id, message_id, image_key, user_message):
    """处理带单张图片的消息（兼容旧接口）"""
    handle_with_images(chat_id, message_id, [image_key], user_message)

def handle_with_files(chat_id, message_id, file_items, user_message):
    """处理带文件的消息"""
    start_time = time.time()
    print(f"📄 处理带文件的消息: text='{user_message[:50] if user_message else ''}...', 文件数量={len(file_items)}")

    file_paths = download_files(message_id, file_items)
    if not file_paths:
        message_api_client.send_text_with_chat_id(chat_id, "文件下载失败，请重试。")
        return

    print(f"✅ 成功下载 {len(file_paths)} 个文件")

    response_dict = message_processor.process_file_message(user_message, chat_id, file_paths)
    print(f"⏱️ AI处理时间: {time.time() - start_time:.2f}秒")
    send_response(chat_id, response_dict)

def is_self_triggered_message(sender_id, message_content):
    """检查是否是机器人自己触发的优化消息"""
    if message_content and message_content.startswith("[优化重试]"):
        return True
    if config.BOT_OPEN_ID and sender_id == config.BOT_OPEN_ID:
        return True
    return False
