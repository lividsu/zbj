def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    """
    Execute the general conversation skill.
    """
    result = {
        "text": "", 
        "image_path": None,
        "needs_reflection": False,
        "reflection_context": None
    }

    result["text"] = processor.chat_handler.get_ai_response(
        message,
        context=processor.conversation_history.get(chat_id, [])
    )
        
    return result