# ZBJ Agent 完整消息处理流程

本文档梳理了当前 Agent (`zbj`) 从接收到用户消息，到解析、意图识别、Skill 路由执行，再到响应返回及反思重试的完整生命周期。

## 核心流程图

```mermaid
graph TD
    %% 1. 接入层
    A(["飞书 Webhook 回调"]) -->|"POST /"| B["Flask App<br>main.py"]
    B --> C{"Event Handler<br>core/event_handler.py"}
    
    C -->|"url_verification"| D["返回 Challenge"]
    C -->|"im.message.receive_v1"| E{"消息校验与过滤"}
    
    %% 2. 预处理层
    E -->|"重复事件 ID"| F["丢弃跳过"]
    E -->|"私聊 p2p"| G["提示前往群聊使用"]
    E -->|"未被 @"| F
    E -->|"群聊且被 @"| H["解析消息与引用上下文"]
    
    %% 3. 分发层
    H -->|"判断是否自我优化消息"| I{"消息类型分支"}
    I -->|"纯文本"| J("handle_text_only")
    I -->|"包含图片/引用图片"| K("handle_with_images")
    I -->|"自我优化重试"| J
    
    K --> L["下载依赖图片<br>bot.download_images"]
    L --> M("MessageProcessor<br>process_image_message")
    J --> N("MessageProcessor<br>process_text_message")
    
    %% 4. 处理层 (Processor)
    M --> O{"Processor 预处理"}
    N --> O
    O -->|"维护 History 保留最近10条"| P["检测 Pro 模式并清洗文本"]
    P --> Q["意图识别<br>determine_skill"]
    
    %% 5. 意图分类与 Skill 路由
    Q -->|"调用 LLM 进行意图推断"| R["SkillsLoader<br>execute_skill"]
    
    R --> S1["image_gen<br>图片生成"]
    R --> S2["image_understanding<br>图片理解"]
    R --> S3["general<br>通用对话"]
    R --> S4["funny<br>幽默吐槽"]
    R --> S5["reflection<br>反思技能"]
    R --> S6["其他动态加载 Skill"]
    
    %% 6. 响应层
    S1 --> T["组装 response_dict<br>包含文字/图片路径/反思上下文"]
    S2 --> T
    S3 --> T
    S4 --> T
    S5 --> T
    S6 --> T
    
    T --> U["bot.send_response"]
    U --> V(["调用 Lark API 发送回复"])
    
    %% 7. 反思与重试闭环 (异步)
    T --> W{"是否触发反思?<br>needs_reflection"}
    W -->|"否"| X(["流程结束"])
    W -->|"是"| Y["异步线程<br>perform_reflection_and_retry"]
    
    Y --> Z["调用 reflection Skill 进行反思<br>reflect_and_decide"]
    Z --> AA{"判断是否重试?<br>should_retry"}
    AA -->|"否"| X
    AA -->|"是"| AB["生成 '[优化重试]' Prompt"]
    AB -.->|"重新发起处理流程"| I
```

## 流程详细说明

1. **接入与路由 (Entry & Routing)**
   - 外部请求通过 `main.py` 的 Flask 应用进入，触发 `callback_event_handler`。
   - `core/event_handler.py` 注册了 `im.message.receive_v1` 事件处理消息。

2. **预处理与过滤 (Preprocessing & Filtering)**
   - **去重**：使用 `processed_events` 集合记录并跳过重复推送的 Event ID。
   - **聊天类型限制**：拦截 `p2p` 私聊，提示用户去群聊中 `@` 机器人。
   - **上下文解析**：提取消息文本，并通过 `get_quoted_message_info` 等方法，识别并提取被引用的历史图片和文本。

3. **消息分发机制 (Bot Handlers)**
   - `core/bot.py` 根据内容分为 `handle_text_only` 和 `handle_with_images` 两种处理链路。
   - 若包含图片，系统会自动调用 Lark API 下载相关图片并保存在本地。
   - 这两类链路最终均交由 `llm/processor.py` 中的 `MessageProcessor` 处理。

4. **意图识别与技能加载 (Intent & Skills)**
   - **Pro 模式检测**：过滤消息中的 "Pro模式"、"高清" 等关键词，打上 `use_pro=True` 标记。
   - **意图识别 (`determine_skill`)**：
     - 完全移除硬编码的关键词匹配，直接组装可用 Skills 的 `summary` 信息，调用大模型（LLM）去推断最合适的 Skill Name，以提供更智能、准确的意图判断。
   - **技能动态加载 (`SkillsLoader`)**：根据识别出的 Skill，动态寻找 `skills/{skill_name}/scripts/main.py` 并执行其 `execute` 方法。

5. **响应反馈 (Response)**
   - 各个 Skill 执行完毕后返回标准化的字典结构（如包含 `text`, `image_path`）。
   - `bot.py` 中的 `send_response` 负责将文字和生成的图片（若有）通过 Lark API 发送给用户。

6. **反思与自优化闭环 (Reflection & Auto-Retry)**
   - 针对复杂的图像生成或图像修改，Skill 可以返回 `needs_reflection=True` 及 `reflection_context`。
   - 此时会拉起一个后台独立线程 `perform_reflection_and_retry`，触发名为 `reflection` 的独立技能。
   - 反思模块会判断本次执行是否符合预期。如果需要优化，它会生成带有 `[优化重试]` 前缀的优化 Prompt，并直接在代码层面发起新一轮处理（回到步骤3），从而实现机器人的“自我重试修正”循环。
