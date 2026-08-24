import os
import random
import threading
import time
from collections import defaultdict, deque

from neonize.client import NewClient
from neonize.events import HistorySyncEv, MessageEv
from neonize.utils import log
from neonize.utils.enum import ChatPresence, ChatPresenceMedia, ReceiptType

import bot_state
from config import ADMIN_NUMBERS, SYNC_WHATSAPP_HISTORY, WHATSAPP_HISTORY_LOOKBACK_HOURS
from database import delete_messages, get_messages, save_contact_name, save_message
from llm import generate_final_response, generate_first_time_greeting
from services import convert_docx_to_markdown, convert_pdf_to_markdown, get_closed_message, is_open_now


def handle_greeting(client: NewClient, chat, sender_id, sender_name, text):
    """Handles first-time greeting for a new conversation."""
    min_total_delay = random.uniform(2, 5)
    start_time = time.time()

    greeting = generate_first_time_greeting(
        sender_name,
        text,
        bot_state.public_prompts["greeting"],
        bot_state.private_prompts["greeting"],
    )

    elapsed = time.time() - start_time
    remaining = min_total_delay - elapsed
    if remaining > 0:
        time.sleep(remaining)

    client.send_message(chat, greeting)
    client.send_chat_presence(
        jid=chat,
        state=ChatPresence.CHAT_PRESENCE_PAUSED,
        media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
    )
    log.info(f"Sent greeting to {sender_name} ({sender_id}).")
    save_message(sender_id, greeting, int(time.time()), True)


def handle_file(client: NewClient, sender_id, message):
    """Handles file attachments (downloads the file)."""
    if sender_id not in ADMIN_NUMBERS:
        log.info(f"Files from {sender_id} are not allowed.")
        return False

    file_name = (
        message.Message.documentMessage.fileName
        or message.Message.imageMessage.fileName
        or "file"
    )
    client.send_message(
        message.Info.MessageSource.Chat,
        f"[SYSTEM] Lataan nyt tiedoston {file_name}...",
    )
    client.download_any(message=message.Message, path=f"./downloads/{file_name}")
    log.info(f"Downloaded file: {file_name}")

    file_extension = os.path.splitext(file_name)[1].lower()
    if file_extension == ".pdf":
        submission_markdown = convert_pdf_to_markdown(f"./downloads/{file_name}")
    elif file_extension == ".docx":
        submission_markdown = convert_docx_to_markdown(f"./downloads/{file_name}")
    elif file_extension == ".txt":
        with open(f"./downloads/{file_name}", "r", encoding="utf-8") as handle:
            submission_markdown = handle.read()
    else:
        client.send_message(
            message.Info.MessageSource.Chat,
            f"[SYSTEM] Tiedoston '{file_name}' tiedostotyyppi '{file_extension}' ei ole tuettu.",
        )
        return True

    base_filename = os.path.splitext(os.path.basename(file_name))[0]
    txt_filepath = os.path.join("converted", f"{base_filename}.txt")
    try:
        with open(txt_filepath, "w", encoding="utf-8") as handle:
            handle.write(submission_markdown)
        client.send_message(
            message.Info.MessageSource.Chat,
            "[SYSTEM] Tiedosto tallennettiin onnistuneesti ja kaytetaan jatkossa vastausten tuottamisessa.",
        )
    except Exception as exc:
        client.send_message(
            message.Info.MessageSource.Chat,
            f"[SYSTEM] Tapahtui virhe tiedostoa tallentaessa: {exc}",
        )

    return True


