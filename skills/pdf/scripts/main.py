import os
import sys
import json
import re
import time
import tempfile
import zipfile
from pathlib import Path

# Add scripts directory to path for local imports (fill_fillable_fields imports extract_form_field_info, etc.)
SCRIPTS_DIR = Path(__file__).parent


def _add_scripts_to_path():
    scripts_str = str(SCRIPTS_DIR)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)


def _parse_json(response: str):
    """Extract JSON object or array from AI response text."""
    text = (response or "").strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
    return None


def _check_fillable(pdf_path: str) -> bool:
    """Check whether PDF has fillable form fields."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        return bool(reader.get_fields())
    except Exception:
        return False


def _extract_text(pdf_path: str) -> str:
    """Extract plain text from PDF (tries pdfplumber first, then pypdf)."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text += f"[第{i+1}页]\n{page.extract_text() or ''}\n\n"
        return text.strip()
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for i, page in enumerate(reader.pages):
            text += f"[第{i+1}页]\n{page.extract_text() or ''}\n\n"
        return text.strip()
    except Exception:
        return ""


def _convert_to_images(pdf_path: str, output_dir: str) -> list:
    _add_scripts_to_path()
    from convert_pdf_to_images import convert
    os.makedirs(output_dir, exist_ok=True)
    convert(pdf_path, output_dir)
    return sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".png")
    )


def _extract_field_info(pdf_path: str) -> list:
    _add_scripts_to_path()
    from extract_form_field_info import get_field_info
    from pypdf import PdfReader
    return get_field_info(PdfReader(pdf_path))


def _extract_form_structure(pdf_path: str) -> dict:
    _add_scripts_to_path()
    from extract_form_structure import extract_form_structure
    return extract_form_structure(pdf_path)


def _fill_fillable_pdf(input_pdf: str, field_values: list, output_pdf: str):
    _add_scripts_to_path()
    tmp_json = os.path.join(tempfile.mkdtemp(), "field_values.json")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(field_values, f, ensure_ascii=False, indent=2)
    from fill_fillable_fields import fill_pdf_fields, monkeypatch_pydpf_method
    monkeypatch_pydpf_method()
    fill_pdf_fields(input_pdf, tmp_json, output_pdf)


