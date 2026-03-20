from llm.humanized_responses import response_builder

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    """
    Execute the reflection skill.
    """
    reflection_context = kwargs.get("reflection_context", {})
    
    generated_image_path = reflection_context.get("generated_image_path")
    original_prompt = reflection_context.get("original_prompt")
    reference_images = reflection_context.get("reference_images")
    current_attempt = reflection_context.get("attempt", 0)
    
    print(f"=" * 50)
    print(f"🔍 开始自我反思 - 第 {current_attempt + 1} 次检查")
    print(f"📝 原始需求: {original_prompt}")
    print(f"=" * 50)
    
    # 调用反思方法
    reflection_result = processor.chat_handler.reflect_on_generated_image(
        generated_image_path=generated_image_path,
        original_prompt=original_prompt,
        reference_image_paths=reference_images
    )
    
    print(f"📊 反思结果:")
    print(f"   - 分数: {reflection_result['score']}/10")
    print(f"   - 满意: {'是' if reflection_result['is_satisfactory'] else '否'}")
    print(f"   - 分析: {reflection_result['analysis']}")
    if reflection_result['issues']:
        print(f"   - 问题: {reflection_result['issues']}")
    if reflection_result.get('improved_prompt'):
        print(f"   - 优化Prompt: {reflection_result['improved_prompt']}")
    
    # 测试模式强制低分
    if processor.test_mode:
        reflection_result['score'] = 3
        reflection_result['is_satisfactory'] = False
        if not reflection_result.get('improved_prompt'):
            base_prompt = original_prompt or reflection_context.get("current_prompt") or ""
            reflection_result['improved_prompt'] = f"请提高细节和清晰度：{base_prompt}"
        print("⚠️ 测试模式：强制低分触发重试")
    
    result = {
        'should_retry': False,
        'text': "",
        'optimization_message': None,
        'reference_images': reference_images
    }
    
    # 判断是否需要重试
    if not reflection_result['is_satisfactory'] and current_attempt < processor.max_retry_attempts:
        improved_prompt = reflection_result.get('improved_prompt', '') + 'pro模式'
        if improved_prompt:
            result['should_retry'] = True
            result['optimization_message'] = processor.create_optimization_message(
                improved_prompt=improved_prompt,
                attempt=current_attempt + 1,
                original_prompt=original_prompt
            )
            print(f"=" * 50)
            print(f"🔄 决定重试！")
            print(f"✨ 改进后的Prompt: {improved_prompt}")
            print(f"=" * 50)
            
            result["text"] = response_builder.build_reflection_response(
                should_retry=True,
                score=reflection_result['score'],
                analysis=reflection_result['analysis'],
                issues=reflection_result['issues'],
                attempt=current_attempt + 1
            )
    else:
        print(f"✅ 不需要重试，结果{'满意' if reflection_result['is_satisfactory'] else '已达最大尝试次数'}")
        result["text"] = response_builder.build_reflection_response(
            should_retry=False,
            score=reflection_result['score'],
            analysis=reflection_result['analysis'],
            issues=reflection_result['issues'],
            attempt=current_attempt
        )
    
    return result