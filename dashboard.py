import os
import tempfile
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

import bot_state
from database import init_db
from services import (
    create_lead_task,
    create_lead_note,
    ensure_runtime_directories,
    generate_ai_reply_for_lead,
    get_availability_summary,
    get_business_profile,
    get_conversation_messages,
    get_dashboard_snapshot,
    get_lead_workspace,
    get_quote_intake,
    import_knowledge_file,
    list_conversations,
    list_knowledge_files,
    remove_knowledge_file,
    rename_bot,
    reset_user_conversation,
    run_customer_chat,
    set_bot_running,
    set_reply_mode,
    toggle_manual_tag,
    update_availability_settings,
    update_lead_name,
    update_lead_stage,
    update_task_status,
    update_public_prompt,
)
from whatsapp_runtime import runtime as whatsapp_runtime


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def page_url(endpoint: str, user_id: str | None = None, **kwargs) -> str:
    if user_id:
        kwargs["user_id"] = user_id
    return url_for(endpoint, **kwargs)


def _format_timestamp(value):
    if not value:
        return "-"
    return datetime.fromtimestamp(value).strftime("%d %b %Y %I:%M %p")


app.jinja_env.filters["datetimeformat"] = _format_timestamp
app.jinja_env.globals["page_url"] = page_url


def bootstrap() -> None:
    ensure_runtime_directories()
    init_db()


def build_page_context(active_page: str) -> dict:
    bootstrap()
    conversations = list_conversations()
    active_user_id = request.args.get("user_id") or (conversations[0]["user_id"] if conversations else "")
    active_conversation = next((conversation for conversation in conversations if conversation["user_id"] == active_user_id), None)
    active_messages = get_conversation_messages(active_user_id) if active_user_id else []
    active_intake = get_quote_intake(active_user_id) if active_user_id else None
    active_lead_workspace = get_lead_workspace(active_user_id) if active_user_id else get_lead_workspace("")
    knowledge_files = list_knowledge_files()
    snapshot = get_dashboard_snapshot()
    recent_conversations = conversations[:6]
    return {
        "active_page": active_page,
        "auth_email": os.getenv("WORKSPACE_AUTH_EMAIL", "rajm267747@gmail.com"),
        "auth_password": os.getenv("WORKSPACE_AUTH_PASSWORD", "WhatsAppTest"),
        "business": get_business_profile(),
        "snapshot": snapshot,
        "whatsapp_status": whatsapp_runtime.get_status(),
        "conversations": conversations,
        "active_conversation": active_conversation,
        "recent_conversations": recent_conversations,
        "active_user_id": active_user_id,
        "active_messages": active_messages,
        "active_intake": active_intake,
        "active_lead_workspace": active_lead_workspace,
        "knowledge_files": knowledge_files,
        "public_prompts": bot_state.public_prompts,
        "private_prompts": bot_state.private_prompts,
    }


@app.get("/")
def overview():
    return render_template("workspace.html", **build_page_context("overview"))


@app.get("/inbox")
def inbox():
    return render_template("workspace.html", **build_page_context("inbox"))


@app.get("/leads")
def leads():
    return render_template("workspace.html", **build_page_context("leads"))


@app.get("/knowledge")
def knowledge():
    return render_template("workspace.html", **build_page_context("knowledge"))


@app.get("/automation")
def automation():
    return render_template("workspace.html", **build_page_context("automation"))


@app.post("/api/chat")
def api_chat():
    payload = request.get_json(force=True)
    result = run_customer_chat(
        user_id=payload.get("user_id", "lead-001"),
        user_name=payload.get("user_name", "Customer"),
        text=payload.get("message", ""),
    )
    return jsonify(result)


@app.get("/api/whatsapp/status")
def api_whatsapp_status():
    status = whatsapp_runtime.get_status()
    if status.get("qr_path"):
        status["qr_url"] = url_for(
            "static",
            filename="generated/whatsapp-qr.svg",
            v=status.get("last_event_at") or int(datetime.now().timestamp()),
        )
    return jsonify(status)


@app.post("/api/whatsapp/start")
def api_whatsapp_start():
    return jsonify(whatsapp_runtime.start())


@app.post("/api/whatsapp/stop")
def api_whatsapp_stop():
    return jsonify(whatsapp_runtime.stop())


@app.post("/api/whatsapp/reset")
def api_whatsapp_reset():
    return jsonify(whatsapp_runtime.reset_session())


@app.post("/api/intake/<user_id>")
def api_intake(user_id: str):
    return jsonify({"intake": get_quote_intake(user_id)})


@app.get("/api/conversations/<user_id>")
def api_conversation(user_id: str):
    return jsonify({"messages": get_conversation_messages(user_id)})


