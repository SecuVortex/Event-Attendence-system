/**
 * Participant Portal Handler.
 * PIN-gated personal attendance record: participant ID + Access PIN,
 * with inline error states and session-by-session history rendering.
 */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("formParticipantLookup");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const id = document.getElementById("lookupIdInput").value.trim().toUpperCase();
      const pin = document.getElementById("lookupPinInput").value.trim();
      if (!id || !pin) {
        showLookupError("Please enter both your Participant ID and Access PIN.");
        return;
      }
      fetchParticipantData(id, pin);
    });
  }

  // Only prefill from ?id= query param or remembered ID — never auto-submit,
  // since a PIN is now always required.
  const urlParams = new URLSearchParams(window.location.search);
  const queryId = urlParams.get("id");
  const storedId = localStorage.getItem("last_participant_id");
  const initialId = queryId || storedId || "";

  if (initialId) {
    const input = document.getElementById("lookupIdInput");
    if (input && !input.value) input.value = initialId.toUpperCase();
    document.getElementById("lookupPinInput")?.focus();
  } else {
    document.getElementById("lookupIdInput")?.focus();
  }
});

function showLookupError(message) {
  const box = document.getElementById("lookupErrorBox");
  const text = document.getElementById("lookupErrorText");
  if (!box) return;
  if (text) text.textContent = message;
  box.style.display = "flex";
}

function hideLookupError() {
  const box = document.getElementById("lookupErrorBox");
  if (box) box.style.display = "none";
}

async function fetchParticipantData(participantId, pin) {
  const btn = document.getElementById("btnLookup");
  btn.disabled = true;
  btn.textContent = "Verifying...";

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
      hideRecordCard();
      showLookupError(data.message || "Invalid Participant ID or Access PIN.");
      return;
    }

    hideLookupError();
    renderParticipantPortal(data.data);
    showToast("Record verified. Welcome back!", "success");
    localStorage.setItem("last_participant_id", participantId);
  } catch (err) {
    showLookupError("Network error. Please check your connection and try again.");
  } finally {
    btn.disabled = false;
    btn.textContent = "View My Record";
  }
}

function hideRecordCard() {
  const card = document.getElementById("participantRecordCard");
  if (card) card.style.display = "none";
}

function renderParticipantPortal(p) {
  const card = document.getElementById("participantRecordCard");
  card.style.display = "block";

  document.getElementById("pEventName").textContent = `${p.event_code} // ${p.event_name}`;
  document.getElementById("pFullName").textContent = p.full_name;
  document.getElementById("pCode").textContent = p.participant_id;
  document.getElementById("pOrg").textContent = p.organization || "Independent";
  // BUGFIX: pEmail element now exists in the template; guard keeps older DOM safe
  const emailEl = document.getElementById("pEmail");
  if (emailEl) emailEl.textContent = p.email || "";

  document.getElementById("pAttendancePct").textContent = `${p.attendance_percentage}%`;
  const pBar = document.getElementById("pProgressBar");
  if (pBar) {
    pBar.style.width = "0%";
    setTimeout(() => {
      pBar.style.width = `${Math.min(100, Math.max(0, p.attendance_percentage))}%`;
    }, 50);
  }

  document.getElementById("pTotalSessions").textContent = p.total_sessions;
  document.getElementById("pAttended").textContent = p.sessions_attended;
  document.getElementById("pMissed").textContent = p.sessions_missed;

  const tbody = document.getElementById("pHistoryTableBody");

  if (!p.history || p.history.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--muted-gray); padding: 24px;">No sessions have been scheduled for your event yet.</td></tr>';
    return;
  }

  tbody.innerHTML = p.history.map(s => `
    <tr>
      <td><strong>${esc(s.session_name)}</strong></td>
      <td class="mono text-muted" style="font-size: 0.85rem;">${esc(s.session_date)} • ${esc(s.start_time)} - ${esc(s.end_time)}</td>
      <td>
        <span class="status-pill ${
          s.status === 'Present' ? 'status-present' : (s.status === 'Late' ? 'status-late' : 'status-absent')
        }">
          ${esc(s.status.toUpperCase())}
        </span>
      </td>
      <td class="mono ${s.checkin_time ? 'text-neon' : 'text-dim'}" style="font-size: 0.85rem;">
        ${s.checkin_time ? esc(s.checkin_time) : '—'}
      </td>
    </tr>
  `).join("");
}

// Escape untrusted text before injecting into innerHTML
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
