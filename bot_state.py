from prompts import (
    PUBLIC_FINAL_RESPONSE_PROMPT,
    PUBLIC_GREETING_PROMPT,
    PRIVATE_FINAL_RESPONSE_PROMPT,
    PRIVATE_GREETING_PROMPT,
    PRIVATE_WATCHDOG_PROMPT,
)
from config import AI_ASSISTANT_NAME

is_bot_running = True
bot_name = AI_ASSISTANT_NAME or "Assistant"
reply_mode = "automatic"

timezone = "Asia/Dubai"
business_hours = {
    "monday": {"enabled": True, "start": "08:00", "end": "18:00"},
    "tuesday": {"enabled": True, "start": "08:00", "end": "18:00"},
    "wednesday": {"enabled": True, "start": "08:00", "end": "18:00"},
    "thursday": {"enabled": True, "start": "08:00", "end": "18:00"},
    "friday": {"enabled": True, "start": "08:00", "end": "18:00"},
    "saturday": {"enabled": True, "start": "09:00", "end": "16:00"},
    "sunday": {"enabled": False, "start": "09:00", "end": "16:00"},
}

public_prompts = {
    "greeting": PUBLIC_GREETING_PROMPT,
    "final_response": PUBLIC_FINAL_RESPONSE_PROMPT,
}

private_prompts = {
    "greeting": PRIVATE_GREETING_PROMPT,
    "final_response": PRIVATE_FINAL_RESPONSE_PROMPT,
    "watchdog": PRIVATE_WATCHDOG_PROMPT,
}