def _fill_annotations_pdf(input_pdf: str, fields_data: dict, output_pdf: str):
    _add_scripts_to_path()
    tmp_json = os.path.join(tempfile.mkdtemp(), "annotations.json")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(fields_data, f, ensure_ascii=False, indent=2)
    from fill_pdf_form_with_annotations import fill_pdf_form
    fill_pdf_form(input_pdf, tmp_json, output_pdf)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute(message: str, chat_id: str, processor, **kwargs) -> dict:
    has_files = kwargs.get("has_files", False)
    file_paths = kwargs.get("file_paths", [])

    result = {
        "text": "",
        "image_path": None,
        "file_path": None,
        "needs_reflection": False,
        "reflection_context": None,
    }

    # --- No file attached: give guidance ---
    if not has_files or not file_paths:
        guidance_prompt = f"""你是 PDF 助手。请基于用户消息给出简洁可执行建议。
要求：
- 优先中文回答
- 输出 2-4 条可执行步骤
- 若用户需要实际处理 PDF，提醒其上传 PDF 文件

用户消息：{message if message else '请告诉我你能做什么'}"""
        result["text"] = processor.chat_handler.get_ai_response(
            guidance_prompt,
            context=processor.conversation_history.get(chat_id, [])
        )
        return result

    pdf_paths = [p for p in file_paths if str(p).lower().endswith(".pdf")]
    if not pdf_paths:
        result["text"] = "我收到了文件，但不是 PDF 格式。请发送 .pdf 文件后再试。"
        return result

    source_pdf = pdf_paths[0]
    output_dir = os.path.join(os.getcwd(), "generated_files")
    os.makedirs(output_dir, exist_ok=True)
    ts = int(time.time())
    user_intent = (message or "").strip()

    # --- Intent detection ---
    intent_prompt = f"""用户发送了一个 PDF 文件。根据用户消息判断操作意图，只回复以下标识之一：
- fill_form: 填写/填入/填表/表单/form
- extract_text: 提取文字/阅读/查看/翻译/内容
- rotate: 旋转页面
- merge: 合并多个PDF
- split: 拆分PDF
- query: 询问PDF内容或问题

用户消息："{user_intent if user_intent else '（无说明）'}"

只输出标识，不要其他内容。"""
    intent_raw = processor.chat_handler.get_ai_response(intent_prompt, temperature=0.1).strip().lower()

    if "fill" in intent_raw or "form" in intent_raw:
        intent = "fill_form"
    elif "extract" in intent_raw or "text" in intent_raw:
        intent = "extract_text"
    elif "rotat" in intent_raw:
        intent = "rotate"
    elif "merge" in intent_raw:
        intent = "merge"
    elif "split" in intent_raw:
        intent = "split"
    else:
        intent = "fill_form" if user_intent else "query"

    print(f"📋 PDF 意图: {intent}  (原始: {intent_raw!r})")

    # ==========================================================================
    # FILL FORM
    # ==========================================================================
    if intent == "fill_form":
        try:
            tmp_dir = tempfile.mkdtemp(prefix=f"pdf_{chat_id}_")
            output_pdf = os.path.join(output_dir, f"{chat_id}_{ts}_filled.pdf")

            has_fillable = _check_fillable(source_pdf)
            print(f"📋 有可填字段: {has_fillable}")

            # Convert PDF pages to images for visual understanding
            images_dir = os.path.join(tmp_dir, "images")
            image_paths = []
            try:
                image_paths = _convert_to_images(source_pdf, images_dir)
                print(f"✅ 转换为 {len(image_paths)} 张图片")
            except Exception as e:
                print(f"⚠️ 图片转换失败（将仅用字段信息）: {e}")

            if has_fillable:
                # ---------- Fillable form ----------
                field_info = _extract_field_info(source_pdf)
                field_info_str = json.dumps(field_info, ensure_ascii=False, indent=2)

                fill_prompt = f"""你是 PDF 表单填写专家。

用户指令：{user_intent if user_intent else '请根据表单字段填写合适的示例数据'}

表单字段信息（每个字段的 ID、类型、页码）：
{field_info_str}

请根据用户指令，为需要填写的字段提供值。
只输出 JSON 数组，不要任何其他文字：
[
  {{
    "field_id": "字段ID（必须与上面完全一致）",
    "description": "字段描述",
    "page": 页码整数,
    "value": "填写的值"
  }}
]

填写规则：
- checkbox 字段：使用对应的 checked_value 或 unchecked_value
- radio_group 字段：使用 radio_options 中某个 value
- choice 字段：使用 choice_options 中某个 value
- 如果用户没有提供具体数据，请用合理的示例数据"""

                if image_paths:
                    fill_response = processor.chat_handler.understand_images(image_paths, fill_prompt)
                else:
                    fill_response = processor.chat_handler.get_ai_response(fill_prompt, temperature=0.2)

                field_values = _parse_json(fill_response)
                if not isinstance(field_values, list) or not field_values:
                    result["text"] = f"无法解析填写指令，请提供更具体的说明。\n\nAI响应摘要：{fill_response[:300]}"
                    return result

                _fill_fillable_pdf(source_pdf, field_values, output_pdf)

                if os.path.exists(output_pdf):
                    result["file_path"] = output_pdf
                    result["text"] = f"✅ PDF 表单已填写完成，共填写了 {len(field_values)} 个字段。"
                else:
                    result["text"] = "PDF 填写失败：输出文件未生成。"

            else:
                # ---------- Non-fillable form: use text annotations ----------
                structure = _extract_form_structure(source_pdf)
                pages_info = structure.get("pages", [])
                labels = structure.get("labels", [])
                checkboxes = structure.get("checkboxes", [])

                structure_summary = json.dumps({
                    "pages": pages_info,
                    "labels": labels[:80],
                    "checkboxes": checkboxes,
                }, ensure_ascii=False)

                fill_prompt = f"""你是 PDF 表单填写专家。这个 PDF 没有可填字段，需要用文字注释填写。

用户指令：{user_intent if user_intent else '请根据表单标签填写合适的示例数据'}

PDF 结构（PDF 坐标系：原点在页面左上角，y 向下增大，单位为 PDF 点）：
{structure_summary}

请为每个需要填写的字段确定内容和位置，只输出以下 JSON，不要其他文字：
{{
  "pages": [
    {{"page_number": 1, "pdf_width": 页面宽度数值, "pdf_height": 页面高度数值}}
  ],
  "form_fields": [
    {{
      "page_number": 1,
      "description": "字段描述",
      "field_label": "字段标签文本",
      "label_bounding_box": [标签x0, 标签top, 标签x1, 标签bottom],
      "entry_bounding_box": [填入区x0, 填入区top, 填入区x1, 填入区bottom],
      "entry_text": {{"text": "填写的内容", "font_size": 10}}
    }}
  ]
}}

根据标签位置，entry_bounding_box 通常在标签右侧或下方的空白区域。"""

                if image_paths:
                    fill_response = processor.chat_handler.understand_images(image_paths, fill_prompt)
                else:
                    fill_response = processor.chat_handler.get_ai_response(fill_prompt, temperature=0.2)

                fields_data = _parse_json(fill_response)
                if not isinstance(fields_data, dict) or "form_fields" not in fields_data:
                    result["text"] = "无法解析表单结构，请提供更具体的填写指令。"
                    return result

                _fill_annotations_pdf(source_pdf, fields_data, output_pdf)

                if os.path.exists(output_pdf):
                    num_fields = len(fields_data.get("form_fields", []))
                    result["file_path"] = output_pdf
                    result["text"] = f"✅ PDF 已填写完成，共添加了 {num_fields} 处文字注释。"
                else:
                    result["text"] = "PDF 填写失败：输出文件未生成。"

        except Exception as e:
            import traceback
            print(f"❌ PDF 表单填写错误:\n{traceback.format_exc()}")
            result["text"] = f"PDF 处理出错：{str(e)}"

        return result

    # ==========================================================================
    # EXTRACT TEXT
    # ==========================================================================
    elif intent == "extract_text":
        try:
            text = _extract_text(source_pdf)
            if not text:
                result["text"] = "未能从 PDF 中提取到文字（可能是扫描版 PDF，建议使用 OCR 工具）。"
                return result

            summary_prompt = f"""用户希望从 PDF 中提取或查看内容。
用户消息：{user_intent if user_intent else '提取文字内容'}

PDF 内容：
{text[:4000]}{'...(内容已截断)' if len(text) > 4000 else ''}

请根据用户需求整理和呈现内容，用中文简洁回答。"""
            result["text"] = processor.chat_handler.get_ai_response(
                summary_prompt,
                context=processor.conversation_history.get(chat_id, [])
            )
        except Exception as e:
            result["text"] = f"文字提取出错：{str(e)}"
        return result

    # ==========================================================================
    # ROTATE
    # ==========================================================================
    elif intent == "rotate":
        try:
            from pypdf import PdfReader, PdfWriter
            output_pdf = os.path.join(output_dir, f"{chat_id}_{ts}_rotated.pdf")
            angle = 90
            angle_match = re.search(r'(\d+)\s*度', user_intent)
            if angle_match:
                angle = int(angle_match.group(1))
            reader = PdfReader(source_pdf)
            writer = PdfWriter()
            for page in reader.pages:
                page.rotate(angle)
                writer.add_page(page)
            with open(output_pdf, "wb") as f:
                writer.write(f)
            result["file_path"] = output_pdf
            result["text"] = f"✅ PDF 所有页面已旋转 {angle} 度。"
        except Exception as e:
            result["text"] = f"旋转出错：{str(e)}"
        return result

    # ==========================================================================
    # MERGE
    # ==========================================================================
    elif intent == "merge":
        all_pdfs = [p for p in file_paths if str(p).lower().endswith(".pdf")]
        if len(all_pdfs) < 2:
            result["text"] = "合并 PDF 需要至少上传两个 PDF 文件。"
            return result
        try:
            from pypdf import PdfWriter, PdfReader
            output_pdf = os.path.join(output_dir, f"{chat_id}_{ts}_merged.pdf")
            writer = PdfWriter()
            for pdf in all_pdfs:
                reader = PdfReader(pdf)
                for page in reader.pages:
                    writer.add_page(page)
            with open(output_pdf, "wb") as f:
                writer.write(f)
            result["file_path"] = output_pdf
            result["text"] = f"✅ 已合并 {len(all_pdfs)} 个 PDF 文件。"
        except Exception as e:
            result["text"] = f"合并出错：{str(e)}"
        return result

    # ==========================================================================
    # SPLIT
    # ==========================================================================
    elif intent == "split":
        try:
            from pypdf import PdfReader, PdfWriter
            reader = PdfReader(source_pdf)
            num_pages = len(reader.pages)
            zip_path = os.path.join(output_dir, f"{chat_id}_{ts}_split.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for i, page in enumerate(reader.pages):
                    page_pdf = os.path.join(output_dir, f"page_{i+1}_tmp.pdf")
                    writer = PdfWriter()
                    writer.add_page(page)
                    with open(page_pdf, "wb") as f:
                        writer.write(f)
                    zf.write(page_pdf, f"page_{i+1}.pdf")
                    os.remove(page_pdf)
            result["file_path"] = zip_path
            result["text"] = f"✅ 已将 PDF（共 {num_pages} 页）拆分为单页文件并打包。"
        except Exception as e:
            result["text"] = f"拆分出错：{str(e)}"
        return result

    # ==========================================================================
    # QUERY / FALLBACK
    # ==========================================================================
    else:
        text = _extract_text(source_pdf)
        query_prompt = f"""用户发送了一个 PDF 文件。
用户问题/请求：{user_intent if user_intent else '请介绍这个 PDF 的内容'}

PDF 内容：
{text[:3000] if text else '（无法提取文字，可能是扫描版或图片型 PDF）'}{'...' if len(text or '') > 3000 else ''}

请根据 PDF 内容回答用户问题，用中文回答。"""
        result["text"] = processor.chat_handler.get_ai_response(
            query_prompt,
            context=processor.conversation_history.get(chat_id, [])
        )
        return result
