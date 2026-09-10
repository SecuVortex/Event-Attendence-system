/**
 * Admin Console Logic for Event Attendance Platform.
 * Manages live QR generation, session activation switches, real-time analytics polling,
 * participant directories with complete session-by-session history, and multi-format exports.
 */

let currentEventId = null;
let currentSessionId = null;
let currentSessionData = null;
let qrInstance = null;
let pollTimer = null;

// On session loss (server restart, expiry), send staff to the login page instead of polling failures
async function fetchWithAuth(input, init) {
  const res = await fetch(input, init);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Authentication required");
  }
  return res;
}

// Escape untrusted text before injecting into innerHTML templates
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initEventHandlers();

  const eventSelect = document.getElementById("eventSelect");
  if (eventSelect && eventSelect.value) {
    currentEventId = parseInt(eventSelect.value);
    loadSessions(currentEventId);
  } else if (eventSelect) {
    // Fresh install: no events yet — show a clear empty state instead of blank KPIs
    const tbody = document.getElementById("liveFeedBody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--muted-gray); padding:24px;">No event selected. Create an event to begin.</td></tr>';
  }

  // Auto-refresh live attendance every 3.5s
  pollTimer = setInterval(() => {
    if (document.getElementById("tabLive")?.classList.contains("active")) {
      refreshAnalytics(false);
    }
  }, 3500);
});

// ----------------- TABS SETUP -----------------
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      if (targetId === "tabAnalytics") {
        refreshAnalytics(true);
      } else if (targetId === "tabParticipants") {
        loadParticipants();
      } else if (targetId === "tabSessions") {
        loadSessionsTable();
      }
    });
  });
}

// ----------------- EVENT LISTENERS -----------------
function initEventHandlers() {
  const eventSelect = document.getElementById("eventSelect");
  if (eventSelect) {
    eventSelect.addEventListener("change", (e) => {
      currentEventId = parseInt(e.target.value);
      loadSessions(currentEventId);
      loadParticipants();
    });
  }

  const sessionSelect = document.getElementById("sessionSelect");
  if (sessionSelect) {
    sessionSelect.addEventListener("change", (e) => {
      currentSessionId = e.target.value ? parseInt(e.target.value) : null;
      onSessionChanged();
    });
  }

  // Toggle Attendance
  const btnToggle = document.getElementById("btnToggleAttendance");
  if (btnToggle) {
    btnToggle.addEventListener("click", toggleSessionAttendance);
  }

  // Regenerate Token
  const btnRegen = document.getElementById("btnRegenerateQR");
  if (btnRegen) {
    btnRegen.addEventListener("click", regenerateQR);
  }

  // Copy Checkin URL
  const btnCopy = document.getElementById("btnCopyCheckinLink");
  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      if (!currentSessionData) { showToast("No session selected.", "warning"); return; }
      const checkinUrl = `${window.location.origin}/checkin?session_id=${currentSessionData.id}&token=${currentSessionData.session_token}`;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(checkinUrl).then(() => {
          showToast("Check-in URL copied to clipboard!", "success");
        }).catch(() => {
          prompt("Copy the check-in URL:", checkinUrl);
        });
      } else {
        prompt("Copy the check-in URL:", checkinUrl);
      }
      // clipboard is unavailable in non-secure contexts (plain LAN IP): fall back to a manual copy prompt
    });
  }

  // Download QR PNG
  const btnDownloadQR = document.getElementById("btnDownloadQR");
  if (btnDownloadQR) {
    btnDownloadQR.addEventListener("click", async () => {
      if (!currentSessionData) { showToast("QR code not ready yet.", "warning"); return; }
      const checkinUrl = `${window.location.origin}/checkin?session_id=${currentSessionData.id}&token=${currentSessionData.session_token}`;
      const qrSrc = `/api/qr?data=${encodeURIComponent(checkinUrl)}&size=14`;
      try {
        const res = await fetch(qrSrc);
        const blob = await res.blob();
        const link = document.createElement("a");
        link.download = `attendance_qr_${currentSessionData.name.replace(/\s+/g, '_')}.png`;
        link.href = URL.createObjectURL(blob);
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 5000);
      } catch(e) {
        showToast("Download failed. Try again.", "error");
      }
    });
  }

  // Participant Search & Org Filter
  const pSearch = document.getElementById("participantSearchInput");
  if (pSearch) {
    pSearch.addEventListener("input", debounce(() => loadParticipants(), 300));
  }
  const orgFilter = document.getElementById("participantOrgFilter");
  if (orgFilter) {
    orgFilter.addEventListener("change", () => loadParticipants());
  }

  // Modals Triggers
  document.getElementById("btnNewSession")?.addEventListener("click", () => openModal("modalNewSession"));
  document.getElementById("btnCreateSessionTab")?.addEventListener("click", () => openModal("modalNewSession"));
  document.getElementById("btnNewEvent")?.addEventListener("click", () => openModal("modalNewEvent"));
  document.getElementById("btnOpenAddParticipant")?.addEventListener("click", () => openModal("modalAddParticipant"));
  document.getElementById("btnOpenBulkParticipant")?.addEventListener("click", () => openModal("modalBulkParticipant"));

  // Form Submissions
  document.getElementById("formCreateSession")?.addEventListener("submit", handleCreateSession);
  document.getElementById("formCreateEvent")?.addEventListener("submit", handleCreateEvent);
  document.getElementById("formAddParticipant")?.addEventListener("submit", handleAddParticipant);
  document.getElementById("btnSubmitBulk")?.addEventListener("click", handleBulkParticipants);

  // Exports
  document.getElementById("btnDownloadCSV")?.addEventListener("click", () => triggerExport("csv"));
  document.getElementById("btnDownloadExcel")?.addEventListener("click", () => triggerExport("excel"));
  document.getElementById("btnDownloadPDF")?.addEventListener("click", () => triggerExport("pdf"));
}

