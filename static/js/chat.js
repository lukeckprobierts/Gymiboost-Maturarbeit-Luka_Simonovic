// chat.js

function ensureMathJax(callback) {
    if (window.mathJaxReady) {
        callback();
    } else {
        const checkInterval = setInterval(() => {
            if (window.mathJaxReady) {
                clearInterval(checkInterval);
                callback();
            }
        }, 100);
    }
}

document.addEventListener('DOMContentLoaded', () => {
  // Ensure Marked.js library is loaded
  if (typeof marked === 'undefined') {
    console.error('Marked.js library is not loaded. Chat functionality will be severely affected.');
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow) {
        chatWindow.innerHTML = "<p style='color:red; text-align:center; margin-top:20px;'>Critical Error: Markdown library not loaded. Please reload.</p>";
    }
    return; // Stop further script execution
  }

  try {
    marked.setOptions({
      breaks: true,
      gfm: true,
      highlight: (code, language) => {
        if (typeof hljs === 'undefined') {
          console.warn('Highlight.js library not loaded. Code highlighting will be plain.');
          return code; // Return raw code if hljs is not available
        }
        try {
            const validLang = hljs.getLanguage(language) ? language : 'plaintext';
            return hljs.highlight(code, { language: validLang }).value;
        } catch (e) {
            console.error('Error during code highlighting:', e);
            return code; // Return raw code on error
        }
      }
    });

    // Custom Marked.js extension to handle MathJax
    const mathJaxExtension = {
      name: 'mathjax',
      level: 'inline',
      start(src) {
        // Simplified check: if src starts with '\' followed by '(' or '['
        if (src.length > 1 && src[0] === '\\') {
          if (src[1] === '(' || src[1] === '[') {
            return 1; // Indicate a potential match for the tokenizer to confirm.
          }
        }
        return undefined; // No potential match here
      },
      tokenizer(src, tokens) {
        const inlineRegex = /^\\\((.+?)\\\)/s;  // Matches \( ... \)
        const displayRegex = /^\\\[(.+?)\\\]/s; // Matches \[ ... \]
        let match;

        // Check display math first as it might be more specific
        if (match = displayRegex.exec(src)) {
          return {
            type: 'mathjax',
            raw: match[0],
            text: match[1], // Content of the math expression
            displayMode: true
          };
        } else if (match = inlineRegex.exec(src)) {
          return {
            type: 'mathjax',
            raw: match[0],
            text: match[1],
            displayMode: false
          };
        }
        return undefined; // No match
      },
      renderer(token) {
        // Return the raw LaTeX string. MathJax will process it in the DOM.
        // DOMPurify will sanitize this. Standard LaTeX characters should be safe.
        return token.raw;
      }
    };

    marked.use(mathJaxExtension);

  } catch (e) {
    console.error("Error initializing Marked.js or its MathJax extension:", e);
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow) {
        chatWindow.innerHTML = "<p style='color:red; text-align:center; margin-top:20px;'>Error setting up Markdown processor. Chat functionality may be impaired.</p>";
    }
    // Depending on the error, you might want to return here to prevent further issues.
  }

  // --- Global current session ID and Event Listeners ---
  const sessionFromUrl = new URLSearchParams(window.location.search).get('session_id');
  window.currentSessionId = sessionFromUrl || document.querySelector('.session-link')?.getAttribute('data-session-id') || '0';

  const sessionLinks = document.querySelectorAll('.session-link');
  sessionLinks.forEach(link => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      sessionLinks.forEach(s => s.classList.remove('active'));
      link.classList.add('active');
      const sessionId = link.getAttribute('data-session-id');
      window.currentSessionId = sessionId;
      loadChatHistory(sessionId);
      if (window.innerWidth <= 768) {
        const chatSidebar = document.getElementById('chatSidebar');
        if (chatSidebar) chatSidebar.classList.remove('active');
      }
    });
  });

  // Initial history load
  if (window.currentSessionId && window.currentSessionId !== '0') {
    loadChatHistory(window.currentSessionId);
    const activeLink = document.querySelector(`.session-link[data-session-id="${window.currentSessionId}"]`);
    if (activeLink) activeLink.classList.add('active');
  } else {
    const firstSessionLink = document.querySelector('.session-link');
    if (firstSessionLink) {
      firstSessionLink.classList.add('active');
      window.currentSessionId = firstSessionLink.getAttribute('data-session-id');
      loadChatHistory(window.currentSessionId);
    } else {
      const chatWindow = document.getElementById('chat-window');
      if (chatWindow) chatWindow.innerHTML = "<p style='text-align:center; margin-top: 20px;'>No chat sessions. Create one to begin!</p>";
    }
  }

  const chatForm = document.getElementById('chat-form');
  if (chatForm) {
    chatForm.addEventListener('submit', handleChatSubmit);
  } else {
    console.error('Chat form #chat-form not found in the DOM.');
  }

  const fileUploadInput = document.getElementById('file-upload');
  if (fileUploadInput) {
    fileUploadInput.addEventListener('change', handleFileUpload);
  } else {
    console.error('File upload input #file-upload not found in the DOM.');
  }

  const flashMessages = document.querySelectorAll('.flash-message, .alert');
  flashMessages.forEach(function(message) {
    setTimeout(function() {
      message.style.transition = 'opacity 0.5s ease';
      message.style.opacity = '0';
      setTimeout(function() {
        message.remove();
      }, 500);
    }, 3000);
  });

  const sidebarToggle = document.getElementById('sidebarToggle');
  const chatSidebar = document.getElementById('chatSidebar');
  if (sidebarToggle && chatSidebar) {
    sidebarToggle.addEventListener('click', () => {
      chatSidebar.classList.toggle('active');
    });
  }

  window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
      if (chatSidebar) chatSidebar.classList.remove('active');
    }
  });
 
  // Handle "New Chat" button click (no name required)
  const newChatBtn = document.getElementById('new-chat-btn');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', async () => {
      try {
        const resp = await fetch('/create_session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        const data = await resp.json();
        if (data && data.session_id) {
          const sessionId = data.session_id.toString();
          window.currentSessionId = sessionId;

          // Update active session in sidebar and add new item
          const sessionList = document.querySelector('.session-list');
          if (sessionList) {
            document.querySelectorAll('.session-link').forEach(s => s.classList.remove('active'));
            const li = document.createElement('li');
            li.className = 'session-item';
            const defaultName = 'New Chat';
            li.innerHTML = `
              <a href="#" class="session-link active" data-session-id="${sessionId}">${defaultName}</a>
              <form action="/delete_session/${sessionId}" method="POST">
                <button type="submit" class="delete-button">&times;</button>
              </form>
            `;
            sessionList.appendChild(li);

            // Click handler for the new session link
            li.querySelector('.session-link').addEventListener('click', function(e) {
              e.preventDefault();
              document.querySelectorAll('.session-link').forEach(s => s.classList.remove('active'));
              this.classList.add('active');
              window.currentSessionId = sessionId;
              loadChatHistory(sessionId);
              if (window.innerWidth <= 768) {
                const chatSidebar = document.getElementById('chatSidebar');
                if (chatSidebar) chatSidebar.classList.remove('active');
              }
            });
          }

          // Load blank history and update URL
          loadChatHistory(sessionId);
          if (data.redirect_url) {
            window.history.pushState({}, '', data.redirect_url);
          }

          // Close sidebar on mobile for better UX
          if (window.innerWidth <= 768) {
            const chatSidebar = document.getElementById('chatSidebar');
            if (chatSidebar) chatSidebar.classList.remove('active');
          }
        }
      } catch (error) {
        console.error('Error creating new session:', error);
      }
    });
  }
}); // End of DOMContentLoaded


