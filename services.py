import os
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pdfplumber
from docx import Document

import bot_state
from config import ADMIN_NUMBERS
from database import (
    DEFAULT_LEAD_STAGE,
    add_lead_note,
    add_lead_task,
    delete_lead_tag,
    delete_messages,
    get_contact_name,
    get_lead_meta,
    get_messages,
    get_recent_messages_formatted,
    list_lead_notes,
    list_lead_tasks,
    list_lead_tags,
    save_message,
    set_lead_stage,
    set_lead_task_status,
    set_manual_lead_name,
    upsert_lead_tag,
)
from llm import (
    analyze_quote_request,
    call_watchdog_llm,
    generate_final_response,
    generate_first_time_greeting,
)


PARKSIDE_PROFILE = {
    "name": "Technical Services Company",
    "positioning": "General maintenance services in Dubai for homes, villas, offices, and buildings.",
    "services": [
        "AC maintenance and repair",
        "Plumbing",
        "Electrical",
        "Handyman",
        "Painting",
        "Carpentry",
        "Home and office cleaning",
        "Annual maintenance packages",
    ],
    "contact_phone": "+971 50 000 0000",
    "contact_email": "service@company.com",
    "hours": "8:00 AM - 6:00 PM",
    "website": "company-website.com",
    "location": "Dubai, United Arab Emirates",
}

LEAD_STAGES = [
    ("new", "New"),
    ("qualified", "Qualified"),
    ("quoted", "Quoted"),
    ("follow_up", "Follow Up"),
    ("won", "Won"),
    ("closed", "Closed"),
]

SMART_TAG_RULES = {
    "urgent": ["urgent", "asap", "immediately", "today", "emergency"],
    "quote_ready": ["quote", "quotation", "estimate", "price", "pricing"],
    "location_missing": [],
    "budget_discussed": [],
    "not_interested": ["not interested", "no need", "no service", "maintenance ni jrur nathi"],
}

TASK_PRESETS = [
    "Call back customer",
    "Send quote",
    "Arrange site visit",
    "Waiting for customer details",
    "Confirm booking slot",
]

TIMEZONE_OPTIONS = [
    "Asia/Dubai",
    "Asia/Kolkata",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Australia/Sydney",
    "UTC",
]


