from llm.humanized_responses import designer

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    """
    Execute the image translate skill.
    """
    has_images = kwargs.get("has_images", False)
    image_paths = kwargs.get("image_paths", [])
    use_pro = kwargs.get("use_pro", False)
    current_attempt = kwargs.get("current_attempt", 0)
    original_prompt = kwargs.get("original_prompt", message)

    result = {
        "text": "", 
        "image_path": None,
        "needs_reflection": False,
        "reflection_context": None
    }

    if not has_images:
        result["text"] = "请发送需要更改语言的图片。"
        return result

    # 强调：语言以外的东西不要动，语言的调性和之前保持一致
    prompt = (
        f"任务：更改图片中的语言类型。\n"
        f"要求：除了语言以外的东西（如背景、人物、排版布局等）绝对不要动，语言的风格和调性要与之前保持一致。\n"
        f"用户的具体指令是：{message if message else '请翻译图片中的文字'}"
    )

    text_response, image_bytes = processor.chat_handler.generate_image_with_references(
        image_paths=image_paths,
        user_prompt=prompt,
        use_pro=use_pro
    )
    
    if image_bytes:
        suffix = "_translate_pro" if use_pro else "_translate"
        result["image_path"] = processor._save_generated_image(image_bytes, chat_id, suffix)
        result["text"] = "语言转换已完成！(已保持原图风格和调性)"
        
        if current_attempt < processor.max_retry_attempts:
            result["needs_reflection"] = True
            result["reflection_context"] = {
                "generated_image_path": result["image_path"],
                "original_prompt": original_prompt if original_prompt else prompt,
                "current_prompt": prompt,
                "reference_images": image_paths,
                "attempt": current_attempt,
                "use_pro": use_pro
            }
    else:
        result["text"] = designer.get_image_gen_failed()
        if text_response:
            result["text"] += f"\n({text_response})"
            
    return result
