async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
}

const workspaceAuthConfig = window.workspaceAuthConfig || {};
const workspaceSessionKey = "wa_workspace_auth_v1";
const workspaceRememberedEmailKey = "wa_workspace_email_v1";

function isWorkspaceAuthenticated() {
    return localStorage.getItem(workspaceSessionKey) === "true";
}

function showWorkspaceApp() {
    document.body.classList.remove("auth-locked");
    document.getElementById("auth-gate")?.setAttribute("hidden", "");
    document.getElementById("app-shell")?.removeAttribute("hidden");
}

function showWorkspaceLogin() {
    document.body.classList.add("auth-locked");
    document.getElementById("app-shell")?.setAttribute("hidden", "");
    document.getElementById("auth-gate")?.removeAttribute("hidden");
    setSidebarOpen(false);
}

function bootstrapWorkspaceAuth() {
    const loginForm = document.getElementById("workspace-login-form");
    const emailInput = document.getElementById("workspace-email-input");
    const passwordInput = document.getElementById("workspace-password-input");
    const rememberInput = document.getElementById("workspace-remember-input");
    const loginError = document.getElementById("workspace-login-error");
    const signoutButton = document.getElementById("workspace-signout");

    const rememberedEmail = localStorage.getItem(workspaceRememberedEmailKey);
    if (emailInput && rememberedEmail) {
        emailInput.value = rememberedEmail;
    }

    loginForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        const email = emailInput?.value.trim().toLowerCase() || "";
        const password = passwordInput?.value || "";
        const validEmail = String(workspaceAuthConfig.email || "").trim().toLowerCase();
        const validPassword = String(workspaceAuthConfig.password || "");

        if (email !== validEmail || password !== validPassword) {
            if (loginError) {
                loginError.hidden = false;
            }
            return;
        }

        if (loginError) {
            loginError.hidden = true;
        }
        localStorage.setItem(workspaceSessionKey, "true");
        if (rememberInput?.checked) {
            localStorage.setItem(workspaceRememberedEmailKey, emailInput?.value.trim() || "");
        } else {
            localStorage.removeItem(workspaceRememberedEmailKey);
        }
        showWorkspaceApp();
    });

    signoutButton?.addEventListener("click", () => {
        localStorage.removeItem(workspaceSessionKey);
        if (passwordInput) {
            passwordInput.value = "";
        }
        showWorkspaceLogin();
    });

    if (isWorkspaceAuthenticated()) {
        showWorkspaceApp();
    } else {
        showWorkspaceLogin();
    }
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
}

function textOrFallback(value, fallback = "-") {
    return value && String(value).trim() ? value : fallback;
}

function hasMeaningfulValue(value) {
    return Boolean(value && String(value).trim() && String(value).trim() !== "-");
}

function renderConversation(messages, activeUserId) {
    const container = document.getElementById("demo-chat");
    if (!container) {
        return;
    }

    container.innerHTML = "";
    if (!messages.length) {
        container.innerHTML = '<div class="empty-block">Start a customer inquiry to populate the inbox.</div>';
        return;
    }

    messages.forEach((message) => {
        const bubble = document.createElement("div");
        bubble.className = `message ${message.from_me ? "assistant" : "customer"}`;

        const role = document.createElement("span");
        role.className = "message-role";
        role.textContent = message.from_me ? "Service Desk" : getSelectedLeadLabel();

        const text = document.createElement("p");
        text.textContent = message.message_content || "";

        bubble.appendChild(role);
        bubble.appendChild(text);
        container.appendChild(bubble);
    });

    container.scrollTop = container.scrollHeight;
}