def ensure_runtime_directories() -> None:
    os.makedirs("db", exist_ok=True)
    os.makedirs("messages", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("converted", exist_ok=True)


def convert_pdf_to_markdown(pdf_path: str) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            markdown_lines = []
            for page_num, page in enumerate(pdf.pages, start=1):
                markdown_lines.append(f"## Page {page_num}\n")
                text = page.extract_text()
                if text:
                    markdown_lines.append(text.strip() + "\n")
                else:
                    markdown_lines.append("*(No text could be extracted from this page)*\n")
            return "\n".join(markdown_lines)
    except Exception as exc:
        return f"Error reading PDF: {exc}"


def convert_docx_to_markdown(docx_path: str) -> str:
    try:
        document = Document(docx_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:
        return f"Error reading DOCX: {exc}"


def list_knowledge_files() -> list[dict[str, Any]]:
    ensure_runtime_directories()
    files = []
    for file_name in sorted(os.listdir("downloads")):
        download_path = os.path.join("downloads", file_name)
        base_name, _ = os.path.splitext(file_name)
        converted_path = os.path.join("converted", f"{base_name}.txt")
        files.append(
            {
                "name": file_name,
                "download_path": download_path,
                "converted_path": converted_path,
                "converted_exists": os.path.exists(converted_path),
                "size": os.path.getsize(download_path),
            }
        )
    return files


def import_knowledge_file(source_path: str, original_name: str) -> dict[str, str]:
    ensure_runtime_directories()
    target_path = os.path.join("downloads", original_name)
    with open(source_path, "rb") as src, open(target_path, "wb") as dst:
        dst.write(src.read())

    extension = os.path.splitext(original_name)[1].lower()
    if extension == ".pdf":
        content = convert_pdf_to_markdown(target_path)
    elif extension == ".docx":
        content = convert_docx_to_markdown(target_path)
    elif extension in {".txt", ".md"}:
        with open(target_path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    else:
        os.remove(target_path)
        raise ValueError(f"Unsupported file type: {extension}")

    converted_name = f"{os.path.splitext(original_name)[0]}.txt"
    converted_path = os.path.join("converted", converted_name)
    with open(converted_path, "w", encoding="utf-8") as handle:
        handle.write(content)

    return {"download_path": target_path, "converted_path": converted_path}


def remove_knowledge_file(file_name: str) -> None:
    download_path = os.path.join("downloads", file_name)
    converted_path = os.path.join("converted", f"{os.path.splitext(file_name)[0]}.txt")
    if os.path.exists(download_path):
        os.remove(download_path)
    if os.path.exists(converted_path):
        os.remove(converted_path)


def get_dashboard_snapshot() -> dict[str, Any]:
    ensure_runtime_directories()
    total_messages = 0
    if os.path.exists("db/conversations.sqlite3"):
        import sqlite3

        conn = sqlite3.connect("db/conversations.sqlite3")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM messages")
        total_messages, unique_user_count = cursor.fetchone()
        conn.close()
    else:
        unique_user_count = 0

    stage_counts = {stage_key: 0 for stage_key, _ in LEAD_STAGES}
    conversations = list_conversations()
    hot_leads = 0
    quote_ready_leads = 0
    open_tasks = 0
    for conversation in conversations:
        stage_key = conversation.get("stage", DEFAULT_LEAD_STAGE)
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        if conversation.get("score_band") == "Hot":
            hot_leads += 1
        if conversation.get("quote_ready"):
            quote_ready_leads += 1
        open_tasks += conversation.get("open_task_count", 0)

    return {
        "bot_name": bot_state.bot_name,
        "is_bot_running": bot_state.is_bot_running,
        "reply_mode": bot_state.reply_mode,
        "admin_numbers": ADMIN_NUMBERS,
        "knowledge_file_count": len(list_knowledge_files()),
        "total_messages": total_messages,
        "unique_user_count": unique_user_count,
        "stage_counts": stage_counts,
        "lead_stage_options": [{"value": value, "label": label} for value, label in LEAD_STAGES],
        "timezone": bot_state.timezone,
        "timezone_options": TIMEZONE_OPTIONS,
        "business_hours": bot_state.business_hours,
        "availability": get_availability_summary(),
        "hot_leads": hot_leads,
        "quote_ready_leads": quote_ready_leads,
        "open_tasks": open_tasks,
        "task_presets": TASK_PRESETS,
    }


def get_business_profile() -> dict[str, Any]:
    return PARKSIDE_PROFILE


def _parse_hour_minute(value: str) -> tuple[int, int]:
    hour, minute = (value or "00:00").split(":")
    return int(hour), int(minute)


def is_open_now() -> tuple[bool, str]:
    timezone_name = getattr(bot_state, "timezone", "Asia/Dubai")
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.utcnow()
        timezone_name = "UTC"

    day_name = now.strftime("%A").lower()
    day_config = bot_state.business_hours.get(day_name, {"enabled": False})
    if not day_config.get("enabled"):
        return False, f"Closed today. Business timezone: {timezone_name}."

    start_hour, start_minute = _parse_hour_minute(day_config.get("start", "08:00"))
    end_hour, end_minute = _parse_hour_minute(day_config.get("end", "18:00"))
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute

    if start_minutes <= current_minutes <= end_minutes:
        return True, f"Open now until {day_config.get('end', '18:00')} ({timezone_name})."
    return False, (
        f"We are currently closed. Business hours today are "
        f"{day_config.get('start', '08:00')} - {day_config.get('end', '18:00')} ({timezone_name})."
    )


def get_availability_summary() -> dict[str, Any]:
    is_open, status_text = is_open_now()
    return {
        "is_open": is_open,
        "status_text": status_text,
        "timezone": bot_state.timezone,
        "business_hours": bot_state.business_hours,
    }


def update_availability_settings(timezone_name: str, business_hours: dict[str, Any]) -> dict[str, Any]:
    if timezone_name not in TIMEZONE_OPTIONS:
        raise ValueError("Unsupported timezone")

    normalized = {}
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        value = business_hours.get(day, {})
        normalized[day] = {
            "enabled": bool(value.get("enabled")),
            "start": str(value.get("start", "08:00")),
            "end": str(value.get("end", "18:00")),
        }

    bot_state.timezone = timezone_name
    bot_state.business_hours = normalized
    return get_availability_summary()


def get_closed_message() -> str:
    summary = get_availability_summary()
    return (
        f"Thank you for your message. {summary['status_text']} "
        f"Please share your request, location, and preferred timing, and the team will respond in working hours."
    )


def get_stage_label(stage_value: str | None) -> str:
    stage_map = dict(LEAD_STAGES)
    return stage_map.get(stage_value or DEFAULT_LEAD_STAGE, "New")


def format_lead_label(
    user_id: str,
    manual_name: str | None = None,
    contact_name: str | None = None,
    intake_name: str | None = None,
) -> str:
    if manual_name and manual_name.strip():
        return manual_name.strip()
    if contact_name and contact_name.strip():
        return contact_name.strip()
    if intake_name and intake_name.strip():
        return intake_name.strip()
    if user_id.startswith("+"):
        return user_id
    if user_id.isdigit():
        return f"+{user_id}"
    return user_id


def set_bot_running(is_running: bool) -> None:
    bot_state.is_bot_running = is_running


def set_reply_mode(mode: str) -> None:
    if mode not in {"automatic", "manual"}:
        raise ValueError("Unsupported reply mode")
    bot_state.reply_mode = mode


def rename_bot(name: str) -> None:
    bot_state.bot_name = name.strip() or bot_state.bot_name


def update_public_prompt(prompt_name: str, content: str) -> None:
    if prompt_name not in bot_state.public_prompts:
        raise KeyError(prompt_name)
    bot_state.public_prompts[prompt_name] = content


def reset_user_conversation(user_id: str) -> None:
    delete_messages(user_id)


def derive_smart_tags(user_id: str, intake: dict[str, Any] | None, messages: list[tuple[str, int, bool]]) -> list[str]:
    combined_text = " ".join(message_content.lower() for message_content, _, _ in messages if message_content)
    tags = set()

    for tag, keywords in SMART_TAG_RULES.items():
        if keywords and any(keyword in combined_text for keyword in keywords):
            tags.add(tag)

    if intake:
        if intake.get("quote_readiness") and "ready" in str(intake["quote_readiness"]).lower():
            tags.add("quote_ready")
        if intake.get("budget_signal"):
            tags.add("budget_discussed")
        missing_details = [str(item).lower() for item in intake.get("missing_details", [])]
        if any("location" in item for item in missing_details):
            tags.add("location_missing")
        if intake.get("urgency") and "urgent" in str(intake["urgency"]).lower():
            tags.add("urgent")

    stored_tags = list_lead_tags(user_id)
    for tag in tags:
        upsert_lead_tag(user_id, tag, "smart", int(time.time()))

    stored_smart_tags = {item["tag"] for item in stored_tags if item.get("source") == "smart"}
    for tag in stored_smart_tags - tags:
        delete_lead_tag(user_id, tag)

    final_tags = list_lead_tags(user_id)
    return [item["tag"] for item in final_tags]


def calculate_lead_score(intake: dict[str, Any] | None, tags: list[str], messages: list[tuple[str, int, bool]]) -> dict[str, Any]:
    score = 20
    reasons = []
    if intake:
        readiness = str(intake.get("quote_readiness", "")).lower()
        if "qualified" in readiness:
            score += 25
            reasons.append("Qualified inquiry")
        missing_count = len(intake.get("missing_details", []))
        if missing_count == 0:
            score += 15
            reasons.append("No missing details")
        elif missing_count >= 3:
            score -= 10
            reasons.append("Several details still missing")
        if intake.get("urgency") and "urgent" in str(intake["urgency"]).lower():
            score += 15
            reasons.append("Urgent request")
        if intake.get("budget_signal"):
            score += 8
            reasons.append("Budget intent detected")
        if intake.get("preferred_visit_time"):
            score += 8
            reasons.append("Timing shared")
        if intake.get("location"):
            score += 8
            reasons.append("Location shared")

    if "quote_ready" in tags:
        score += 10
    if "urgent" in tags:
        score += 6
    if "not_interested" in tags:
        score -= 35
        reasons.append("Low buying intent")

    customer_messages = [m for m in messages if not m[2]]
    if len(customer_messages) >= 3:
        score += 8
        reasons.append("Engaged conversation")

    score = max(0, min(100, score))
    if score >= 75:
        band = "Hot"
    elif score >= 45:
        band = "Warm"
    else:
        band = "Cold"
    return {"score": score, "band": band, "reasons": reasons[:3]}


def derive_follow_up_recommendation(intake: dict[str, Any] | None, score_band: str) -> dict[str, Any]:
    if not intake:
        return {
            "readiness_label": "Waiting for intake",
            "next_task": "Review latest conversation",
            "due_label": "Today",
        }
    missing = intake.get("missing_details", [])
    if "Qualified" in str(intake.get("quote_readiness", "")):
        if score_band == "Hot":
            return {"readiness_label": "Quote ready", "next_task": "Send quote", "due_label": "Within 1 hour"}
        return {"readiness_label": "Quote ready", "next_task": "Arrange site visit", "due_label": "Today"}
    if missing:
        return {"readiness_label": "Needs more details", "next_task": f"Ask for {missing[0]}", "due_label": "Next reply"}
    return {"readiness_label": "Review needed", "next_task": "Check lead and follow up", "due_label": "Today"}


def get_lead_workspace(user_id: str) -> dict[str, Any]:
    if not user_id:
        return {
            "meta": {"manual_name": None, "stage": DEFAULT_LEAD_STAGE, "updated_at": None},
            "notes": [],
            "tags": [],
            "tasks": [],
            "score": {"score": 0, "band": "Cold", "reasons": []},
            "readiness": {"readiness_label": "Waiting for intake", "next_task": "Review lead", "due_label": "Today"},
        }
    messages = get_messages(user_id)
    intake = None
    try:
        intake = get_quote_intake(user_id)
    except Exception:
        intake = None
    tags = derive_smart_tags(user_id, intake, messages)
    score = calculate_lead_score(intake, tags, messages)
    recommendation = derive_follow_up_recommendation(intake, score["band"])
    tasks = list_lead_tasks(user_id)
    return {
        "meta": get_lead_meta(user_id),
        "notes": list_lead_notes(user_id),
        "tags": tags,
        "tasks": tasks,
        "score": score,
        "readiness": recommendation,
    }


def update_lead_stage(user_id: str, stage: str) -> dict[str, Any]:
    stage_values = {value for value, _ in LEAD_STAGES}
    if stage not in stage_values:
        raise ValueError("Unsupported stage")
    set_lead_stage(user_id, stage, int(time.time()))
    return get_lead_workspace(user_id)


def update_lead_name(user_id: str, name: str) -> dict[str, Any]:
    set_manual_lead_name(user_id, name, int(time.time()))
    return get_lead_workspace(user_id)


def create_lead_note(user_id: str, note: str) -> list[dict[str, Any]]:
    add_lead_note(user_id, note, int(time.time()))
    return list_lead_notes(user_id)


def toggle_manual_tag(user_id: str, tag: str, enabled: bool) -> list[str]:
    cleaned_tag = (tag or "").strip().lower().replace(" ", "_")
    if not cleaned_tag:
        raise ValueError("Tag is required")
    if enabled:
        upsert_lead_tag(user_id, cleaned_tag, "manual", int(time.time()))
    else:
        delete_lead_tag(user_id, cleaned_tag)
    return [item["tag"] for item in list_lead_tags(user_id)]


def create_lead_task(user_id: str, title: str, due_label: str | None = None) -> list[dict[str, Any]]:
    add_lead_task(user_id, title, due_label, int(time.time()))
    return list_lead_tasks(user_id)


def update_task_status(task_id: int, status: str, user_id: str) -> list[dict[str, Any]]:
    if status not in {"open", "done"}:
        raise ValueError("Unsupported task status")
    set_lead_task_status(task_id, status, int(time.time()))
    return list_lead_tasks(user_id)


def list_conversations() -> list[dict[str, Any]]:
    if not os.path.exists("db/conversations.sqlite3"):
        return []

    import sqlite3

    conn = sqlite3.connect("db/conversations.sqlite3")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, MAX(timestamp) AS latest_timestamp, COUNT(*) AS message_count
        FROM messages
        GROUP BY user_id
        ORDER BY latest_timestamp DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    conversations = []
    for user_id, latest_timestamp, message_count in rows:
        intake_name = None
        intake = None
        try:
            intake = get_quote_intake(user_id)
            intake_name = intake.get("customer_name")
        except Exception:
            intake_name = None
        contact_name = get_contact_name(user_id)
        meta = get_lead_meta(user_id)
        tags = derive_smart_tags(user_id, intake, get_messages(user_id))
        notes = list_lead_notes(user_id)
        tasks = list_lead_tasks(user_id)
        score = calculate_lead_score(intake, tags, get_messages(user_id))
        readiness = derive_follow_up_recommendation(intake, score["band"])
        conversations.append(
            {
                "user_id": user_id,
                "display_name": format_lead_label(user_id, meta.get("manual_name"), contact_name, intake_name),
                "latest_timestamp": latest_timestamp,
                "message_count": message_count,
                "stage": meta.get("stage") or DEFAULT_LEAD_STAGE,
                "stage_label": get_stage_label(meta.get("stage")),
                "tags": tags,
                "notes_count": len(notes),
                "last_note_preview": notes[0]["note"] if notes else "",
                "lead_score": score["score"],
                "score_band": score["band"],
                "score_reasons": score["reasons"],
                "quote_ready": readiness["readiness_label"] == "Quote ready",
                "readiness_label": readiness["readiness_label"],
                "next_task": readiness["next_task"],
                "next_due_label": readiness["due_label"],
                "open_task_count": len([task for task in tasks if task["status"] == "open"]),
            }
        )
    return conversations


def get_conversation_messages(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "message_content": message_content,
            "timestamp": timestamp,
            "from_me": bool(from_me),
        }
        for message_content, timestamp, from_me in get_messages(user_id)
    ]


def get_quote_intake(user_id: str) -> dict[str, Any]:
    messages = get_messages(user_id)
    conversation_text = "\n".join(
        [
            f"{'Assistant' if from_me else 'Customer'}: {message_content}"
            for message_content, _, from_me in messages
        ]
    )
    intake = analyze_quote_request(conversation_text)
    return intake.model_dump()


def generate_ai_reply_for_lead(user_id: str) -> dict[str, Any]:
    user_id = user_id.strip()
    if not user_id:
        raise ValueError("Lead ID is required")

    messages = get_messages(user_id)
    if not messages:
        raise ValueError("No conversation found for this lead")

    last_customer_message = next((text for text, _, from_me in reversed(messages) if not from_me), "")
    if not last_customer_message:
        raise ValueError("No customer message available to answer")

    open_now, _ = is_open_now()
    if not open_now:
        response = get_closed_message()
        save_message(user_id, response, int(time.time()), True)
        return {
            "mode": "closed_hours",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    is_first_customer_message = len([message for message in messages if not message[2]]) == 1

    if is_first_customer_message:
        response = generate_first_time_greeting(
            "Customer",
            last_customer_message,
            bot_state.public_prompts["greeting"],
            bot_state.private_prompts["greeting"],
        )
        save_message(user_id, response, int(time.time()), True)
        return {
            "mode": "greeting",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    is_relevant, watchdog_response = call_watchdog_llm(
        last_customer_message,
        bot_state.private_prompts["watchdog"],
    )
    if not is_relevant:
        response = watchdog_response or "I cannot answer that request."
        return {
            "mode": "watchdog_blocked",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    response = generate_final_response(
        user_id=user_id,
        user_text=last_customer_message,
        public_prompt=bot_state.public_prompts["final_response"],
        private_prompt=bot_state.private_prompts["final_response"],
    )
    save_message(user_id, response, int(time.time()), True)
    return {
        "mode": "final_response",
        "response": response,
        "conversation": get_conversation_messages(user_id),
        "history": get_recent_messages_formatted(user_id),
        "intake": get_quote_intake(user_id),
    }


def run_customer_chat(user_id: str, user_name: str, text: str) -> dict[str, Any]:
    ensure_runtime_directories()
    user_id = user_id.strip() or "lead-001"
    user_name = user_name.strip() or "Customer"
    text = text.strip()
    if not text:
        raise ValueError("Message is required")

    timestamp = int(time.time())
    save_message(user_id, text, timestamp, False)

    open_now, _ = is_open_now()
    if not open_now:
        response = get_closed_message()
        save_message(user_id, response, int(time.time()), True)
        return {
            "mode": "closed_hours",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    previous_messages = get_messages(user_id)
    is_first_message = len(previous_messages) == 1

    if is_first_message:
        response = generate_first_time_greeting(
            user_name,
            text,
            bot_state.public_prompts["greeting"],
            bot_state.private_prompts["greeting"],
        )
        save_message(user_id, response, int(time.time()), True)
        return {
            "mode": "greeting",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    is_relevant, watchdog_response = call_watchdog_llm(
        text,
        bot_state.private_prompts["watchdog"],
    )
    if not is_relevant:
        response = watchdog_response or "I cannot answer that request."
        return {
            "mode": "watchdog_blocked",
            "response": response,
            "conversation": get_conversation_messages(user_id),
            "intake": get_quote_intake(user_id),
        }

    response = generate_final_response(
        user_id=user_id,
        user_text=text,
        public_prompt=bot_state.public_prompts["final_response"],
        private_prompt=bot_state.private_prompts["final_response"],
    )
    save_message(user_id, response, int(time.time()), True)
    return {
        "mode": "final_response",
        "response": response,
        "conversation": get_conversation_messages(user_id),
        "history": get_recent_messages_formatted(user_id),
        "intake": get_quote_intake(user_id),
    }
