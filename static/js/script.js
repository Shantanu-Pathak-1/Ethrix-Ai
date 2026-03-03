// ==================================================================================
//  FILE: static/js/script.js
//  DESCRIPTION: Main Frontend Logic (Updated with Image Gen Options)
// ==================================================================================

let currentSessionId = localStorage.getItem('session_id') || null;
let currentMode = 'chat';
let isRecording = false;
let recognition = null;
let currentFile = null;
// Naya variable add karo top par
let lastMessageDate = null; 

// Helper function date calculate karne ke liye
// Helper function date calculate karne ke liye
function getDateLabel(timestamp) {
    let ts = timestamp;
    // Backend ke time ko strict UTC maan kar IST mein badalne ka logic
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) {
        ts += 'Z'; 
    }
    
    const date = ts ? new Date(ts) : new Date();
    
    // Direct date dikhayega (e.g., "22 Feb 2026")
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// New Global Variables for Image Settings
let imageSettings = {
    quality: 'fast', // 'fast' or 'pro'
    style: 'painting' // 'painting' or 'realistic'
};

document.addEventListener('DOMContentLoaded', () => {
    // Check saved theme
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-mode');
    }

    // Initialize Vanta Background
    initVanta();

    loadHistory();
    loadProfile();
    
    if (!currentSessionId) createNewChat();
    else loadChat(currentSessionId);
});

// --- THEME & VANTA CONFIG (Dual Effects) ---
let vantaEffect = null;

function initVanta() {
    if (!window.VANTA) return;
    
    const isLight = document.body.classList.contains('light-mode');
    
    // Destroy previous effect to prevent overlap/crash
    if (vantaEffect) vantaEffect.destroy();

    if (isLight) {
        // LIGHT MODE = RINGS
        vantaEffect = VANTA.RINGS({
            el: "#vanta-bg",
            mouseControls: true,
            touchControls: true,
            gyroControls: false,
            minHeight: 200.00,
            minWidth: 200.00,
            scale: 1.00,
            scaleMobile: 1.00,
            backgroundColor: 0xe0e7ff, // Light Cool Grey/Blue
            color: 0x2563eb // Blue Rings
        });
    } else {
        // DARK MODE = HALO (FIXED: SMALLER SIZE)
      // DARK MODE = HALO 
        vantaEffect = VANTA.HALO({
            el: "#vanta-bg",
            mouseControls: true,
            touchControls: true,
            gyroControls: false,
            minHeight: 200.00,
            minWidth: 200.00,
            baseColor: 0xec4899, // Pink
            backgroundColor: 0x000000, // Black
            size: 0.8, 
            amplitudeFactor: 1.0,
            xOffset: 0.0, // <-- Ise 0.0 kar do
            yOffset: 0.0  // <-- Ise bhi 0.0 kar do
        });
    }
}

function toggleTheme() {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    
    // Restart Vanta to switch effect
    initVanta();
}

// --- PROFILE SAVE ---
async function saveProfile() {
    const nameInput = document.getElementById('profile-name-input');
    const newName = nameInput.value.trim();
    const btn = document.querySelector('button[onclick="saveProfile()"]');

    if (!newName) return alert("Name cannot be empty");

    btn.textContent = "Saving...";
    
    try {
        const res = await fetch('/api/update_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });

        if (res.ok) {
            btn.textContent = "Saved!";
            document.getElementById('profile-name-sidebar').innerText = newName;
            setTimeout(() => { 
                btn.textContent = "Save Changes"; 
                closeModal('profile-modal'); 
            }, 1000);
        } else {
            btn.textContent = "Error";
        }
    } catch (e) {
        console.error(e);
        btn.textContent = "Failed";
    }
}

// --- CHAT FUNCTIONS ---

async function createNewChat() {
    const res = await fetch('/api/new_chat');
    const data = await res.json();
    currentSessionId = data.session_id;
    localStorage.setItem('session_id', currentSessionId);
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-80 text-center animate-fade-in px-4">
            <img src="/static/images/logo.png" class="w-20 h-20 md:w-24 md:h-24 rounded-full mb-4 md:mb-6 shadow-[0_0_30px_rgba(236,72,153,0.5)] animate-pulse">
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
    
    // Nayi chat load hone par date reset
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
            // SENDING NEW IMAGE SETTINGS TO BACKEND
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
        
        appendMessage('assistant', data.reply, null);
        loadHistory();

        if (document.getElementById('voice-toggle') && document.getElementById('voice-toggle').checked) {
            playAudio(data.reply);
        }

    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not connect to Shanvika.</span>';
    }
}