// ----------------- SESSIONS & QR LOGIC -----------------
async function loadSessions(eventId) {
  if (!eventId) return;
  try {
    const res = await fetchWithAuth(`/api/sessions?event_id=${eventId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.success) return;

    const select = document.getElementById("sessionSelect");
    const exportSelect = document.getElementById("exportSessionSelect");
    select.innerHTML = "";
    exportSelect.innerHTML = '<option value="">All Sessions in Event</option>';

    if (data.sessions.length === 0) {
      select.innerHTML = '<option value="">No sessions configured</option>';
      currentSessionId = null;
      currentSessionData = null;
      updateSessionUI();
      refreshAnalytics(true);
      return;
    }

    // Remember which session was active before reload so it stays selected
    const previousId = currentSessionId;

    data.sessions.forEach((s, idx) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = `${s.name} (${s.session_date} ${s.start_time}-${s.end_time})${s.is_active ? ' [ACTIVE]' : ''}`;
      select.appendChild(opt);

      const expOpt = document.createElement("option");
      expOpt.value = s.id;
      expOpt.textContent = s.name;
      exportSelect.appendChild(expOpt);
    });

    const prev = data.sessions.find(s => s.id === previousId);
    const chosen = prev || data.sessions[0];
    currentSessionId = chosen.id;
    currentSessionData = chosen;
    select.value = String(chosen.id);
    updateSessionUI();
    refreshAnalytics(true);
  } catch (err) {
    console.error("Failed to load sessions:", err);
    const select = document.getElementById("sessionSelect");
    if (select) select.innerHTML = '<option value="">Failed to load sessions — retry by switching event</option>';
  }
}

async function onSessionChanged() {
  if (!currentSessionId) return;
  try {
    const res = await fetchWithAuth(`/api/sessions/${currentSessionId}`);
    const data = await res.json();
    if (data.success) {
      currentSessionData = data.session;
      updateSessionUI();
      refreshAnalytics(true);
    }
  } catch (err) {
    console.error("Failed to fetch session detail:", err);
  }
}

function updateSessionUI() {
  const badge = document.getElementById("sessionStatusBadge");
  const btnToggle = document.getElementById("btnToggleAttendance");
  const projectorLink = document.getElementById("btnOpenProjector");
  const qrName = document.getElementById("qrSessionName");
  const qrTime = document.getElementById("qrTimingInfo");

  if (!currentSessionData) {
    badge.className = "status-pill status-inactive";
    badge.innerHTML = '<span>NO ACTIVE SESSION</span>';
    btnToggle.disabled = true;
    qrName.textContent = "No session selected";
    qrTime.textContent = "--";
    return;
  }

  btnToggle.disabled = false;
  projectorLink.href = `/projector?session_id=${currentSessionData.id}`;
  qrName.textContent = currentSessionData.name;
  qrTime.textContent = `Date: ${currentSessionData.session_date} | Window: ${currentSessionData.start_time} - ${currentSessionData.end_time}`;

  if (currentSessionData.is_active) {
    badge.className = "status-pill status-active";
    badge.innerHTML = '<span class="pulse-dot"></span><span>ATTENDANCE: ACTIVE</span>';
    btnToggle.className = "btn btn-danger btn-sm";
    btnToggle.textContent = "DEACTIVATE ATTENDANCE";
  } else {
    badge.className = "status-pill status-inactive";
    badge.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#7A8580;"></span><span>ATTENDANCE: CLOSED</span>';
    btnToggle.className = "btn btn-neon btn-sm";
    btnToggle.textContent = "ACTIVATE ATTENDANCE";
  }

  renderAdminQR();
}

function renderAdminQR() {
  const container = document.getElementById("adminQrCanvas");
  if (!container || !currentSessionData) return;

  // The common QR URL encodes session ID + token (one per session, for all participants)
  const checkinUrl = `${window.location.origin}/checkin?session_id=${currentSessionData.id}&token=${currentSessionData.session_token}`;
  const qrSrc = `/api/qr?data=${encodeURIComponent(checkinUrl)}&size=11`;

  container.innerHTML = `<img id="adminQrImg" src="${qrSrc}" alt="Check-in QR Code"
    style="width:220px;height:220px;display:block;border-radius:4px;"
    onerror="this.style.display='none';this.insertAdjacentHTML('afterend','<div style=\\'color:#ff4444;font-size:0.8rem;padding:1rem;\\'>QR generation failed. Check server.</div>')"
  >`;
}

async function toggleSessionAttendance() {
  if (!currentSessionData) return;
  try {
    const nextState = currentSessionData.is_active ? 0 : 1;
    const res = await fetchWithAuth(`/api/sessions/${currentSessionData.id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: nextState })
    });
    const data = await res.json();
    if (data.success) {
      currentSessionData.is_active = data.is_active ? 1 : 0;
      updateSessionUI();
      showToast(data.message, data.is_active ? "success" : "warning");
      refreshAnalytics(false);
      // Reload session dropdown text
      const opt = document.querySelector(`#sessionSelect option[value="${currentSessionData.id}"]`);
      if (opt) {
        opt.textContent = `${currentSessionData.name} (${currentSessionData.session_date} ${currentSessionData.start_time}-${currentSessionData.end_time})${currentSessionData.is_active ? ' [ACTIVE]' : ''}`;
      }
    }
  } catch (err) {
    showToast("Error toggling attendance state", "error");
  }
}

