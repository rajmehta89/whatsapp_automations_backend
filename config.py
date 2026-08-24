import os
from dotenv import load_dotenv
load_dotenv()

# Database Configuration
CONV_DB_PATH = "db/conversations.sqlite3"
NEO_DB_PATH = "db/neonize.sqlite3"

# "ollama" or "openai" or "openrouter" or "azure"
LLM_PROVIDER = os.getenv("LLM_PROVIDER")

# OpenAI configuration
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY_1")
    or os.getenv("OPENAI_API_KEY_2")
    or os.getenv("OPENAI_API_KEY_3")
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# Azure configuration
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
AZURE_SUBSCRIPTION_KEY = os.getenv("AZURE_SUBSCRIPTION_KEY")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION")

# Prompt Configuration
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", 5))

# AI Assistant Configuration
AI_ASSISTANT_NAME = os.getenv("ASSISTANT_NAME")
ADMIN_NUMBERS = [num.strip() for num in os.getenv("ADMIN_NUMBERS", "").split(",") if num.strip()]
SYNC_WHATSAPP_HISTORY = os.getenv("SYNC_WHATSAPP_HISTORY", "true").strip().lower() == "true"
WHATSAPP_HISTORY_LOOKBACK_HOURS = int(os.getenv("WHATSAPP_HISTORY_LOOKBACK_HOURS", "6"))
