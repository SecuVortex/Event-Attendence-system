/**
 * Mobile Participant Check-in Handler.
 * Submits participant ID + PIN to server, verifying session status,
 * enforcing duplicate checks, and displaying authoritative confirmation.
 */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("formCheckin");
  if (form) {
    form.addEventListener("submit", handleCheckinSubmit);
  }

  // Auto-uppercase Participant ID input as user types
  const pidInput = document.getElementById("participantIdInput");
  if (pidInput) {
    pidInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.toUpperCase();
    });
  }
});

async function handleCheckinSubmit(e) {
  e.preventDefault();

  const hiddenSessionId = document.getElementById("checkinSessionId")?.value;
  const manualSessionId = document.getElementById("manualSessionIdInput")?.value;
  const sessionId = hiddenSessionId ? parseInt(hiddenSessionId) : (manualSessionId ? parseInt(manualSessionId) : null);

  const participantId = document.getElementById("participantIdInput").value.trim().toUpperCase();
  const pin = document.getElementById("participantPinInput").value.trim();
  const btn = document.getElementById("btnSubmitCheckin");
  const resultBox = document.getElementById("checkinResultBox");

  if (!sessionId) {
    showToast("No active session ID provided. Please scan the venue QR.", "error");
    return;
  }

  if (!participantId || !pin) {
    showToast("Please enter your Participant ID and Access PIN.", "warning");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="pulse-dot"></span> VERIFYING CREDENTIALS...';
  resultBox.style.display = "none";
  resultBox.className = "";

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
      // 1. Success State: ATTENDANCE MARKED
      playChime('success');
      renderSuccessResult(data);
      showToast("Attendance successfully recorded!", "success");
      localStorage.setItem("last_participant_id", participantId);
    } else if (data.status_code === "ALREADY_CHECKED_IN") {
      // 2. Duplicate State: ALREADY CHECKED IN
      playChime('warning');
      renderDuplicateResult(data);
      showToast("Already checked in for this session.", "warning");
    } else if (data.status_code === "SESSION_INACTIVE") {
      // 3. Inactive State: SESSION CLOSED
      playChime('error');
      renderInactiveResult(data);
      showToast("Session attendance is currently inactive.", "error");
    } else {
      // 4. Invalid State: INVALID PARTICIPANT
      playChime('error');
      renderInvalidResult(data);
      showToast(data.message || "Invalid participant credentials.", "error");
    }
  } catch (err) {
    playChime('error');
    renderInvalidResult({ message: "Network connection error. Please verify venue Wi-Fi and try again." });
  } finally {
    btn.disabled = false;
    btn.textContent = "VERIFY & MARK ATTENDANCE";
  }
}

// Reuse a single AudioContext — browsers cap the number of contexts per page
let _audioCtx = null;
function getAudioCtx() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!_audioCtx || _audioCtx.state === "closed") {
    try {
      _audioCtx = new AudioCtx();
    } catch (e) {
      return null;
    }
  }
  // Browsers start contexts suspended until a user gesture; resume opportunistically
  if (_audioCtx.state === "suspended") {
    _audioCtx.resume().catch(() => {});
  }
  return _audioCtx;
}

