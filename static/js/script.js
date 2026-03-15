// ==================================================================================
//  FILE: static/js/script.js
//  DESCRIPTION: Main Frontend Logic (Updated with Global Colors & Image Gen Options)
// ==================================================================================

let currentSessionId = localStorage.getItem('session_id') || null;
let currentMode = 'chat';
let isRecording = false;
let recognition = null;
let currentFile = null;
let lastMessageDate = null; 

// Helper function date calculate karne ke liye
function getDateLabel(timestamp) {
    let ts = timestamp;
    // Backend ke time ko strict UTC maan kar IST mein badalne ka logic
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) {
        ts += 'Z'; 
    }
    
    const date = ts ? new Date(ts) : new Date();
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// Global Variables for Image Settings
let imageSettings = {
    quality: 'fast', // 'fast' or 'pro'
    style: 'painting' // 'painting' or 'realistic'
};

document.addEventListener('DOMContentLoaded', () => {
    // Sabse pehle Global Preferences load hongi (Colors, Fonts, Theme)
    loadGlobalPreferences();

    loadHistory();
    loadProfile();
    
    if (!currentSessionId) {
        createNewChat();
    } else {
        loadChat(currentSessionId);
    }
});

// --- THEME & VANTA CONFIG (Dual Effects with Custom Colors) ---
let vantaEffect = null;

function initVanta() {
    if (!window.VANTA) return;
    
    const isLight = document.body.classList.contains('light-mode');
    
    if (vantaEffect) {
        vantaEffect.destroy();
    }

    if (isLight) {
        // LIGHT MODE = RINGS (Remains default as per user request)
        vantaEffect = VANTA.RINGS({
            el: "#vanta-bg",
            mouseControls: true, 
            touchControls: true, 
            gyroControls: false,
            minHeight: 200.00, 
            minWidth: 200.00,
            scale: 1.00, 
            scaleMobile: 1.00,
            backgroundColor: 0xe0e7ff, 
            color: 0x2563eb 
        });
    } else {
        // DARK MODE = HALO (With Custom Selected Color! ✨)
        let pColor = localStorage.getItem('primary_color') || '#00E5FF';
        let hexColor = parseInt(pColor.replace('#', '0x'), 16); 

        vantaEffect = VANTA.HALO({
            el: "#vanta-bg",
            mouseControls: true, 
            touchControls: true, 
            gyroControls: false,
            minHeight: 200.00, 
            minWidth: 200.00,
            baseColor: hexColor, // ✨ Yahan color apply hoga
            backgroundColor: 0x000000, 
            size: 0.8, 
            amplitudeFactor: 1.0,
            xOffset: 0.0, 
            yOffset: 0.0  
        });
    }
}

function toggleTheme() {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    initVanta();
}

// --- CHAT FUNCTIONS ---

