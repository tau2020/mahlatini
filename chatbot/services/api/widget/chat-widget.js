/**
 * Mahlatini AI Chat Widget
 * ========================
 * Embeddable chat widget for Mahlatini Luxury Travel.
 *
 * Usage:
 *   <script src="https://chat.mahlatini.com/widget/chat-widget.js"
 *           data-api-url="https://chat.mahlatini.com"
 *           defer></script>
 *
 * Optional attributes:
 *   data-provider="groq"    — default LLM provider ("groq" or "claude")
 *   data-show-toggle="true" — show provider toggle in header
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

  // Provider config
  let currentProvider =
    (scriptTag && scriptTag.getAttribute("data-provider")) || "groq";
  const showToggle =
    (scriptTag && scriptTag.getAttribute("data-show-toggle")) === "true";

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

    // Provider toggle HTML (only if enabled)
    const toggleHTML = showToggle
      ? `<div class="mah-provider-toggle" id="mah-provider-toggle">
           <button class="mah-provider-btn ${currentProvider === "groq" ? "mah-provider-active" : ""}"
                   data-provider="groq" title="Groq (Llama)">A</button>
           <button class="mah-provider-btn ${currentProvider === "claude" ? "mah-provider-active" : ""}"
                   data-provider="claude" title="Claude">B</button>
         </div>`
      : "";

    // Chat container
    const container = document.createElement("div");
    container.className = "mah-chat-container";
    container.id = "mah-chat-container";
    container.innerHTML = `
      <div class="mah-chat-header">
        <div class="mah-chat-header-avatar">🌍</div>
        <div class="mah-chat-header-info">
          <div class="mah-chat-header-title">Mahlatini Travel Concierge</div>
          <div class="mah-chat-header-status">
            <span class="mah-status-dot"></span> Online — ready to help
          </div>
        </div>
        ${toggleHTML}
        <button class="mah-chat-header-close" id="mah-chat-close" aria-label="Close chat">✕</button>
      </div>

      <div class="mah-chat-messages" id="mah-chat-messages">
        <div class="mah-welcome">
          <div class="mah-welcome-icon">✨</div>
          <div class="mah-welcome-title">Welcome to Mahlatini</div>
          <div class="mah-welcome-text">
            I'm your AI travel concierge. Ask me about safaris, beach holidays,
            honeymoons, and luxury travel across Africa, Indian Ocean, and beyond.
          </div>
        </div>
      </div>

      <div class="mah-quick-actions" id="mah-quick-actions">
        <button class="mah-quick-btn" data-msg="What destinations do you recommend for a first-time safari?">🦁 Safari Ideas</button>
        <button class="mah-quick-btn" data-msg="Tell me about honeymoon destinations">💍 Honeymoons</button>
        <button class="mah-quick-btn" data-msg="What are your best family holiday options?">👨‍👩‍👧‍👦 Family Holidays</button>
        <button class="mah-quick-btn" data-msg="I'd like a beach and safari combination">🏖️ Beach & Safari</button>
      </div>

      <div class="mah-chat-input-area">
        <textarea
          class="mah-chat-input"
          id="mah-chat-input"
          placeholder="Ask about destinations, experiences..."
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
    }
  }

  function addMessage(content, role) {
    const messagesEl = document.getElementById("mah-chat-messages");
    if (!messagesEl) return;

    // Remove quick actions after first user message
    if (role === "user") {
      const qa = document.getElementById("mah-quick-actions");
      if (qa) qa.remove();
    }

    const msgDiv = document.createElement("div");
    msgDiv.className = `mah-message mah-message-${role}`;

    const avatarContent = role === "bot" ? "🌍" : "";
    const avatarHTML =
      role === "bot"
        ? `<div class="mah-message-avatar">${avatarContent}</div>`
        : "";

    msgDiv.innerHTML = `
      ${avatarHTML}
      <div class="mah-message-bubble">${escapeHTML(content)}</div>
    `;

    messagesEl.appendChild(msgDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showTyping() {
    if (isTyping) return;
    isTyping = true;

    const messagesEl = document.getElementById("mah-chat-messages");
    if (!messagesEl) return;

    const typingDiv = document.createElement("div");
    typingDiv.className = "mah-typing";
    typingDiv.id = "mah-typing-indicator";
    typingDiv.innerHTML = `
      <div class="mah-typing-dot"></div>
      <div class="mah-typing-dot"></div>
      <div class="mah-typing-dot"></div>
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

  // ─── Provider Toggle ────────────────────────────────
  function switchProvider(newProvider) {
    currentProvider = newProvider;

    // Update toggle button styles
    document.querySelectorAll(".mah-provider-btn").forEach((btn) => {
      btn.classList.toggle(
        "mah-provider-active",
        btn.getAttribute("data-provider") === newProvider,
      );
    });

    // Reconnect WebSocket with new provider
    if (ws) {
      ws.close();
      ws = null;
    }
    connectWebSocket();
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
          addMessage(data.reply, "bot");

          if (data.requires_human) {
            setTimeout(() => {
              addMessage(
                "I've flagged this conversation for one of our travel experts. " +
                  "They'll be in touch shortly. In the meantime, feel free to keep chatting!",
                "bot",
              );
            }, 500);
          }
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
      // isSending is cleared when ws.onmessage receives the response
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
      addMessage(data.reply, "bot");

      if (data.requires_human) {
        setTimeout(() => {
          addMessage(
            "I've flagged this conversation for one of our travel experts. " +
              "They'll be in touch shortly!",
            "bot",
          );
        }, 500);
      }
    } catch (err) {
      hideTyping();
      addMessage(
        "I'm having trouble connecting right now. Please try again, " +
          "or contact us directly at +27 213 002 325.",
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

    // Provider toggle buttons
    if (showToggle) {
      document.querySelectorAll(".mah-provider-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const provider = btn.getAttribute("data-provider");
          if (provider && provider !== currentProvider) {
            switchProvider(provider);
          }
        });
      });
    }
  }

  // Start when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
