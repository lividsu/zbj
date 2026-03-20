# message_processor.py
from typing import Optional, Tuple, List, Union
import os
import time
from pathlib import Path
from .chat_client import ChatHandler
from .humanized_responses import designer, response_builder
from core.skills_loader import SkillsLoader

class MessageProcessor:
    def __init__(self):
        self.chat_handler = ChatHandler(model_type=os.getenv("AI_MODEL_PROVIDER", "gemini"))
        # 对话历史记录
        self.conversation_history = {}
        
        # 反思优化相关配置
        self.max_retry_attempts = 2  # 最多重试次数
        self.min_satisfactory_score = 7  # 满意分数阈值
        
        # 记录正在进行的优化任务，避免无限循环
        # 格式: {chat_id: {'attempt': int, 'original_prompt': str, 'reference_images': list}}
        self.optimization_tasks = {}
        self.test_mode = str(os.getenv("AI_TEST_MODE", "")).lower() in ["1", "true", "yes", "on"]
        
        # Pro 模式关键词
        self.pro_keywords = [
            "pro模式", "pro 模式", "专业模式", "高级模式",
            "pro", "professional", "高清", "4k", "高质量",
            "精细", "专业版", "pro版"
        ]
        
        # Skills Loader
        workspace_dir = Path(os.getcwd())
        self.skills_loader = SkillsLoader(workspace=workspace_dir)

    def _check_pro_mode(self, message: str) -> Tuple[bool, str]:
        """
        检查是否启用 Pro 模式，并返回清理后的消息
        
        Returns:
            Tuple[bool, str]: (是否Pro模式, 清理后的消息)
        """
        msg_lower = message.lower()
        use_pro = False
        clean_message = message
        
        for keyword in self.pro_keywords:
            if keyword in msg_lower:
                use_pro = True
                # 从消息中移除 pro 关键词，避免影响生成
                import re
                clean_message = re.sub(re.escape(keyword), '', clean_message, flags=re.IGNORECASE).strip()
                break
        
        return use_pro, clean_message

    def is_self_optimization_message(self, message: str) -> bool:
        """检查是否是自我优化触发的消息"""
        return message.startswith("[优化重试]")

    def parse_optimization_message(self, message: str) -> dict:
        """解析优化消息，提取优化信息"""
        try:
            if not message.startswith("[优化重试]"):
                return None
            
            content = message[len("[优化重试]"):].strip()
            parts = content.split(" | ")
            
            result = {}
            for part in parts:
                if part.startswith("attempt="):
                    result['attempt'] = int(part[len("attempt="):])
                elif part.startswith("original="):
                    result['original_prompt'] = part[len("original="):]
                elif part.startswith("improved="):
                    result['improved_prompt'] = part[len("improved="):]
            
            return result
        except Exception as e:
            print(f"解析优化消息失败: {e}")
            return None

    def create_optimization_message(self, improved_prompt: str, attempt: int, original_prompt: str) -> str:
        """创建优化触发消息"""
        return f"[优化重试] attempt={attempt} | original={original_prompt} | improved={improved_prompt}"

    def determine_skill(
        self,
        message: str,
        has_images: bool = False,
        num_images: int = 0,
        has_files: bool = False,
        num_files: int = 0,
        file_exts: List[str] | None = None
    ) -> str:
        """
        基于技能系统分类消息，决定使用哪个 Skill (完全使用大模型判断)
        """
        skills_summary = self.skills_loader.build_skills_summary()
        if has_images:
            attachment_hint = f"（用户发送了 {num_images} 张图片）"
        elif has_files:
            ext_hint = ",".join(file_exts or [])
            attachment_hint = f"（用户发送了 {num_files} 个文件，类型: {ext_hint or 'unknown'}）"
        else:
            attachment_hint = "（用户发送了纯文本消息）"
        
        classification_prompt = f"""分析以下用户消息，并根据可用的 Skills 判断用户的意图属于哪一个 Skill。

可用 Skills 列表如下:
{skills_summary}

用户消息: {message}
附加信息: {attachment_hint}

请仔细阅读 Skills 列表中的描述，找出最匹配的 skill name。
如果消息为空或只是简单的@机器人，有图片时默认为 image_understanding，有文件时默认为 pdf，无附件时默认为 general。
请只回复匹配的 skill 的 name（例如: image_gen、funny、image_understanding、general），不要包含任何其他内容。"""

        response = self.chat_handler.get_ai_response(
            classification_prompt,
            temperature=0.3
        )
        result = response.strip().lower()
        
        # 验证返回的 skill name 是否有效
        available_skills = [s["name"] for s in self.skills_loader.list_skills()]
        for skill_name in available_skills:
            if skill_name in result:
                return skill_name
                
        # 默认 fallback
        if has_images:
            return "image_understanding"
        if has_files:
            return "pdf"
        return "general"

    def get_funny_response(self, message: str, context: list) -> str:
        """获取幽默回复"""
        funny_prompt = f"""你是一个有点毒舌但本质善良的设计师，请用幽默的方式回应下面的消息。
要求：
- 说话要像真人，不要太正式
- 可以适当阴阳怪气、吐槽
- 用emoji但不要太多
- 语气自然，像朋友聊天

消息: {message}"""

        return self.chat_handler.get_ai_response(
            funny_prompt,
            context=context,
            temperature=0.9
        )

    def _save_generated_image(self, image_bytes: bytes, chat_id: str, suffix: str = "") -> str:
        """保存生成的图片并返回路径"""
        folder = os.path.join(os.getcwd(), "generated_images")
        os.makedirs(folder, exist_ok=True)
        filename = f"{chat_id}_{int(time.time())}{suffix}.png"
        file_path = os.path.join(folder, filename)
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        print(f"图片已保存: {file_path}")
        return file_path

    def process_text_message(self, message: str, chat_id: str) -> dict:
        """
        处理纯文字消息
        """
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []
        
        # 检查是否是优化重试消息
        optimization_info = None
        current_attempt = 0
        original_prompt = message
        
        if self.is_self_optimization_message(message):
            optimization_info = self.parse_optimization_message(message)
            if optimization_info:
                current_attempt = optimization_info.get('attempt', 0)
                original_prompt = optimization_info.get('original_prompt', message)
                message = optimization_info.get('improved_prompt', message)
                print(f"=" * 50)
                print(f"🔄 优化重试 - 第 {current_attempt} 次尝试")
                print(f"📝 原始Prompt: {original_prompt}")
                print(f"✨ 优化后Prompt: {message}")
                print(f"=" * 50)
        
        # 检查 Pro 模式
        use_pro, clean_message = self._check_pro_mode(message)
        if use_pro:
            print(f"🚀 Pro模式启动")
        
        message_type = self.determine_skill(clean_message, has_images=False)
        print(f"📋 消息类型 (Skill): {message_type}")
        
        result = self.skills_loader.execute_skill(
            name=message_type,
            message=clean_message,
            chat_id=chat_id,
            processor=self,
            has_images=False,
            use_pro=use_pro,
            current_attempt=current_attempt,
            original_prompt=original_prompt
        )
        
        # 更新对话历史
        self._update_history(chat_id, message, result.get("text", ""))
        
        return result

    def process_image_message(
        self, 
        message: str, 
        chat_id: str, 
        image_paths: Union[str, List[str]]
    ) -> dict:
        """
        处理带图片的消息（支持1-2张图片）
        """
        # 统一转换为列表格式
        if isinstance(image_paths, str):
            image_paths = [image_paths]
        
        num_images = len(image_paths)
        print(f"📷 处理 {num_images} 张图片")
        
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []
        
        # 检查是否是优化重试消息
        optimization_info = None
        current_attempt = 0
        original_prompt = message
        
        if self.is_self_optimization_message(message):
            optimization_info = self.parse_optimization_message(message)
            if optimization_info:
                current_attempt = optimization_info.get('attempt', 0)
                original_prompt = optimization_info.get('original_prompt', message)
                message = optimization_info.get('improved_prompt', message)
                print(f"=" * 50)
                print(f"🔄 优化重试（带图片）- 第 {current_attempt} 次尝试")
                print(f"📝 原始Prompt: {original_prompt}")
                print(f"✨ 优化后Prompt: {message}")
                print(f"=" * 50)
        
        # 检查 Pro 模式
        use_pro, clean_message = self._check_pro_mode(message)
        if use_pro:
            print(f"🚀 Pro模式启动")
        
        effective_message = clean_message.strip() if clean_message else ""
        message_type = self.determine_skill(effective_message, has_images=True, num_images=num_images)
        print(f"📋 消息类型 (Skill): {message_type}, 图片数量: {num_images}")
        
        result = self.skills_loader.execute_skill(
            name=message_type,
            message=effective_message,
            chat_id=chat_id,
            processor=self,
            has_images=True,
            image_paths=image_paths,
            use_pro=use_pro,
            current_attempt=current_attempt,
            original_prompt=original_prompt
        )
        
        # 更新对话历史
        image_count_hint = f"[{num_images}张图片]" if num_images > 1 else "[图片]"
        self._update_history(chat_id, f"{image_count_hint} {message}", result.get("text", ""))
        
        return result

    def process_file_message(
        self,
        message: str,
        chat_id: str,
        file_paths: Union[str, List[str]]
    ) -> dict:
        """
        处理带文件的消息（当前重点支持 PDF）
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        num_files = len(file_paths)
        print(f"📄 处理 {num_files} 个文件")

        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        normalized_message = (message or "").strip()
        file_exts = sorted({Path(p).suffix.lower() for p in file_paths if p})

        message_type = self.determine_skill(
            normalized_message,
            has_files=True,
            num_files=num_files,
            file_exts=file_exts
        )
        print(f"📋 消息类型 (Skill): {message_type}, 文件数量: {num_files}")

        result = self.skills_loader.execute_skill(
            name=message_type,
            message=normalized_message,
            chat_id=chat_id,
            processor=self,
            has_files=True,
            file_paths=file_paths,
            file_exts=file_exts
        )

        file_count_hint = f"[{num_files}个文件]"
        self._update_history(chat_id, f"{file_count_hint} {normalized_message}", result.get("text", ""))
        return result

    def reflect_and_decide(self, reflection_context: dict) -> dict:
        """
        执行反思技能，并决定是否重试
        """
        return self.skills_loader.execute_skill(
            name="reflection",
            message="",
            chat_id="",
            processor=self,
            reflection_context=reflection_context
        )

    def _update_history(self, chat_id: str, user_msg: str, assistant_msg: str):
        """更新对话历史"""
        self.conversation_history[chat_id].append({"role": "user", "content": user_msg})
        self.conversation_history[chat_id].append({"role": "assistant", "content": assistant_msg})
        
        if len(self.conversation_history[chat_id]) > 10:
            self.conversation_history[chat_id] = self.conversation_history[chat_id][-10:]
