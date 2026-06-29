"""PlateAgent 全局配置 — Day 4 新增 Session/Memory 配置"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- DeepSeek ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# --- Session 配置 ---
SESSION_EVENT_TTL_SECONDS = int(os.getenv("SESSION_EVENT_TTL", "3600"))   # 事件保留 1 小时
SESSION_MAX_EVENTS = int(os.getenv("SESSION_MAX_EVENTS", "200"))           # 最多 200 条事件
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL", "86400"))               # 会话 24 小时过期

# --- Memory 配置 ---
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"     # 默认开启
MEMORY_TTL_SECONDS = int(os.getenv("MEMORY_TTL", "86400"))                  # 记忆 24 小时


# --- ChromaDB ---
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")  # 向量数据库持久化目录
CHROMA_COLLECTION_BLACKLIST = "plate_blacklist"
CHROMA_COLLECTION_PLATE_SPECS = "plate_specs"
CHROMA_COLLECTION_CONFUSION = "confusion_chars"

# --- Server ---
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))


def get_model_config():
    """Get DeepSeek model config"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY must be set in .env file")
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


def get_redis_url() -> str:
    """构建 Redis 连接 URL。

    支持三种模式：
        - 无密码：redis://host:port/db
        - 有密码：redis://:password@host:port/db
        - 自定义：直接设置 REDIS_URL 环境变量
    """
    custom_url = os.getenv("REDIS_URL", "")
    if custom_url:
        return custom_url
    if REDIS_PASSWORD:
        return f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    return f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
