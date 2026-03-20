from llm.humanized_responses import designer, response_builder

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    """
    Execute the image generation/editing skill.
    """
    has_images = kwargs.get("has_images", False)
    image_paths = kwargs.get("image_paths", [])
    num_images = len(image_paths) if image_paths else 0
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
        # Text to Image
        text_response, image_bytes = processor.chat_handler.generate_image(
            message, 
            use_pro=use_pro
        )
        
        if image_bytes:
            suffix = "_pro" if use_pro else "_gen"
            result["image_path"] = processor._save_generated_image(image_bytes, chat_id, suffix)
            result["text"] = response_builder.build_image_gen_response(True, use_pro)
            
            if current_attempt < processor.max_retry_attempts:
                result["needs_reflection"] = True
                result["reflection_context"] = {
                    "generated_image_path": result["image_path"],
                    "original_prompt": original_prompt,
                    "current_prompt": message,
                    "reference_images": None,
                    "attempt": current_attempt,
                    "use_pro": use_pro
                }
        else:
            result["text"] = response_builder.build_image_gen_response(False)
            if text_response:
                result["text"] += f"\n({text_response})"
    else:
        # Image to Image (Editing/Styling)
        if num_images == 1:
            prompt = message if message else "基于这张图片进行创意改编"
        else:
            prompt = message if message else "基于这些图片进行创意合成或融合"
        
        text_response, image_bytes = processor.chat_handler.generate_image_with_references(
            image_paths=image_paths,
            user_prompt=prompt,
            use_pro=use_pro
        )
        
        if image_bytes:
            suffix = "_pro_edited" if use_pro else "_edited"
            result["image_path"] = processor._save_generated_image(image_bytes, chat_id, suffix)
            if num_images > 1:
                result["text"] = designer.get_image_edit_success() + " (基于多张图片)"
            else:
                result["text"] = designer.get_image_edit_success()
            
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