async function createNewChat() {
    const res = await fetch('/api/new_chat');
    const data = await res.json();
    currentSessionId = data.session_id;
    localStorage.setItem('session_id', currentSessionId);
    
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-80 text-center animate-fade-in px-4">
            <img src="/static/images/logo.png" class="w-20 h-20 md:w-24 md:h-24 rounded-full mb-4 md:mb-6 shadow-[0_0_30px_rgba(0,229,255,0.5)] animate-pulse">
            <h2 class="text-2xl md:text-3xl font-bold mb-2">Namaste!</h2>
            <p class="text-sm md:text-base text-gray-400">Main taiyaar hu. Aaj kya create karein?</p>
        </div>
    `;
    loadHistory();
}

async function loadChat(sid) {
    currentSessionId = sid;
    localStorage.setItem('session_id', sid);
    const res = await fetch(`/api/chat/${sid}`);
    const data = await res.json();
    
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = '';
    lastMessageDate = null; 
    
    data.messages.forEach(msg => {
        appendMessage(msg.role === 'user' ? 'user' : 'assistant', msg.content, msg.timestamp);
    });
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const msg = input.value.trim();
    if (!msg && !currentFile) return;

    const welcome = document.getElementById('welcome-screen');
    if (welcome) welcome.remove();

    appendMessage('user', msg, null);

    playSfx('send');
    
    input.value = '';
    
    const chatBox = document.getElementById('chat-box');
    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'msg-ai';
    thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatBox.appendChild(thinkingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const payload = {
            message: msg,
            session_id: currentSessionId,
            mode: currentMode,
            file_data: currentFile ? currentFile.data : null,
            file_type: currentFile ? currentFile.type : null,
            image_quality: imageSettings.quality,
            image_style: imageSettings.style
        };

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        document.getElementById(thinkingId).remove();
        currentFile = null; 

        // Rate limit hit — upgrade modal dikhao
        if (res.status === 429 || data.limit_reached) {
            appendMessage('assistant', data.reply, null);
            if (data.upgrade_needed) {
                setTimeout(() => { openUpgradeModal(); }, 600);
            }
            if (typeof updateUsageBar === 'function' && data.limit !== undefined) {
                updateUsageBar(0, data.limit, 0, data.tool_limit || 10);
            }
            return;
        }

        appendMessage('assistant', data.reply, null);
        loadHistory();

        // Usage bar update karo
        if (typeof updateUsageBar === 'function' && data.remaining !== undefined) {
            updateUsageBar(data.remaining, data.limit, data.tool_remaining, data.tool_limit);
        }

        // Agar voice true hai preferences mein, toh bolegi
        let voicePref = document.getElementById('voice-toggle');
        if ((voicePref && voicePref.checked) || localStorage.getItem('voice_reply') === 'true') {
            playAudio(data.reply);
        }
    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not connect to Ethrix.</span>';
    }
}

function appendMessage(role, text, timestamp = null) {
    const chatBox = document.getElementById('chat-box');
    
    let ts = timestamp;
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) { 
        ts += 'Z'; 
    }
    const msgDateObj = ts ? new Date(ts) : new Date();
    
    const displayTime = msgDateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    const dateLabel = getDateLabel(ts);

    if (lastMessageDate !== dateLabel) {
        const divider = document.createElement('div');
        divider.className = 'date-divider';
        divider.innerText = dateLabel;
        chatBox.appendChild(divider);
        lastMessageDate = dateLabel;
    }

    const msgId = 'msg_' + Date.now() + Math.floor(Math.random() * 1000);
    const div = document.createElement('div');
    div.className = role === 'user' ? 'msg-user' : 'msg-ai';
    
    let content = text;
    if (role === 'assistant') { 
        content = marked.parse(text); 
    }
    let actionHTML = '';
    
    if (role === 'assistant') {
        actionHTML = `
            <div class="msg-meta">
                <span class="msg-time">${displayTime}</span>
                <div class="msg-actions">
                    <button class="action-btn" onclick="regenerateMessage('${msgId}')" title="Regenerate"><i class="fas fa-sync-alt text-[12px]"></i></button>
                    <button class="action-btn" onclick="copyText('${msgId}')" title="Copy"><i class="fas fa-copy text-[12px]"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'good')" title="Good"><i class="fas fa-thumbs-up text-[12px]"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'bad')" title="Bad"><i class="fas fa-thumbs-down text-[12px]"></i></button>
                    <button class="action-btn" onclick="shareResponse('${msgId}')" title="Share"><i class="fas fa-share-alt text-[12px]"></i></button>
                </div>
            </div>
        `;
    } else {
        actionHTML = `
            <div class="msg-meta" style="border-top:none; justify-content:flex-end; gap: 8px;">
                <button class="action-btn" onclick="editMyMessage('${msgId}')" title="Edit Message"><i class="fas fa-pen text-[11px]"></i></button>
                <button class="action-btn" onclick="copyText('${msgId}')" title="Copy Message"><i class="fas fa-copy text-[11px]"></i></button>
                <span class="msg-time">${displayTime}</span>
            </div>
        `;
    }
    
    // ⚡ Fast Mode & Typing Effect Logic
    if (role === 'assistant' && window.ethrixPrefs && !window.ethrixPrefs.fast_mode) {
        // Natural Typing jaisa smooth reveal effect
        div.innerHTML = `<div id="${msgId}_content" style="opacity:0; transform: translateY(10px); transition: all 0.4s ease-out;">${content}</div> ${actionHTML}`;
        chatBox.appendChild(div);
        playSfx('pop'); // AI ka message aaya toh 'pop' sound

        setTimeout(() => {
            const contentDiv = document.getElementById(`${msgId}_content`);
            if (contentDiv) {
                contentDiv.style.opacity = '1';
                contentDiv.style.transform = 'translateY(0)';
            }
        }, 50);
    } else {
        // Fast Mode (Instant show)
        div.innerHTML = `<div id="${msgId}_content">${content}</div> ${actionHTML}`;
        chatBox.appendChild(div);
        if(role === 'assistant') playSfx('pop');
    }

    // 📜 Auto-Scroll Logic
    if (!window.ethrixPrefs || window.ethrixPrefs.auto_scroll) {
        chatBox.scrollTop = chatBox.scrollHeight; // Auto-scroll ON
    }

    // Code blocks ke liye syntax highlight + copy button add karo
    if (role === 'assistant') {
        div.querySelectorAll('pre code').forEach((block) => {
            if (window.hljs) hljs.highlightElement(block);
            // Copy button add karo har code block par
            const pre = block.parentElement;
            if (pre && !pre.querySelector('.copy-btn')) {
                pre.style.position = 'relative';
                const copyBtn = document.createElement('button');
                copyBtn.className = 'copy-btn';
                copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                copyBtn.addEventListener('click', () => {
                    navigator.clipboard.writeText(block.innerText).then(() => {
                        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                        copyBtn.style.background = 'rgba(74,222,128,0.3)';
                        setTimeout(() => {
                            copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                            copyBtn.style.background = '';
                        }, 2000);
                    }).catch(() => {
                        // Fallback for older browsers
                        const ta = document.createElement('textarea');
                        ta.value = block.innerText;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        ta.remove();
                        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                        setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 2000);
                    });
                });
                pre.appendChild(copyBtn);
            }
        });
    }
}

// --- ACTIONS & FEEDBACK ---
function copyText(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    navigator.clipboard.writeText(content).then(() => {
        const btn = document.querySelector(`button[onclick="copyText('${msgId}')"] i`);
        btn.className = "fas fa-check text-green-400";
        setTimeout(() => { btn.className = "fas fa-copy"; }, 2000);
    });
}

function shareResponse(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    if (navigator.share) {
        navigator.share({ title: 'Ethrix AI', text: content, url: window.location.href });
    } else {
        copyText(msgId);
        Swal.fire({ icon: 'success', title: 'Copied!', text: 'Link copied to clipboard', timer: 1500, showConfirmButton: false });
    }
}

async function handleFeedback(msgId, type) {
    const userEmail = document.getElementById('profile-name-sidebar').innerText === 'Guest' ? 'guest' : 'user';
    
    const options = type === 'good' 
        ? [ 
            { id: 'helpful', label: '🧠 Helpful', color: 'bg-green-500/20 text-green-400 border-green-500/50' }, 
            { id: 'creative', label: '🎨 Creative', color: 'bg-purple-500/20 text-purple-400 border-purple-500/50' }, 
            { id: 'fast', label: '⚡ Fast', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' }, 
            { id: 'other', label: '✨ Other', color: 'bg-gray-700 text-gray-300 border-gray-600' } 
          ]
        : [ 
            { id: 'inaccurate', label: '❌ Inaccurate', color: 'bg-red-500/20 text-red-400 border-red-500/50' }, 
            { id: 'rude', label: '😠 Rude', color: 'bg-orange-500/20 text-orange-400 border-orange-500/50' }, 
            { id: 'bug', label: '🐞 Bug', color: 'bg-blue-500/20 text-blue-400 border-blue-500/50' }, 
            { id: 'other', label: '❓ Other', color: 'bg-gray-700 text-gray-300 border-gray-600' } 
          ];

    let tagsHTML = `<div class="flex flex-wrap gap-2 justify-center mb-4">`;
    options.forEach(opt => { 
        tagsHTML += `
            <input type="radio" name="fb_category" value="${opt.id}" id="${opt.id}" class="hidden peer">
            <label for="${opt.id}" class="cursor-pointer px-4 py-2 rounded-full border ${opt.color} hover:brightness-125 transition-all text-sm font-medium peer-checked:ring-2 peer-checked:ring-white peer-checked:brightness-150 select-none">
                ${opt.label}
            </label>
        `; 
    });
    tagsHTML += `</div>`;

    const { value: formValues } = await Swal.fire({
        title: type === 'good' ? 'Nice! What did you like? ❤️' : 'Oops! What went wrong? 💔',
        html: `
            ${tagsHTML}
            <textarea id="fb_comment" class="swal2-textarea w-full bg-[#111] text-white border border-gray-700 rounded-lg p-3 text-sm focus:outline-none focus:border-pink-500" placeholder="(Optional) Tell us more details..." style="margin: 0; display: block; height: 80px;"></textarea>
        `,
        background: '#1e1e1e', 
        color: '#fff', 
        showCancelButton: true,
        confirmButtonText: 'Submit Feedback', 
        confirmButtonColor: type === 'good' ? '#4ade80' : '#f87171', 
        cancelButtonColor: '#374151',
        preConfirm: () => {
            const selected = document.querySelector('input[name="fb_category"]:checked');
            const comment = document.getElementById('fb_comment').value;
            if (!selected) {
                Swal.showValidationMessage('Please select a category');
            }
            return { category: selected ? selected.value : null, comment: comment };
        }
    });

    if (formValues) {
        await fetch('/api/feedback', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ message_id: msgId, user_email: userEmail, type: type, category: formValues.category, comment: formValues.comment }) 
        });
        
        const btn = document.querySelector(`button[onclick="handleFeedback('${msgId}', '${type}')"]`);
        if(btn) { 
            btn.classList.add(type === 'good' ? 'text-green-400' : 'text-red-400'); 
            btn.classList.add('scale-110'); 
        }
        Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' }).fire({ icon: 'success', title: 'Thanks!' });
    }
}

// --- FILE UPLOAD & PREVIEW ---
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        currentFile = { data: e.target.result.split(',')[1], type: file.type, name: file.name };
        const previewContainer = document.getElementById('file-preview-container');
        const previewName = document.getElementById('file-preview-name');
        
        if (previewContainer && previewName) {
            previewName.innerText = file.name;
            previewContainer.classList.remove('hidden');
            previewContainer.classList.add('flex'); 
        }
    };
    reader.readAsDataURL(file);
}

function removeFile() {
    currentFile = null;
    document.getElementById('file-upload').value = '';
    const previewContainer = document.getElementById('file-preview-container');
    
    if (previewContainer) {
        previewContainer.classList.add('hidden');
        previewContainer.classList.remove('flex');
    }
}

// --- MODE SELECTION ---
async function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    if (mode === 'image_gen') {
        const { value: formValues } = await Swal.fire({
            title: '🎨 Image Studio Settings',
            html: `
                <div class="text-left mb-2 text-gray-400 text-sm">Select Quality Mode:</div>
                <div class="flex gap-2 mb-4">
                    <input type="radio" name="quality" value="fast" id="q_fast" class="hidden peer/fast" checked>
                    <label for="q_fast" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/fast:bg-pink-600 peer-checked/fast:border-pink-500 hover:bg-white/5 transition">⚡ Fast (CPU)</label>
                    <input type="radio" name="quality" value="pro" id="q_pro" class="hidden peer/pro">
                    <label for="q_pro" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/pro:bg-purple-600 peer-checked/pro:border-purple-500 hover:bg-white/5 transition">💎 Pro (HQ)</label>
                </div>
                <div class="text-left mb-2 text-gray-400 text-sm">Select Art Style:</div>
                <div class="flex gap-2">
                    <input type="radio" name="style" value="painting" id="s_paint" class="hidden peer/paint" checked>
                    <label for="s_paint" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/paint:bg-orange-600 peer-checked/paint:border-orange-500 hover:bg-white/5 transition">🖌️ Painting</label>
                    <input type="radio" name="style" value="realistic" id="s_real" class="hidden peer/real">
                    <label for="s_real" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/real:bg-blue-600 peer-checked/real:border-blue-500 hover:bg-white/5 transition">📸 Realistic</label>
                </div>
            `,
            background: '#111', 
            color: '#fff', 
            confirmButtonText: 'Set Preferences', 
            confirmButtonColor: '#ec4899',
            preConfirm: () => { 
                return { 
                    quality: document.querySelector('input[name="quality"]:checked').value, 
                    style: document.querySelector('input[name="style"]:checked').value 
                };
            }
        });

        if (formValues) {
            imageSettings = formValues;
            Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' })
                .fire({ icon: 'success', title: `Mode Set: ${imageSettings.quality.toUpperCase()} + ${imageSettings.style.toUpperCase()}` });
        }
    } 
    else if (mode === 'ethrix_agent') {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2000, background: '#020205', color: '#0ff' }).fire({ icon: 'success', title: '🌌 Ethrix Agent Online' });
    } 
    else {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 1000 }).fire({ icon: 'info', title: `Mode: ${mode}` });
    }
}

// --- VOICE FUNCTIONS ---
function toggleRecording() {
    if (!('webkitSpeechRecognition' in window)) { 
        alert("Voice not supported"); 
        return; 
    }
    
    if (isRecording) { 
        recognition.stop(); 
        isRecording = false; 
        document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); 
        return; 
    }
    
    recognition = new webkitSpeechRecognition();
    recognition.lang = "en-IN";
    
    recognition.onstart = () => { 
        isRecording = true; 
        document.getElementById('mic-btn').classList.add('text-red-500', 'animate-pulse'); 
    };
    
    recognition.onresult = (event) => { 
        document.getElementById('user-input').value = event.results[0][0].transcript; 
        sendMessage(); 
    };
    
    recognition.onend = () => { 
        isRecording = false; 
        document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); 
    };
    
    recognition.start();
}

async function playAudio(text) {
    try {
        const res = await fetch('/api/speak', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ text: text }) 
        });
        const blob = await res.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play();
    } catch (e) { 
        console.error(e); 
    }
}

// --- SIDEBAR DATA LOADERS ---
async function loadHistory() {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('history-list');
    list.innerHTML = '';
    
    data.history.filter(chat => !chat.title.startsWith('Tool:')).forEach(chat => {
        const div = document.createElement('div');
        div.className = 'history-item';
        div.innerHTML = `<div class="history-icon"><i class="far fa-comment-alt"></i></div><span class="nav-label truncate text-xs md:text-sm flex-1">${chat.title}</span>`;
        div.onclick = () => loadChat(chat.id);
        
        // Context menu check if it exists in another js file
        if (typeof showContextMenu === "function") {
            div.oncontextmenu = (e) => { e.preventDefault(); showContextMenu(e, chat.id); };
        }
        list.appendChild(div);
    });
}

async function loadProfile() {
    try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        
        const sidebarName = document.getElementById('profile-name-sidebar');
        if(sidebarName) sidebarName.innerText = data.name || "User";
        
        const sidebarImg = document.getElementById('profile-img-sidebar');
        if(sidebarImg) sidebarImg.src = data.avatar || "/static/images/logo.png";
        
        const sidebarPlan = document.getElementById('profile-plan-sidebar');
        if(sidebarPlan) sidebarPlan.innerText = data.plan;
    } catch(e) {
        console.log("Profile could not be fetched.");
    }
}

// --- UTILITIES ---
function closeModal(id) { 
    const el = document.getElementById(id);
    if(el) el.style.display = 'none'; 
}

function toggleVoice() { 
    // Handled globally in preferences now 
}

async function deleteAllChats() {
    if(confirm("Delete all history?")) {
        await fetch('/api/delete_all_chats', { method: 'DELETE' });
        loadHistory(); 
        createNewChat(); 
        closeModal('settings-modal');
    }
}

function editMyMessage(msgId) {
    const contentDiv = document.getElementById(msgId + '_content');
    if(contentDiv) {
        const text = contentDiv.innerText;
        document.getElementById('user-input').value = text;
        document.getElementById('user-input').focus();
    }
}

// --- CUSTOM CURSOR LOGIC ---
document.addEventListener("DOMContentLoaded", () => {
    if (window.matchMedia("(pointer: fine)").matches) {
        // Mark body so CSS knows neon cursor is active (tool pages won't have this class)
        document.body.classList.add("neon-cursor-active");

        const dot = document.createElement("div"); 
        dot.className = "cursor-dot";
        
        const outline = document.createElement("div"); 
        outline.className = "cursor-outline";
        
        document.body.appendChild(dot); 
        document.body.appendChild(outline);

        window.addEventListener("mousemove", (e) => {
            dot.style.left = `${e.clientX}px`; 
            dot.style.top = `${e.clientY}px`;
            outline.animate({ left: `${e.clientX}px`, top: `${e.clientY}px` }, { duration: 500, fill: "forwards" });
        });

        window.addEventListener("mousedown", (e) => {
            const ripple = document.createElement("div"); 
            ripple.className = "click-ripple";
            ripple.style.left = `${e.clientX}px`; 
            ripple.style.top = `${e.clientY}px`;
            
            document.body.appendChild(ripple);
            outline.style.transform = "translate(-50%, -50%) scale(0.7)";
            
            setTimeout(() => { outline.style.transform = "translate(-50%, -50%) scale(1)"; }, 150);
            setTimeout(() => { ripple.remove(); }, 500);
        });

        const addHoverEffect = () => {
            document.querySelectorAll("a, button, input, textarea, select, .tool-card, .goti, .dice").forEach(el => {
                el.addEventListener("mouseenter", () => { 
                    outline.style.width = "50px"; 
                    outline.style.height = "50px"; 
                    outline.style.backgroundColor = "rgba(236, 72, 153, 0.1)"; 
                });
                el.addEventListener("mouseleave", () => { 
                    outline.style.width = "32px"; 
                    outline.style.height = "32px"; 
                    outline.style.backgroundColor = "transparent"; 
                });
            });
        };
        addHoverEffect();
    }
});

// --- REGENERATE MESSAGE ---
async function regenerateMessage(msgId) {
    const chatBox = document.getElementById('chat-box');
    const aiMsgDiv = document.getElementById(msgId + '_content').closest('.msg-ai');
    if (!aiMsgDiv) return;

    let prevElement = aiMsgDiv.previousElementSibling;
    let userText = "";
    
    while (prevElement) {
        if (prevElement.classList.contains('msg-user')) {
            let contentDiv = prevElement.querySelector('[id$="_content"]');
            if (contentDiv) { 
                userText = contentDiv.innerText.trim(); 
            }
            break;
        }
        prevElement = prevElement.previousElementSibling;
    }

    if (!userText) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'error', title: 'Original message not found!', timer: 2000, showConfirmButton: false, background: '#1e1e1e', color: '#fff' });
        return;
    }

    aiMsgDiv.remove();

    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'msg-ai';
    thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatBox.appendChild(thinkingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const payload = { 
            message: userText, 
            session_id: currentSessionId, 
            mode: currentMode, 
            image_quality: imageSettings.quality, 
            image_style: imageSettings.style 
        };
        
        const res = await fetch('/api/chat', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify(payload) 
        });
        const data = await res.json();
        
        document.getElementById(thinkingId).remove();
        appendMessage('assistant', data.reply, null);
    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not regenerate.</span>';
    }
}

// ==================================================================================
// 🚀 ETHRIX GLOBAL PREFERENCES & CUSTOM THEME INJECTOR
// ==================================================================================
async function loadGlobalPreferences() {
    try {
        const res = await fetch('/api/get_preferences');
        const prefs = await res.json();
        
        // 1. Font Apply
        if(prefs.font) {
            document.body.style.fontFamily = prefs.font + ", sans-serif";
            document.querySelectorAll('input, button, select, textarea').forEach(el => {
                el.style.fontFamily = prefs.font + ", sans-serif";
            });
        }
        
        // 2. Theme Apply
        if(prefs.theme === 'light') {
            document.body.classList.add('light-mode');
            localStorage.setItem('theme', 'light');
        } else {
            document.body.classList.remove('light-mode');
            localStorage.setItem('theme', 'dark');
        }

        // 3. Voice Toggle state
        const voiceToggle = document.getElementById('voice-toggle');
        if(voiceToggle) voiceToggle.checked = prefs.voice;
        localStorage.setItem('voice_reply', prefs.voice);

        // 🚀 THE ZEN MODE & TEXT SIZE MAGIC
        if (!document.getElementById('ethrix-features-style')) {
            let style = document.createElement('style');
            style.id = 'ethrix-features-style';
            // CSS jo automatically Sidebar aur Tools ko control karegi
            style.innerHTML = `
                /* 🧘 ZEN MODE RULES */
                .zen-mode-active a[href="/tools"],
                .zen-mode-active a[href="/diary"] { display: none !important; }
                
                .zen-mode-active #history-list .history-item { display: none !important; }
                
                .zen-mode-active #history-list::after { 
                    content: '🧘 Zen Mode ON'; 
                    display: block; 
                    text-align: center; 
                    color: var(--dynamic-color, #00E5FF); 
                    margin-top: 20px; 
                    font-size: 0.85rem; 
                    font-weight: bold; 
                    background: rgba(0,0,0,0.3); 
                    padding: 10px; 
                    border-radius: 10px; 
                    margin-inline: 15px; 
                    border: 1px dashed var(--dynamic-color, #00E5FF); 
                }
                
                /* 💬 TEXT SIZE RULES */
                body[data-text-size="small"] .msg-user, body[data-text-size="small"] .msg-ai { font-size: 0.85rem !important; }
                body[data-text-size="large"] .msg-user, body[data-text-size="large"] .msg-ai { font-size: 1.15rem !important; }
            `;
            document.head.appendChild(style);
        }

        // Apply Zen Mode Status
        if (prefs.zen_mode) {
            document.body.classList.add('zen-mode-active');
        } else {
            document.body.classList.remove('zen-mode-active');
        }

        // Apply Chat Text Size
        document.body.setAttribute('data-text-size', prefs.chat_text_size || 'default');

        // Update Global Prefs for Chat API
        window.ethrixPrefs = {
            send_on_enter: prefs.send_on_enter !== false,
            ui_sfx: prefs.ui_sfx !== false,
            fast_mode: prefs.fast_mode === true,
            auto_scroll: prefs.auto_scroll !== false,
            smart_memory: prefs.smart_memory !== false,
            ai_persona: prefs.ai_persona || 'friendly'
        };
        // 🚀 NAYA: 4 Naye Features ko Global Variable mein save karna
        window.ethrixPrefs = {
            send_on_enter: prefs.send_on_enter !== false,
            ui_sfx: prefs.ui_sfx !== false,
            fast_mode: prefs.fast_mode === true,
            auto_scroll: prefs.auto_scroll !== false
        };

        // 4. ✨ Custom User Colors Apply Karna
        let pColor = prefs.primary_color || '#00E5FF';
        localStorage.setItem('primary_color', pColor); 
        applyCustomColor(pColor);

    } catch (e) { 
        console.log("Preferences load error", e); 
    }
}

// Ye function tumhare custom color ki magic injection karta hai!
function applyCustomColor(color) {
    // Purana dynamic style hatao
    let oldStyle = document.getElementById('dynamic-theme-style');
    if(oldStyle) oldStyle.remove();

    // Hex to RGB conversion for transparency effects (rgba)
    let r = parseInt(color.slice(1, 3), 16);
    let g = parseInt(color.slice(3, 5), 16);
    let b = parseInt(color.slice(5, 7), 16);
    let rgb = `${r}, ${g}, ${b}`;

    // Naya CSS Style banaya gaya custom color ke sath!
    let css = `
        /* User Chat Bubbles */
        .msg-user { background: linear-gradient(135deg, rgba(${rgb}, 0.7), ${color}) !important; box-shadow: 0 4px 12px rgba(${rgb}, 0.3) !important; }
        
        /* Active Mode Button */
        .mode-btn.active { background: linear-gradient(135deg, rgba(${rgb}, 0.7), ${color}) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.4) !important; color: white !important; }
        
        /* Hover over Chat History */
        .history-item:hover { background: rgba(${rgb}, 0.15) !important; color: ${color} !important; }
        .history-item:hover .history-icon { color: ${color} !important; }
        
        /* Highlights & Borders */
        #chat-search:focus { border-color: rgba(${rgb}, 0.5) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.15) !important; }
        
        /* ✨ Send Button & File Upload Icon Glow Fix ✨ */
        .input-container button[type="submit"] { background: linear-gradient(135deg, rgba(${rgb}, 0.8), ${color}) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.4) !important; }
        .input-container button:hover i { color: ${color} !important; }
        
        /* Cursor Glow (Only on desktop) */
        .cursor-dot { background: ${color} !important; box-shadow: 0 0 10px ${color}, 0 0 20px ${color} !important; }
        .cursor-outline { border-color: rgba(${rgb}, 0.6) !important; }
        .click-ripple { background: radial-gradient(circle, rgba(${rgb}, 0.8) 0%, rgba(0, 0, 0, 0) 70%) !important; }
    `;

    // Usko document mein inject kar diya
    let style = document.createElement('style');
    style.id = 'dynamic-theme-style';
    style.innerHTML = css;
    document.head.appendChild(style);

    // Initialize/Restart Vanta background to apply this new color
    if (typeof initVanta === 'function') {
        initVanta();
    }
}
// ==================================================================================
// 🎵 NAYA: UI SOUND EFFECTS & ENTER KEY LOGIC
// ==================================================================================

function playSfx(type = 'pop') {
    // Agar user ne settings se SFX off kiya hai, toh aawaz nahi aayegi
    if (!window.ethrixPrefs || !window.ethrixPrefs.ui_sfx) return;
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        
        if (type === 'pop') { // Message aane ka sweet sound
            osc.type = 'sine';
            osc.frequency.setValueAtTime(600, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
        } else if (type === 'send') { // Message bhejne ka swoosh sound
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(300, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
        }
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.1);
    } catch(e) { console.log("SFX Error", e); }
}

// ⌨️ Enter dabaney par message send ho jaye! (Shift+Enter for new line)
document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('user-input');
    if (userInput) {
        userInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                if (window.ethrixPrefs && window.ethrixPrefs.send_on_enter) {
                    e.preventDefault(); // Nayi line banne se rokega
                    sendMessage(); // Message bhej dega
                }
            }
        });
    }
});