def handle_commands(client: NewClient, chat, sender_id, text: str) -> bool:
    """
    Checks for special commands. If one of the commands is detected and the sender's number
    matches a specific number, it sends back pre-formatted info and returns True.
    """
    if not text.startswith("!") or not text.strip():
        return False

    if sender_id not in ADMIN_NUMBERS:
        log.info(f"Command {text} from {sender_id} not allowed.")
        return False

    log.info(f"Command {text} from {sender_id} is allowed.")

    delay = random.uniform(2, 5)
    time.sleep(delay)
    if text.startswith("!files"):
        downloads_folder = "./downloads"
        files = sorted(os.listdir(downloads_folder))
        if not files:
            client.send_message(chat, "[KOMENTO] Ei tiedostoja.")
        else:
            files_list = "\n".join([f"{i + 1}. {file}" for i, file in enumerate(files)])
            client.send_message(
                chat,
                f"[KOMENTO] Kansiosta loytyvat tiedostot:\n{files_list}",
            )
        log.info(f"Processed !files command for {sender_id}.")
        return True
    if text.startswith("!removefile"):
        parts = text.split(" ", 1)
        if len(parts) < 2:
            client.send_message(
                chat,
                "[KOMENTO] Anna poistettavan tiedoston ID-numero tai nimi.",
            )
            return True
        file_identifier = parts[1].strip()
        downloads_folder = "./downloads"
        files = sorted(os.listdir(downloads_folder))

        filename = None
        if file_identifier.isdigit():
            file_index = int(file_identifier) - 1
            if 0 <= file_index < len(files):
                filename = files[file_index]
            else:
                client.send_message(chat, f"[KOMENTO] Virheellinen ID-numero: {file_identifier}")
                return True
        elif file_identifier in files:
            filename = file_identifier
        else:
            client.send_message(chat, f"[KOMENTO] Tiedostoa ei loytynyt: {file_identifier}")
            return True

        dl_path = os.path.join(downloads_folder, filename)
        conv_path = os.path.join("./converted", f"{os.path.splitext(filename)[0]}.txt")

        os.remove(dl_path)
        if os.path.exists(conv_path):
            os.remove(conv_path)
        client.send_message(chat, f"[KOMENTO] Tiedosto poistettu: {filename}")
        log.info(f"Processed !removefile command for {sender_id} and file {filename}.")
        return True
    if text.startswith("!commands") or text.startswith("!komennot"):
        commands = [
            "!commands - Nayta kaytettavissa olevat komennot",
            "!files - Listaa tiedostot downloads-kansiosta",
            "!removefile <ID tai tiedostonimi> - Poista tiedosto downloads-kansiosta",
            "!prompts - Nayta kaytettavissa olevat promptit",
            "!editprompt <promptin_nimi> <uusi_prompti> - Muokkaa promptia",
            "!renamebot <uusi_botin_nimi> - Vaihda botin nimi",
            "!reset - Tyhjenna keskusteluhistoria numerollesi",
            "!pause - Pysayta botti",
            "!resume - Jatka botin toimintaa",
            "!permanentstop - Sammuta botti pysyvasti",
        ]
        client.send_message(chat, "[KOMENTO] Kaytettavissa olevat komennot:\n" + "\n".join(commands))
        log.info(f"Processed !commands command for {sender_id}.")
        return True
    if text.startswith("!prompts"):
        prompts = [
            f"greeting: {bot_state.public_prompts['greeting']}",
            f"final_response: {bot_state.public_prompts['final_response']}",
        ]
        client.send_message(
            chat,
            "[KOMENTO] Julkiset promptit (muokattavissa):\n\n" + "\n".join(prompts),
        )
        log.info(f"Processed !prompts command for {sender_id}.")
        return True
    if text.startswith("!editprompt"):
        parts = text.split(" ", 2)
        if len(parts) < 3:
            client.send_message(chat, "[KOMENTO] Anna muokattava promptin nimi ja uusi sisältö.")
            return True
        prompt_name = parts[1]
        new_prompt_content = parts[2]
        if prompt_name not in bot_state.public_prompts:
            client.send_message(chat, f"[KOMENTO] Tuntematon promptin nimi: {prompt_name}")
            return True
        bot_state.public_prompts[prompt_name] = new_prompt_content
        client.send_message(chat, f"[KOMENTO] Julkinen prompti {prompt_name} paivitetty.")
        log.info(f"Processed !editprompt command for {sender_id} and prompt {prompt_name}.")
        return True
    if text.startswith("!renamebot"):
        parts = text.split(" ", 1)
        if len(parts) < 2:
            client.send_message(chat, "[KOMENTO] Anna uusi botin nimi.")
            return True
        new_bot_name = parts[1]
        bot_state.bot_name = new_bot_name
        client.send_message(chat, f"[KOMENTO] Botin nimi paivitetty: {new_bot_name}.")
        log.info(f"Processed !renamebot command for {sender_id}.")
        return True
    if text.startswith("!reset"):
        client.send_message(chat, "[KOMENTO] Keskusteluhistoria tyhjennetty!")
        delete_messages(sender_id)
        log.info(f"Cleared conversation history for {sender_id} due to '!reset' command.")
        return True
    if text.startswith("!pause"):
        client.send_message(chat, "[KOMENTO] Botti on nyt pysaytetty!")
        bot_state.is_bot_running = False
        log.info(f"Processed !pause command for {sender_id}.")
        return True
    if text.startswith("!resume"):
        client.send_message(chat, "[KOMENTO] Botti on nyt jatkanut toimintaansa!")
        bot_state.is_bot_running = True
        log.info(f"Processed !resume command for {sender_id}.")
        return True
    if text.startswith("!permanentstop"):
        client.send_message(chat, "[KOMENTO] Botti sammuu nyt pysyvasti!")
        log.info(f"Processed !permanentstop command for {sender_id}.")
        os._exit(0)
    if text.startswith("!"):
        client.send_message(
            chat,
            "[KOMENTO] Tuntematon komento. Kayta !commands nahdaksesi kaytettavissa olevat komennot.",
        )
        log.info(f"Processed unknown command for {sender_id}.")
        return True

    return False


