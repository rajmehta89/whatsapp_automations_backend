import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import bot_state
from config import (
    LLM_PROVIDER,
    AI_ASSISTANT_NAME,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    AZURE_SUBSCRIPTION_KEY,
    AZURE_ENDPOINT,
    AZURE_DEPLOYMENT_NAME,
    AZURE_API_VERSION
)
from database import get_recent_messages_formatted
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel
from neonize.utils import log


def _is_azure_configured() -> bool:
    return all(
        [
            LLM_PROVIDER == "azure",
            AZURE_ENDPOINT,
            AZURE_DEPLOYMENT_NAME,
            AZURE_SUBSCRIPTION_KEY,
            AZURE_API_VERSION,
        ]
    )


def _is_openai_configured() -> bool:
    return bool(LLM_PROVIDER == "openai" and OPENAI_API_KEY)


def _generate_demo_response(user_prompt: str, system_prompt: str) -> str:
    assistant_name = AI_ASSISTANT_NAME or "Assistant"
    trimmed_prompt = user_prompt.strip() or "your message"
    short_system = " ".join(system_prompt.split())[:180]
    return (
        f"[Demo Mode] {assistant_name} received: \"{trimmed_prompt}\".\n\n"
        f"This is a local preview response so the UI and conversation flow can be shown "
        f"without live Azure credentials.\n\n"
        f"Active prompt context: {short_system}"
    )


def _watchdog_demo_response(user_message: str) -> tuple[bool, Optional[str]]:
    blocked_terms = ["porn", "kill", "bomb", "hack", "exploit", "weapon"]
    lowered = user_message.lower()
    if any(term in lowered for term in blocked_terms):
        return False, "I cannot answer that request."
    return True, None


def _get_availability_context() -> str:
    timezone_name = getattr(bot_state, "timezone", "Asia/Dubai")
    hours = getattr(bot_state, "business_hours", {})
    try:
        now = datetime.now(ZoneInfo(timezone_name))
        now_label = now.strftime("%A, %I:%M %p")
    except Exception:
        now_label = "Unavailable"

    lines = [f"Timezone: {timezone_name}", f"Current local time: {now_label}"]
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        day_config = hours.get(day, {})
        if day_config.get("enabled"):
            lines.append(f"{day.title()}: {day_config.get('start', '08:00')} - {day_config.get('end', '18:00')}")
        else:
            lines.append(f"{day.title()}: Closed")
    return "\n".join(lines)

def get_client_and_model():
    """
    Returns an LLM client configured for the chosen provider.
    This example uses the OpenAI Python SDK interface for all providers.
    """
    if _is_openai_configured():
        return OpenAI(api_key=OPENAI_API_KEY), OPENAI_MODEL
    if _is_azure_configured():
        return AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_SUBSCRIPTION_KEY,
            api_version=AZURE_API_VERSION
        ), AZURE_DEPLOYMENT_NAME
    return None, None

