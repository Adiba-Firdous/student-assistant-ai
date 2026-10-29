(function () {
  "use strict";

  /* ── DOM refs ── */
  var welcomeScreen = document.getElementById("welcomeScreen");
  var messagesList  = document.getElementById("messagesList");
  var chatScroll    = document.getElementById("chatScroll");
  var messageInput  = document.getElementById("messageInput");
  var sendBtn       = document.getElementById("sendBtn");
  var sendSpinner   = document.getElementById("sendSpinner");
  var sendIcon      = document.getElementById("sendIcon");
  var charCounter   = document.getElementById("charCounter");
  var clearBtn      = document.getElementById("clearBtn");
  var newChatBtn    = document.getElementById("newChatBtn");
  var menuBtn       = document.getElementById("menuBtn");
  var sidebar       = document.getElementById("sidebar");
  var overlay       = document.getElementById("sidebarOverlay");
  var bubbleTpl     = document.getElementById("bubbleTemplate");

  /* ── State ── */
  var messages     = [];
  var isLoading    = false;
  var lastUserText = "";

  /* ── Action prompts ── */
  var ACTION_PROMPTS = {
    explain:    "Please explain this topic clearly with examples: ",
    notes:      "Create concise, well-structured study notes on: ",
    solve:      "Solve this step-by-step, showing all working: ",
    quiz:       "Generate a 5-question practice quiz (with answers) on: ",
    plan:       "Create a detailed study plan for: ",
    code:       "Explain what this code does and how it works: ",
    assignment: "Help me improve this assignment - suggest structure and improvements: ",
    interview:  "Give me practice interview questions with ideal answers for: "
  };

  /* ── Sidebar ── */
  function openSidebar() {
    sidebar.classList.add("open");
    overlay.classList.add("active");
    overlay.removeAttribute("aria-hidden");
    menuBtn.setAttribute("aria-expanded", "true");
  }
  function closeSidebar() {
    sidebar.classList.remove("open");
    overlay.classList.remove("active");
    overlay.setAttribute("aria-hidden", "true");
    menuBtn.setAttribute("aria-expanded", "false");
  }
  menuBtn.addEventListener("click", function () {
    sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
  });
  overlay.addEventListener("click", closeSidebar);

  /* ── Quick actions ── */
  document.querySelectorAll("[data-action]").forEach(function (el) {
    el.addEventListener("click", function () {
      var p = ACTION_PROMPTS[el.dataset.action];
      if (!p) return;
      closeSidebar();
      messageInput.value = p;
      messageInput.dispatchEvent(new Event("input"));
      messageInput.focus();
      var l = messageInput.value.length;
      messageInput.setSelectionRange(l, l);
    });
  });

  /* ── Helpers ── */
  function fmt(d) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  function esc(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ── Markdown renderer ── */
  function md(text) {
    var lines = text.split("\n");
    var html  = "";
    var listType  = null;
    var inCode    = false;
    var codeLines = [];

    function flushList() {
      if (listType) { html += "</" + listType + ">"; listType = null; }
    }
    function flushCode() {
      if (!inCode) return;
      var e = codeLines.map(esc).join("\n");
      html += "<pre><code>" + e + "</code></pre>";
      inCode = false; codeLines = [];
    }
    function inline(t) {
      t = t.replace(/`([^`]+)`/g, function (_, c) { return "<code>" + esc(c) + "</code>"; });
      t = t.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      t = t.replace(/__(.*?)__/g,      "<strong>$1</strong>");
      t = t.replace(/\*(.*?)\*/g,      "<em>$1</em>");
      return t;
    }

    for (var i = 0; i < lines.length; i++) {
      var raw   = lines[i];
      var fence = raw.match(/^```(\w*)$/);
      if (fence) {
        if (!inCode) { flushList(); inCode = true; }
        else          { flushCode(); }
        continue;
      }
      if (inCode) { codeLines.push(raw); continue; }

      var h4 = raw.match(/^####\s+(.*)/);
      var h3 = raw.match(/^###\s+(.*)/);
      var h2 = raw.match(/^##\s+(.*)/);
      var h1 = raw.match(/^#\s+(.*)/);
      if (h4) { flushList(); html += "<h4>" + inline(h4[1]) + "</h4>"; continue; }
      if (h3) { flushList(); html += "<h3>" + inline(h3[1]) + "</h3>"; continue; }
      if (h2) { flushList(); html += "<h2>" + inline(h2[1]) + "</h2>"; continue; }
      if (h1) { flushList(); html += "<h1>" + inline(h1[1]) + "</h1>"; continue; }

      var bq = raw.match(/^>\s?(.*)/);
      if (bq) { flushList(); html += "<blockquote><p>" + inline(bq[1]) + "</p></blockquote>"; continue; }

      var ul = raw.match(/^[-*\u2022]\s+(.*)/);
      if (ul) {
        if (listType === "ol") flushList();
        if (!listType) { html += "<ul>"; listType = "ul"; }
        html += "<li>" + inline(ul[1]) + "</li>";
        continue;
      }
      var ol = raw.match(/^\d+\.\s+(.*)/);
      if (ol) {
        if (listType === "ul") flushList();
        if (!listType) { html += "<ol>"; listType = "ol"; }
        html += "<li>" + inline(ol[1]) + "</li>";
        continue;
      }

      flushList();
      if (raw.trim()) html += "<p>" + inline(raw) + "</p>";
    }
    flushList(); flushCode();
    return html;
  }

  /* ── UI state ── */
  function showChat() {
    welcomeScreen.hidden = true;
    messagesList.hidden  = false;
    clearBtn.hidden      = false;
  }
  function showWelcome() {
    welcomeScreen.hidden = false;
    messagesList.hidden  = true;
    clearBtn.hidden      = true;
  }
  function scrollDown() {
    chatScroll.scrollTo({ top: chatScroll.scrollHeight, behavior: "smooth" });
  }
  function setLoading(s) {
    isLoading             = s;
    messageInput.disabled = s;
    sendBtn.disabled      = s || !messageInput.value.trim();
    sendIcon.classList.toggle("hidden", s);
    sendSpinner.hidden    = !s;
  }

  /* ── Typing indicator ── */
  function addTyping() {
    var el = document.createElement("div");
    el.id        = "typingIndicator";
    el.className = "typing-row";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML =
      '<div class="typing-avatar" aria-hidden="true"><span>\uD83C\uDF93</span></div>' +
      '<div class="typing-bubble">' +
        '<span class="typing-dot"></span>' +
        '<span class="typing-dot"></span>' +
        '<span class="typing-dot"></span>' +
        '<span class="sr-only">Assistant thinking\u2026</span>' +
      '</div>';
    messagesList.appendChild(el);
    scrollDown();
  }
  function removeTyping() {
    var el = document.getElementById("typingIndicator");
    if (el) el.remove();
  }

  /* ── Append bubble ── */
  function appendBubble(role, content, isError) {
    var isUser = role === "user";
    var frag   = bubbleTpl.content.cloneNode(true);
    var row    = frag.querySelector(".bubble-row");

    row.classList.add(isUser ? "bubble-row--user" : "bubble-row--bot");

    var avatar    = row.querySelector(".bubble__avatar");
    var avatarSpan = avatar.querySelector("span");
    var wrap      = row.querySelector(".bubble__content-wrap");
    var bubble    = row.querySelector(".bubble");
    var timeEl    = row.querySelector(".bubble__time");
    var copyBtn   = row.querySelector(".bubble__copy-btn");
    var retryBtn  = row.querySelector(".bubble__retry-btn");
    var meta      = row.querySelector(".bubble__meta");

    if (isUser) {
      avatar.classList.add("bubble__avatar--user");
      avatarSpan.textContent = "\uD83D\uDC64";
      row.appendChild(avatar);
      wrap.classList.add("bubble__content-wrap--user");
      meta.classList.add("bubble__meta--right");
      bubble.classList.add("bubble--user");
      bubble.innerHTML = md(content);
    } else {
      avatarSpan.textContent = "\uD83C\uDF93";
      if (isError) {
        bubble.classList.add("bubble--error");
        bubble.innerHTML =
          '<div class="bubble__error-body">' +
          '<span class="bubble__error-icon" aria-hidden="true">\u26A0</span>' +
          '<div>' + md(content) + '</div>' +
          '</div>';
        retryBtn.hidden = false;
        retryBtn.addEventListener("click", handleRetry);
      } else {
        bubble.classList.add("bubble--bot");
        bubble.innerHTML = md(content);
        copyBtn.hidden = false;
        (function (btn, txt) {
          btn.addEventListener("click", function () {
            navigator.clipboard.writeText(txt).then(function () {
              btn.textContent = "\u2713 Copied";
              setTimeout(function () {
                btn.innerHTML =
                  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
                  '<rect x="9" y="9" width="13" height="13" rx="2"/>' +
                  '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>' +
                  '</svg> Copy';
              }, 1800);
            }).catch(function () { btn.textContent = "Failed"; });
          });
        }(copyBtn, content));
      }
    }

    var now = new Date();
    timeEl.textContent = fmt(now);
    timeEl.setAttribute("datetime", now.toISOString());
    messagesList.appendChild(row);
    scrollDown();
  }

  /* ── Send message ── */
  function sendMessage(text) {
    text = text.trim();
    if (!text || isLoading) return;

    lastUserText = text;
    messages.push({ role: "user", content: text });
    showChat();
    appendBubble("user", text, false);

    messageInput.value        = "";
    messageInput.style.height = "auto";
    sendBtn.disabled          = true;
    charCounter.hidden        = true;
    setLoading(true);
    addTyping();

    // Read CSRF token from meta tag
    var csrfMeta  = document.querySelector("meta[name='csrf-token']");
    var csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    fetch("/chat", {
      method:  "POST",
      headers: {
        "Content-Type":  "application/json",
        "X-CSRF-Token":  csrfToken
      },
      body:    JSON.stringify({ messages: messages })
    })
    .then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    })
    .then(function (r) {
      removeTyping();
      if (!r.ok || r.data.error) {
        appendBubble("assistant", r.data && r.data.error ? r.data.error : "Something went wrong. Please try again.", true);
      } else {
        messages.push({ role: "assistant", content: r.data.reply });
        appendBubble("assistant", r.data.reply, false);
      }
    })
    .catch(function () {
      removeTyping();
      appendBubble("assistant", "Could not reach the server. Check your connection and try again.", true);
    })
    .finally(function () { setLoading(false); });
  }

  /* ── Retry ── */
  function handleRetry() {
    document.querySelectorAll(".bubble--error").forEach(function (b) {
      var r = b.closest(".bubble-row");
      if (r) r.remove();
    });
    while (messages.length && messages[messages.length - 1].role === "assistant") {
      messages.pop();
    }
    if (lastUserText) {
      if (messages.length && messages[messages.length - 1].role === "user") messages.pop();
      var rows = messagesList.querySelectorAll(".bubble-row--user");
      if (rows.length) rows[rows.length - 1].remove();
      sendMessage(lastUserText);
    }
  }

  /* ── Reset ── */
  function resetChat() {
    messages               = [];
    lastUserText           = "";
    messagesList.innerHTML = "";
    showWelcome();
    closeSidebar();
    messageInput.value        = "";
    messageInput.style.height = "auto";
    charCounter.hidden        = true;
  }
  clearBtn.addEventListener("click", resetChat);
  newChatBtn.addEventListener("click", resetChat);

  /* ── Input events ── */
  messageInput.addEventListener("input", function () {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + "px";
    sendBtn.disabled = !messageInput.value.trim() || isLoading;
    var rem = 4000 - messageInput.value.length;
    if (rem < 200) {
      charCounter.textContent = rem + " left";
      charCounter.hidden      = false;
      charCounter.classList.toggle("input-wrap__counter--warn", rem <= 50);
    } else {
      charCounter.hidden = true;
    }
  });

  messageInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      var t = messageInput.value.trim();
      if (t && !isLoading) sendMessage(t);
    }
  });

  sendBtn.addEventListener("click", function () {
    var t = messageInput.value.trim();
    if (t && !isLoading) sendMessage(t);
  });

}());