def handle_final_response(client: NewClient, chat, sender_id, text):
    """Generates and sends the final response using the LLM, with watchdog check."""
    from llm import call_watchdog_llm

    min_total_delay = random.uniform(2, 5)
    start_time = time.time()

    is_relevant, response = call_watchdog_llm(text, bot_state.private_prompts["watchdog"])
    if not is_relevant:
        elapsed = time.time() - start_time
        remaining = min_total_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

        client.send_message(chat, response)
        log.info(f"Watchdog prevented response for {sender_id}. Message not relevant.")
        return

    final_answer = generate_final_response(
        user_id=sender_id,
        user_text=text,
        public_prompt=bot_state.public_prompts["final_response"],
        private_prompt=bot_state.private_prompts["final_response"],
    )
    log.debug(f"Final answer generated: {final_answer}")
    if not final_answer.strip():
        log.info(f"No final response generated for {sender_id}.")
        return

    elapsed = time.time() - start_time
    remaining = min_total_delay - elapsed
    if remaining > 0:
        time.sleep(remaining)

    client.send_message(chat, final_answer)
    client.send_chat_presence(
        jid=chat,
        state=ChatPresence.CHAT_PRESENCE_PAUSED,
        media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
    )
    save_message(sender_id, final_answer, int(time.time()), True)
    log.info(f"Sent final response to {sender_id}.")


def on_history_sync(client: NewClient, history: HistorySyncEv):
    """
    Processes historical messages from the sync data, storing them in the DB.
    The data structure is at `history.Data.conversations[...]`.
    """
    if not SYNC_WHATSAPP_HISTORY:
        log.info("Skipping WhatsApp history sync import because SYNC_WHATSAPP_HISTORY is disabled.")
        return

    now_ts = int(time.time())
    lookback_seconds = max(0, WHATSAPP_HISTORY_LOOKBACK_HOURS) * 60 * 60
    cutoff_ts = now_ts - lookback_seconds if lookback_seconds else now_ts

    sync_type = getattr(history.Data, "syncType", None)
    log.info(f"Received history sync event with syncType: {sync_type}")
    log.debug(f"Full history sync data: {history}")

    if not hasattr(history.Data, "conversations"):
        log.info("No conversations found in HistorySyncEv.")
        return

    for conversation in history.Data.conversations:
        user_id = conversation.ID.split("@")[0]
        log.debug(f"Processing conversation for user {user_id}")
        for message_obj in conversation.messages:
            message_data = message_obj.message
            msg = message_data.message
            from_me = getattr(message_data.key, "fromMe", False)
            log.debug(f"Processing message (from_me={from_me}): {msg}")

            if hasattr(msg, "conversation") and msg.conversation:
                message_content = msg.conversation
            elif hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage.text:
                message_content = msg.extendedTextMessage.text
            else:
                log.debug("Message is not a text message; skipping.")
                continue

            timestamp = message_obj.message.messageTimestamp
            if timestamp < cutoff_ts:
                log.debug(
                    "Skipping historical message for %s because timestamp %s is older than cutoff %s",
                    user_id,
                    timestamp,
                    cutoff_ts,
                )
                continue
            log.debug(f"Saving message with timestamp {timestamp} for user {user_id}")
            save_message(user_id, message_content, timestamp, from_me)