@app.get("/api/leads/<user_id>")
def api_lead_workspace(user_id: str):
    return jsonify({"lead": get_lead_workspace(user_id)})


@app.post("/api/leads/<user_id>/stage")
def api_lead_stage(user_id: str):
    payload = request.get_json(force=True)
    return jsonify({"ok": True, "lead": update_lead_stage(user_id, payload.get("stage", ""))})


@app.post("/api/leads/<user_id>/name")
def api_lead_name(user_id: str):
    payload = request.get_json(force=True)
    return jsonify({"ok": True, "lead": update_lead_name(user_id, payload.get("name", ""))})


@app.get("/api/leads/<user_id>/notes")
def api_lead_notes(user_id: str):
    return jsonify({"notes": get_lead_workspace(user_id).get("notes", [])})


@app.post("/api/leads/<user_id>/notes")
def api_lead_note_create(user_id: str):
    payload = request.get_json(force=True)
    return jsonify({"ok": True, "notes": create_lead_note(user_id, payload.get("note", ""))})


@app.post("/api/leads/<user_id>/tags")
def api_lead_tag_toggle(user_id: str):
    payload = request.get_json(force=True)
    return jsonify(
        {
            "ok": True,
            "tags": toggle_manual_tag(
                user_id,
                payload.get("tag", ""),
                bool(payload.get("enabled")),
            ),
        }
    )


@app.post("/api/leads/<user_id>/tasks")
def api_lead_task_create(user_id: str):
    payload = request.get_json(force=True)
    return jsonify(
        {
            "ok": True,
            "tasks": create_lead_task(
                user_id,
                payload.get("title", ""),
                payload.get("due_label", ""),
            ),
        }
    )


@app.post("/api/leads/<user_id>/tasks/<int:task_id>")
def api_lead_task_update(user_id: str, task_id: int):
    payload = request.get_json(force=True)
    return jsonify(
        {
            "ok": True,
            "tasks": update_task_status(task_id, payload.get("status", "open"), user_id),
        }
    )


@app.post("/api/bot-state")
def api_bot_state():
    payload = request.get_json(force=True)
    set_bot_running(bool(payload.get("is_running")))
    return jsonify({"ok": True, "is_running": bot_state.is_bot_running})


@app.post("/api/reply-mode")
def api_reply_mode():
    payload = request.get_json(force=True)
    set_reply_mode(payload.get("mode", "automatic"))
    return jsonify({"ok": True, "reply_mode": bot_state.reply_mode})


@app.post("/api/bot-name")
def api_bot_name():
    payload = request.get_json(force=True)
    rename_bot(payload.get("name", ""))
    return jsonify({"ok": True, "name": bot_state.bot_name})


@app.get("/api/availability")
def api_availability():
    return jsonify({"availability": get_availability_summary()})


@app.post("/api/availability")
def api_availability_update():
    payload = request.get_json(force=True)
    return jsonify(
        {
            "ok": True,
            "availability": update_availability_settings(
                payload.get("timezone", "Asia/Dubai"),
                payload.get("business_hours", {}),
            ),
        }
    )


@app.post("/api/prompts/<prompt_name>")
def api_prompt_update(prompt_name: str):
    payload = request.get_json(force=True)
    update_public_prompt(prompt_name, payload.get("content", ""))
    return jsonify({"ok": True})


@app.post("/api/conversations/<user_id>/reset")
def api_conversation_reset(user_id: str):
    reset_user_conversation(user_id)
    return jsonify({"ok": True})


@app.post("/api/support-reply")
def api_support_reply():
    payload = request.get_json(force=True)
    whatsapp_runtime.send_support_reply(
        user_id=payload.get("user_id", ""),
        text=payload.get("message", ""),
    )
    return jsonify({"ok": True})


@app.post("/api/ai-reply")
def api_ai_reply():
    payload = request.get_json(force=True)
    user_id = payload.get("user_id", "").strip()
    result = generate_ai_reply_for_lead(user_id)
    whatsapp_runtime.send_support_reply(
        user_id=user_id,
        text=result.get("response", ""),
        save_to_db=False,
    )
    return jsonify(result)


@app.post("/files/upload")
def upload_file():
    bootstrap()
    uploaded_file = request.files.get("knowledge_file")
    if not uploaded_file or not uploaded_file.filename:
        return redirect(url_for("knowledge"))

    with tempfile.NamedTemporaryFile(delete=False) as handle:
        uploaded_file.save(handle.name)
        temp_path = handle.name

    try:
        import_knowledge_file(temp_path, uploaded_file.filename)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return redirect(url_for("knowledge"))


@app.post("/files/delete/<path:file_name>")
def delete_file(file_name: str):
    remove_knowledge_file(file_name)
    return redirect(url_for("knowledge"))


if __name__ == "__main__":
    bootstrap()
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
