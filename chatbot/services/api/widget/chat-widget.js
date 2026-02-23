/**
 * Mahlatini AI Chat Widget
 * ========================
 * Embeddable chat widget for Mahlatini Luxury Travel.
 *
 * Usage:
 *   <script src="https://chat.mahlatini.com/widget/chat-widget.js"
 *           data-api-url="https://chat.mahlatini.com"
 *           defer></script>
 */

(function () {
  "use strict";

  // ─── Configuration ──────────────────────────────────
  const scriptTag =
    document.currentScript || document.querySelector("script[data-api-url]");
  const API_URL =
    (scriptTag && scriptTag.getAttribute("data-api-url")) ||
    window.location.origin;
  const WS_URL = API_URL.replace(/^http/, "ws");
  const SESSION_KEY = "mah_chat_session";
  const CSS_URL = `${API_URL}/widget/chat-widget.css`;
  const AVATAR_URL = `${API_URL}/widget/sarah-avatar.png`;

  // Provider config
  let currentProvider = "claude";

  // Conversation state
  let messageCount = 0;
  let hasOpenedBefore = false;
  let enquiryProgress = null;

  // ─── Session Management ─────────────────────────────
  function getSessionId() {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id =
        "mah_" +
        Date.now().toString(36) +
        Math.random().toString(36).substr(2, 8);
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  const sessionId = getSessionId();

  // ─── Load CSS ───────────────────────────────────────
  function loadCSS() {
    if (document.querySelector(`link[href="${CSS_URL}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS_URL;
    document.head.appendChild(link);

    // Load Inter font
    if (
      !document.querySelector(
        'link[href*="fonts.googleapis.com/css2?family=Inter"]',
      )
    ) {
      const font = document.createElement("link");
      font.rel = "stylesheet";
      font.href =
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap";
      document.head.appendChild(font);
    }
  }

  // ─── Build Widget DOM ──────────────────────────────
  function buildWidget() {
    // Trigger button
    const trigger = document.createElement("button");
    trigger.className = "mah-chat-trigger";
    trigger.id = "mah-chat-trigger";
    trigger.setAttribute("aria-label", "Open chat");
    trigger.innerHTML = `
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/>
        <path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/>
      </svg>
    `;

    // Chat container
    const container = document.createElement("div");
    container.className = "mah-chat-container";
    container.id = "mah-chat-container";
    container.innerHTML = `
      <div class="mah-chat-header">
        <img class="mah-chat-header-avatar" src="${AVATAR_URL}" alt="Sarah" />
        <div class="mah-chat-header-info">
          <div class="mah-chat-header-title">Sarah: AI Travel Advisor</div>
          <div class="mah-chat-header-status" id="mah-header-status">
            <span class="mah-status-dot" id="mah-status-dot"></span>
            <span id="mah-status-text">Typically replies in seconds</span>
          </div>
        </div>
        <button class="mah-chat-header-close" id="mah-chat-close" aria-label="Close chat">✕</button>
      </div>

      <div class="mah-enquiry-progress" id="mah-enquiry-progress" style="display: none;">
        <div class="mah-progress-bar">
          <div class="mah-progress-fill" id="mah-progress-fill"></div>
        </div>
        <div class="mah-progress-text" id="mah-progress-text"></div>
      </div>

      <div class="mah-chat-messages" id="mah-chat-messages">
        <div class="mah-welcome">
          <div class="mah-welcome-title">Mahlatini Travel</div>
          <div class="mah-welcome-text">
            I know 300+ safari lodges and beach retreats across Africa and the Indian Ocean.<br>
            What kind of trip are you dreaming about?
          </div>
          <div class="mah-welcome-proof">
            Trusted by 2,000+ travellers since 2002
          </div>
        </div>
      </div>

      <div class="mah-quick-actions" id="mah-quick-actions">
        <button class="mah-quick-btn" data-msg="I've never been on safari before — where should I start?">Plan my first safari</button>
        <button class="mah-quick-btn" data-msg="We're planning our honeymoon and want something unforgettable — what do you suggest?">Surprise honeymoon ideas</button>
        <button class="mah-quick-btn" data-msg="We have young kids — what are the best family-friendly safari options?">Travelling with kids</button>
        <button class="mah-quick-btn" data-msg="I'd love to combine a safari with beach time — what's the best way to do that?">Beach + bush combo</button>
        <button class="mah-quick-btn" data-msg="I'm not sure where to go yet — can you help me figure out what's right for us?">Help me choose</button>
      </div>

      <div class="mah-chat-input-area">
        <textarea
          class="mah-chat-input"
          id="mah-chat-input"
          placeholder="Tell me about your dream trip..."
          rows="1"
          maxlength="4000"
        ></textarea>
        <button class="mah-chat-send" id="mah-chat-send" aria-label="Send message">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
      <div class="mah-powered-by">Powered by Mahlatini AI</div>
    `;

    document.body.appendChild(trigger);
    document.body.appendChild(container);

    return { trigger, container };
  }

  // ─── Chat Logic ────────────────────────────────────
  let isOpen = false;
  let isTyping = false;
  let isSending = false;
  let ws = null;

  function toggleChat(trigger, container) {
    isOpen = !isOpen;
    trigger.classList.toggle("mah-open", isOpen);
    container.classList.toggle("mah-visible", isOpen);

    if (isOpen) {
      const input = document.getElementById("mah-chat-input");
      setTimeout(() => input && input.focus(), 350);
      connectWebSocket();

      // Stop pulse after first open
      if (!hasOpenedBefore) {
        hasOpenedBefore = true;
        trigger.classList.add("mah-pulsed");
      }

      // Update status to "Active now"
      updateStatus("Active now", false);
    }
  }

  function updateStatus(text, isGold) {
    const statusText = document.getElementById("mah-status-text");
    const statusDot = document.getElementById("mah-status-dot");
    if (statusText) statusText.textContent = text;
    if (statusDot) statusDot.classList.toggle("mah-dot-gold", isGold);
  }

  function addMessage(content, role) {
    const messagesEl = document.getElementById("mah-chat-messages");
    if (!messagesEl) return;

    // Remove quick actions after first user message
    if (role === "user") {
      const qa = document.getElementById("mah-quick-actions");
      if (qa) qa.remove();
    }

    messageCount++;

    const msgDiv = document.createElement("div");
    msgDiv.className = `mah-message mah-message-${role}`;

    let avatarHTML;
    if (role === "bot") {
      avatarHTML = `<img class="mah-message-avatar" src="${AVATAR_URL}" alt="Sarah" />`;
    } else {
      avatarHTML = '<div class="mah-message-avatar mah-message-avatar-user">You</div>';
    }

    msgDiv.innerHTML = `
      ${avatarHTML}
      <div class="mah-message-bubble">${escapeHTML(content)}</div>
    `;

    messagesEl.appendChild(msgDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ─── Enquiry Progress ─────────────────────────────
  function updateProgressBar(progress) {
    const container = document.getElementById("mah-enquiry-progress");
    const fill = document.getElementById("mah-progress-fill");
    const text = document.getElementById("mah-progress-text");
    if (!container || !fill || !text) return;

    enquiryProgress = progress;

    // Hide during exploring and after submission
    if (progress.phase === "exploring" || progress.phase === "submitted") {
      container.style.display = "none";

      if (progress.phase === "submitted") {
        updateStatus("Enquiry submitted", true);
      }
      return;
    }

    // Show during collecting and confirming
    container.style.display = "block";
    fill.style.width = progress.percentage + "%";

    if (progress.phase === "confirming") {
      text.textContent = "Ready to submit your enquiry";
      fill.style.width = "100%";
    } else {
      const remaining = progress.total_required - progress.filled_count;
      if (remaining === 1) {
        text.textContent = "Just 1 more detail needed";
      } else if (remaining > 1) {
        text.textContent = remaining + " details to go";
      } else {
        text.textContent = "Collecting your trip details...";
      }
    }
  }

  function showConfirmationButtons() {
    const messagesEl = document.getElementById("mah-chat-messages");
    if (!messagesEl) return;

    // Don't show if already present
    if (document.getElementById("mah-confirm-actions")) return;

    const actionsDiv = document.createElement("div");
    actionsDiv.className = "mah-confirm-actions";
    actionsDiv.id = "mah-confirm-actions";
    actionsDiv.innerHTML = `
      <button class="mah-confirm-btn mah-confirm-yes">Yes, submit my enquiry</button>
      <button class="mah-confirm-btn mah-confirm-edit">I need to change something</button>
    `;

    messagesEl.appendChild(actionsDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    actionsDiv.querySelector(".mah-confirm-yes").addEventListener("click", () => {
      sendMessage("Yes, that's all correct — please submit it");
      actionsDiv.remove();
    });

    actionsDiv.querySelector(".mah-confirm-edit").addEventListener("click", () => {
      sendMessage("Actually, let me correct something");
      actionsDiv.remove();
    });
  }

  function handleEnquiryProgress(data) {
    if (data.enquiry_progress) {
      updateProgressBar(data.enquiry_progress);
    }
  }

  // ─── Typing Indicator ─────────────────────────────
  function showTyping() {
    if (isTyping) return;
    isTyping = true;

    const messagesEl = document.getElementById("mah-chat-messages");
    if (!messagesEl) return;

    const typingDiv = document.createElement("div");
    typingDiv.className = "mah-typing";
    typingDiv.id = "mah-typing-indicator";
    typingDiv.innerHTML = `
      <img class="mah-typing-avatar" src="${AVATAR_URL}" alt="Sarah" />
      <div class="mah-typing-dots">
        <div class="mah-typing-dot"></div>
        <div class="mah-typing-dot"></div>
        <div class="mah-typing-dot"></div>
      </div>
    `;

    messagesEl.appendChild(typingDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    isTyping = false;
    const el = document.getElementById("mah-typing-indicator");
    if (el) el.remove();
  }

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ─── WebSocket Connection ──────────────────────────
  function connectWebSocket() {
    if (
      ws &&
      (ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING)
    )
      return;

    try {
      const wsUrl = `${WS_URL}/api/chat/ws/${sessionId}?provider=${currentProvider}`;
      const socket = new WebSocket(wsUrl);
      ws = socket;

      socket.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.type === "typing") {
          if (data.status) showTyping();
          else hideTyping();
          return;
        }

        if (data.type === "message") {
          isSending = false;
          hideTyping();

          // Update enquiry progress
          handleEnquiryProgress(data);

          // Brief pause after typing stops — feels more human
          setTimeout(() => {
            addMessage(data.reply, "bot");

            // Show confirmation buttons if in confirming phase
            if (
              data.enquiry_progress &&
              data.enquiry_progress.phase === "confirming"
            ) {
              setTimeout(() => showConfirmationButtons(), 400);
            }
          }, 300);
        }
      };

      socket.onclose = function () {
        if (ws === socket) ws = null;
      };

      socket.onerror = function () {
        if (ws === socket) ws = null;
      };
    } catch (e) {
      ws = null;
    }
  }

  // ─── Send Message ──────────────────────────────────
  async function sendMessage(text) {
    text = text.trim();
    if (!text || isSending) return;

    isSending = true;
    addMessage(text, "user");

    // Remove confirmation buttons if present
    const confirmEl = document.getElementById("mah-confirm-actions");
    if (confirmEl) confirmEl.remove();

    const input = document.getElementById("mah-chat-input");
    const sendBtn = document.getElementById("mah-chat-send");
    if (input) input.value = "";
    if (sendBtn) sendBtn.disabled = true;

    showTyping();

    // Try WebSocket first
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          message: text,
          source_page: window.location.pathname,
          provider: currentProvider,
        }),
      );
      if (sendBtn) sendBtn.disabled = false;
      return;
    }

    // Fallback to REST API
    try {
      const response = await fetch(`${API_URL}/api/chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          source_page: window.location.pathname,
          provider: currentProvider,
        }),
      });

      hideTyping();

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();

      // Update enquiry progress
      handleEnquiryProgress(data);

      // Brief pause after response arrives
      setTimeout(() => {
        addMessage(data.reply, "bot");

        // Show confirmation buttons if in confirming phase
        if (
          data.enquiry_progress &&
          data.enquiry_progress.phase === "confirming"
        ) {
          setTimeout(() => showConfirmationButtons(), 400);
        }
      }, 300);
    } catch (err) {
      hideTyping();
      addMessage(
        "I'm having trouble connecting right now. Please try again, " +
          "or reach us directly at +27 213 002 325.",
        "bot",
      );
    } finally {
      isSending = false;
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  // ─── Auto-resize textarea ─────────────────────────
  function autoResize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 100) + "px";
  }

  // ─── Initialise ───────────────────────────────────
  function init() {
    loadCSS();
    const { trigger, container } = buildWidget();

    // Toggle chat open/close
    trigger.addEventListener("click", () => toggleChat(trigger, container));

    // Close button
    document.getElementById("mah-chat-close").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleChat(trigger, container);
    });

    // Send button
    document.getElementById("mah-chat-send").addEventListener("click", () => {
      const input = document.getElementById("mah-chat-input");
      if (input) sendMessage(input.value);
    });

    // Enter to send (Shift+Enter for newline)
    document
      .getElementById("mah-chat-input")
      .addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendMessage(e.target.value);
        }
      });

    // Auto-resize
    document.getElementById("mah-chat-input").addEventListener("input", (e) => {
      autoResize(e.target);
    });

    // Quick action buttons
    document.querySelectorAll(".mah-quick-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const msg = btn.getAttribute("data-msg");
        if (msg) sendMessage(msg);
      });
    });
  }

  // Start when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
