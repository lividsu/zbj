import json
import logging
from config import config
from core.dependencies import message_api_client

def extract_image_keys_from_post(content_str):
    """从post类型消息中提取所有image_key"""
    try:
        content_data = json.loads(content_str)
        image_keys = []
        
        if "content" in content_data:
            for line in content_data["content"]:
                for element in line:
                    if element.get("tag") == "img" and "image_key" in element:
                        image_keys.append(element["image_key"])
                        if len(image_keys) >= config.MAX_IMAGES:
                            return image_keys
        
        return image_keys
    except Exception as e:
        logging.error(f"解析post消息失败: {e}")
        return []

def extract_text_from_post(content_str):
    """从post类型消息中提取文本内容"""
    try:
        content_data = json.loads(content_str)
        text_parts = []
        
        if "title" in content_data and content_data["title"]:
            text_parts.append(content_data["title"])
        
        if "content" in content_data:
            for line in content_data["content"]:
                for element in line:
                    if element.get("tag") == "text" and "text" in element:
                        text_parts.append(element["text"])
        
        return " ".join(text_parts).strip()
    except Exception as e:
        logging.error(f"解析post消息文本失败: {e}")
        return ""

def extract_text_from_message(message):
    """从消息对象中提取文本内容"""
    try:
        if message.message_type == "text":
            content_data = json.loads(message.content)
            return content_data.get("text", "").replace('@_user_1 ', '').strip()
        elif message.message_type == "post":
            return extract_text_from_post(message.content)
        else:
            return ""
    except:
        return ""

def get_quoted_message_info(message):
    """获取被引用消息的信息"""
    if not hasattr(message, 'parent_id') or not message.parent_id:
        return None
    
    parent_message_id = message.parent_id
    print(f"检测到引用消息, parent_id: {parent_message_id}")
    
    try:
        parent_message = message_api_client.get_message_content(parent_message_id)
        print(f"获取到被引用消息: {parent_message}")
        return parent_message
    except Exception as e:
        logging.error(f"获取被引用消息失败: {e}")
        return None