function renderIntake(intake) {
    const requiredIds = [
        "intake-service",
        "intake-readiness",
        "intake-location",
        "intake-urgency",
        "intake-property",
        "intake-visit",
        "intake-budget",
        "intake-name",
        "intake-summary",
        "intake-next-action",
        "intake-missing",
    ];
    if (!requiredIds.every((id) => document.getElementById(id))) {
        return;
    }

    const detailFields = [
        ["service_category", "intake-service", "card-intake-service"],
        ["quote_readiness", "intake-readiness", "card-intake-readiness"],
        ["location", "intake-location", "card-intake-location"],
        ["urgency", "intake-urgency", "card-intake-urgency"],
        ["property_type", "intake-property", "card-intake-property"],
        ["preferred_visit_time", "intake-visit", "card-intake-visit"],
        ["budget_signal", "intake-budget", "card-intake-budget"],
        ["customer_name", "intake-name", "card-intake-name"],
    ];
    detailFields.forEach(([fieldName, valueId, cardId]) => {
        const value = intake[fieldName];
        const valueEl = document.getElementById(valueId);
        const cardEl = document.getElementById(cardId);
        if (valueEl) {
            valueEl.textContent = textOrFallback(value);
        }
        if (cardEl) {
            cardEl.style.display = hasMeaningfulValue(value) ? "" : "none";
        }
    });

    document.getElementById("intake-summary").textContent = textOrFallback(intake.issue_summary, "No conversation summary available yet.");
    document.getElementById("intake-next-action").textContent = textOrFallback(
        intake.next_action,
        "Start a conversation to produce the first lead summary."
    );

    const missingContainer = document.getElementById("intake-missing");
    missingContainer.innerHTML = "";
    const hasMissing = Boolean(intake.missing_details && intake.missing_details.length);
    const items = hasMissing ? intake.missing_details : ["No blockers yet"];
    items.forEach((item) => {
        const chip = document.createElement("span");
        chip.className = `chip ${hasMissing ? "warn" : "ok"}`;
        chip.textContent = item;
        missingContainer.appendChild(chip);
    });
}

function getSelectedLeadId() {
    return document.getElementById("support-user-id")?.value.trim() || "";
}

function getSelectedLeadLabel() {
    return document.getElementById("selected-lead-title")?.textContent?.trim() || getSelectedLeadId();
}

function renderLeadTags(containerId, tags) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    container.innerHTML = "";
    if (!tags || !tags.length) {
        container.innerHTML = '<span class="chip ok">No tags yet</span>';
        return;
    }

    tags.forEach((tag) => {
        const isInteractive = containerId === "lead-tags";
        const chip = document.createElement(isInteractive ? "button" : "span");
        chip.className = "chip";
        chip.textContent = String(tag).replaceAll("_", " ");
        if (isInteractive) {
            chip.type = "button";
            chip.dataset.tag = tag;
            chip.classList.add("tag-chip");
            chip.addEventListener("click", () => toggleLeadTag(tag, false));
        }
        container.appendChild(chip);
    });
}

function renderLeadNotes(containerId, notes) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    container.innerHTML = "";
    if (!notes || !notes.length) {
        container.innerHTML = '<div class="empty-block">No internal notes saved for this lead yet.</div>';
        return;
    }

    notes.forEach((note) => {
        const card = document.createElement("div");
        card.className = "note-card";
        const title = document.createElement("strong");
        title.textContent = note.created_at ? new Date(note.created_at * 1000).toLocaleString() : "Saved note";
        const body = document.createElement("p");
        body.textContent = note.note || "";
        card.appendChild(title);
        card.appendChild(body);
        container.appendChild(card);
    });
}

