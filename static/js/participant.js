/**
 * Unified Attendee Portal & Mobile Check-in Handler.
 * Combines Session Attendance Check-in and Personal Attendance Record Lookup
 * into a single seamless, mobile-optimized experience with instant profile reveals.
 */

document.addEventListener("DOMContentLoaded", () => {
  initTabSwitching();
  initPinToggle();
  initFormHandler();
  initAutoCapitalize();
  initPrefill();
});

// --- Tab Switching Logic (Mark Attendance vs My Record) ---
function initTabSwitching() {
  const btnCheckin = document.getElementById("tabBtnCheckin");
  const btnRecord = document.getElementById("tabBtnRecord");
  const activeModeInput = document.getElementById("activeTabMode");

  if (!btnCheckin || !btnRecord) return;

  btnCheckin.addEventListener("click", () => setPortalMode("checkin"));
  btnRecord.addEventListener("click", () => setPortalMode("history"));

  // Check initial mode if passed from server
  const initialMode = activeModeInput?.value || "checkin";
  setPortalMode(initialMode, false);
}

function setPortalMode(mode, clearFeedback = true) {
  const btnCheckin = document.getElementById("tabBtnCheckin");
  const btnRecord = document.getElementById("tabBtnRecord");
  const activeModeInput = document.getElementById("activeTabMode");
  const btnActionIcon = document.getElementById("btnActionIcon");
  const btnActionText = document.getElementById("btnActionText");
  const manualSession = document.getElementById("manualSessionGroup");
  const hiddenSessionId = document.getElementById("checkinSessionId")?.value;

  if (activeModeInput) activeModeInput.value = mode;

  if (mode === "history") {
    btnRecord.classList.add("active");
    btnRecord.setAttribute("aria-selected", "true");
    btnCheckin.classList.remove("active");
    btnCheckin.setAttribute("aria-selected", "false");

    if (btnActionIcon) btnActionIcon.textContent = "📊";
    if (btnActionText) btnActionText.textContent = "VIEW MY ATTENDANCE RECORD";
    if (manualSession) manualSession.style.display = "none";
  } else {
    btnCheckin.classList.add("active");
    btnCheckin.setAttribute("aria-selected", "true");
    btnRecord.classList.remove("active");
    btnRecord.setAttribute("aria-selected", "false");

    if (btnActionIcon) btnActionIcon.textContent = "⚡";
    if (btnActionText) btnActionText.textContent = "VERIFY & MARK ATTENDANCE";
    if (manualSession) {
      manualSession.style.display = !hiddenSessionId ? "block" : "none";
    }
  }

  if (clearFeedback) {
    hideFeedback();
  }
}

// --- PIN Eye Visibility Toggle ---
function initPinToggle() {
  const btnToggle = document.getElementById("btnTogglePin");
  const pinInput = document.getElementById("participantPinInput");
  if (!btnToggle || !pinInput) return;

  btnToggle.addEventListener("click", () => {
    if (pinInput.type === "password") {
      pinInput.type = "text";
      btnToggle.textContent = "🔒";
      btnToggle.setAttribute("aria-label", "Hide PIN");
    } else {
      pinInput.type = "password";
      btnToggle.textContent = "👁";
      btnToggle.setAttribute("aria-label", "Show PIN");
    }
  });
}

// --- Auto-uppercase ID on typing ---
function initAutoCapitalize() {
  const idInput = document.getElementById("participantIdInput");
  if (!idInput) return;
  idInput.addEventListener("input", (e) => {
    e.target.value = e.target.value.toUpperCase();
  });
}

// --- Prefill from local storage or URL query ---
function initPrefill() {
  const urlParams = new URLSearchParams(window.location.search);
  const queryId = urlParams.get("id");
  const storedId = localStorage.getItem("last_participant_id");
  const idInput = document.getElementById("participantIdInput");
  const pinInput = document.getElementById("participantPinInput");

  const initial = queryId || storedId;
  if (initial && idInput && !idInput.value) {
    idInput.value = initial.toUpperCase();
    pinInput?.focus();
  } else if (idInput && !idInput.value) {
    idInput.focus();
  }

  const resetBtn = document.getElementById("btnResetForNext");
  if (resetBtn) {
    resetBtn.addEventListener("click", resetUnifiedForm);
  }
}

// --- Form Submit Dispatcher ---
function initFormHandler() {
  const form = document.getElementById("formUnifiedPortal");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mode = document.getElementById("activeTabMode")?.value || "checkin";
    const participantId = document.getElementById("participantIdInput").value.trim().toUpperCase();
    const pin = document.getElementById("participantPinInput").value.trim();

    if (!participantId || !pin) {
      showFeedback("Please enter both your Participant ID and Access PIN.", "error");
      return;
    }

    if (mode === "checkin") {
      await handleCheckinAction(participantId, pin);
    } else {
      await handleRecordLookupAction(participantId, pin);
    }
  });
}

