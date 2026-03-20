from config import config
from lark_bot.api import MessageApiClient
from lark_bot.event import EventManager
from llm.processor import MessageProcessor

# Initialize global services
message_api_client = MessageApiClient(config.APP_ID, config.APP_SECRET, config.LARK_HOST)
event_manager = EventManager()
message_processor = MessageProcessor()

# 记录正在进行的反思任务，避免重复处理
pending_reflections = {}
processed_events = set()