// --- Core Chat Functions ---

function loadChatHistory(sessionId) {
  if (!sessionId || sessionId === '0') {
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow) chatWindow.innerHTML = "<p style='text-align:center; margin-top: 20px;'>Select a chat or create a new one.</p>";
    return;
  }
  fetch(`/chat_history/${sessionId}`)
    .then(response => {
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return response.json();
    })
    .then(history => {
      const chatWindow = document.getElementById('chat-window');
      if (!chatWindow) { console.error("Chat window not found for history."); return; }
      chatWindow.innerHTML = "";
      history.forEach(msg => appendMessage(msg.content, !msg.is_user));
      chatWindow.scrollTop = chatWindow.scrollHeight;
    })
    .catch(error => {
      console.error('Error loading chat history for session ' + sessionId + ':', error);
      const chatWindow = document.getElementById('chat-window');
      if (chatWindow) chatWindow.innerHTML = `<p style='color: red; text-align:center; margin-top: 20px;'>Error loading history. Please try again.</p>`;
    });
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const messageInput = document.getElementById('message-input');
  if (!messageInput) { console.error("Message input not found."); return; }
  const userMessage = messageInput.value.trim();

  if (!userMessage) return;

  // If no session selected yet, auto-create one
  if (!window.currentSessionId || window.currentSessionId === '0') {
    try {
      const resp = await fetch('/create_session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await resp.json();
      if (data && data.session_id) {
        const sessionId = data.session_id.toString();
        window.currentSessionId = sessionId;

        // Add to sidebar and set active
        const sessionList = document.querySelector('.session-list');
        if (sessionList) {
          document.querySelectorAll('.session-link').forEach(s => s.classList.remove('active'));
          const li = document.createElement('li');
          li.className = 'session-item';
          const defaultName = 'New Chat';
          li.innerHTML = `
            <a href="#" class="session-link active" data-session-id="${sessionId}">${defaultName}</a>
            <form action="/delete_session/${sessionId}" method="POST">
              <button type="submit" class="delete-button">&times;</button>
            </form>
          `;
          sessionList.appendChild(li);
          li.querySelector('.session-link').addEventListener('click', function(e) {
            e.preventDefault();
            document.querySelectorAll('.session-link').forEach(s => s.classList.remove('active'));
            this.classList.add('active');
            window.currentSessionId = sessionId;
            loadChatHistory(sessionId);
          });
        }

        // Load blank conversation and update URL
        loadChatHistory(sessionId);
        if (data.redirect_url) {
          window.history.pushState({}, '', data.redirect_url);
        }
      } else {
        console.error('Failed to create a new chat session.');
        return;
      }
    } catch (e) {
      console.error('Error creating new session:', e);
      return;
    }
  }

  messageInput.value = "";
  appendMessage(userMessage, false);

  const submitBtn = document.getElementById('submit-btn');
  const thinkingLoader = document.getElementById('thinking-loader');

  if (submitBtn) submitBtn.disabled = true;
  if (thinkingLoader) thinkingLoader.style.display = 'block';

  // Start polling for auto-generated title if current name is still a default
  (function startNamePolling() {
    try {
      const defaultNames = new Set(['New Chat', 'Neuer Chat', 'Default Chat']);
      const link = document.querySelector(`.session-link[data-session-id="${window.currentSessionId}"]`);
      const initialName = (link && link.textContent) ? link.textContent.trim() : '';
      if (initialName && !defaultNames.has(initialName)) return; // already named

      let attempts = 0;
      const tid = setInterval(async () => {
        attempts++;
        try {
          const r = await fetch(`/api/session/${window.currentSessionId}`);
          if (r.ok) {
            const d = await r.json();
            const nm = (d.name || '').trim();
            if (nm && !defaultNames.has(nm)) {
              const l = document.querySelector(`.session-link[data-session-id="${window.currentSessionId}"]`);
              if (l) l.textContent = nm;
              clearInterval(tid);
            }
          }
        } catch (e) {
          // ignore transient errors
        }
        if (attempts >= 20) clearInterval(tid); // ~20s max
      }, 1000);
    } catch (e) {
      // ignore polling errors
    }
  })();

  fetch('/send_message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: userMessage, session_id: window.currentSessionId })
  })
  .then(response => {
    if (thinkingLoader) thinkingLoader.style.display = 'none';
    if (!response.ok) {
      response.json().then(err => {
        appendMessage(`Server error: ${err.error || response.statusText}`, true);
      }).catch(() => {
        appendMessage(`Server error: ${response.statusText}`, true);
      });
      if (submitBtn) submitBtn.disabled = false;
      throw new Error(`Server error: ${response.status}`);
    }
    return streamBotResponse(response.body);
  })
  .catch(error => {
    console.error('Error sending message:', error);
    if (thinkingLoader) thinkingLoader.style.display = 'none';
    if (submitBtn) submitBtn.disabled = false;
    appendMessage("Failed to get a response. Please check your connection or try again.", true);
  });
}