def call_llm_api(system_prompt, user_prompt):
    """
    Unified function to call the LLM API using the OpenAI Python SDK.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        # Call the chat completions endpoint using the client
        client, model = get_client_and_model()
        if not client or not model:
            return _generate_demo_response(user_prompt, system_prompt)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=500,
        )
        # Correctly access the response content
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return ""

class WatchdogResponse(BaseModel):
    relevant: bool
    response: str = None


class IntakeAnalysis(BaseModel):
    customer_name: str | None = None
    service_category: str | None = None
    issue_summary: str | None = None
    property_type: str | None = None
    location: str | None = None
    urgency: str | None = None
    preferred_visit_time: str | None = None
    budget_signal: str | None = None
    quote_readiness: str
    missing_details: list[str]
    next_action: str


def _heuristic_intake_analysis(conversation_text: str) -> IntakeAnalysis:
    lowered = conversation_text.lower()
    categories = {
        "Pricing Request": ["price", "pricing", "quote", "cost", "rate", "package"],
        "Sales Inquiry": ["buy", "purchase", "plan", "demo", "proposal", "subscription"],
        "Support Request": ["issue", "problem", "help", "support", "error", "not working"],
        "Appointment Request": ["book", "schedule", "meeting", "visit", "appointment", "slot"],
        "Complaint": ["complaint", "angry", "bad service", "refund", "delay"],
        "Service Request": [
            "service", "repair", "install", "maintenance", "ac", "plumb", "electric",
            "clean", "paint", "carpentry", "fix"
        ],
    }
    service_category = "General Inquiry"
    for service, keywords in categories.items():
        if any(keyword in lowered for keyword in keywords):
            service_category = service
            break

    location = None
    for area in [
        "dubai marina", "jvc", "business bay", "downtown", "arabian ranches", "jlt",
        "deira", "abu dhabi", "dubai south", "remote", "online", "london", "new york"
    ]:
        if area in lowered:
            location = area.title()
            break

    urgency = "Normal"
    if any(term in lowered for term in ["urgent", "asap", "today", "immediately", "emergency"]):
        urgency = "Urgent"
    elif any(term in lowered for term in ["tomorrow", "this weekend", "next week"]):
        urgency = "Scheduled"

    property_type = None
    for label, terms in {
        "Residential": ["apartment", "flat", "studio", "villa", "townhouse", "home"],
        "Business": ["office", "shop", "workspace", "store", "company", "warehouse"],
        "Remote / Online": ["remote", "online", "virtual"],
    }.items():
        if any(term in lowered for term in terms):
            property_type = label
            break

    preferred_visit_time = None
    if "morning" in lowered:
        preferred_visit_time = "Morning"
    elif "afternoon" in lowered:
        preferred_visit_time = "Afternoon"
    elif "evening" in lowered:
        preferred_visit_time = "Evening"
    elif "today" in lowered:
        preferred_visit_time = "Today"
    elif "tomorrow" in lowered:
        preferred_visit_time = "Tomorrow"

    budget_signal = None
    if any(term in lowered for term in ["cheap", "lowest", "best price", "budget", "quote", "discount"]):
        budget_signal = "Price-sensitive"
    elif any(term in lowered for term in ["premium", "priority", "enterprise", "fastest"]):
        budget_signal = "Quality / speed priority"

    missing_details = []
    if not location:
        missing_details.append("Location")
    if not property_type:
        missing_details.append("Business or customer context")
    if not preferred_visit_time:
        missing_details.append("Preferred timing")

    readiness = "Qualified" if len(missing_details) <= 1 else "Needs more details"
    next_action = (
        "Move this lead to the next business step and prepare a tailored response."
        if readiness == "Qualified"
        else "Ask focused follow-up questions for the missing context before handoff."
    )

    issue_summary = conversation_text.strip().splitlines()[-1][:180] if conversation_text.strip() else None
    return IntakeAnalysis(
        customer_name=None,
        service_category=service_category,
        issue_summary=issue_summary,
        property_type=property_type,
        location=location,
        urgency=urgency,
        preferred_visit_time=preferred_visit_time,
        budget_signal=budget_signal,
        quote_readiness=readiness,
        missing_details=missing_details,
        next_action=next_action,
    )

def call_watchdog_llm(user_message, watchdog_prompt):
    """
    Calls the watchdog LLM and returns True if the message is relevant, otherwise False.
    Uses a Pydantic model and the response_format parameter to ensure JSON format.
    """
    print("Calling watchdog LLM with user message:", user_message)
    additional_content = ""
    for file in os.listdir("converted"):
        with open(os.path.join("converted", file), "r", encoding="utf-8", errors="replace") as f:
            additional_content += f.read()
    system_prompt = watchdog_prompt.format(
        user_message=user_message,
        additional_content=additional_content or "Ei lisätietoa tiedostoista."
    )
    try:
        client, model = get_client_and_model()
        if not client or not model:
            return _watchdog_demo_response(user_message)
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=200,
            response_format=WatchdogResponse
        )
        result = response.choices[0].message.parsed.relevant, response.choices[0].message.parsed.response
        return result
    except Exception as e:
        print(f"Error calling watchdog LLM: {e}")
        log.exception(e)
        return False, None


def analyze_quote_request(conversation_text: str) -> IntakeAnalysis:
    system_prompt = """
You are extracting a structured business lead summary from a customer conversation.
Return a concise intake analysis that works across different businesses such as services, sales, support, appointments, and general inquiries.
Infer carefully but do not invent missing facts.

Fields:
- customer_name
- service_category: short detected inquiry type or category
- issue_summary
- property_type
- location
- urgency
- preferred_visit_time
- budget_signal
- quote_readiness: either "Qualified" or "Needs more details"
- missing_details: short list of missing details still needed
- next_action: the most useful next business step
"""
    try:
        client, model = get_client_and_model()
        if not client or not model:
            return _heuristic_intake_analysis(conversation_text)
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": conversation_text},
            ],
            max_tokens=300,
            response_format=IntakeAnalysis,
        )
        return response.choices[0].message.parsed
    except Exception as exc:
        print(f"Error analyzing intake: {exc}")
        log.exception(exc)
        return _heuristic_intake_analysis(conversation_text)

def generate_first_time_greeting(user_name, user_message, public_prompt, private_prompt):
    """
    Luo ensimmäisen tervehdyksen yhdistämällä julkinen ja yksityinen prompti.
    """
    log.info(f"Generating first time greeting for user: {user_name}")
    system_prompt = (public_prompt + "\n" + private_prompt).format(ai_assistant_name=AI_ASSISTANT_NAME)
    raw_response = call_llm_api(system_prompt, user_message)
    final_response = raw_response.replace("USER_NAME_HERE", user_name)
    return final_response

def generate_final_response(user_id, user_text, public_prompt, private_prompt):
    """
    Luo loppuvastaus yhdistämällä julkinen ja yksityinen prompti.
    """
    conversation_history = get_recent_messages_formatted(user_id)
    additional_content = ""
    for file in os.listdir("converted"):
        with open(os.path.join("converted", file), "r", encoding="utf-8", errors="replace") as f:
            additional_content += f.read()
    system_prompt = (public_prompt + "\n" + private_prompt).format(
        ai_assistant_name=AI_ASSISTANT_NAME,
        previous_messages=conversation_history,
        additional_content=additional_content or "Ei lisätietoa tiedostoista.",
        availability_context=_get_availability_context(),
    )
    return call_llm_api(system_prompt, user_text)
