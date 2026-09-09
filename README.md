# Cyber-Attend // Modern Event Attendance Management Platform

An event attendance management platform designed for tech symposiums, hackathons, and conferences. Built with a dark cyberpunk aesthetic featuring `#00FF66` neon green accents, subtle glows, and clean typography.

---

## Key System Concepts & Architecture

1. **Single Admin-Generated QR Code per Session**:
   - The admin generates **ONLY ONE** common QR code for the active session.
   - There is **NO** individual QR code per participant.
   - The QR code encodes the session check-in URL and a session token. It identifies the event and session, not the participant.
2. **Secure Participant Authentication (Anti-Spoofing)**:
   - When participants scan the common QR with their mobile phones, the check-in screen opens.
   - The participant authenticates using their unique **Participant ID** (e.g. `TECHSTAR-26-00842`) and **Access PIN / Password** (e.g. `2026`).
   - A participant knowing someone else's ID cannot mark attendance for them without their secret PIN.
3. **Database-Level Unique Constraint**:
   - Enforces `UNIQUE(participant_id, session_id)` in SQLite to guarantee that duplicate attendance records are impossible.
   - Re-attempts return `ALREADY CHECKED IN` with their original check-in timestamp.
4. **Authoritative Server Timestamps**:
   - Attendance timestamps are generated strictly using the backend server clock (`datetime.now()`), preventing device clock spoofing.
5. **Session Gatekeeping**:
   - Only sessions toggled as **Active** by an admin accept check-in requests. Inactive sessions reject submissions immediately.
6. **Reusable & Zero Hardcoding**:
   - Any event and session can be dynamically created with custom dates and time windows.
   - Sample TECHSTAR 2026 data is completely decoupled in `seed_data.py`.

---

## Color Palette

- `#00FF66` — Neon Green (Primary glow, active indicators, metrics)
- `#00E85D` — Bright Green (Hover states & buttons)
- `#050807` — Near Black (Core background)
- `#062414` — Deep Forest Green (Surfaces & headers)
- `#7A8580` — Muted Gray (Secondary labels & text)
- `#F2F3EF` — Off White (Headings & primary copy)
- `#101513` — Dark Charcoal (Card backgrounds & containers)
- `#123B27` — Dark Green Border (Crisp lines & dividers)

---

## User Interfaces

| Page | URL | Purpose |
|------|-----|---------|
| **Admin Console** | `/admin` | Live session switcher, QR generation, real-time check-in ticker, KPIs, analytics charts, participant directory with full history drawer, and CSV/Excel/PDF export center. |
| **Venue Projector** | `/projector` | Dedicated full-screen view for the common session QR code with glowing neon frame and live check-in counter. |
| **Participant Check-in** | `/checkin` | Mobile-optimized check-in screen with credential authentication, duplicate prevention, and instant confirmation. |
| **Participant Portal** | `/participant` | Personal attendance lookup displaying overall attendance percentage, attended/missed counters, and chronological timeline. |

---

## Admin KPIs & Telemetry

- **Total Registered**: Total participants enrolled in the event roster.
- **Total Present**: Verified check-ins for the active session.
- **Total Absent**: Registered participants who have not yet checked in.
- **Attendance %**: Verified turnout percentage.
- **Total Check-ins**: Total check-in transactions recorded.
- **Late Arrivals**: Arrivals past session start time + grace threshold.
- **Duplicate Attempts**: Duplicate check-in attempts blocked by the database unique constraint.
- **Invalid Attempts**: Failed authentications or attempts against closed sessions.

---

## Exporting Reports

- **CSV**: RFC4180 standard comma-separated audit log.
- **Excel (.xlsx)**: Styled spreadsheet using `openpyxl` with dark green headers, neon green fonts, and auto-adjusted column widths.
- **PDF**: Printable landscape audit document generated using `reportlab` with summary statistics and formatted table rows.

---

## Security Model

- **Staff Admin Console (`/admin`, `/projector`)**: protected by server-side session login at `/login`. Participants never see admin links, and every admin API returns `401` without a staff session.
- **Participant Portal (`/participant`)**: PIN-gated. Each participant can only view their own attendance history by entering their Participant ID + Access PIN.
- **Credentials**: All PINs, passwords, and staff passwords are stored as PBKDF2-SHA256 hashes (never plaintext). Legacy plaintext PINs from older databases are upgraded transparently on the next successful login.
- **Bootstrap account**: Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables (in Render's dashboard or your shell) before first launch. Local dev defaults to `admin` / `admin123` — change them before deploying.
- **Session token**: The check-in QR encodes a per-session token; regenerate it from the admin console to instantly invalidate old printed/posted QR codes.

---

## Quick Start Guide

### 1. Run Seed Data (Optional)
To populate sample TECHSTAR 2026 data:
```bash
python seed_data.py
```
*Sample Participant*: `TECHSTAR-26-00842` (Alex Morgan), PIN: `2026`

### 2. Launch the Web Application
```bash
python app.py
```
Or double-click `run.bat` (or execute `start.ps1` in PowerShell).

Open your browser at `http://localhost:5000` — you'll be asked to log in as staff first.

### 3. Deploying to Render (when ready)

A `render.yaml` blueprint is included. Set these environment variables in the Render dashboard:
- `FLASK_SECRET_KEY` (auto-generated by the blueprint)
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — your real staff credentials

The app boots with `gunicorn` and reads `PORT` automatically.