async function regenerateQR() {
  if (!currentSessionData) return;
  try {
    const res = await fetchWithAuth(`/api/sessions/${currentSessionData.id}/regenerate_token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      currentSessionData.session_token = data.token;
      renderAdminQR();
      showToast("Session QR token regenerated.", "success");
    }
  } catch (err) {
    showToast("Error regenerating token", "error");
  }
}

// ----------------- ANALYTICS & KPIS -----------------
async function refreshAnalytics(updateCharts = false) {
  if (!currentEventId) return;
  const url = `/api/admin/analytics?event_id=${currentEventId}${currentSessionId ? `&session_id=${currentSessionId}` : ''}`;
  try {
    const res = await fetchWithAuth(url);
    const data = await res.json();
    if (!data.success) return;
    const a = data.analytics;

    // Update KPI metrics
    document.getElementById("kpiRegistered").textContent = a.total_registered;
    document.getElementById("kpiPresent").textContent = a.total_present;
    document.getElementById("kpiAbsent").textContent = a.total_absent;
    document.getElementById("kpiPercentage").textContent = `${a.attendance_percentage}%`;
    document.getElementById("kpiCheckins").textContent = a.total_checkins;
    document.getElementById("kpiLate").textContent = a.late_arrivals;
    document.getElementById("kpiDuplicates").textContent = a.duplicate_attempts;
    document.getElementById("kpiInvalid").textContent = a.invalid_attempts;

    // Security tab values
    const auditDup = document.getElementById("auditDupCount");
    if (auditDup) auditDup.textContent = a.duplicate_attempts;
    const auditInv = document.getElementById("auditInvalidCount");
    if (auditInv) auditInv.textContent = a.invalid_attempts;

    // Donut labels
    document.getElementById("donutPresentVal").textContent = a.present_on_time;
    document.getElementById("donutLateVal").textContent = a.late_arrivals;
    document.getElementById("donutAbsentVal").textContent = a.total_absent;
    document.getElementById("txtPeakPeriod").textContent = `Peak: ${a.peak_period}`;

    // Update Live Feed Stream
    renderLiveFeed(a.live_feed);

    // Render Charts
    renderCharts(a);
  } catch (err) {
    console.error("Error refreshing analytics:", err);
  }
}

function renderLiveFeed(feed) {
  const tbody = document.getElementById("liveFeedBody");
  if (!tbody) return;
  if (!feed || feed.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted-gray); padding: 24px;">No check-in records for this session yet.</td></tr>';
    return;
  }

  tbody.innerHTML = feed.map(r => `
    <tr>
      <td class="mono text-muted" style="font-size: 0.8rem;">${esc(r.checkin_time)}</td>
      <td><span class="mono text-neon font-weight-bold">${esc(r.participant_id)}</span></td>
      <td><strong>${esc(r.full_name)}</strong></td>
      <td class="text-muted">${esc(r.organization || 'N/A')}</td>
      <td>
        <span class="status-pill ${r.status === 'Present' ? 'status-present' : 'status-late'}">
          ${esc(r.status.toUpperCase())}
        </span>
      </td>
      <td class="mono text-dim" style="font-size: 0.75rem;">${esc(r.admin_scanner_id)}</td>
    </tr>
  `).join("");
}

// ----------------- VISUALIZATIONS (CANVAS DRAWING) -----------------
function renderCharts(analytics) {
  drawTimelineChart(analytics.attendance_over_time);
  drawSessionsChart(analytics.session_comparison);
  drawDonutChart(analytics.present_on_time, analytics.late_arrivals, analytics.total_absent);
}

function drawTimelineChart(timeline) {
  const canvas = document.getElementById("canvasTimeline");
  if (!canvas) return;
  const parent = canvas.parentElement;
  if (parent && parent.clientWidth > 100) {
    canvas.width = parent.clientWidth;
  }
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);


  if (!timeline || timeline.length === 0) {
    ctx.fillStyle = "#7A8580";
    ctx.font = "13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Check-in timeline data will appear as participants arrive", w / 2, h / 2);
    return;
  }

  const padding = 35;
  const graphW = w - padding * 2;
  const graphH = h - padding * 2;
  const maxVal = Math.max(5, ...timeline.map(t => t.count));

  // Draw axes
  ctx.strokeStyle = "#123B27";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, padding);
  ctx.lineTo(padding, h - padding);
  ctx.lineTo(w - padding, h - padding);
  ctx.stroke();

  // Draw points and line
  const stepX = graphW / Math.max(1, timeline.length - 1);
  ctx.strokeStyle = "#00FF66";
  ctx.lineWidth = 2.5;
  ctx.shadowColor = "rgba(0, 255, 102, 0.4)";
  ctx.shadowBlur = 10;
  ctx.beginPath();

  const coords = [];
  timeline.forEach((item, idx) => {
    const x = padding + idx * stepX;
    const y = (h - padding) - (item.count / maxVal) * graphH;
    coords.push({ x, y, item });
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Fill gradient underneath
  ctx.lineTo(coords[coords.length - 1].x, h - padding);
  ctx.lineTo(coords[0].x, h - padding);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, padding, 0, h - padding);
  grad.addColorStop(0, "rgba(0, 255, 102, 0.2)");
  grad.addColorStop(1, "rgba(0, 255, 102, 0.0)");
  ctx.fillStyle = grad;
  ctx.fill();

  // Draw dots and labels
  ctx.fillStyle = "#00FF66";
  ctx.font = "10px JetBrains Mono";
  ctx.textAlign = "center";
  coords.forEach(pt => {
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#7A8580";
    ctx.fillText(pt.item.time, pt.x, h - padding + 15);
    ctx.fillStyle = "#00FF66";
    ctx.fillText(pt.item.count, pt.x, pt.y - 8);
  });
}

function drawSessionsChart(sessions) {
  const canvas = document.getElementById("canvasSessions");
  if (!canvas) return;
  const parent = canvas.parentElement;
  if (parent && parent.clientWidth > 100) {
    canvas.width = parent.clientWidth;
  }
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);


  if (!sessions || sessions.length === 0) {
    ctx.fillStyle = "#7A8580";
    ctx.font = "13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No sessions available for comparison", w / 2, h / 2);
    return;
  }

  const padding = 35;
  const barWidth = Math.min(60, (w - padding * 2) / (sessions.length * 1.5));
  const maxVal = Math.max(10, ...sessions.map(s => s.total_checkins));

  // Axes
  ctx.strokeStyle = "#123B27";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, h - padding);
  ctx.lineTo(w - padding, h - padding);
  ctx.stroke();

  sessions.forEach((s, idx) => {
    const x = padding + 20 + idx * (barWidth * 1.8);
    const barHeight = (s.total_checkins / maxVal) * (h - padding * 2);
    const y = (h - padding) - barHeight;

    // Draw Bar
    const barGrad = ctx.createLinearGradient(0, y, 0, h - padding);
    barGrad.addColorStop(0, "#00FF66");
    barGrad.addColorStop(1, "#062414");
    ctx.fillStyle = barGrad;
    ctx.fillRect(x, y, barWidth, barHeight);

    // Value on top
    ctx.fillStyle = "#F2F3EF";
    ctx.font = "11px JetBrains Mono";
    ctx.textAlign = "center";
    ctx.fillText(`${s.total_checkins}`, x + barWidth / 2, y - 6);

    // Label on bottom
    ctx.fillStyle = "#7A8580";
    ctx.font = "10px Inter";
    const truncatedName = s.session_name.length > 12 ? s.session_name.substring(0, 10) + '..' : s.session_name;
    ctx.fillText(truncatedName, x + barWidth / 2, h - padding + 16);
  });
}

function drawDonutChart(present, late, absent) {
  const canvas = document.getElementById("canvasDonut");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const total = present + late + absent;
  if (total === 0) {
    ctx.strokeStyle = "#123B27";
    ctx.lineWidth = 20;
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 70, 0, Math.PI * 2);
    ctx.stroke();
    return;
  }

  const segments = [
    { value: present, color: "#00FF66" },
    { value: late, color: "#FFB300" },
    { value: absent, color: "#222a26" }
  ];

  let startAngle = -Math.PI / 2;
  const cx = w / 2;
  const cy = h / 2;
  const radius = 75;
  const lineWidth = 24;

  segments.forEach(seg => {
    if (seg.value === 0) return;
    const sliceAngle = (seg.value / total) * (Math.PI * 2);
    ctx.strokeStyle = seg.color;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, startAngle + sliceAngle);
    ctx.stroke();
    startAngle += sliceAngle;
  });

  // Inner Percentage Text
  const turnoutPct = Math.round(((present + late) / total) * 100);
  ctx.fillStyle = "#00FF66";
  ctx.font = "bold 22px JetBrains Mono";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(`${turnoutPct}%`, cx, cy - 6);
  ctx.fillStyle = "#7A8580";
  ctx.font = "11px Inter";
  ctx.fillText("CHECKED IN", cx, cy + 16);
}

// ----------------- PARTICIPANT DIRECTORY & HISTORY -----------------
async function loadParticipants() {
  if (!currentEventId) return;
  const search = document.getElementById("participantSearchInput")?.value || "";
  const org = document.getElementById("participantOrgFilter")?.value || "ALL";

  try {
    const res = await fetchWithAuth(`/api/participants?event_id=${currentEventId}&search=${encodeURIComponent(search)}&organization=${encodeURIComponent(org)}`);
    const data = await res.json();
    if (!data.success) return;

    const tbody = document.getElementById("participantTableBody");
    if (!tbody) return;

    // Populate Org filter options if needed
    const orgSelect = document.getElementById("participantOrgFilter");
    if (orgSelect && orgSelect.options.length <= 1) {
      const orgs = [...new Set(data.participants.map(p => p.organization).filter(Boolean))];
      orgs.sort().forEach(o => {
        const opt = document.createElement("option");
        opt.value = o;
        opt.textContent = o;
        orgSelect.appendChild(opt);
      });
    }

    if (data.participants.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted-gray); padding: 24px;">No participants match criteria.</td></tr>';
      return;
    }

    // Delegated click handler (bound once) keeps 26+ rows light and ids with quotes safe
    tbody.onclick = (e) => {
      const btn = e.target.closest("button[data-history-pid]");
      if (btn) viewParticipantHistory(btn.getAttribute("data-history-pid"));
    };

    tbody.innerHTML = data.participants.map(p => `
      <tr>
        <td><span class="mono text-neon" style="font-weight:700;">${esc(p.participant_id)}</span></td>
        <td><strong>${esc(p.full_name)}</strong></td>
        <td class="text-muted">${esc(p.email)}</td>
        <td>${esc(p.organization || 'N/A')}</td>
        <td class="mono text-muted" style="font-size:0.8rem;">${esc(p.created_at)}</td>
        <td>
          <button class="btn btn-outline-neon btn-sm" data-history-pid="${esc(p.participant_id)}">
            View History ➔
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Error loading participants:", err);
    const tbody = document.getElementById("participantTableBody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--crimson-danger); padding:24px;">Failed to load directory — check server connection.</td></tr>';
  }
}

async function viewParticipantHistory(participantId) {
  try {
    const res = await fetchWithAuth(`/api/participants/${encodeURIComponent(participantId)}/history`);
    const data = await res.json();
    if (!data.success) {
      showToast(data.message || "Failed to fetch participant history", "error");
      return;
    }

    const h = data.data;
    const modalTitle = document.getElementById("historyModalTitle");
    const modalBody = document.getElementById("historyModalBody");

    modalTitle.innerHTML = `Participant Record: <span class="mono text-neon">${esc(h.participant_id)}</span>`;
    modalBody.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 14px; background: rgba(5,8,7,0.6); border: 1px solid var(--dark-border); border-radius: 8px;">
        <div>
          <h3 style="font-size: 1.2rem; margin-bottom: 4px;">${esc(h.full_name)}</h3>
          <div class="text-muted" style="font-size: 0.85rem;">${esc(h.email)} • ${esc(h.organization || 'Independent')}</div>
        </div>
        <div style="text-align: right;">
          <div class="mono text-neon" style="font-size: 1.6rem; font-weight: 700;">${esc(h.attendance_percentage)}%</div>
          <div class="text-muted" style="font-size: 0.75rem;">ATTENDANCE RATE</div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px;">
        <div style="padding: 10px; background: #050807; border-radius: 6px; text-align: center; border: 1px solid var(--dark-border);">
          <div class="text-muted" style="font-size: 0.7rem;">TOTAL SESSIONS</div>
          <div class="mono" style="font-size: 1.2rem; font-weight: 700;">${h.total_sessions}</div>
        </div>
        <div style="padding: 10px; background: #050807; border-radius: 6px; text-align: center; border: 1px solid var(--dark-border);">
          <div class="text-muted" style="font-size: 0.7rem;">ATTENDED</div>
          <div class="mono text-neon" style="font-size: 1.2rem; font-weight: 700;">${h.sessions_attended}</div>
        </div>
        <div style="padding: 10px; background: #050807; border-radius: 6px; text-align: center; border: 1px solid var(--dark-border);">
          <div class="text-muted" style="font-size: 0.7rem;">MISSED</div>
          <div class="mono text-muted" style="font-size: 1.2rem; font-weight: 700;">${h.sessions_missed}</div>
        </div>
      </div>

      <h4 style="font-size: 0.95rem; margin-bottom: 12px; color: var(--neon-green);">Session-by-Session Attendance Timeline</h4>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Session Name</th>
              <th>Date & Time</th>
              <th>Status</th>
              <th>Verified Check-in Time</th>
            </tr>
          </thead>
          <tbody>
            ${h.history.length === 0 ? `
              <tr><td colspan="4" style="text-align:center; color:var(--muted-gray); padding:20px;">No sessions have been scheduled for this event yet.</td></tr>
            ` : h.history.map(s => `
              <tr>
                <td><strong>${esc(s.session_name)}</strong></td>
                <td class="mono text-muted" style="font-size: 0.8rem;">${esc(s.session_date)} ${esc(s.start_time)}-${esc(s.end_time)}</td>
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
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    openModal("modalParticipantHistory");
  } catch (err) {
    console.error("History fetch error:", err);
    showToast("Error retrieving history", "error");
  }
}

// ----------------- SESSIONS TABLE -----------------
async function loadSessionsTable() {
  if (!currentEventId) return;
  try {
    const res = await fetchWithAuth(`/api/sessions?event_id=${currentEventId}`);
    const data = await res.json();
    if (!data.success) return;

    const tbody = document.getElementById("sessionsTableBody");
    if (!tbody) return;

    if (data.sessions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted-gray); padding: 20px;">No sessions registered yet.</td></tr>';
      return;
    }

    tbody.innerHTML = data.sessions.map(s => `
      <tr>
        <td><strong>${esc(s.name)}</strong></td>
        <td class="mono">${esc(s.session_date)}</td>
        <td class="mono">${esc(s.start_time)} - ${esc(s.end_time)}</td>
        <td class="mono">${esc(s.late_threshold_minutes)} mins</td>
        <td>
          <span class="status-pill ${s.is_active ? 'status-active' : 'status-inactive'}">
            ${s.is_active ? 'ACTIVE' : 'CLOSED'}
          </span>
        </td>
        <td class="mono text-neon">${esc(s.attendance_count)}</td>
        <td>
          <button class="btn btn-sm ${s.is_active ? 'btn-danger' : 'btn-outline-neon'}" onclick="toggleSessionFromTable(${parseInt(s.id, 10)}, ${s.is_active ? 0 : 1})">
            ${s.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Error loading sessions table:", err);
    const tbody = document.getElementById("sessionsTableBody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--crimson-danger); padding:20px;">Failed to load sessions — check server connection.</td></tr>';
  }
}

async function toggleSessionFromTable(sessionId, targetState) {
  try {
    const res = await fetchWithAuth(`/api/sessions/${sessionId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: targetState })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, data.is_active ? "success" : "warning");
      loadSessionsTable();
      if (currentSessionId === sessionId && currentSessionData) {
        currentSessionData.is_active = targetState;
        updateSessionUI();
      }
    } else {
      showToast(data.message || "Failed to update session.", "error");
    }
  } catch (err) {
    showToast("Error updating session", "error");
  }
}

// ----------------- FORM SUBMISSIONS -----------------
async function handleCreateSession(e) {
  e.preventDefault();
  if (!currentEventId) {
    showToast("Please select or create an event first.", "warning");
    return;
  }

  const name = document.getElementById("sessionNameInput").value;
  const date = document.getElementById("sessionDateInput").value;
  const start = document.getElementById("sessionStartInput").value;
  const end = document.getElementById("sessionEndInput").value;
  const grace = parseInt(document.getElementById("sessionGraceInput").value) || 15;

  try {
    const res = await fetchWithAuth("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: currentEventId,
        name: name,
        session_date: date,
        start_time: start,
        end_time: end,
        late_threshold_minutes: grace
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeModal("modalNewSession");
      document.getElementById("formCreateSession").reset();
      await loadSessions(currentEventId);
      loadSessionsTable();
    } else {
      showToast(data.message, "error");
    }
  } catch (err) {
    showToast("Error creating session", "error");
  }
}

async function handleCreateEvent(e) {
  e.preventDefault();
  const name = document.getElementById("eventNameInput").value;
  const code = document.getElementById("eventCodeInput").value;
  const venue = document.getElementById("eventVenueInput").value;
  const start = document.getElementById("eventStartInput").value;
  const end = document.getElementById("eventEndInput").value;
  const desc = document.getElementById("eventDescInput").value;

  try {
    const res = await fetchWithAuth("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        event_code: code,
        venue: venue,
        start_date: start,
        end_date: end,
        description: desc
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeModal("modalNewEvent");
      document.getElementById("formCreateEvent").reset();
      // Add to select and switch
      const select = document.getElementById("eventSelect");
      const opt = document.createElement("option");
      opt.value = data.event_id;
      opt.textContent = `${code} - ${name}`;
      opt.selected = true;
      select.appendChild(opt);
      currentEventId = data.event_id;
      loadSessions(currentEventId);
    } else {
      showToast(data.message, "error");
    }
  } catch (err) {
    showToast("Error creating event", "error");
  }
}

async function handleAddParticipant(e) {
  e.preventDefault();
  if (!currentEventId) return;

  const pid = document.getElementById("partIdInput").value;
  const name = document.getElementById("partNameInput").value;
  const email = document.getElementById("partEmailInput").value;
  const org = document.getElementById("partOrgInput").value;
  const pin = document.getElementById("partPinInput").value;

  try {
    const res = await fetchWithAuth("/api/participants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: currentEventId,
        participant_id: pid,
        full_name: name,
        email: email,
        organization: org,
        password: pin
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeModal("modalAddParticipant");
      document.getElementById("formAddParticipant").reset();
      loadParticipants();
      refreshAnalytics(false);
    } else {
      showToast(data.message, "error");
    }
  } catch (err) {
    showToast("Error registering participant", "error");
  }
}

async function handleBulkParticipants() {
  if (!currentEventId) return;
  const text = document.getElementById("bulkDataInput").value.trim();
  if (!text) {
    showToast("Please enter participant lines.", "warning");
    return;
  }

  const lines = text.split("\n");
  const roster = [];
  const skipped = [];
  lines.forEach((line, i) => {
    const parts = line.split(",").map(p => p.trim());
    if (parts.length >= 3 && parts[0] && parts[1] && parts[2]) {
      if (!parts[4]) {
        // No default PIN: require an explicit one per participant for security
        skipped.push(`Row ${i + 1} (${parts[0]}): missing PIN`);
        return;
      }
      roster.push({
        participant_id: parts[0],
        full_name: parts[1],
        email: parts[2],
        organization: parts[3] || "",
        password: parts[4]
      });
    }
  });

  if (roster.length === 0) {
    showToast("No valid rows parsed. Use comma format with a PIN on every row.", "error");
    if (skipped.length > 0) showToast(skipped[0], "warning");
    return;
  }

  try {
    const res = await fetchWithAuth("/api/participants/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: currentEventId,
        roster: roster
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeModal("modalBulkParticipant");
      document.getElementById("bulkDataInput").value = "";
      loadParticipants();
      refreshAnalytics(false);
      if (data.errors && data.errors.length > 0) {
        showToast(`${data.errors.length} row(s) skipped: ${data.errors[0]}${data.errors.length > 1 ? " …" : ""}`, "warning");
      }
      if (skipped.length > 0) {
        showToast(`${skipped.length} row(s) missing a PIN: ${skipped[0]}${skipped.length > 1 ? " …" : ""}`, "warning");
      }
    } else {
      showToast(data.message || "Import failed.", "error");
    }
  } catch (err) {
    showToast("Error importing bulk participants", "error");
  }
}

// ----------------- EXPORTS -----------------
async function triggerExport(format) {
  if (!currentEventId) return;
  const sessionFilter = document.getElementById("exportSessionSelect")?.value || "";
  const statusFilter = document.getElementById("exportStatusSelect")?.value || "ALL";

  let url = `/api/export/${format}?event_id=${currentEventId}`;
  if (sessionFilter) url += `&session_id=${sessionFilter}`;
  if (statusFilter && statusFilter !== "ALL") url += `&status=${statusFilter}`;

  // Pre-flight with fetch so an expired staff session redirects to /login
  // instead of downloading a JSON error file
  try {
    const res = await fetchWithAuth(url);
    if (!res.ok) {
      showToast(`Export failed (HTTP ${res.status}).`, "error");
      return;
    }
    const blob = await res.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `attendance_report_${format}.${format === "excel" ? "xlsx" : format}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 5000);
  } catch (e) {
    // fetchWithAuth already redirected on 401; anything else is a network problem
  }
}

// ----------------- MODAL HELPERS -----------------
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("open");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("open");
}

// Global modal UX: Esc key closes modal, click outside closes modal
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.querySelectorAll(".modal-overlay.open").forEach(m => m.classList.remove("open"));
  }
});

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-overlay")) {
    e.target.classList.remove("open");
  }
});

// Auto-redraw charts on window resize
window.addEventListener("resize", debounce(() => {
  if (document.getElementById("tabAnalytics")?.classList.contains("active")) {
    refreshAnalytics(true);
  }
}, 250));

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

