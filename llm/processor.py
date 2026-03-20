# message_processor.py
from typing import Tuple, List, Union, Any
import os
import time
import json
import re
from pathlib import Path
from .chat_client import ChatHandler
from core.skills_loader import SkillsLoader
from core.tools import ToolRegistry, ExecuteSkillTool

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
        self.skill_validation_report = self.skills_loader.validate_skills()
        if self.skill_validation_report["errors"]:
            print(f"⚠️ Skills 校验错误: {self.skill_validation_report['errors']}")
        if self.skill_validation_report["warnings"]:
            print(f"ℹ️ Skills 校验警告: {self.skill_validation_report['warnings']}")
        self.max_tool_iterations = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "5"))

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
        
        result = self._run_tool_loop(
            message=clean_message,
            chat_id=chat_id,
            has_images=False,
            image_paths=None,
            has_files=False,
            file_paths=None,
            file_exts=None,
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
        result = self._run_tool_loop(
            message=effective_message,
            chat_id=chat_id,
            has_images=True,
            image_paths=image_paths,
            has_files=False,
            file_paths=None,
            file_exts=None,
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

        result = self._run_tool_loop(
            message=normalized_message,
            chat_id=chat_id,
            has_images=False,
            image_paths=None,
            has_files=True,
            file_paths=file_paths,
            file_exts=file_exts,
            use_pro=False,
            current_attempt=0,
            original_prompt=normalized_message
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

    def _normalize_result(self, result: dict | None) -> dict:
        base = {
            "text": "",
            "image_path": None,
            "file_path": None,
            "pdf_path": None,
            "needs_reflection": False,
            "reflection_context": None,
            "tool_trace": []
        }
        if not isinstance(result, dict):
            return base
        base.update(result)
        return base

    def _extract_json_object(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return {}
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _plan_next_action(
        self,
        user_message: str,
        attachment_hint: str,
        skills_summary: str,
        tools_summary: str,
        trace: list[dict[str, Any]],
        disclosed_skill_context: str
    ) -> dict[str, Any]:
        trace_text = json.dumps(trace[-4:], ensure_ascii=False)
        planning_prompt = f"""你是一个任务编排器。你必须在多轮里决定下一步。

上下文:
- 用户请求: {user_message}
- 附件信息: {attachment_hint}
- 可用工具:
{tools_summary}
- Skills 摘要:
{skills_summary}
- 已执行轨迹:
{trace_text}

已披露的 Skill 详情:
{disclosed_skill_context or "暂无"}

【决策流程 - 请按以下步骤分析后再输出】:
第一步: 理解用户的真实意图。用户究竟想要什么结果？
第二步: 判断信息是否充足。执行所选技能是否有关键必要参数缺失（如：需要知道目标语言、具体尺寸、操作类型等）？这些缺失的参数是否可以从上下文合理推断？
第三步: 如果信息充足 → 选择最合适的技能执行（action=tool）；如果已有结果可直接回复 → action=final；仅当关键参数缺失且无法合理推断时 → action=clarify 向用户提问。

输出必须是 JSON，不要输出其他文字:
{{
  "action": "tool" 或 "clarify" 或 "final",
  "skill_name": "当 action=tool 时必填，要执行的技能名称",
  "message": "传给 skill 的消息，可为空",
  "clarify_text": "当 action=clarify 时必填，向用户提出的具体澄清问题（要友好、具体，如适用则给出选项或示例）",
  "final_text": "当 action=final 时输出给用户的文本"
}}

规则:
1) 只有一个工具 execute_skill。
2) 如果用户请求明确，优先选择最匹配技能并执行，不要多余询问。
3) 仅当关键必要参数缺失且无法合理推断时，才使用 clarify 向用户提问；不要询问可选参数。
4) 如果已有技能执行结果可直接回复，action 用 final。
5) clarify_text 必须具体说明需要什么信息，并给出选项或示例（如果适用）。"""
        response = self.chat_handler.get_ai_response(planning_prompt, temperature=0.2)
        action = self._extract_json_object(response)
        return action

    def _run_tool_loop(
        self,
        message: str,
        chat_id: str,
        has_images: bool,
        image_paths: List[str] | None,
        has_files: bool,
        file_paths: List[str] | None,
        file_exts: List[str] | None,
        use_pro: bool,
        current_attempt: int,
        original_prompt: str
    ) -> dict:
        registry = ToolRegistry()
        registry.register(ExecuteSkillTool())
        num_images = len(image_paths or [])
        num_files = len(file_paths or [])
        attachment_hint = "纯文本"
        if has_images:
            attachment_hint = f"{num_images}张图片"
        if has_files:
            attachment_hint = f"{num_files}个文件({','.join(file_exts or [])})"
        primary_skill = self.determine_skill(
            message=message,
            has_images=has_images,
            num_images=num_images,
            has_files=has_files,
            num_files=num_files,
            file_exts=file_exts
        )
        print(f"📋 首选 Skill: {primary_skill}")
        runtime = {
            "processor": self,
            "skills_loader": self.skills_loader,
            "chat_id": chat_id,
            "message": message,
            "has_images": has_images,
            "image_paths": image_paths,
            "has_files": has_files,
            "file_paths": file_paths,
            "file_exts": file_exts,
            "use_pro": use_pro,
            "current_attempt": current_attempt,
            "original_prompt": original_prompt
        }
        trace: list[dict[str, Any]] = []
        disclosed_skills: set[str] = set()
        last_result = self._normalize_result({})
        available_skills = {s["name"] for s in self.skills_loader.list_skills()}
        for idx in range(self.max_tool_iterations):
            disclosed_context = self.skills_loader.load_skills_for_context(sorted(disclosed_skills)) if disclosed_skills else ""
            action = self._plan_next_action(
                user_message=message,
                attachment_hint=attachment_hint,
                skills_summary=self.skills_loader.build_skills_summary(),
                tools_summary=registry.to_prompt_summary(),
                trace=trace,
                disclosed_skill_context=disclosed_context
            )
            action_type = str(action.get("action", "tool")).strip().lower()
            if action_type == "final":
                final_text = str(action.get("final_text", "")).strip()
                if final_text:
                    last_result["text"] = final_text
                    last_result["tool_trace"] = trace
                    return last_result
            if action_type == "clarify":
                clarify_text = str(action.get("clarify_text", "")).strip()
                if clarify_text:
                    print(f"❓ 向用户提问澄清: {clarify_text[:80]}...")
                    last_result["text"] = clarify_text
                    last_result["tool_trace"] = trace
                    return last_result
            skill_name = str(action.get("skill_name", "")).strip() or primary_skill
            if skill_name not in available_skills:
                skill_name = primary_skill
            disclosed_skills.add(skill_name)
            tool_payload = {
                "skill_name": skill_name,
                "message": str(action.get("message", message)),
                "reason": f"round_{idx + 1}"
            }
            print(f"🛠️ 第{idx + 1}轮调用技能: {skill_name}")
            execution = registry.execute("execute_skill", tool_payload, runtime=runtime)
            normalized = self._normalize_result(execution.get("result"))
            preview = (normalized.get("text") or "")[:120]
            trace.append({"round": idx + 1, "skill": skill_name, "text_preview": preview})
            normalized["tool_trace"] = trace
            last_result = normalized
            if normalized.get("image_path") or normalized.get("file_path") or normalized.get("pdf_path"):
                return normalized
            if normalized.get("needs_reflection"):
                return normalized
            message = normalized.get("text", "") or message
            runtime["message"] = message
            primary_skill = skill_name
        return last_result
