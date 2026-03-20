def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    """
    Execute the image understanding skill.
    """
    has_images = kwargs.get("has_images", False)
    image_paths = kwargs.get("image_paths", [])
    num_images = len(image_paths) if image_paths else 0

    result = {
        "text": "", 
        "image_path": None,
        "needs_reflection": False,
        "reflection_context": None
    }

    if not has_images or not image_paths:
        result["text"] = "请发送需要分析的图片。"
        return result

    if num_images == 1:
        prompt = message if message else "请描述一下这张图片，并给出你的评论。用自然的口语化风格，像设计师点评作品一样。"
    else:
        prompt = message if message else "请描述并比较这些图片，给出你的分析和评论。用自然的口语化风格。"
    
    result["text"] = processor.chat_handler.understand_images(
        image_paths=image_paths,
        user_prompt=prompt,
        context=processor.conversation_history.get(chat_id, [])
    )
        
    return result