user_message_timestamps = defaultdict(lambda: deque(maxlen=5))
pending_response_timers = {}
processing_locks = defaultdict(threading.Lock)
pending_response_lock = threading.Lock()
lead_pause_until = {}


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _is_not_interested_message(text: str) -> bool:
    normalized = _normalize_text(text)
    negative_phrases = [
        "not interested",
        "no need",
        "dont need",
        "don't need",
        "no service needed",
        "no requirement",
        "no support needed",
        "maintenance ma interested nathi",
        "maintenance ni jrur nathi",
        "jrur nathi",
        "nai jrur",
        "nahi jarur",
        "na jarur",
        "naa nai jrur",
        "nathi joi tu",
        "seva ni jarur nathi",
    ]
    return any(phrase in normalized for phrase in negative_phrases)


def _send_not_interested_reply(client: NewClient, chat, sender_id: str):
    reply = (
        "Understood. I will not keep asking about services. "
        "If you need anything later, just message here and I will help."
    )
    client.send_message(chat, reply)
    client.send_chat_presence(
        jid=chat,
        state=ChatPresence.CHAT_PRESENCE_PAUSED,
        media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
    )
    save_message(sender_id, reply, int(time.time()), True)
    lead_pause_until[sender_id] = time.time() + (6 * 60 * 60)
    log.info(f"Marked lead {sender_id} as paused after not-interested response.")


def _send_closed_reply(client: NewClient, chat, sender_id: str):
    reply = get_closed_message()
    client.send_message(chat, reply)
    client.send_chat_presence(
        jid=chat,
        state=ChatPresence.CHAT_PRESENCE_PAUSED,
        media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
    )
    save_message(sender_id, reply, int(time.time()), True)
    log.info(f"Sent closed-hours reply to {sender_id}.")


def _should_pause_lead(sender_id: str, text: str) -> bool:
    pause_until = lead_pause_until.get(sender_id, 0)
    if time.time() >= pause_until:
        return False

    normalized = _normalize_text(text)
    restart_phrases = [
        "need",
        "price",
        "quote",
        "book",
        "schedule",
        "service",
        "help",
        "support",
        "call me",
        "contact",
    ]
    if any(phrase in normalized for phrase in restart_phrases):
        lead_pause_until.pop(sender_id, None)
        return False
    return True


def can_respond_to_user(user_id):
    now = time.time()
    timestamps = user_message_timestamps[user_id]
    while timestamps and now - timestamps[0] > 30:
        timestamps.popleft()
    return len(timestamps) < 5


def record_user_response(user_id):
    user_message_timestamps[user_id].append(time.time())


def _get_pending_customer_turn(user_id):
    messages = get_messages(user_id)
    pending_messages = []
    has_assistant_reply = False

    for message_content, _, from_me in reversed(messages):
        if from_me:
            has_assistant_reply = True
            break
        pending_messages.append(message_content)

    pending_messages.reverse()
    combined_text = "\n".join([msg.strip() for msg in pending_messages if msg.strip()]).strip()
    is_first_turn = not has_assistant_reply
    return combined_text, is_first_turn