// --- Check-in Action ---
async function handleCheckinAction(participantId, pin) {
  const hiddenSessionId = document.getElementById("checkinSessionId")?.value;
  const manualSessionId = document.getElementById("manualSessionIdInput")?.value;
  const sessionId = hiddenSessionId ? parseInt(hiddenSessionId) : (manualSessionId ? parseInt(manualSessionId) : null);

  if (!sessionId) {
    showFeedback("No active event session detected. Please scan the venue QR code on screen.", "error");
    playAudioCue('error');
    return;
  }

  const btn = document.getElementById("btnUnifiedAction");
  btn.disabled = true;
  btn.innerHTML = '<span class="pulse-dot"></span> VERIFYING CREDENTIALS...';
  hideFeedback();

  try {
    const res = await fetch("/api/attendance/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        participant_id: participantId,
        password: pin,
        scanner_id: "MOBILE_WEB_GATE"
      })
    });

    const data = await res.json();

    if (res.ok && data.success) {
      playAudioCue('success');
      showFeedback(`
        <div class="feedback-badge-top">
          <span class="feedback-icon-check">✓</span>
          <span class="feedback-title">ATTENDANCE CONFIRMED</span>
        </div>
        <div class="feedback-body">
          Welcome, <strong>${esc(data.participant_name)}</strong>! Your attendance for <strong>${esc(data.session_name)}</strong> has been recorded at <span class="mono text-neon">${esc(data.checkin_time)}</span>.
        </div>
      `, "success");

      if (typeof showToast === "function") {
        showToast("Attendance successfully recorded!", "success");
      }
      localStorage.setItem("last_participant_id", participantId);

      // Instantly reveal the participant's verified digital record card
      if (data.student_record) {
        renderStudentPass(data.student_record);
      }
    } else if (data.status_code === "ALREADY_CHECKED_IN") {
      playAudioCue('warning');
      showFeedback(`
        <div class="feedback-badge-top">
          <span class="feedback-icon-warn">⚠</span>
          <span class="feedback-title">ALREADY CHECKED IN</span>
        </div>
        <div class="feedback-body">
          You are already marked present for <strong>${esc(data.session_name || 'this session')}</strong>.<br>
          Original Check-in: <span class="mono text-neon">${esc(data.previous_checkin_time)}</span>.
        </div>
      `, "warning");

      if (typeof showToast === "function") {
        showToast("Already checked in for this session.", "warning");
      }
      localStorage.setItem("last_participant_id", participantId);

      if (data.student_record) {
        renderStudentPass(data.student_record);
      }
    } else if (data.status_code === "SESSION_INACTIVE") {
      playAudioCue('error');
      showFeedback(`
        <div class="feedback-badge-top">
          <span class="feedback-icon-err">✕</span>
          <span class="feedback-title">SESSION INACTIVE</span>
        </div>
        <div class="feedback-body">
          ${esc(data.message || 'Attendance is currently closed. Please wait for the event staff to activate check-in.')}
        </div>
      `, "error");
    } else {
      playAudioCue('error');
      showFeedback(`
        <div class="feedback-badge-top">
          <span class="feedback-icon-err">✕</span>
          <span class="feedback-title">AUTHENTICATION FAILED</span>
        </div>
        <div class="feedback-body">
          ${esc(data.message || 'Invalid Participant ID or Access PIN. Please check your registration details.')}
        </div>
      `, "error");
    }
  } catch (err) {
    playAudioCue('error');
    showFeedback("Network error. Please check your Wi-Fi/data connection and try again.", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span id="btnActionIcon">⚡</span> <span id="btnActionText">VERIFY & MARK ATTENDANCE</span>';
  }
}

// --- Record Lookup Action ---
async function handleRecordLookupAction(participantId, pin) {
  const btn = document.getElementById("btnUnifiedAction");
  btn.disabled = true;
  btn.innerHTML = '<span class="pulse-dot"></span> RETRIEVING RECORD...';
  hideFeedback();

  try {
    const res = await fetch("/api/participant/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        participant_id: participantId,
        password: pin
      })
    });

    const data = await res.json();

    if (!res.ok || !data.success) {
      playAudioCue('error');
      hideStudentPass();
      showFeedback(`
        <div class="feedback-badge-top">
          <span class="feedback-icon-err">✕</span>
          <span class="feedback-title">RECORD LOOKUP FAILED</span>
        </div>
        <div class="feedback-body">
          ${esc(data.message || 'Invalid Participant ID or Access PIN.')}
        </div>
      `, "error");
      return;
    }

    playAudioCue('success');
    renderStudentPass(data.data);
    if (typeof showToast === "function") {
      showToast("Attendance record verified.", "success");
    }
    localStorage.setItem("last_participant_id", participantId);
  } catch (err) {
    playAudioCue('error');
    showFeedback("Network error. Please check your connection and try again.", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span id="btnActionIcon">📊</span> <span id="btnActionText">VIEW MY ATTENDANCE RECORD</span>';
  }
}

