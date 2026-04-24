(function () {
  /* ---------- CONFIG ---------- */
  const BACKEND_URL = "https://crevoxega-tzrt.onrender.com/chat";

  const scriptTag = document.currentScript;
  const CLIENT_TOKEN = scriptTag.getAttribute("data-client");

  if (!CLIENT_TOKEN) {
    console.error("Chat widget: client token missing");
    return;
  }

  /* ---------- CONSTANTS ---------- */
  const MAX_MESSAGE_LENGTH = 5000;
  const REQUEST_TIMEOUT = 30000; // 30 seconds

  /* ---------- VISITOR ID ---------- */
  let visitorId = localStorage.getItem("chat_visitor_id");
  if (!visitorId) {
    visitorId = "vs_" + Math.random().toString(36).slice(2);
    localStorage.setItem("chat_visitor_id", visitorId);
  }

  /* ---------- UI ---------- */
  const widget = document.createElement("div");
  widget.innerHTML = `
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

      #chat-bubble {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 56px;
        height: 56px;
        border-radius: 28px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
        z-index: 9999;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border: none;
        touch-action: manipulation;
        -webkit-tap-highlight-color: transparent;
      }

      #chat-bubble svg {
        width: 28px;
        height: 28px;
        fill: white;
        pointer-events: none;
      }

      #chat-bubble:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(102, 126, 234, 0.5);
      }

      #chat-bubble:active {
        transform: scale(0.95);
      }

      #chat-bubble.active {
        transform: scale(0.95);
      }

      #chat-box {
        position: fixed;
        bottom: 90px;
        right: 20px;
        width: 400px;
        height: 600px;
        max-height: calc(100vh - 110px);
        background: #ffffff;
        border-radius: 12px;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05), 0 20px 50px rgba(0, 0, 0, 0.12);
        display: none;
        flex-direction: column;
        z-index: 9999;
        overflow: hidden;
        animation: slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }

      @keyframes slideUp {
        from {
          opacity: 0;
          transform: translateY(10px) scale(0.98);
        }
        to {
          opacity: 1;
          transform: translateY(0) scale(1);
        }
      }

      @media (max-width: 600px) {
        #chat-box {
          right: 0;
          left: 0;
          bottom: 0;
          width: 100%;
          height: 100%;
          max-height: 100%;
          border-radius: 0;
        }

        #chat-bubble {
          bottom: 16px;
          right: 16px;
          width: 60px;
          height: 60px;
          border-radius: 30px;
        }

        #chat-bubble svg {
          width: 30px;
          height: 30px;
        }
      }

      #chat-header {
        padding: 16px 20px;
        background: #ffffff;
        border-bottom: 1px solid #f0f0f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-shrink: 0;
      }

      #chat-title h3 {
        margin: 0;
        font-size: 15px;
        font-weight: 600;
        color: #000;
        letter-spacing: -0.01em;
      }

      #chat-title span {
        font-size: 13px;
        color: #666;
        margin-top: 2px;
        display: block;
      }

      #chat-close {
        background: none;
        border: none;
        color: #666;
        font-size: 20px;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 6px;
        transition: all 0.2s;
        line-height: 1;
        touch-action: manipulation;
        -webkit-tap-highlight-color: transparent;
      }

      #chat-close:hover {
        background: #f5f5f5;
        color: #000;
      }

      #chat-messages {
        padding: 20px;
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
        background: #fafafa;
        display: flex;
        flex-direction: column;
        gap: 16px;
        -webkit-overflow-scrolling: touch;
      }

      #chat-messages::-webkit-scrollbar {
        width: 4px;
      }

      #chat-messages::-webkit-scrollbar-thumb {
        background: #d0d0d0;
        border-radius: 2px;
      }

      #chat-messages::-webkit-scrollbar-track {
        background: transparent;
      }

      .msg {
        display: flex;
        animation: fadeIn 0.3s ease-out;
      }

      @keyframes fadeIn {
        from {
          opacity: 0;
          transform: translateY(8px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      .msg-bubble {
        max-width: 80%;
        padding: 10px 14px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.5;
        word-wrap: break-word;
        word-break: break-word;
        white-space: pre-wrap;
      }

      .user {
        justify-content: flex-end;
      }

      .user .msg-bubble {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: #fff;
        border-bottom-right-radius: 4px;
      }

      .bot {
        justify-content: flex-start;
      }

      .bot .msg-bubble {
        background: #fff;
        color: #1a1a1a;
        border-bottom-left-radius: 4px;
        border: 1px solid #e8e8e8;
      }

      .typing-container {
        display: flex;
        justify-content: flex-start;
      }

      .typing-bubble {
        background: #fff;
        border: 1px solid #e8e8e8;
        padding: 14px 16px;
        border-radius: 16px;
        border-bottom-left-radius: 4px;
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .typing-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #999;
        animation: typingBounce 1.4s infinite ease-in-out;
      }

      .typing-dot:nth-child(1) {
        animation-delay: 0s;
      }

      .typing-dot:nth-child(2) {
        animation-delay: 0.2s;
      }

      .typing-dot:nth-child(3) {
        animation-delay: 0.4s;
      }

      @keyframes typingBounce {
        0%, 60%, 100% {
          transform: translateY(0);
          opacity: 0.7;
        }
        30% {
          transform: translateY(-8px);
          opacity: 1;
        }
      }

      #chat-input-container {
        padding: 16px;
        background: #fff;
        border-top: 1px solid #f0f0f0;
        flex-shrink: 0;
      }

      #chat-input {
        display: flex;
        gap: 8px;
        align-items: center;
        background: #f5f5f5;
        border-radius: 22px;
        padding: 6px 6px 6px 16px;
        transition: background 0.2s;
      }

      #chat-input:focus-within {
        background: #ebebeb;
      }

      #chat-input input {
        flex: 1;
        padding: 8px 0;
        border: none;
        background: none;
        outline: none;
        font-size: 14px;
        color: #000;
        font-family: inherit;
        -webkit-appearance: none;
        touch-action: manipulation;
      }

      #chat-input input::placeholder {
        color: #999;
      }

      #chat-input button {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        border: none;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: #fff;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        transition: all 0.2s;
        flex-shrink: 0;
        touch-action: manipulation;
        -webkit-tap-highlight-color: transparent;
      }

      #chat-input button:hover:not(:disabled) {
        transform: scale(1.05);
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
      }

      #chat-input button:active:not(:disabled) {
        transform: scale(0.95);
      }

      #chat-input button:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }

      .welcome-message {
        text-align: center;
        padding: 60px 30px;
        color: #666;
      }

      .welcome-message h4 {
        margin: 0 0 8px 0;
        color: #000;
        font-size: 18px;
        font-weight: 600;
        letter-spacing: -0.02em;
      }

      .welcome-message p {
        margin: 0;
        font-size: 14px;
        line-height: 1.5;
      }

      .error-message {
        background: #fee;
        color: #c33;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 13px;
        text-align: center;
        margin: 0 20px;
      }

      /* Smooth text reveal animation for bot messages */
      @keyframes textReveal {
        from {
          opacity: 0;
        }
        to {
          opacity: 1;
        }
      }

      .bot .msg-bubble.revealing {
        animation: textReveal 0.2s ease-out;
      }

      /* Mobile keyboard handling */
      @supports (height: 100dvh) {
        @media (max-width: 600px) {
          #chat-box {
            height: 100dvh;
          }
        }
      }
    </style>

    <div id="chat-bubble">
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2C6.48 2 2 6.48 2 12c0 1.54.36 3 .97 4.29L2 22l5.71-.97C9 21.64 10.46 22 12 22c5.52 0 10-4.48 10-10S17.52 2 12 2zm0 18c-1.38 0-2.68-.28-3.87-.78l-.28-.12-2.89.49.49-2.89-.12-.28C4.78 14.68 4.5 13.38 4.5 12c0-4.14 3.36-7.5 7.5-7.5s7.5 3.36 7.5 7.5-3.36 7.5-7.5 7.5z"/>
        <circle cx="8" cy="12" r="1.5"/>
        <circle cx="12" cy="12" r="1.5"/>
        <circle cx="16" cy="12" r="1.5"/>
      </svg>
    </div>

    <div id="chat-box">
      <div id="chat-header">
        <div id="chat-title">
          <h3>Chat</h3>
          <span>Trained on our business</span>
        </div>
        <button id="chat-close">✕</button>
      </div>
      <div id="chat-messages">
        <div class="welcome-message">
          <h4>👋 Hey! Excited to see you here</h4>
          <p>I'm powered by everything we know about our business. Ask me anything—let's discover how I can help you today!</p>
        </div>
      </div>
      <div id="chat-input-container">
        <div id="chat-input">
          <input type="text" placeholder="Type a message..." autocomplete="off" maxlength="${MAX_MESSAGE_LENGTH}" />
          <button>↑</button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(widget);

  const bubble = document.getElementById("chat-bubble");
  const box = document.getElementById("chat-box");
  const messages = document.getElementById("chat-messages");
  const input = document.querySelector("#chat-input input");
  const sendBtn = document.querySelector("#chat-input button");
  const closeBtn = document.getElementById("chat-close");

  // Track if user is manually scrolling
  let isUserScrolling = false;
  let scrollTimeout = null;
  let isTyping = false;

  // Prevent double-tap zoom on mobile
  let lastTouchEnd = 0;
  document.addEventListener('touchend', function (event) {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
      event.preventDefault();
    }
    lastTouchEnd = now;
  }, false);

  bubble.onclick = () => {
    const isOpen = box.style.display === "flex";
    box.style.display = isOpen ? "none" : "flex";
    bubble.classList.toggle("active", !isOpen);
    if (!isOpen) {
      setTimeout(() => input.focus(), 100);
    }
  };

  closeBtn.onclick = () => {
    box.style.display = "none";
    bubble.classList.remove("active");
  };

  // Detect user scrolling
  messages.addEventListener('scroll', () => {
    if (isTyping) {
      const isAtBottom = messages.scrollHeight - messages.scrollTop <= messages.clientHeight + 50;
      
      if (!isAtBottom) {
        isUserScrolling = true;
      } else {
        isUserScrolling = false;
      }
      
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        isUserScrolling = false;
      }, 1000);
    }
  });

  function showError(message) {
    const errorDiv = document.createElement("div");
    errorDiv.className = "error-message";
    errorDiv.textContent = message;
    messages.appendChild(errorDiv);
    
    setTimeout(() => {
      errorDiv.remove();
    }, 5000);
    
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, type, animate = false) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "msg " + type;
    
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    
    if (animate && type === "bot") {
      bubble.classList.add("revealing");
      isTyping = true;
      isUserScrolling = false;
      
      let i = 0;
      bubble.textContent = "";
      
      const typeNextChar = () => {
        if (i < text.length) {
          bubble.textContent += text.charAt(i);
          i++;
          
          // Only auto-scroll if user hasn't manually scrolled up
          if (!isUserScrolling) {
            messages.scrollTop = messages.scrollHeight;
          }
          
          // Variable speed: 1-9ms random interval for human-like typing
          const baseSpeed = Math.floor(Math.random() * 9) + 1;
          
          // Add extra delay for punctuation and spaces (more realistic)
          const char = text.charAt(i - 1);
          let delay = baseSpeed;
          
          if (char === '.' || char === '!' || char === '?') {
            delay += Math.floor(Math.random() * 150) + 100; // 100-250ms pause
          } else if (char === ',' || char === ';') {
            delay += Math.floor(Math.random() * 50) + 30; // 30-80ms pause
          } else if (char === ' ') {
            delay += Math.floor(Math.random() * 20) + 10; // 10-30ms pause
          }
          
          setTimeout(typeNextChar, delay);
        } else {
          isTyping = false;
          isUserScrolling = false;
        }
      };
      
      typeNextChar();
    } else {
      bubble.textContent = text;
    }
    
    msgDiv.appendChild(bubble);
    messages.appendChild(msgDiv);
    messages.scrollTop = messages.scrollHeight;
  }

  function showTypingIndicator() {
    const typing = document.createElement("div");
    typing.className = "typing-container";
    typing.id = "typing-indicator";
    typing.innerHTML = `
      <div class="typing-bubble">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    `;
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;
  }

  function removeTypingIndicator() {
    const typing = document.getElementById("typing-indicator");
    if (typing) typing.remove();
  }

  async function sendMessage() {
    const text = input.value.trim();
    
    if (!text) return;
    
    if (text.length > MAX_MESSAGE_LENGTH) {
      showError(`Message too long. Maximum ${MAX_MESSAGE_LENGTH} characters.`);
      return;
    }

    addMessage(text, "user");
    input.value = "";
    sendBtn.disabled = true;

    showTypingIndicator();

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

      const res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          client_token: CLIENT_TOKEN,
          visitor_id: visitorId,
          message: text
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        throw new Error("Invalid response format");
      }

      const data = await res.json();
      
      if (!data || typeof data.reply !== 'string') {
        throw new Error("Invalid response structure");
      }
      
      await new Promise(resolve => setTimeout(resolve, 600));
      
      removeTypingIndicator();
      addMessage(data.reply, "bot", true);
      
    } catch (error) {
      removeTypingIndicator();
      
      if (error.name === 'AbortError') {
        showError("Request timed out. Please try again.");
      } else {
        console.error('Chat error:', error);
        showError("Unable to send message. Please try again.");
      }
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.onclick = sendMessage;
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Handle mobile keyboard visibility
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      if (box.style.display === "flex") {
        setTimeout(() => {
          messages.scrollTop = messages.scrollHeight;
        }, 100);
      }
    });
  }

})();
