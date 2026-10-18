/* ==================================================================================
   FILE: static/js/tools.js
   DESCRIPTION: Frontend Logic for Tools Modal & Selection
   CATEGORIES:
     1. MODAL MANAGEMENT (Open/Close)
     2. TOOL SELECTION (Switch Case for Placeholders & Modes)
   ================================================================================== */

// [CATEGORY] 1. MODAL MANAGEMENT
function openToolsModal() {
    const modal = document.getElementById('tools-modal');
    if(modal) modal.style.display = 'flex';
}

// [CATEGORY] 2. TOOL SELECTION LOGIC
function selectTool(toolName) {
    // Set global mode variable
    if (typeof setMode === 'function') currentMode = toolName;
    else window.currentMode = toolName;

    const input = document.getElementById('user-input');
    const uploadBtn = document.getElementById('file-upload');
    
    // Reset visual state of mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));

    // Configure Input & Alerts based on selected tool
    switch(toolName) {
        case 'sing_with_me':
            input.placeholder = "🎤 Start a song (e.g., 'Tera hone laga hoon')...";
            input.focus();
            Swal.fire({
                toast:true, position:'top-end', icon:'success', title:'Humsafar Mode Activated ❤️', 
                background:'#1f2937', color:'#f472b6', timer:3000, showConfirmButton:false
            });
            break;
            
        case 'resume_analyzer':
            input.placeholder = "📄 Upload PDF Resume & press send...";
            if(uploadBtn) uploadBtn.click();
            Swal.fire({toast:true, position:'top-end', icon:'info', title:'Upload Resume (PDF)', showConfirmButton:false, timer:3000});
            break;
            
        case 'math_solver':
            input.placeholder = "📐 Upload Math Photo or type equation...";
            if(uploadBtn) uploadBtn.click();
            break;
            
        case 'smart_todo': input.placeholder = "📝 Type tasks roughly (e.g. 'Buy milk, Study')..."; input.focus(); break;
        case 'resume_builder': input.placeholder = "💼 Paste Name, Exp, Skills to build CV..."; input.focus(); break;
        case 'youtube_summarizer': input.placeholder = "📺 Paste YouTube Link..."; input.focus(); break;
        case 'mock_interviewer': input.placeholder = "🎓 Enter Role (e.g. Java Dev) to START..."; input.focus(); break;
        case 'interview_questions': input.placeholder = "📋 Enter Role for Questions..."; input.focus(); break;
        case 'github_review': input.placeholder = "🐙 Paste GitHub Link..."; input.focus(); break;
        case 'currency_converter': input.placeholder = "💱 E.g. 100 USD to INR..."; input.focus(); break;
        case 'password_generator': input.placeholder = "🔐 Press send for password..."; input.focus(); break;
        case 'grammar_fixer': input.placeholder = "📝 Paste text to fix..."; input.focus(); break;
        case 'qr_generator': input.placeholder = "🔗 Enter text/link..."; input.focus(); break;
        case 'prompt_writer': input.placeholder = "✨ Describe idea..."; input.focus(); break;
        
        default: input.placeholder = `Using ${toolName}...`;
    }
    
    // Close modal after selection
    closeModal('tools-modal');
}