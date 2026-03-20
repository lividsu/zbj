import json
import logging
import threading
from flask import jsonify

from config import config
from core.dependencies import event_manager, message_api_client, message_processor, processed_events
from core.message_parser import (
    extract_text_from_message, 
    get_quoted_message_info, 
    extract_image_keys_from_post, 
    extract_text_from_post
)
from core.bot import (
    is_self_triggered_message, 
    handle_text_only, 
    handle_with_images,
    handle_with_files,
    download_images,
    send_response,
    perform_reflection_and_retry
)
from llm.humanized_responses import designer

def _parse_file_item(content_str):
    try:
        content_data = json.loads(content_str)
        file_key = content_data.get("file_key")
        file_name = content_data.get("file_name")
        if file_key:
            return {"file_key": file_key, "file_name": file_name}
    except Exception as e:
        logging.error(f"解析文件消息失败: {e}")
    return None

@event_manager.register("url_verification")
def request_url_verify_handler(req_data):
    print("url_verification handler invoked")
    if req_data.event.token != config.VERIFICATION_TOKEN:
        raise Exception("VERIFICATION_TOKEN is invalid")
    return jsonify({"challenge": req_data.event.challenge})

@event_manager.register("im.message.receive_v1")
def message_receive_event_handler(req_data):
    print("=" * 60)
    print("📨 收到新消息")
    
    event_id = req_data.header.event_id
    if event_id in processed_events:
        print(f"⏭️ 跳过重复事件: {event_id}")
        return jsonify()
    
    processed_events.add(event_id)
    
    sender_id = req_data.event.sender.sender_id
    message = req_data.event.message
    open_id = sender_id.open_id
    
    print(f"📋 消息类型: {message.message_type}, 聊天类型: {message.chat_type}")

    if message.chat_type == "p2p":
        message_api_client.add_reaction(message.message_id)
        message_api_client.send_text_with_open_id(open_id, "嗨～请在群里@我吧，私聊我还不太会处理 😅")
        return jsonify()
    
    if message.chat_type == "group":
        is_mentioned = False
        if hasattr(message, 'mentions') and message.mentions:
            try:
                if config.BOT_NAME and message.mentions[0].name in {config.BOT_NAME}:
                    is_mentioned = True
            except Exception as e:
                print(f"检查mentions时出错: {e}")
        
        if not is_mentioned:
            print("未@机器人，跳过")
            return jsonify()
        
        # 确认收到消息后，添加 reaction
        message_api_client.add_reaction(message.message_id)
        
        current_text = extract_text_from_message(message)
        
        if is_self_triggered_message(open_id, current_text):
            print(f"🔄 检测到自我触发的优化消息")
            handle_text_only(message.chat_id, current_text)
            return jsonify()
        
        all_image_keys = []
        image_message_id = message.message_id
        quoted_file_item = None
        
        quoted_message = get_quoted_message_info(message)
        
        # ========== 情况1: 引用了消息 ==========
        if quoted_message:
            quoted_msg_type = quoted_message.get('msg_type')
            quoted_content = quoted_message.get('content')
            quoted_message_id = quoted_message.get('message_id')
            
            print(f"📎 被引用消息类型: {quoted_msg_type}")
            
            if quoted_msg_type == "image":
                try:
                    content_data = json.loads(quoted_content)
                    image_key = content_data.get("image_key")
                    if image_key:
                        all_image_keys.append(image_key)
                        image_message_id = quoted_message_id
                except Exception as e:
                    logging.error(f"处理被引用的图片消息失败: {e}")
            
            elif quoted_msg_type == "post":
                image_keys = extract_image_keys_from_post(quoted_content)
                if image_keys:
                    all_image_keys.extend(image_keys[:config.MAX_IMAGES])
                    image_message_id = quoted_message_id
                else:
                    quoted_text = extract_text_from_post(quoted_content)
                    combined_text = f"[引用内容: {quoted_text}]\n\n{current_text}" if quoted_text else current_text
                    handle_text_only(message.chat_id, combined_text)
                    return jsonify()
            
            elif quoted_msg_type == "text":
                try:
                    quoted_text = json.loads(quoted_content).get("text", "")
                except:
                    quoted_text = quoted_content
                combined_text = f"[引用内容: {quoted_text}]\n\n{current_text}"
                handle_text_only(message.chat_id, combined_text)
                return jsonify()
            elif quoted_msg_type == "file":
                quoted_file_item = _parse_file_item(quoted_content)
            
            if all_image_keys:
                current_image_keys = []
                
                if message.message_type == "post":
                    current_image_keys = extract_image_keys_from_post(message.content)
                elif message.message_type == "image":
                    try:
                        content_data = json.loads(message.content)
                        image_key = content_data.get("image_key")
                        if image_key:
                            current_image_keys = [image_key]
                    except Exception as e:
                        logging.error(f"解析当前图片消息失败: {e}")
                
                remaining_slots = config.MAX_IMAGES - len(all_image_keys)
                if current_image_keys and remaining_slots > 0:
                    quoted_image_paths = download_images(quoted_message_id, all_image_keys)
                    current_image_paths = download_images(message.message_id, current_image_keys[:remaining_slots])
                    
                    all_image_paths = quoted_image_paths + current_image_paths
                    if all_image_paths:
                        response_dict = message_processor.process_image_message(current_text, message.chat_id, all_image_paths)
                        send_response(message.chat_id, response_dict)
                        
                        if response_dict.get("needs_reflection") and response_dict.get("reflection_context"):
                            threading.Thread(
                                target=perform_reflection_and_retry,
                                args=(message.chat_id, response_dict["reflection_context"], all_image_paths),
                                daemon=True
                            ).start()
                        
                        total_found = len(all_image_keys) + len(current_image_keys)
                        if total_found > config.MAX_IMAGES:
                            notice = designer.get_multi_image_notice(config.MAX_IMAGES, total_found)
                            message_api_client.send_text_with_chat_id(message.chat_id, notice)
                    return jsonify()
            
            if all_image_keys:
                handle_with_images(message.chat_id, image_message_id, all_image_keys, current_text)
                return jsonify()
            if quoted_file_item:
                handle_with_files(message.chat_id, quoted_message_id, [quoted_file_item], current_text)
                return jsonify()
        
        # ========== 情况2: 当前消息直接包含图片 ==========
        if message.message_type == "image":
            try:
                content_data = json.loads(message.content)
                image_key = content_data.get("image_key")
                if image_key:
                    handle_with_images(message.chat_id, message.message_id, [image_key], current_text)
                else:
                    message_api_client.send_text_with_chat_id(message.chat_id, designer.get_image_info_failed())
            except Exception as e:
                logging.error(f"处理图片消息失败: {e}")
                message_api_client.send_text_with_chat_id(message.chat_id, designer.get_image_process_failed())
            return jsonify()
        
        elif message.message_type == "post":
            image_keys = extract_image_keys_from_post(message.content)
            if image_keys:
                keys_to_process = image_keys[:config.MAX_IMAGES]
                handle_with_images(message.chat_id, message.message_id, keys_to_process, current_text)
                
                if len(image_keys) > config.MAX_IMAGES:
                    notice = designer.get_multi_image_notice(config.MAX_IMAGES, len(image_keys))
                    message_api_client.send_text_with_chat_id(message.chat_id, notice)
            else:
                if current_text:
                    handle_text_only(message.chat_id, current_text)
                else:
                    message_api_client.send_text_with_chat_id(message.chat_id, designer.get_empty_message_reply())
            return jsonify()
        elif message.message_type == "file":
            file_item = _parse_file_item(message.content)
            if file_item:
                handle_with_files(message.chat_id, message.message_id, [file_item], current_text)
            else:
                message_api_client.send_text_with_chat_id(message.chat_id, "文件消息解析失败，请重新发送。")
            return jsonify()
        
        # ========== 情况3: 纯文字消息 ==========
        elif message.message_type == "text":
            if current_text:
                handle_text_only(message.chat_id, current_text)
            else:
                message_api_client.send_text_with_chat_id(message.chat_id, designer.get_empty_text_reply())
            return jsonify()
    
    return jsonify()