// --- COMPLETE APPEND MESSAGE FUNCTION ---
function appendMessage(role, text, timestamp = null) {
    const chatBox = document.getElementById('chat-box');
    
    let ts = timestamp;
    // Timezone Fix: Z lagane se browser exact Real Time (India) nikal lega
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) {
        ts += 'Z'; 
    }
    
    const msgDateObj = ts ? new Date(ts) : new Date();
    
    // Exact 12-hour format time (jaise 10:15 PM)
    const displayTime = msgDateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    const dateLabel = getDateLabel(ts);

    // Date Divider Logic (Agar day change hua toh bas 1 baar divider aayega)
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
                    <button class="action-btn" onclick="copyText('${msgId}')" title="Copy"><i class="fas fa-copy"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'good')" title="Good"><i class="fas fa-thumbs-up"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'bad')" title="Bad"><i class="fas fa-thumbs-down"></i></button>
                    <button class="action-btn" onclick="shareResponse('${msgId}')" title="Share"><i class="fas fa-share-alt"></i></button>
                </div>
            </div>
        `;
    } else {
        // User ke message mein Edit icon aur fix time
        actionHTML = `
            <div class="msg-meta" style="border-top:none; justify-content:flex-end; gap: 8px;">
                <button class="action-btn" onclick="editMyMessage('${msgId}')" title="Edit Message"><i class="fas fa-pen text-[11px]"></i></button>
                <span class="msg-time">${displayTime}</span>
            </div>
        `;
    }

    // Message aur HTML ko add karna
    div.innerHTML = `<div id="${msgId}_content">${content}</div> ${actionHTML}`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Code blocks ke liye syntax highlight
    if (role === 'assistant') {
        div.querySelectorAll('pre code').forEach((block) => {
            if (window.hljs) hljs.highlightElement(block);
        });
    }
}
// --- ACTIONS ---
function copyText(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    navigator.clipboard.writeText(content).then(() => {
        const btn = document.querySelector(`button[onclick="copyText('${msgId}')"] i`);
        btn.className = "fas fa-check text-green-400";
        setTimeout(() => btn.className = "fas fa-copy", 2000);
    });
}

function shareResponse(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    if (navigator.share) {
        navigator.share({ title: 'Shanvika AI', text: content, url: window.location.href });
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
            <textarea id="fb_comment" class="swal2-textarea w-full bg-[#111] text-white border border-gray-700 rounded-lg p-3 text-sm focus:outline-none focus:border-pink-500" 
            placeholder="(Optional) Tell us more details..." style="margin: 0; display: block; height: 80px;"></textarea>
        `,
        background: '#1e1e1e', color: '#fff', showCancelButton: true,
        confirmButtonText: 'Submit Feedback', confirmButtonColor: type === 'good' ? '#4ade80' : '#f87171',
        cancelButtonColor: '#374151',
        preConfirm: () => {
            const selected = document.querySelector('input[name="fb_category"]:checked');
            const comment = document.getElementById('fb_comment').value;
            if (!selected) Swal.showValidationMessage('Please select a category');
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
        if(btn) { btn.classList.add(type === 'good' ? 'text-green-400' : 'text-red-400'); btn.classList.add('scale-110'); }
        Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' }).fire({ icon: 'success', title: 'Thanks!' });
    }
}

function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        // Data aur file ka naam save karo
        currentFile = { data: e.target.result.split(',')[1], type: file.type, name: file.name };
        
        // Input bar ke upar Preview Box dikhao
        const previewContainer = document.getElementById('file-preview-container');
        const previewName = document.getElementById('file-preview-name');
        if (previewContainer && previewName) {
            previewName.innerText = file.name;
            previewContainer.classList.remove('hidden');
            previewContainer.classList.add('flex'); // Flex layout active karein
        }
    };
    reader.readAsDataURL(file);
}

