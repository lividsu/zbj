from llm.humanized_responses import designer

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
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

    if not has_images or len(image_paths) < 2:
        # 如果只有一张图，可能是用户说“把这图里的产品放到沙滩上”等。
        # 虽然主要是多图，但单图如果也走到了这里，也做一定处理。
        if len(image_paths) == 1:
            prompt = f"任务：场景融合/主体替换。要求将图片中的主体放置到新的自然场景中，保证光影和透视自然融洽。用户的具体要求是：{message}"
        else:
            result["text"] = "请至少发送两张图片（如一张场景图，一张产品图）来进行合成。"
            return result
    else:
        # 至少两张图
        prompt = (
            f"任务：图像合成与场景融合。\n"
            f"要求：将提供的产品/主体自然地融合到场景中。请注意光影、透视和比例，使得最终生成的图片看起来像是一张真实的实拍照片，极其自然融洽。\n"
            f"用户的具体指令是：{message if message else '请将这些图片自然地合成在一起，把主体放到场景中'}"
        )

    text_response, image_bytes = processor.chat_handler.generate_image_with_references(
        image_paths=image_paths,
        user_prompt=prompt,
        use_pro=use_pro
    )
    
    if image_bytes:
        suffix = "_composite_pro" if use_pro else "_composite"
        result["image_path"] = processor._save_generated_image(image_bytes, chat_id, suffix)
        result["text"] = "图片合成已完成，已将主体自然融入场景中！"
        
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
