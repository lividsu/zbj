# humanized_responses.py
"""
人性化回复模块 - 让机器人像一个真实的设计师 (使用 FAST_MODEL 动态生成)
"""
from typing import Optional, List
from llm.chat_client import ChatHandler

class DesignerPersonality:
    """设计师人格化回复生成器"""
    
    def __init__(self):
        self.chat_handler = ChatHandler()
        
    def _generate(self, prompt: str) -> str:
        try:
            return self.chat_handler.get_ai_response(
                user_message=prompt,
                temperature=0.8,
                max_tokens=100
            ).strip(' "')
        except Exception as e:
            return "好的，马上处理..."
            
    def get_starting_image_gen(self, use_pro: bool = False) -> str:
        """获取开始生成图片的回复"""
        pro_hint = "并且提一下你启动了Pro/高清专业模式，" if use_pro else ""
        prompt = f"你是一个有个性的设计师。请用一句非常简短、自然、口语化的话（15字以内），告诉用户你马上要开始构思和画图了。{pro_hint}不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_image_gen_success(self, use_pro: bool = False) -> str:
        """获取图片生成成功的回复"""
        pro_hint = "并且提一下这是用Pro专业模式生成的，细节很好，" if use_pro else ""
        prompt = f"你是一个有个性的设计师。请用一句非常简短、自然、口语化的话（15字以内），告诉用户图片已经画好了，让他看看效果。{pro_hint}不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_image_gen_failed(self) -> str:
        """获取图片生成失败的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然、有点小遗憾的口语化话语（15字以内），告诉用户这次图片生成失败了，让他换个描述方式试试。不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_starting_image_edit(self) -> str:
        """获取开始编辑图片的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户你马上开始帮他修改/编辑这张图片。不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_image_edit_success(self) -> str:
        """获取图片编辑成功的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户图片已经修改完毕，让他看看效果如何。不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_starting_image_understand(self) -> str:
        """获取开始图片理解的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户你正在仔细看他发的图片，马上给他分析。不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_starting_reflection(self) -> str:
        """获取开始反思的回复"""
        prompt = "你是一个对自己要求很高的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户你自己先审视/检查一下刚才画的作品。不要有任何前缀或解释，直接输出回复内容。"
        return self._generate(prompt)
    
    def get_reflection_need_improve(self, score: int, issues: List[str]) -> str:
        """获取需要优化的反思回复"""
        issues_str = "、".join(issues[:3]) if issues else "一些细节"
        prompt = f"你是一个对自己要求很高的设计师。刚才对自己画的图打了{score}分（满分10分），发现了一些问题：{issues_str}。请用自然、口语化的语气（30字以内），告诉用户你不太满意，决定再调整优化一下。直接输出回复内容。"
        base = self._generate(prompt)
        return f"🤔 自检得分：{score}/10\n{base}"
    
    def get_reflection_satisfied(self, score: int, analysis: str = "") -> str:
        """获取满意的反思回复"""
        prompt = f"你是一个对自己要求很高的设计师。刚才对自己画的图打了{score}分（满分10分），觉得挺满意的。请用自然、自信的口语化语气（20字以内），告诉用户你自我审查通过了。直接输出回复内容。"
        base = self._generate(prompt)
        result = f"✅ 自检得分：{score}/10\n{base}"
        if analysis and len(analysis) < 50:
            result += f"\n{analysis}"
        return result
    
    def get_multi_image_notice(self, max_n: int, total: int) -> str:
        """获取多图片限制提示"""
        prompt = f"你是一个设计师。用户发了{total}张图片，但你一次最多只能处理{max_n}张。请用简短、友好的口语化语气（15字以内），告诉用户你先看前{max_n}张。直接输出回复内容。"
        return f"({self._generate(prompt)})"
    
    def get_image_info_failed(self) -> str:
        """获取获取图片信息失败的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户你没拿到图片信息，带点疑惑的语气。直接输出回复内容。"
        return self._generate(prompt)

    def get_image_process_failed(self) -> str:
        """获取处理图片失败的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户处理图片的时候出了点问题，带点抱歉的语气。直接输出回复内容。"
        return self._generate(prompt)

    def get_empty_message_reply(self) -> str:
        """获取收到空消息的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），告诉用户收到消息了但好像没什么内容，带点调侃的语气。直接输出回复内容。"
        return self._generate(prompt)

    def get_empty_text_reply(self) -> str:
        """获取收到纯艾特无文字的回复"""
        prompt = "你是一个有个性的设计师。请用一句简短、自然的口语化话语（15字以内），吐槽用户是不是忘了说点什么。直接输出回复内容。"
        return self._generate(prompt)
    
    def get_thinking(self) -> str:
        """获取思考中的回复"""
        prompt = "你是一个有个性的设计师。请用两三个字（比如：让我想想、嗯...），表达你正在思考。直接输出回复内容。"
        return self._generate(prompt)
    
    def humanize_response(self, technical_response: str, context: str = "general") -> str:
        """将技术性回复转换为更人性化的表达"""
        prompt = f"请将以下偏技术或机械的回复，用一个有个性的设计师的口吻重新表达，要求自然、口语化、不做作。保持原意，但去掉生硬的套话（如'好的'、'没问题'）。\n原回复：{technical_response}\n直接输出优化后的回复。"
        return self._generate(prompt)


class ResponseBuilder:
    """回复构建器 - 组合人性化回复"""
    
    def __init__(self):
        self.personality = DesignerPersonality()
    
    def build_image_gen_response(
        self, 
        success: bool, 
        use_pro: bool = False,
        custom_message: str = ""
    ) -> str:
        """构建图片生成的回复"""
        if success:
            base = self.personality.get_image_gen_success(use_pro)
            if custom_message:
                return f"{base}\n{custom_message}"
            return base
        else:
            return self.personality.get_image_gen_failed()
    
    def build_reflection_response(
        self,
        should_retry: bool,
        score: int,
        analysis: str,
        issues: List[str],
        attempt: int
    ) -> str:
        """构建反思回复"""
        if should_retry:
            return self.personality.get_reflection_need_improve(score, issues)
        else:
            return self.personality.get_reflection_satisfied(score, analysis)
    
    def build_retry_notice(self, attempt: int, improved_prompt: str) -> str:
        """构建重试通知"""
        notice = f"🔄 第{attempt}次优化中..."
        return notice


# 导出
designer = DesignerPersonality()
response_builder = ResponseBuilder()