function streamBotResponse(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let botMessageAccumulator = "";
  let tempBotMessageElement = null;

  function read() {
    reader.read().then(({ done, value }) => {
      if (done) {
        finalizeBotMessage(botMessageAccumulator, tempBotMessageElement);
        const submitBtn = document.getElementById('submit-btn');
        if (submitBtn) submitBtn.disabled = false;
        return;
      }
      botMessageAccumulator += decoder.decode(value, { stream: true });
      tempBotMessageElement = updateTempBotMessage(botMessageAccumulator, tempBotMessageElement);
      read();
    }).catch(error => {
      console.error('Error streaming response:', error);
      if (tempBotMessageElement && tempBotMessageElement.parentElement) tempBotMessageElement.remove();
      appendMessage("Error receiving stream. Please try again.", true);
      const submitBtn = document.getElementById('submit-btn');
      if (submitBtn) submitBtn.disabled = false;
    });
  }
  read();
}

function appendMessage(text, isBot) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) { console.error("Cannot append message: Chat window not found."); return; }

  if (typeof DOMPurify === 'undefined') {
    console.error('DOMPurify is not loaded. Cannot safely append message.');
    // Display a simplified, un-sanitized message or an error.
    // This is a fallback - DOMPurify should be loaded.
    const errorDiv = document.createElement('div');
    errorDiv.textContent = isBot ? "Bot: [Content Error]" : "User: [Content Error]";
    errorDiv.style.color = "red";
    chatWindow.appendChild(errorDiv);
    return;
  }
  
  // Ensure 'marked' is available before trying to use it.
  // This check is more critical if the initial DOMContentLoaded check somehow passed
  // but 'marked' became undefined later, or for robustness.
  if (isBot && typeof marked === 'undefined') {
      console.error('Marked.js is not available for bot message. Displaying raw text.');
      const rawBotMsgDiv = document.createElement('div');
      rawBotMsgDiv.className = 'message bot';
      rawBotMsgDiv.innerHTML = `<div class="message-content">${DOMPurify.sanitize(text)}</div>
                                <div class="message-time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>`;
      chatWindow.appendChild(rawBotMsgDiv);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      return;
  }


  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${isBot ? 'bot' : 'user'}`;

  let htmlContent;
  if (isBot) {
    // First protect LaTeX blocks from Markdown processing
    const protected = text.replace(/(\\\(.*?\\\)|\\\[.*?\\\])/gs, 
        match => `%%MATHJAX:${btoa(match)}%%`);
    
    // Process Markdown
    const dirty = marked.parse(protected);
    const clean = DOMPurify.sanitize(dirty, {
        ADD_TAGS: ['mjx-container'],
        ADD_ATTR: ['jax', 'display']
    });
    
    // Restore LaTeX blocks
    htmlContent = clean.replace(/%%MATHJAX:(.*?)%%/gs, 
        (_, encoded) => atob(encoded));
  } else {
    htmlContent = DOMPurify.sanitize(text);
  }

  messageDiv.innerHTML = `
    <div class="message-content math-container">${htmlContent}</div>
    <div class="message-time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
  `;

  chatWindow.appendChild(messageDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  if (isBot && (text.includes('\\(') || text.includes('\\['))) {
    ensureMathJax(() => {
      MathJax.typesetPromise([messageDiv])
        .catch(err => console.error('MathJax typeset error:', err));
    });
  }

  if (isBot && typeof hljs !== 'undefined') {
    messageDiv.querySelectorAll('pre code').forEach(block => {
      try {
        hljs.highlightElement(block);
      } catch (e) {
        console.error('Error highlighting block:', e, block);
      }
    });
  }
}

function updateTempBotMessage(text, existingElement) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return existingElement;

  if (typeof DOMPurify === 'undefined' || (typeof marked === 'undefined')) {
    console.error('DOMPurify or Marked not loaded. Cannot update temp bot message.');
    return existingElement;
  }

  let tempEl = existingElement;
  if (!tempEl || !tempEl.parentElement) {
    tempEl = document.createElement('div');
    tempEl.id = 'temp-bot-message';
    tempEl.className = 'message bot';
    chatWindow.appendChild(tempEl);
  }

  // Process content immediately without waiting for complete messages
  const protected = text.replace(/(\\\(.*?\\\)|\\\[.*?\\\])/gs, 
      match => `%%MATHJAX:${btoa(match)}%%`);
  
  const dirty = marked.parse(protected);
  const clean = DOMPurify.sanitize(dirty, {
      ADD_TAGS: ['mjx-container'],
      ADD_ATTR: ['jax', 'display']
  });
  
  const withMath = clean.replace(/%%MATHJAX:(.*?)%%/gs, 
      (_, encoded) => atob(encoded));
  
  tempEl.innerHTML = `
    <div class="message-content math-container">${withMath}</div>
    <div class="message-time">Typing...</div>
  `;

  // Force immediate MathJax processing
  if (window.MathJax) {
    try {
      // Clear any pending typesetting
      MathJax.typesetClear();
      
      // Process math immediately with aggressive settings
      MathJax.startup.promise = MathJax.startup.promise
        .then(() => MathJax.typesetPromise([tempEl]))
        .then(() => {
          // Schedule a re-render to catch any missed math
          setTimeout(() => MathJax.typesetPromise([tempEl]).catch(() => {}), 100);
        })
        .catch(err => console.error('MathJax immediate render failed:', err));
    } catch (e) {
      console.error('MathJax processing error:', e);
    }
  }

  // Highlight code if available
  if (typeof hljs !== 'undefined') {
    tempEl.querySelectorAll('pre code').forEach(block => {
        try {
            hljs.highlightElement(block);
        } catch(e) {
            console.error('Error highlighting temp block:', e, block);
        }
    });
  }

  chatWindow.scrollTop = chatWindow.scrollHeight;
  return tempEl;
}

function finalizeBotMessage(finalText, tempMessageElement) {
  if (tempMessageElement && tempMessageElement.parentElement) {
    tempMessageElement.remove();
  }
  appendMessage(finalText, true);
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Check file type
    if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
        alert('Please upload a PDF file only.');
        event.target.value = '';
        return;
    }

    // Show upload progress
    const overlay = document.createElement('div');
    overlay.className = 'upload-overlay';
    overlay.innerHTML = `
        <div class="upload-progress">
            <div>Processing ${file.name}...</div>
            <div class="progress-bar"><div class="progress-bar-fill" style="width: 0%;"></div></div>
        </div>
    `;
    document.body.appendChild(overlay);
    const progressBarFill = overlay.querySelector('.progress-bar-fill');

    try {
        // Read file as text (for plain text) or as ArrayBuffer (for PDF)
        const fileReader = new FileReader();
        
        const readPromise = new Promise((resolve, reject) => {
            fileReader.onload = (e) => resolve(e.target.result);
            fileReader.onerror = (e) => reject(new Error('File reading failed'));
            
            if (progressBarFill) progressBarFill.style.width = '30%';
            if (file.type.includes('pdf')) {
                fileReader.readAsArrayBuffer(file);
            } else {
                fileReader.readAsText(file);
            }
        });

        const fileContent = await readPromise;
        if (progressBarFill) progressBarFill.style.width = '70%';

        // Send to server for processing
        const formData = new FormData();
        formData.append('file', file);
        formData.append('session_id', window.currentSessionId);
        
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (progressBarFill) progressBarFill.style.width = '100%';
        
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        
        // Show success notification
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); 
            background: var(--primary, #4CAF50); color: white; padding: 12px 24px; 
            border-radius: 8px; z-index: 1001; font-size: 0.9em; box-shadow: var(--shadow, 0 2px 8px rgba(0,0,0,0.1));
            text-align: center;
        `;
        notification.innerHTML = `📎 ${DOMPurify.sanitize(file.name)} loaded.<br>It will be used as context for your next message.`;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 4000);

    } catch (error) {
        console.error('File processing error:', error);
        if (progressBarFill) {
            progressBarFill.style.width = '100%';
            progressBarFill.style.backgroundColor = 'red';
        }
        alert(`Error processing file: ${error.message}`);
    } finally {
        setTimeout(() => overlay.remove(), 1500);
        event.target.value = '';
    }
}