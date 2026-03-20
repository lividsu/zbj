import time
import os
import json
from PIL import Image
from llm.humanized_responses import designer

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    has_images = kwargs.get("has_images", False)
    image_paths = kwargs.get("image_paths", [])
    use_pro = kwargs.get("use_pro", False)

    result = {
        "text": "", 
        "image_path": None,
        "needs_reflection": False,
        "reflection_context": None
    }

    if not has_images or not image_paths:
        result["text"] = "请发送需要更改分辨率的图片。"
        return result
        
    image_path = image_paths[0]
    
    # 获取原图分辨率
    try:
        with Image.open(image_path) as img:
            orig_w, orig_h = img.size
    except Exception as e:
        result["text"] = f"无法读取图片: {e}"
        return result

    # 让 LLM 解析目标分辨率
    parse_prompt = f"""
用户想要修改图片分辨率。原图分辨率为 {orig_w}x{orig_h}。
用户的具体要求是: "{message}"

请提取出目标宽度和高度，以及是否需要填充背景（比如用户要求把正方形改成长方形，且提到留白、填充、在中间等）。
如果用户只给了一个比例（例如缩小一半），请计算出具体数值。
如果无法确定具体数值，请返回原图尺寸。
如果用户提到背景颜色（如白色、黑色），请提取出来。如果没提但需要填充，默认用白色（white）。
请只返回 JSON 格式，包含 width, height, needs_padding (布尔值), padding_color (字符串，如 "#FFFFFF" 或 "white")，不要有其他多余的字符或 markdown 标记。
示例: {{"width": 300, "height": 225, "needs_padding": true, "padding_color": "white"}}
"""
    response = processor.chat_handler.get_ai_response(parse_prompt, temperature=0.1)
    
    # 清理响应中的可能包含的 markdown
    clean_json = response.strip()
    if clean_json.startswith("```"):
        lines = clean_json.split('\n')
        lines = [line for line in lines if not line.startswith("```")]
        clean_json = "\n".join(lines).strip()
        
    try:
        target_size = json.loads(clean_json)
        target_w = int(target_size.get("width", orig_w))
        target_h = int(target_size.get("height", orig_h))
        needs_padding = bool(target_size.get("needs_padding", False))
        padding_color = target_size.get("padding_color", "white")
    except Exception as e:
        print(f"解析分辨率失败: {e}, 响应: {response}")
        target_w, target_h = orig_w, orig_h
        needs_padding = False
        padding_color = "white"
        
    # 判断是缩小还是放大（如果面积变小或任一边变小且另一边不变大，我们认为是缩小/裁剪/缩放）
    # 只要宽高都小于等于原图，或者用户明确是缩小，或者是需要填充背景（说明不用大模型重绘），我们用 PIL
    is_downscale = (target_w * target_h) <= (orig_w * orig_h) or needs_padding
    
    if is_downscale:
        try:
            with Image.open(image_path) as img:
                if needs_padding:
                    # 计算缩放比例，使得原图能完整放入目标尺寸中
                    ratio_w = target_w / orig_w
                    ratio_h = target_h / orig_h
                    ratio = min(ratio_w, ratio_h)
                    
                    new_w = int(orig_w * ratio)
                    new_h = int(orig_h * ratio)
                    
                    # 缩放原图
                    resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    
                    # 创建带有背景色的新图
                    new_img = Image.new("RGB", (target_w, target_h), padding_color)
                    
                    # 计算粘贴位置（居中）
                    paste_x = (target_w - new_w) // 2
                    paste_y = (target_h - new_h) // 2
                    
                    new_img.paste(resized_img, (paste_x, paste_y))
                    final_img = new_img
                else:
                    # 直接缩放，可能改变比例
                    final_img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                
                # 保存图片
                folder = os.path.join(os.getcwd(), "generated_images")
                os.makedirs(folder, exist_ok=True)
                filename = f"{chat_id}_{int(time.time())}_resized.png"
                out_path = os.path.join(folder, filename)
                
                final_img.save(out_path)
                
                result["image_path"] = out_path
                action_desc = "按比例缩放并居中填充背景" if needs_padding else "代码调小"
                result["text"] = f"分辨率已通过{action_desc}，从 {orig_w}x{orig_h} 修改为 {target_w}x{target_h}。"
                return result
        except Exception as e:
            result["text"] = f"代码调整分辨率失败: {e}"
            return result
    else:
        # 放大，使用大模型
        prompt = f"任务：无损放大/提升图片分辨率。目标分辨率大致为 {target_w}x{target_h}，请保留所有细节并增强画质。用户原始要求：{message}"
        
        text_response, image_bytes = processor.chat_handler.generate_image_with_references(
            image_paths=[image_path],
            user_prompt=prompt,
            use_pro=use_pro
        )
        
        if image_bytes:
            suffix = "_upscale_pro" if use_pro else "_upscale"
            result["image_path"] = processor._save_generated_image(image_bytes, chat_id, suffix)
            result["text"] = f"已通过大模型提升分辨率并增强画质，目标大约为 {target_w}x{target_h}。"
        else:
            result["text"] = designer.get_image_gen_failed() + " (放大失败)"
            if text_response:
                result["text"] += f"\n({text_response})"
                
        return result