// --- Render Verified Digital Student Pass ---
function renderStudentPass(p) {
  const card = document.getElementById("participantRecordCard");
  if (!card) return;

  card.style.display = "block";
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });

  document.getElementById("pFullName").textContent = p.full_name || "--";
  document.getElementById("pCode").textContent = p.participant_id || "--";
  document.getElementById("pOrg").textContent = p.organization || "Independent";
  
  const emailEl = document.getElementById("pEmail");
  if (emailEl) emailEl.textContent = p.email || "";

  const eventEl = document.getElementById("pEventName");
  if (eventEl) eventEl.textContent = `${p.event_code} // ${p.event_name}`;

  // Turnout Percentage & Progress Bar
  const pct = Math.min(100, Math.max(0, p.attendance_percentage || 0));
  document.getElementById("pAttendancePct").textContent = `${pct}%`;
  const pBar = document.getElementById("pProgressBar");
  if (pBar) {
    pBar.style.width = "0%";
    setTimeout(() => {
      pBar.style.width = `${pct}%`;
    }, 60);
  }

  // Summary Metrics
  document.getElementById("pTotalSessions").textContent = p.total_sessions ?? "--";
  document.getElementById("pAttended").textContent = p.sessions_attended ?? "--";
  document.getElementById("pMissed").textContent = p.sessions_missed ?? "--";

  // Session Timeline (Mobile-First Cards)
  const timelineList = document.getElementById("pTimelineList");
  if (!timelineList) return;

  if (!p.history || p.history.length === 0) {
    timelineList.innerHTML = `
      <div class="timeline-empty-card">
        No sessions have been scheduled for this event yet.
      </div>
    `;
    return;
  }

  timelineList.innerHTML = p.history.map(s => {
    const isPresent = s.status === 'Present';
    const isLate = s.status === 'Late';
    const statusClass = isPresent ? 'status-card-present' : (isLate ? 'status-card-late' : 'status-card-absent');
    const badgeClass = isPresent ? 'status-present' : (isLate ? 'status-late' : 'status-absent');

    return `
      <div class="timeline-item-card ${statusClass}">
        <div class="timeline-card-header">
          <strong class="timeline-session-name">${esc(s.session_name)}</strong>
          <span class="status-pill ${badgeClass}">
            ${esc(s.status.toUpperCase())}
          </span>
        </div>
        <div class="timeline-meta-row mono">
          <span>📅 ${esc(s.session_date)}</span>
          <span>⏰ ${esc(s.start_time)} - ${esc(s.end_time)}</span>
        </div>
        <div class="timeline-checkin-row">
          <span class="text-muted" style="font-size: 0.75rem;">Verified Check-in:</span>
          <span class="mono ${s.checkin_time ? 'text-neon font-weight-bold' : 'text-dim'}">
            ${s.checkin_time ? `✓ ${esc(s.checkin_time)}` : '— Not Recorded'}
          </span>
        </div>
      </div>
    `;
  }).join("");
}

function hideStudentPass() {
  const card = document.getElementById("participantRecordCard");
  if (card) card.style.display = "none";
}

// --- Feedback Box Helpers ---
function showFeedback(htmlOrText, type = "error") {
  const box = document.getElementById("portalFeedbackBox");
  if (!box) return;

  box.className = `portal-feedback-card feedback-${type}`;
  box.innerHTML = htmlOrText;
  box.style.display = "block";
}

function hideFeedback() {
  const box = document.getElementById("portalFeedbackBox");
  if (box) {
    box.style.display = "none";
    box.innerHTML = "";
  }
}

function resetUnifiedForm() {
  const form = document.getElementById("formUnifiedPortal");
  if (form) form.reset();
  hideFeedback();
  hideStudentPass();
  document.getElementById("participantIdInput")?.focus();
}

// --- Web Audio Cues ---
let _audioCtx = null;
function getAudioCtx() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!_audioCtx || _audioCtx.state === "closed") {
    try { _audioCtx = new AudioCtx(); } catch (e) { return null; }
  }
  if (_audioCtx.state === "suspended") {
    _audioCtx.resume().catch(() => {});
  }
  return _audioCtx;
}

function playAudioCue(type) {
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    if (type === 'success') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(659.25, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880.00, ctx.currentTime + 0.14);
      gain.gain.setValueAtTime(0.10, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } else if (type === 'warning') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.setValueAtTime(392, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    } else {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(180, ctx.currentTime);
      gain.gain.setValueAtTime(0.07, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.22);
    }
  } catch (e) {}
}

// --- Escape Untrusted Text ---
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