def _process_pending_reply(client: NewClient, chat, sender_id: str, sender_name: str):
    with processing_locks[sender_id]:
        text, is_first_turn = _get_pending_customer_turn(sender_id)
        if not text:
            return

        if _is_not_interested_message(text):
            _send_not_interested_reply(client, chat, sender_id)
            record_user_response(sender_id)
            return

        is_open, _ = is_open_now()
        if not is_open:
            _send_closed_reply(client, chat, sender_id)
            record_user_response(sender_id)
            return

        if not bot_state.is_bot_running or bot_state.reply_mode == "manual":
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        if not can_respond_to_user(sender_id):
            log.info(f"Rate limit reached for {sender_id}; skipping grouped response.")
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        if is_first_turn:
            log.info(f"Sending grouped greeting to {sender_id}.")
            handle_greeting(client, chat, sender_id, sender_name, text)
            record_user_response(sender_id)
            return

        log.info(f"Sending grouped final response to {sender_id}.")
        handle_final_response(client, chat, sender_id, text)
        record_user_response(sender_id)


def _schedule_grouped_reply(client: NewClient, chat, sender_id: str, sender_name: str):
    def run():
        try:
            _process_pending_reply(client, chat, sender_id, sender_name)
        finally:
            with pending_response_lock:
                timer = pending_response_timers.get(sender_id)
                if timer is current_timer:
                    pending_response_timers.pop(sender_id, None)

    with pending_response_lock:
        existing_timer = pending_response_timers.get(sender_id)
        if existing_timer:
            existing_timer.cancel()

        current_timer = threading.Timer(3.0, run)
        current_timer.daemon = True
        pending_response_timers[sender_id] = current_timer
        current_timer.start()


def on_message(client: NewClient, message: MessageEv):
    """
    Real-time incoming messages.
    Uses one big try/except to capture any errors and separates out key functionality
    into helper functions.
    """
    try:
        chat = message.Info.MessageSource.Chat
        sender_id = message.Info.MessageSource.Chat.User
        text = (
            message.Message.conversation
            or message.Message.extendedTextMessage.text
            or message.Message.imageMessage.caption
            or message.Message.documentMessage.caption
            or ""
        )
        from_me = message.Info.MessageSource.IsFromMe
        is_group = message.Info.MessageSource.IsGroup
        is_edit = message.IsEdit
        is_viewonce = (
            message.IsViewOnce
            or message.IsViewOnceV2
            or message.IsViewOnceV2Extension
        )
        timestamp = message.Info.Timestamp // 1000
        sender_name = message.Info.Pushname or "User"

        log.info(f"Message from {sender_name} ({sender_id}): {text}")

        if chat.User == sender_id and from_me:
            log.info(f"Skipping message from bot itself: {sender_id}")
            return

        if is_group or is_edit or is_viewonce:
            log.info(f"Skipping group/edit/view once message from {sender_id}.")
            return

        if time.time() - timestamp > 60:
            log.info(f"Message from {sender_name} ({sender_id}) is older than one minute; skipping.")
            return

        client.mark_read(
            message.Info.ID,
            chat=chat,
            sender=message.Info.MessageSource.Sender,
            receipt=ReceiptType.READ,
        )
        log.info(f"Marked message {message.Info.ID} as read.")

        save_message(sender_id, text, timestamp, from_me)
        log.info(f"Saved incoming message for user {sender_id} at timestamp {timestamp}.")
        save_contact_name(sender_id, sender_name, timestamp)

        client.send_chat_presence(
            jid=chat,
            state=ChatPresence.CHAT_PRESENCE_COMPOSING,
            media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
        )

        if handle_commands(client, chat, sender_id, text):
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        if message.Info.Type == "media" and message.Info.MediaType != "url":
            if handle_file(client, sender_id, message):
                return

        if not bot_state.is_bot_running:
            log.info("Bot is paused; skipping message processing.")
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        if bot_state.reply_mode == "manual":
            log.info(f"Manual reply mode active for {sender_id}; waiting for admin reply.")
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        if _should_pause_lead(sender_id, text):
            log.info(f"Lead {sender_id} is in paused follow-up state; skipping repeated outreach.")
            client.send_chat_presence(
                jid=chat,
                state=ChatPresence.CHAT_PRESENCE_PAUSED,
                media=ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            return

        log.info(f"Scheduling grouped AI reply for {sender_id}.")
        _schedule_grouped_reply(client, chat, sender_id, sender_name)

    except Exception as exc:
        log.error(f"Error in on_message handler: {exc}")
        log.exception(exc)