// File Cancel karne ka function
function removeFile() {
    currentFile = null;
    document.getElementById('file-upload').value = '';
    const previewContainer = document.getElementById('file-preview-container');
    if (previewContainer) {
        previewContainer.classList.add('hidden');
        previewContainer.classList.remove('flex');
    }
}
// --- UPDATED: SET MODE WITH POPUP FOR IMAGE GEN ---
async function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // IF IMAGE GEN IS SELECTED -> SHOW OPTIONS
    if (mode === 'image_gen') {
        const { value: formValues } = await Swal.fire({
            title: '🎨 Image Studio Settings',
            html: `
                <div class="text-left mb-2 text-gray-400 text-sm">Select Quality Mode:</div>
                <div class="flex gap-2 mb-4">
                    <input type="radio" name="quality" value="fast" id="q_fast" class="hidden peer/fast" checked>
                    <label for="q_fast" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/fast:bg-pink-600 peer-checked/fast:border-pink-500 hover:bg-white/5 transition">
                        ⚡ Fast (CPU)
                    </label>

                    <input type="radio" name="quality" value="pro" id="q_pro" class="hidden peer/pro">
                    <label for="q_pro" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/pro:bg-purple-600 peer-checked/pro:border-purple-500 hover:bg-white/5 transition">
                        💎 Pro (HQ)
                    </label>
                </div>

                <div class="text-left mb-2 text-gray-400 text-sm">Select Art Style:</div>
                <div class="flex gap-2">
                    <input type="radio" name="style" value="painting" id="s_paint" class="hidden peer/paint" checked>
                    <label for="s_paint" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/paint:bg-orange-600 peer-checked/paint:border-orange-500 hover:bg-white/5 transition">
                        🖌️ Painting
                    </label>

                    <input type="radio" name="style" value="realistic" id="s_real" class="hidden peer/real">
                    <label for="s_real" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/real:bg-blue-600 peer-checked/real:border-blue-500 hover:bg-white/5 transition">
                        📸 Realistic
                    </label>
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
                }
            }
        });

        if (formValues) {
            imageSettings = formValues;
            Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' })
                .fire({ icon: 'success', title: `Mode Set: ${imageSettings.quality.toUpperCase()} + ${imageSettings.style.toUpperCase()}` });
        }
    } else {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 1000 }).fire({ icon: 'info', title: `Mode: ${mode}` });
    }
}

function toggleRecording() {
    if (!('webkitSpeechRecognition' in window)) { alert("Voice not supported"); return; }
    if (isRecording) { recognition.stop(); isRecording = false; document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); return; }
    recognition = new webkitSpeechRecognition();
    recognition.lang = "en-IN";
    recognition.onstart = () => { isRecording = true; document.getElementById('mic-btn').classList.add('text-red-500', 'animate-pulse'); };
    recognition.onresult = (event) => { document.getElementById('user-input').value = event.results[0][0].transcript; sendMessage(); };
    recognition.onend = () => { isRecording = false; document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); };
    recognition.start();
}

async function playAudio(text) {
    try {
        const res = await fetch('/api/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
        const blob = await res.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play();
    } catch (e) { console.error(e); }
}

async function loadHistory() {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('history-list');
    list.innerHTML = '';
    data.history.forEach(chat => {
        const div = document.createElement('div');
        div.className = 'history-item';
        // Yaha par nav-label class add ki hai taaki title hide ho sake
        div.innerHTML = `<div class="history-icon"><i class="far fa-comment-alt"></i></div><span class="nav-label truncate text-xs md:text-sm flex-1">${chat.title}</span>`;
        div.onclick = () => loadChat(chat.id);
        div.oncontextmenu = (e) => { e.preventDefault(); showContextMenu(e, chat.id); };
        list.appendChild(div);
    });
}
async function loadProfile() {
    const res = await fetch('/api/profile');
    const data = await res.json();
    document.getElementById('profile-name-sidebar').innerText = data.name || "User";
    document.getElementById('profile-img-sidebar').src = data.avatar || "/static/images/logo.png";
    document.getElementById('profile-plan-sidebar').innerText = data.plan;
    document.getElementById('profile-name-input').value = data.name || "";
    document.getElementById('profile-img-modal').src = data.avatar || "/static/images/logo.png";
}

function openSettingsModal() { document.getElementById('settings-modal').style.display = 'flex'; }
function openProfileModal() { document.getElementById('profile-modal').style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function toggleVoice() { }

async function deleteAllChats() {
    if(confirm("Delete all history?")) {
        await fetch('/api/delete_all_chats', { method: 'DELETE' });
        loadHistory(); createNewChat(); closeModal('settings-modal');
    }
}
// Message Edit Function
function editMyMessage(msgId) {
    const contentDiv = document.getElementById(msgId + '_content');
    if(contentDiv) {
        const text = contentDiv.innerText;
        document.getElementById('user-input').value = text;
        document.getElementById('user-input').focus();
    }
}