function renderLeadTasks(containerId, tasks, userId) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    container.innerHTML = "";
    if (!tasks || !tasks.length) {
        container.innerHTML = '<div class="empty-block">No follow-up tasks for this lead yet.</div>';
        return;
    }
    tasks.forEach((task) => {
        const card = document.createElement("div");
        card.className = `note-card task-card ${task.status === "done" ? "task-done" : ""}`;
        const title = document.createElement("strong");
        title.textContent = task.title || "";
        const body = document.createElement("p");
        body.textContent = `${task.due_label || "Today"} | ${task.status === "done" ? "Completed" : "Open"}`;
        card.appendChild(title);
        card.appendChild(body);
        if (task.status !== "done") {
            const button = document.createElement("button");
            button.className = "soft-button task-toggle";
            button.type = "button";
            button.textContent = "Mark Done";
            button.addEventListener("click", async () => {
                try {
                    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/tasks/${task.id}`, { status: "done" });
                    renderLeadTasks("lead-tasks", result.tasks || [], userId);
                    renderLeadTasks("inbox-lead-tasks", result.tasks || [], userId);
                } catch (error) {
                    window.alert(error.message);
                }
            });
            card.appendChild(button);
        }
        container.appendChild(card);
    });
}

function syncLeadIdentity(name, stageLabel, stageValue) {
    if (name) {
        document.getElementById("selected-lead-title")?.replaceChildren(document.createTextNode(name));
        const leadsInput = document.getElementById("lead-display-name");
        const inboxInput = document.getElementById("inbox-lead-display-name");
        if (leadsInput) {
            leadsInput.value = name;
        }
        if (inboxInput) {
            inboxInput.value = name;
        }
    }

    if (stageLabel) {
        document.getElementById("selected-lead-stage")?.replaceChildren(document.createTextNode(stageLabel));
        document.getElementById("lead-stage-badge")?.replaceChildren(document.createTextNode(stageLabel));
    }

    if (stageValue) {
        const leadsStage = document.getElementById("lead-stage");
        const inboxStage = document.getElementById("inbox-lead-stage");
        if (leadsStage) {
            leadsStage.value = stageValue;
        }
        if (inboxStage) {
            inboxStage.value = stageValue;
        }
    }
}

function collectAvailabilityPayload() {
    const businessHours = {};
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].forEach((day) => {
        businessHours[day] = {
            enabled: Boolean(document.querySelector(`.availability-enabled[data-day="${day}"]`)?.checked),
            start: document.querySelector(`.availability-start[data-day="${day}"]`)?.value || "08:00",
            end: document.querySelector(`.availability-end[data-day="${day}"]`)?.value || "18:00",
        };
    });
    return {
        timezone: document.getElementById("availability-timezone")?.value || "Asia/Dubai",
        business_hours: businessHours,
    };
}

function renderAvailabilitySummary(summary) {
    if (!summary) {
        return;
    }
    const copy = document.getElementById("availability-status-copy");
    const automationCopy = document.getElementById("automation-status-copy");
    if (copy) {
        copy.textContent = summary.status_text || "";
    }
    if (automationCopy) {
        automationCopy.textContent = summary.status_text || "";
    }
}

function renderWhatsAppStatus(status) {
    const stateEl = document.getElementById("wa-state");
    const sessionEl = document.getElementById("wa-session");
    const pill = document.getElementById("whatsapp-connection-pill");
    const frame = document.getElementById("wa-qr-frame");
    const overviewFrame = document.getElementById("wa-qr-frame-overview");
    const automationSummary = document.getElementById("automation-status-summary");
    const automationCopy = document.getElementById("automation-status-copy");
    const overviewCopy = document.getElementById("overview-status-copy");
    const replyModePill = document.getElementById("reply-mode-pill");
    if (!stateEl || !sessionEl || !pill || !frame) {
        // continue for overview-only pages
    }

    if (stateEl) {
        stateEl.textContent = textOrFallback(status.state, "stopped");
    }
    if (sessionEl) {
        sessionEl.textContent = status.connected ? "Connected" : "Not linked";
    }
    if (pill) {
        pill.classList.toggle("live", Boolean(status.connected));
        pill.classList.toggle("paused", !status.connected);
        pill.innerHTML = `<span class="status-dot"></span>${status.connected ? "WhatsApp Connected" : "WhatsApp Not Connected"}`;
    }
    const replyModeIsAutomatic = replyModePill?.textContent?.includes("Automatic");
    if (automationSummary) {
        automationSummary.textContent = `${status.connected ? "Connected" : "Not connected"} | ${replyModeIsAutomatic ? "Automatic" : "Manual"}`;
    }
    if (automationCopy) {
        automationCopy.textContent = status.connected
            ? "The live session is active. You can keep automatic replies on or switch to manual takeover."
            : "Connect a device, choose reply mode, and manage the live session here.";
    }
    if (overviewCopy) {
        overviewCopy.textContent = status.connected
            ? "WhatsApp is connected and ready."
            : "Connect WhatsApp to start live intake.";
    }

    const qrHtml = status.qr_url && !status.connected
        ? `<img id="wa-qr-image" src="${status.qr_url}" alt="WhatsApp QR code">`
        : !status.connected
            ? '<div class="empty-block" id="wa-qr-empty">Start the WhatsApp runtime to generate a QR code here.</div>'
            : '<div class="empty-block">WhatsApp is connected. Incoming messages will sync here.</div>';

    if (frame) {
        frame.innerHTML = qrHtml;
    }
    if (overviewFrame) {
        overviewFrame.innerHTML = status.qr_url && !status.connected
            ? `<img id="wa-qr-image-overview" src="${status.qr_url}" alt="WhatsApp QR code">`
            : !status.connected
                ? '<div class="empty-block">Click Connect WhatsApp to generate the QR here.</div>'
                : '<div class="empty-block">WhatsApp is connected. You can move to Inbox or Automation now.</div>';
    }
}

function renderReplyMode(mode) {
    const pill = document.getElementById("reply-mode-pill");
    const supportModeText = document.getElementById("support-mode-text");
    const inboxStatusCopy = document.getElementById("inbox-status-copy");
    const supportMessage = document.getElementById("support-message");
    const supportSendButton = document.getElementById("send-support-reply");
    const supportSendNote = document.getElementById("support-send-note");
    const selectedLeadMode = document.getElementById("selected-lead-mode");
    const sendAiReplyButton = document.getElementById("send-ai-reply");
    const automaticButton = document.getElementById("mode-automatic");
    const manualButton = document.getElementById("mode-manual");
    const inboxAutomaticButton = document.getElementById("inbox-mode-automatic");
    const inboxManualButton = document.getElementById("inbox-mode-manual");
    if (pill) {
        pill.classList.toggle("live", mode === "automatic");
        pill.classList.toggle("paused", mode !== "automatic");
        pill.innerHTML = `<span class="status-dot"></span>${mode === "automatic" ? "AI Replies" : "Human Replies"}`;
    }
    if (supportModeText) {
        supportModeText.textContent = mode === "automatic"
            ? "The bot is currently replying automatically. Switch to human replies to take over the conversation yourself."
            : "Human replies are active. Messages from this panel go directly to WhatsApp.";
    }
    if (inboxStatusCopy) {
        inboxStatusCopy.textContent = mode === "automatic"
            ? "AI replies are active."
            : "Human replies are active.";
    }
    if (selectedLeadMode) {
        selectedLeadMode.textContent = mode === "automatic" ? "AI Replies" : "Human Replies";
    }
    if (automaticButton && manualButton) {
        automaticButton.className = mode === "automatic" ? "primary-button" : "soft-button";
        manualButton.className = mode === "manual" ? "primary-button" : "soft-button";
    }
    if (inboxAutomaticButton && inboxManualButton) {
        inboxAutomaticButton.className = mode === "automatic" ? "primary-button" : "soft-button";
        inboxManualButton.className = mode === "manual" ? "primary-button" : "soft-button";
    }
    if (supportMessage) {
        supportMessage.disabled = mode !== "manual";
        supportMessage.placeholder = mode === "manual"
            ? "Type a human reply here..."
            : "Switch to Human Replies to type and send a reply.";
    }
    if (supportSendButton) {
        supportSendButton.disabled = mode !== "manual";
    }
    if (sendAiReplyButton) {
        sendAiReplyButton.disabled = mode !== "automatic";
    }
    if (supportSendNote) {
        supportSendNote.textContent = mode === "manual"
            ? "Uses the active WhatsApp session. Your message will be sent as a human reply."
            : "Human reply sending is locked while AI Replies is active.";
    }
}

async function saveLeadName(button, inputId) {
    const userId = button?.dataset.userId;
    const input = document.getElementById(inputId);
    const name = input?.value.trim() || "";
    if (!userId || !input) {
        return;
    }
    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/name`, { name });
    syncLeadIdentity(name || getSelectedLeadId(), document.getElementById("selected-lead-stage")?.textContent?.trim(), result.lead?.meta?.stage);
}

async function saveLeadStage(selectId) {
    const select = document.getElementById(selectId);
    const userId = select?.dataset.userId;
    if (!select || !userId) {
        return;
    }
    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/stage`, { stage: select.value });
    const stageLabel = select.options[select.selectedIndex]?.textContent || select.value;
    syncLeadIdentity(getSelectedLeadLabel(), stageLabel, result.lead?.meta?.stage || select.value);
}

async function addLeadNote(buttonId, inputId, listId) {
    const button = document.getElementById(buttonId);
    const input = document.getElementById(inputId);
    const userId = button?.dataset.userId;
    const note = input?.value.trim();
    if (!userId || !note || !input) {
        return;
    }
    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/notes`, { note });
    input.value = "";
    renderLeadNotes(listId, result.notes || []);
}

async function toggleLeadTag(tag, enabled) {
    const userId = document.getElementById("add-lead-tag")?.dataset.userId || getSelectedLeadId();
    if (!userId) {
        return;
    }
    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/tags`, { tag, enabled });
    renderLeadTags("lead-tags", result.tags || []);
    renderLeadTags("inbox-lead-tags", result.tags || []);
}

async function addLeadTag() {
    const input = document.getElementById("lead-tag-input");
    const tag = input?.value.trim();
    if (!tag || !input) {
        return;
    }
    await toggleLeadTag(tag, true);
    input.value = "";
}

async function addLeadTask(buttonId, inputId, listId) {
    const button = document.getElementById(buttonId);
    const input = document.getElementById(inputId);
    const userId = button?.dataset.userId;
    const title = input?.value.trim();
    if (!userId || !title || !input) {
        return;
    }
    const result = await postJson(`/api/leads/${encodeURIComponent(userId)}/tasks`, { title, due_label: "Today" });
    input.value = "";
    renderLeadTasks(listId, result.tasks || [], userId);
    if (listId === "lead-tasks") {
        renderLeadTasks("inbox-lead-tasks", result.tasks || [], userId);
    } else {
        renderLeadTasks("lead-tasks", result.tasks || [], userId);
    }
}

async function refreshWhatsAppStatus() {
    if (!document.getElementById("wa-state") && !document.getElementById("whatsapp-connection-pill")) {
        return;
    }
    try {
        const status = await fetchJson("/api/whatsapp/status");
        renderWhatsAppStatus(status);
    } catch (_error) {
        // ignore transient polling failures in UI
    }
}

function setSidebarOpen(isOpen) {
    const appShell = document.getElementById("app-shell");
    const sidebarToggle = document.getElementById("sidebar-toggle");
    if (!appShell || !sidebarToggle) {
        return;
    }

    appShell.classList.toggle("nav-open", isOpen);
    sidebarToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    document.body.style.overflow = isOpen && window.innerWidth <= 1080 ? "hidden" : "";
}

document.getElementById("sidebar-toggle")?.addEventListener("click", () => {
    const appShell = document.getElementById("app-shell");
    const isOpen = Boolean(appShell?.classList.contains("nav-open"));
    setSidebarOpen(!isOpen);
});

document.getElementById("mobile-nav-backdrop")?.addEventListener("click", () => {
    setSidebarOpen(false);
});

document.querySelectorAll(".sidebar .nav-link").forEach((link) => {
    link.addEventListener("click", () => {
        if (window.innerWidth <= 1080) {
            setSidebarOpen(false);
        }
    });
});

window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        setSidebarOpen(false);
    }
});

window.addEventListener("resize", () => {
    if (window.innerWidth > 1080) {
        setSidebarOpen(false);
    }
});

document.getElementById("save-bot-name")?.addEventListener("click", async () => {
    const name = document.getElementById("bot-name").value.trim();
    try {
        await postJson("/api/bot-name", { name });
        window.location.reload();
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("toggle-bot")?.addEventListener("click", async (event) => {
    const shouldPause = event.currentTarget.textContent.includes("Pause");
    try {
        await postJson("/api/bot-state", { is_running: !shouldPause });
        window.location.reload();
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("start-whatsapp")?.addEventListener("click", async () => {
    try {
        await postJson("/api/whatsapp/start", {});
        await refreshWhatsAppStatus();
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("start-whatsapp-cta")?.addEventListener("click", async () => {
    try {
        await postJson("/api/whatsapp/start", {});
        await refreshWhatsAppStatus();
        const qrPanel = document.getElementById("wa-qr-panel");
        if (qrPanel) {
            qrPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("start-whatsapp-cta-overview")?.addEventListener("click", async () => {
    try {
        await postJson("/api/whatsapp/start", {});
        await refreshWhatsAppStatus();
        const qrPanel = document.getElementById("wa-qr-panel-overview");
        if (qrPanel) {
            qrPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("stop-whatsapp")?.addEventListener("click", async () => {
    try {
        await postJson("/api/whatsapp/stop", {});
        await refreshWhatsAppStatus();
    } catch (error) {
        window.alert(error.message);
    }
});

async function resetWhatsAppSession() {
    try {
        await postJson("/api/whatsapp/reset", {});
        await refreshWhatsAppStatus();
    } catch (error) {
        window.alert(error.message);
    }
}

document.getElementById("reset-whatsapp-session")?.addEventListener("click", resetWhatsAppSession);
document.getElementById("reset-whatsapp-session-secondary")?.addEventListener("click", resetWhatsAppSession);

document.getElementById("mode-automatic")?.addEventListener("click", async () => {
    try {
        const result = await postJson("/api/reply-mode", { mode: "automatic" });
        renderReplyMode(result.reply_mode);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("mode-manual")?.addEventListener("click", async () => {
    try {
        const result = await postJson("/api/reply-mode", { mode: "manual" });
        renderReplyMode(result.reply_mode);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-mode-automatic")?.addEventListener("click", async () => {
    try {
        const result = await postJson("/api/reply-mode", { mode: "automatic" });
        renderReplyMode(result.reply_mode);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-mode-manual")?.addEventListener("click", async () => {
    try {
        const result = await postJson("/api/reply-mode", { mode: "manual" });
        renderReplyMode(result.reply_mode);
    } catch (error) {
        window.alert(error.message);
    }
});

document.querySelectorAll("[data-prompt-name]").forEach((button) => {
    button.addEventListener("click", async () => {
        const promptName = button.dataset.promptName;
        const textarea = document.getElementById(`prompt-${promptName}`);
        if (!textarea) {
            return;
        }

        try {
            await postJson(`/api/prompts/${promptName}`, { content: textarea.value });
            const previousLabel = button.textContent;
            button.textContent = "Saved";
            setTimeout(() => {
                button.textContent = previousLabel;
            }, 1200);
        } catch (error) {
            window.alert(error.message);
        }
    });
});

document.getElementById("send-support-reply")?.addEventListener("click", async () => {
    const userId = getSelectedLeadId();
    const message = document.getElementById("support-message")?.value.trim();
    if (!userId || !message) {
        return;
    }
    try {
        await postJson("/api/support-reply", { user_id: userId, message });
        document.getElementById("support-message").value = "";
        window.location.reload();
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("send-ai-reply")?.addEventListener("click", async () => {
    const userId = getSelectedLeadId();
    if (!userId) {
        return;
    }
    try {
        const result = await postJson("/api/ai-reply", { user_id: userId });
        renderConversation(result.conversation, userId);
        renderIntake(result.intake);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("save-lead-name")?.addEventListener("click", async (event) => {
    try {
        await saveLeadName(event.currentTarget, "lead-display-name");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-save-lead-name")?.addEventListener("click", async (event) => {
    try {
        await saveLeadName(event.currentTarget, "inbox-lead-display-name");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("lead-stage")?.addEventListener("change", async () => {
    try {
        await saveLeadStage("lead-stage");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-lead-stage")?.addEventListener("change", async () => {
    try {
        await saveLeadStage("inbox-lead-stage");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("add-lead-note")?.addEventListener("click", async () => {
    try {
        await addLeadNote("add-lead-note", "lead-note-input", "lead-notes");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-add-lead-note")?.addEventListener("click", async () => {
    try {
        await addLeadNote("inbox-add-lead-note", "inbox-lead-note-input", "inbox-lead-notes");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("add-lead-tag")?.addEventListener("click", async () => {
    try {
        await addLeadTag();
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("add-lead-task")?.addEventListener("click", async () => {
    try {
        await addLeadTask("add-lead-task", "lead-task-input", "lead-tasks");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("inbox-add-lead-task")?.addEventListener("click", async () => {
    try {
        await addLeadTask("inbox-add-lead-task", "inbox-lead-task-input", "inbox-lead-tasks");
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("save-availability")?.addEventListener("click", async () => {
    try {
        const result = await postJson("/api/availability", collectAvailabilityPayload());
        renderAvailabilitySummary(result.availability);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById("reset-conversation")?.addEventListener("click", async (event) => {
    const userId = event.currentTarget.dataset.userId;
    if (!userId) {
        return;
    }
    try {
        await postJson(`/api/conversations/${encodeURIComponent(userId)}/reset`, {});
        window.location.href = "/inbox";
    } catch (error) {
        window.alert(error.message);
    }
});

refreshWhatsAppStatus();
renderReplyMode(document.getElementById("mode-manual")?.classList.contains("primary-button") ? "manual" : "automatic");
setSidebarOpen(false);
bootstrapWorkspaceAuth();
renderLeadTags("lead-tags", Array.from(document.querySelectorAll("#lead-tags [data-tag]")).map((node) => node.dataset.tag));
renderLeadTags("inbox-lead-tags", Array.from(document.querySelectorAll("#inbox-lead-tags .chip")).map((node) => node.textContent.trim().replaceAll(" ", "_")));
renderLeadTasks("lead-tasks", Array.from(document.querySelectorAll("#lead-tasks .task-card")).map((node) => ({
    id: Number(node.querySelector(".task-toggle")?.dataset.taskId || 0),
    title: node.querySelector("strong")?.textContent || "",
    status: node.classList.contains("task-done") ? "done" : "open",
    due_label: node.querySelector("p")?.textContent?.split("|")[0]?.trim() || "Today",
})), document.getElementById("add-lead-task")?.dataset.userId || getSelectedLeadId());
renderLeadTasks("inbox-lead-tasks", Array.from(document.querySelectorAll("#inbox-lead-tasks .task-card")).map((node) => ({
    id: Number(node.querySelector(".task-toggle")?.dataset.taskId || 0),
    title: node.querySelector("strong")?.textContent || "",
    status: node.classList.contains("task-done") ? "done" : "open",
    due_label: node.querySelector("p")?.textContent?.split("|")[0]?.trim() || "Today",
})), document.getElementById("inbox-add-lead-task")?.dataset.userId || getSelectedLeadId());
if (document.getElementById("wa-state") || document.getElementById("whatsapp-connection-pill")) {
    window.setInterval(refreshWhatsAppStatus, 5000);
}