function playChime(type) {
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    if (type === 'success') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(659.25, ctx.currentTime); // E5
      osc.frequency.exponentialRampToValueAtTime(880.00, ctx.currentTime + 0.14); // A5
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

// Escape untrusted text before injecting into innerHTML
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function resetCheckinForm() {
  document.getElementById("formCheckin").reset();
  document.getElementById("checkinResultBox").style.display = "none";
  document.getElementById("participantIdInput").focus();
}

function renderSuccessResult(data) {
  const box = document.getElementById("checkinResultBox");
  box.className = "result-card result-success";
  box.style.display = "block";

  box.innerHTML = `
    <div style="font-size: 2.5rem; color: var(--neon-green); margin-bottom: 8px; line-height: 1;">✓</div>
    <h3 style="color: var(--neon-green); font-weight: 800; letter-spacing: 0.05em; font-size: 1.25rem; margin-bottom: 16px;">
      ATTENDANCE MARKED
    </h3>

    <div style="background: rgba(5,8,7,0.7); border: 1px solid var(--dark-border); border-radius: 10px; padding: 16px; text-align: left; display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between;">
        <span class="text-muted" style="font-size: 0.8rem;">Participant Name:</span>
        <strong style="color: var(--off-white);">${esc(data.participant_name)}</strong>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span class="text-muted" style="font-size: 0.8rem;">Participant ID:</span>
        <span class="mono text-neon font-weight-bold">${esc(data.participant_id)}</span>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span class="text-muted" style="font-size: 0.8rem;">Session:</span>
        <span>${esc(data.session_name)}</span>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span class="text-muted" style="font-size: 0.8rem;">Check-in Time:</span>
        <span class="mono" style="color: var(--off-white);">${esc(data.checkin_time)}</span>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span class="text-muted" style="font-size: 0.8rem;">Status:</span>
        <span class="status-pill ${data.status === 'Present' ? 'status-present' : 'status-late'}">
          ${esc(data.status.toUpperCase())}
        </span>
      </div>
    </div>

    <div style="display: flex; gap: 10px;">
      <a href="/participant?id=${encodeURIComponent(data.participant_id)}" class="btn btn-outline-neon btn-sm" style="flex: 1;">
        View History ➔
      </a>
      <button type="button" onclick="resetCheckinForm()" class="btn btn-secondary btn-sm" style="flex: 1;">
        + Check in Next
      </button>
    </div>
  `;
}

function renderDuplicateResult(data) {
  const box = document.getElementById("checkinResultBox");
  box.className = "result-card result-duplicate";
  box.style.display = "block";

  box.innerHTML = `
    <div style="font-size: 2.2rem; color: var(--amber-warning); margin-bottom: 8px; line-height: 1;">⚠</div>
    <h3 style="color: var(--amber-warning); font-weight: 800; letter-spacing: 0.05em; font-size: 1.2rem; margin-bottom: 12px;">
      ALREADY CHECKED IN
    </h3>

    <p style="font-size: 0.85rem; color: var(--off-white); margin-bottom: 14px;">
      Your attendance for <strong>${esc(data.session_name || 'this session')}</strong> was already recorded.
    </p>

    <div style="background: rgba(5,8,7,0.7); border: 1px solid rgba(255,179,0,0.3); border-radius: 8px; padding: 12px; text-align: left; display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px;">
      <div style="display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;">
        <span class="text-muted" style="font-size: 0.8rem;">Participant:</span>
        <span style="text-align: right;">${esc(data.participant_name)} (${esc(data.participant_id)})</span>
      </div>
      <div style="display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;">
        <span class="text-muted" style="font-size: 0.8rem;">Previous Check-in:</span>
        <span class="mono text-neon" style="text-align: right;">${esc(data.previous_checkin_time)}</span>
      </div>
    </div>

    <div class="text-dim" style="font-size: 0.75rem;">
      Duplicate attendance records for the same session are strictly prevented.
    </div>
  `;
}

function renderInactiveResult(data) {
  const box = document.getElementById("checkinResultBox");
  box.className = "result-card result-invalid";
  box.style.display = "block";

  box.innerHTML = `
    <div style="font-size: 2.2rem; color: var(--crimson-danger); margin-bottom: 8px; line-height: 1;">✕</div>
    <h3 style="color: var(--crimson-danger); font-weight: 800; letter-spacing: 0.05em; font-size: 1.2rem; margin-bottom: 10px;">
      SESSION INACTIVE
    </h3>
    <p style="font-size: 0.85rem; color: var(--off-white);">
      ${esc(data.message || 'Attendance is currently closed for this session. Please wait for the event administrator to open check-in.')}
    </p>
  `;
}

function renderInvalidResult(data) {
  const box = document.getElementById("checkinResultBox");
  box.className = "result-card result-invalid";
  box.style.display = "block";

  box.innerHTML = `
    <div style="font-size: 2.2rem; color: var(--crimson-danger); margin-bottom: 8px; line-height: 1;">✕</div>
    <h3 style="color: var(--crimson-danger); font-weight: 800; letter-spacing: 0.05em; font-size: 1.2rem; margin-bottom: 10px;">
      INVALID PARTICIPANT
    </h3>
    <p style="font-size: 0.85rem; color: var(--off-white); margin-bottom: 8px;">
      ${esc(data.message || 'Verification failed. Participant ID or Access PIN does not match event roster.')}
    </p>
    <div class="text-dim" style="font-size: 0.75rem;">
      Please verify your Participant ID format or consult the event registration desk.
    </div>
  `;
}
