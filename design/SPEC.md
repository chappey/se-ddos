# DroneDash CLE (CLE_DDOS) — System Specification

This living document is the authoritative human-readable specification of the Drone Delivery Operations System (`CLE_DDOS`). It must remain in strict synchronization with the executable formal specification in [`contracts.py`](contracts.py).

---

## 1. Domain Entities & Canonical Attributes

1. **Customer**: `id`, `name`, `email`, `phone`, `addresses` (list of registered delivery addresses).
2. **DeliveryAddress**: `id`, `street`, `city`, `state`, `zip`, `latitude`, `longitude`.
3. **Package**: `id`, `weight_lbs`, `dimensions_inches` (L x W x H), `package_type`, `special_handling`.
4. **Drone**: `id`, `model`, `max_payload_lbs`, `max_flight_range_miles`, `battery_level_pct`, `current_location` (lat/lon), `current_station_id`, `status`, `base_consumption_rate`.
5. **DroneStation**: `id`, `name`, `latitude`, `longitude`, `total_docks`, `available_docks`.
6. **AirspacePolygon**: `id`, `name`, `vertices` (list of GPS coordinates), `is_active`, `restriction_type` (Permanent, Temporary), `bbox` (Axis-Aligned Bounding Box).
7. **DeliveryOrder**: `id`, `customer_id`, `package`, `pickup_address`, `delivery_address`, `priority` (Standard, Express), `created_at_timestamp`, `status`, `assigned_drone_id`, `retry_count`.
8. **Flight**: `id`, `order_id`, `drone_id`, `origin_station_id`, `destination_coords`, `departure_time`, `arrival_time`, `battery_consumed_pct`, `status`.
9. **TelemetryPacket**: `timestamp_sec`, `drone_id`, `phase` (CLIMB, CRUISE, DESCEND, LANDED), `latitude`, `longitude`, `altitude_feet`, `speed_mph`, `battery_pct`, `distance_remaining_miles`.
10. **DeliveryException**: `id`, `order_id`, `drone_id`, `exception_type`, `timestamp`, `resolution_action`, `notes`.
11. **MaintenanceRecord**: `id`, `drone_id`, `start_time`, `end_time`, `technician_notes`, `work_performed`, `post_maintenance_status`.

---

## 2. Order Lifecycle & Transition Invariants

Valid Order Statuses: `REQUESTED`, `ACCEPTED`, `SCHEDULED`, `ASSIGNED`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED`, `FAILED`, `RESCHEDULING_REQUIRED`.

### Transition Matrix:
- `REQUESTED` $\rightarrow$ `ACCEPTED`, `CANCELLED`
- `ACCEPTED` $\rightarrow$ `SCHEDULED`, `CANCELLED`
- `SCHEDULED` $\rightarrow$ `ASSIGNED`, `RESCHEDULING_REQUIRED`, `CANCELLED`
- `ASSIGNED` $\rightarrow$ `IN_TRANSIT`, `SCHEDULED` (reassignment), `CANCELLED`
- `IN_TRANSIT` $\rightarrow$ `DELIVERED`, `FAILED`, `RESCHEDULING_REQUIRED` (RTB abort)
- `RESCHEDULING_REQUIRED` $\rightarrow$ `SCHEDULED`, `CANCELLED`, `FAILED`
- `DELIVERED`, `CANCELLED`, `FAILED` are terminal states.

### Operational Guard Rules:
- **Pre-Transit Cancellation Lockout:** Customers may cancel only while an order is in `REQUESTED`, `ACCEPTED`, `SCHEDULED`, or `ASSIGNED`. Once `IN_TRANSIT`, cancellation is strictly locked out.
- **Rescheduling Retry Threshold:** An order in `RESCHEDULING_REQUIRED` may only be rescheduled if `retry_count < 3`. Upon the 3rd failed attempt (`retry_count >= 3`), the order unconditionally transitions to `FAILED`.

---

## 3. Drone Operational Lifecycle & Transition Invariants

Valid Drone Statuses: `AVAILABLE`, `ASSIGNED`, `IN_FLIGHT`, `CHARGING`, `MAINTENANCE`, `OUT_OF_SERVICE`.

### Transition Matrix:
- `AVAILABLE` $\rightarrow$ `ASSIGNED`, `CHARGING`, `MAINTENANCE`, `OUT_OF_SERVICE`
- `ASSIGNED` $\rightarrow$ `IN_FLIGHT`, `AVAILABLE` (order unassigned/cancelled), `MAINTENANCE`
- `IN_FLIGHT` $\rightarrow$ `AVAILABLE`, `CHARGING`, `MAINTENANCE`
- `CHARGING` $\rightarrow$ `AVAILABLE`, `MAINTENANCE`, `OUT_OF_SERVICE`
- `MAINTENANCE` $\rightarrow$ `CHARGING`, `AVAILABLE`, `OUT_OF_SERVICE`
- `OUT_OF_SERVICE` $\rightarrow$ `MAINTENANCE`

### Operational Guard Rules:
- **Single-Flight Assignment:** Overlapping missions are forbidden. A drone must be `AVAILABLE` and currently docked to receive an assignment.
- **Battery Charging Threshold:** When returning with $\le 60\%$ battery, or idling below operational reserves, drone transitions to `CHARGING` until reaching $100\%$ capacity before becoming `AVAILABLE`.

---

## 4. Spatial Math, Bounding Boxes & Geofencing

1. **Cleveland Operational Bounding Box:**
   All operations, stations, and delivery addresses are constrained to Greater Cleveland:
   $$41.2 \le \text{latitude} \le 41.7, \quad -81.9 \le \text{longitude} \le -81.4$$
2. **Great-Circle Distance:** Computed via the spherical Haversine formula ($R = 3958.8$ statute miles).
3. **Polygon Geofencing (Zero-Dependency):**
   - Each `AirspacePolygon` precomputes an Axis-Aligned Bounding Box (AABB) for $O(1)$ fast rejection.
   - Point-in-polygon queries execute via the standard ray-casting algorithm.
   - Trajectory clearances evaluate segment-segment intersection between the flight vector and all polygon perimeter edges.
4. **Trajectory Invalidation Policy:** Any straight flight leg intersecting an active restricted airspace polygon is immediately disqualified. Orders whose direct route is obstructed are routed to `RESCHEDULING_REQUIRED`.
5. **Canonical Fixtures:**
   - **Station 1 (Downtown Hub):** `(41.4993, -81.6944)`, 5 docks.
   - **Station 2 (University Circle Hub):** `(41.5075, -81.6083)`, 4 docks.
   - **Station 3 (Ohio City Hub):** `(41.4842, -81.7056)`, 3 docks.
   - **Burke Lakefront Airport Airspace (KBKL):** Permanent restricted polygon.
   - **Cleveland Stadium Zone:** Temporary game-day restricted polygon.

---

## 5. Energy Model & Normalized Payload Scaling

Battery consumption scales linearly with the package payload carried relative to airframe capacity:
$$\text{rate}(\text{weight}) = R_{\text{base}} \times \left(1.0 + \frac{\text{package.weight\_lbs}}{\text{drone.max\_payload\_lbs}}\right)$$
- **Unladen Ferry Leg (Station $\to$ Pickup):** $\text{weight} = 0 \implies \text{rate} = R_{\text{base}}$ (nominally $1.5\%$ / mile).
- **Laden Delivery Leg (Pickup $\to$ Destination):** $\text{rate} = R_{\text{base}} \times (1 + \text{ratio})$ (at 100% capacity, consumption is exactly $2 \times R_{\text{base}}$).
- **Unladen Return Leg (Destination $\to$ Recovery Station):** $\text{weight} = 0 \implies \text{rate} = R_{\text{base}}$.
- **Energy Feasibility with 20% Reserve:**
  $$\text{Required Battery Pct} = \text{Leg}_1\text{ energy} + \text{Leg}_2\text{ energy} + \text{Leg}_3\text{ energy} + 20.0\%$$
  A drone cannot be assigned unless $\text{drone.battery\_level\_pct} \ge \text{Required Battery Pct}$.

---

## 6. Scheduling, Dispatch & Multi-Attribute Tie-Breaking

1. **Queue Traversal & Preemption:**
   - Orders are sorted by Priority (`EXPRESS` before `STANDARD`), then FIFO by creation timestamp.
   - **Non-Blocking Traversal:** If the highest-priority pending order cannot currently be assigned (e.g., waiting on charging equipment), the scheduler continues traversing subsequent orders to avoid fleet idle starvation.
2. **Multi-Attribute Drone Ranking:**
   When multiple `AVAILABLE` drones satisfy payload, range, battery reserve, and airspace clearance, candidates are ranked deterministically:
   1. **Proximity-First:** Minimum distance from drone current station to pickup (ascending).
   2. **Payload Fit:** Smallest capacity margin ($\text{max\_payload\_lbs} - \text{package.weight\_lbs}$, ascending) to conserve heavy-lift airframes for heavier cargo.
   3. **Battery Level:** Highest remaining battery percentage (descending) to maximize diversion buffer.
   4. **Deterministic Tie-Break:** Lexicographical order of `drone.id`.

---

## 7. In-Flight Telemetry & Simulation Physics

1. **Discrete Simulation Step:** Telemetry state advances via a 1 Hz discrete simulation tick ($\Delta t = 1.0\text{ s}$).
2. **3-Phase Flight Profile:**
   - **CLIMB:** Vertical ascent at $15\text{ ft/s}$ from $0\text{ ft}$ to cruise altitude ($200\text{ ft}$ AGL).
   - **CRUISE:** Level flight at $30\text{ mph}$ ($44\text{ ft/s}$) at $200\text{ ft}$ AGL along the great-circle track.
   - **DESCEND:** Vertical descent at $15\text{ ft/s}$ initiating at calculated descent threshold distance to land at $0\text{ ft}$.
3. **Telemetry Packet:** Emits structured packets containing timestamp, drone ID, flight phase, GPS position, altitude, ground speed, battery percentage, and remaining distance.

---

## 8. Station Docking & Atomic RTB Mechanics

1. **Atomic Dock Reservation:**
   When an in-flight anomaly (weather, battery advisory, hardware fault) triggers a Return-to-Base (RTB) abort:
   - System queries all stations within remaining battery range having $\text{available\_docks} > 0$.
   - Selects the closest available station.
   - **Immediately reserves the dock** ($\text{available\_docks} \leftarrow \text{available\_docks} - 1$) before beginning transit to eliminate mid-air landing dock contention.
2. **Post-Landing Handoff:**
   - Package is placed into station secure holding storage.
   - Drone transitions to `MAINTENANCE` (or `CHARGING`).
   - Order transitions to `RESCHEDULING_REQUIRED` with incremented `retry_count`.

---

## 9. Technology Stack, Persistence & Deployment Architecture

### 9.1 Core Technology Choices
1. **Toolchain & Environment:**
   - Python 3.10+ managed via the **`uv`** toolchain (`uv sync`, `uv run`).
   - No global pip pollution; locked virtual environment dependencies.
2. **Backend API & Web Server:**
   - **FastAPI**: High-performance asynchronous web framework providing REST endpoints, WebSocket connections, and HTML template rendering.
   - **Uvicorn**: Production-grade ASGI server (`uvicorn src.backend.main:app`).
3. **Frontend Hypermedia Stack (Zero-Build Pipeline):**
   - **Jinja2 + HTMX**: Server-rendered HTML templates utilizing HTMX attributes (`hx-get`, `hx-post`, `hx-swap`) for dynamic table updates and modal dialogs without Node.js or JavaScript bundlers.
   - **Tailwind CSS (CDN)**: Modern utility-first responsive styling without an npm build step.
   - **Leaflet.js (CDN)**: Interactive OpenStreetMap geospatial viewer rendering Cleveland base stations, drone breadcrumbs, and active restricted airspace polygons.
   - **WebSockets (`/ws/telemetry`)**: Low-latency 1 Hz telemetry stream from the backend simulation loop directly driving Leaflet drone map markers and dashboard telemetry HUDs.
4. **Data Persistence Strategy:**
   - **SQLite via SQLModel / SQLAlchemy**: Embedded zero-configuration relational database storing customer accounts, orders, flight histories, and audit records.
   - **Contract Invariant Synchronization**: Application SQLModel models reside in `src/backend/models/` and are verified against `design/contracts.py` invariants via automated parity tests.
   - **Automatic Seeding**: Initial database launch automatically populates the 3 canonical Cleveland base stations and standard restricted airspace boundaries.
5. **Simulation Execution Engine:**
   - **Asyncio Lifespan Task**: Simulation runs as a native FastAPI `@asynccontextmanager` background task in the same process.
   - Eliminates external broker dependencies (no Redis, Celery, or external worker processes).

### 9.2 Deployment & Cloudflare Tunneling
1. **Local Host Execution:**
   - Web application listens locally on `http://127.0.0.1:8000`.
2. **Cloudflare Tunnel (`cloudflared`, Free Tier):**
   - **Ephemeral Quick Tunnel (Zero-Config Demos):**
     `cloudflared tunnel --url http://localhost:8000`
     Exposes a temporary public `https://<random>.trycloudflare.com` URL with automatic TLS termination for remote evaluation and grading presentations.
   - **Persistent Named Tunnel (Staging / Production):**
     Configured via a local `cloudflared.yml` mapping traffic to a dedicated subdomain on a custom domain registered with Cloudflare.

---

## 10. Authentication, Authorization & Identity Management

### 10.1 Primary Authentication Flow: Google OAuth 2.0 (OIDC)
- **Standard Protocol:** Implemented via OpenID Connect (OIDC) discovery (`https://accounts.google.com/.well-known/openid-configuration`) using `authlib`.
- **Session Transport:** Authenticated sessions use signed, `HttpOnly`, `SameSite=Lax` cookies. Client-side JavaScript has zero access to raw credentials or tokens.
- **Auto-Provisioning:** On initial successful Google sign-in, the system automatically checks if a `Customer` record exists for the Google user's verified email. If not, a new `Customer` profile is provisioned with their full name, email, and Google profile picture.

### 10.2 Role-Based Access Control (RBAC)
- **Demo / Guest Customer (Evaluation Persona):**
  - Purpose: Zero-friction audience participation for live classroom demonstrations and rapid grading evaluation.
  - Permitted actions: One-click session initialization, placing simulated delivery orders without financial payment or physical address verification, viewing live order stepper tracking, and testing pre-transit cancellation.
  - Scope: Strictly an evaluation and testing facility; automatically disabled/deprecated in commercial production.
  - Boundary: Strictly isolated to self-owned demo session; zero access to dispatcher operations, fleet telemetry HUD, or other customer records.
- **Customer Role (Registered):**
  - Permitted actions: Register permanent delivery addresses, place orders, cancel orders pre-transit, track own active deliveries, view own historical records.
  - Boundary: Strictly isolated from viewing other customers' records or fleet operations management.
- **Dispatcher / Operations Admin Role:**
  - Permitted actions: View fleet-wide live telemetry, trigger manual drone reassignments, modify restricted airspace zones, view operational audit reports.
  - Assignment: Automatically assigned if the user's email matches an entry in the `ADMIN_EMAILS` environment variable list (or seeded admin table).
- **Maintenance Technician Role:**
  - Permitted actions: Quarantine drones, log maintenance records, release serviced drones back to `AVAILABLE`.

### 10.3 Evaluation & Grader Bypass (Instant Demo Persona Switcher)
To ensure evaluators and course graders are never blocked by OAuth credential configuration or localhost redirect URI mismatches, the application provides pre-configured demo persona endpoints (active in `dev` / demo mode):
- `/auth/demo/customer`: Instantly establishes a session authenticated as the canonical `Cleveland Medical Supplies` persona.
- `/auth/demo/dispatcher`: Instantly establishes a session authenticated as the `Chief Dispatcher` persona with administrative map controls.
- `/auth/demo/technician`: Instantly establishes a session authenticated as a `Lead Maintenance Technician`.

---

## 11. Dispatcher Geospatial UI & Map Visualization

### 11.1 Interactive Canvas
- Built with **Leaflet.js** over OpenStreetMap tiles, centered on Greater Cleveland (`41.4993, -81.6944`, initial zoom 12) bounded by the official operating envelope.
- Responsive split-panel layout: Left/top panel displays live map; right/bottom panel displays order queues and telemetry feeds.

### 11.2 Map Visual Elements & Layer Controls
1. **Base Stations:** Custom hub pin icons displaying station name, total dock capacity, and a live badge of currently available docks (`available_docks / total_docks`).
2. **Active Airframe Markers:**
   - Directional SVG aircraft icons rotated dynamically to flight heading.
   - Status color halos:
     - 🟢 **AVAILABLE**: Solid green badge at station.
     - 🔵 **IN_FLIGHT**: Pulsing blue badge with altitude and speed tooltips.
     - 🟡 **CHARGING**: Amber lightning bolt indicator with live % meter.
     - 🟠 **MAINTENANCE**: Orange wrench indicator.
     - 🔴 **OUT_OF_SERVICE**: Red alert indicator.
3. **Flight Trajectory Lines:**
   - Active missions render dashed polyline routes: Station $\to$ Pickup $\to$ Destination $\to$ Recovery Station.
   - Moving drone marker interpolates smoothly along the path driven by 1 Hz WebSocket updates.
4. **Airspace Restriction Polygons:**
   - Rendered as semi-transparent red/amber polygon overlays with hatched borders.
   - Clicking a zone reveals a popup card showing restriction reason, active hours, and regulatory authority.
5. **Head-Up Display (HUD) Telemetry Overlay:**
   - Floating semi-transparent HUD in the corner of the map displaying selected drone stats:
     - Ground Speed ($30\text{ mph}$)
     - Altitude AGL ($200\text{ ft}$)
     - Battery Gauge with dynamic color gradient ($100\% \to 0\%$)
     - Flight Phase indicator (`CLIMB`, `CRUISE`, `DESCEND`).

---

## 12. Real-Time Event Alerts & Notification Audio

### 12.1 Browser Audio Cues (Web Audio API)
To provide operational situational awareness for dispatchers and customers without constant screen monitoring, the UI generates distinct synthetic browser tones:
- **Order Dispatched:** Brief rising two-tone chime upon takeoff.
- **Delivery Completed:** Harmonic three-tone confirmation chime upon package touchdown.
- **In-Flight Exception / RTB Abort:** Low-frequency pulsing alert tone upon automated Return-to-Base trigger.
- **Audio Mute Toggle:** Persistent user preference toggle in the navigation header to silence audio alerts during silent grading or meetings.

### 12.2 Visual Toast Notifications
- HTMX / Alpine-style floating toast alerts in the upper-right corner for major lifecycle changes (e.g., *"Order ORD-20481 diverted: Return-to-Base initiated to Station 1"*).

---

## 13. Operational Auditing & Data Export

### 13.1 CSV Operational Exports
Administrators and dispatchers can export audit records for external analysis and grading compliance:
1. **Delivery Operations Log (`/api/reports/deliveries.csv`):**
   - Columns: `order_id`, `customer_name`, `priority`, `package_id`, `weight_lbs`, `drone_id`, `pickup_station`, `destination_address`, `distance_miles`, `departure_time`, `arrival_time`, `battery_consumed_pct`, `final_status`.
2. **Operational Exceptions Log (`/api/reports/exceptions.csv`):**
   - Columns: `exception_id`, `order_id`, `drone_id`, `timestamp`, `exception_type`, `battery_at_failure`, `coordinates_at_failure`, `resolution_action`, `diverted_station_id`, `technician_notes`.
3. **Fleet Maintenance Log (`/api/reports/maintenance.csv`):**
   - Columns: `record_id`, `drone_id`, `start_time`, `end_time`, `technician_id`, `issue_description`, `parts_serviced`, `post_maintenance_status`.

### 13.2 Clean Print-to-PDF Formatting
- All operational report views include dedicated CSS `@media print` stylesheets.
- Allows operators to generate clean, professionally paginated PDF reports directly via the browser's native Print dialog (`Ctrl+P` / `Cmd+P`) without requiring server-side headless browser rendering dependencies.

---

## 14. DevOps, Security Controls & Public Internet Hardening

Given that the application will be exposed directly to the public internet via Cloudflare Tunnel (`cloudflared`), the system enforces multi-layered defense-in-depth across the web, application, and network tiers.

### 14.1 Input Validation & Anti-Injection (SQLi & XSS Defense)
1. **Zero Raw SQL / 100% Parameterized Queries:**
   - All persistence queries utilize SQLModel / SQLAlchemy ORM abstractions.
   - Raw SQL string formatting (e.g. `f"SELECT ... WHERE id = '{id}'"`) is strictly forbidden and verified via static analysis.
2. **Jinja2 Autoescape Enforcement:**
   - Jinja2 template environment enforces global HTML autoescaping (`autoescape=True`).
   - Dynamic user-provided text (customer names, delivery notes, package descriptions, exception logs) is automatically escaped prior to DOM insertion.
   - Prohibit the use of `| safe` filter on any user-controllable input strings.
3. **Pydantic Boundary Validation:**
   - Every incoming HTTP request payload (JSON or form body) is parsed through strict Pydantic schemas.
   - Field validations enforce string length caps (e.g., package notes $\le 500$ chars), numeric boundaries (package weight $0 < w \le 50$ lbs), and coordinate boundaries ($41.2 \le \text{lat} \le 41.7$, $-81.9 \le \text{lon} \le -81.4$).
   - Strips malicious control characters and control sequences.

### 14.2 Content Security Policy (CSP) & HTTP Security Headers
All HTTP responses passing through FastAPI pass through a dedicated Security Headers Middleware injecting:
- **`Content-Security-Policy` (CSP):**
  ```http
  default-src 'self';
  script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com;
  style-src 'self' 'unsafe-inline' https://unpkg.com;
  img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com;
  connect-src 'self' wss: ws:;
  font-src 'self' data:;
  frame-ancestors 'none';
  object-src 'none';
  base-uri 'self';
  ```
- **`X-Content-Type-Options: nosniff`**: Prevents MIME-type sniffing exploits.
- **`X-Frame-Options: DENY`**: Protects against clickjacking attacks.
- **`Referrer-Policy: strict-origin-when-cross-origin`**: Prevents leaking sensitive URL paths to third parties.
- **`Permissions-Policy: camera=(), microphone=(), geolocation=()`**: Disables unused browser hardware capabilities.

### 14.3 CSRF & Session Security
1. **HttpOnly Cookie Architecture:**
   - Session tokens are stored exclusively in `HttpOnly`, `SameSite=Lax`, `Secure` (over HTTPS) cookies.
   - Tokens cannot be read by browser JavaScript or malicious XSS snippets.
2. **Cryptographic Signing:**
   - Sessions are signed with HMAC-SHA256 using an external `SECRET_KEY` loaded from environment variables.
3. **HTMX Anti-CSRF Token:**
   - Mutating state operations (POST, PUT, DELETE) require valid session authentication and verify the `HX-Request` header or a synchronized session token to prevent cross-site request forgery.

### 14.4 Ingress Network Architecture & Cloudflare Tunnel Defense
1. **Loopback Host Binding:**
   - The FastAPI/Uvicorn server binds strictly to the host loopback interface (`127.0.0.1:8000`), **never** to `0.0.0.0`.
   - Local LAN devices cannot access the service directly; all external ingress is forced through Cloudflare.
2. **Zero Inbound Open Ports:**
   - `cloudflared` initiates outbound-only encrypted TLS tunnels to the Cloudflare edge.
   - No router port-forwarding, no open firewall ports, and no public IP exposure of the host machine.
3. **Edge DDoS & TLS Termination:**
   - Automatic TLS 1.3 encryption and DDoS mitigation are handled at the Cloudflare network edge before traffic reaches the host.

### 14.5 Rate Limiting & DoS Protection
1. **Application Rate Limiter:**
   - Middleware applies an in-memory sliding window rate limiter:
     - General API read endpoints: 120 requests/minute per client IP.
     - State mutation endpoints (order creation, drone dispatch): 30 requests/minute per client IP.
     - Authentication attempts: 10 requests/minute per client IP.
   - Exceeded limits return `429 Too Many Requests` with a `Retry-After` header.
2. **Simulation Tick Protection:**
   - The 1 Hz background simulation loop runs asynchronously without blocking HTTP request workers.

### 14.6 Authorization & Multi-Tenant Isolation
1. **Customer Record Isolation:**
   - Customer API endpoints enforce strict ownership validation:
     $$\text{current\_user.id} == \text{order.customer\_id}$$
   - Attempting to access an order belonging to another customer unconditionally returns `404 Not Found` (to avoid ID enumeration) or `403 Forbidden`.
2. **Administrative Role Protection:**
   - Dispatcher and maintenance management endpoints enforce `Depends(require_dispatcher_role)` or `Depends(require_technician_role)`.
   - Unauthorized requests immediately terminate with `403 Forbidden` and log a security audit event.

### 14.7 Environment Segregation & Demo Guardrails
1. **Production Mode Locks:**
   - When `ENVIRONMENT=prod`:
     - Demo bypass persona endpoints (`/auth/demo/*`) are **completely disabled**.
     - Swagger UI (`/docs`, `/redoc`, `/openapi.json`) is disabled to prevent automated schema scraping.
     - Database auto-seeding does not overwrite existing data.
2. **Dev / Grading Mode:**
   - When `ENVIRONMENT=dev`:
     - Demo persona switcher buttons are enabled in the UI for instant evaluator grading without Google OAuth credentials.

---

## 15. Production Host Infrastructure & Agent Isolation Runbook

This section formalizes the operational runbook for deploying `CLE_DDOS` onto the production Gentoo Linux host co-located with existing services (e.g., Canvas LMS @ `canvas.nathanchappie.com`). It guarantees that autonomous agents and remote SSH editing cannot compromise host stability, escalate privileges, or interfere with neighboring services.

### 15.1 Host Topology & Co-Location Model
- **Host OS:** Gentoo Linux (AMD64).
- **Internal Network:** Tailscale mesh interface (`100.115.243.43`).
- **Monitoring & Observability Stack:**
  - **Dozzle (Container Log Viewer):** `http://100.115.243.43:8888/`
  - **Uptime Kuma (Service Monitor):** `http://100.115.243.43:3001/dashboard/1`
- **Public Domain Routing:** `nathanchappie.com`
  - `canvas.nathanchappie.com` $\rightarrow$ Canvas LMS container/service.
  - `ddos.nathanchappie.com` $\rightarrow$ `cle_ddos` container service (Port 8000).

### 15.2 Agent Scoping & Unprivileged User Isolation (`ddos`)
To prevent autonomous agents or remote IDE connections from reading or modifying host configurations, personal files, or Canvas data, all remote access is scoped to a dedicated unprivileged user:
1. **User Account Creation:**
   ```bash
   sudo useradd -m -s /bin/bash -c "CLE_DDOS Service Account" ddos
   ```
2. **Filesystem Quarantine:**
   ```bash
   sudo chmod 700 /home/ddos
   sudo chmod 700 /home/chappey
   sudo chmod -R o-rwx /var/www/canvas
   ```
   *Invariant:* The `ddos` user has zero read/write permissions outside of `/home/ddos`.
3. **Dedicated Agent SSH Keypair (Instant Revocation):**
   - The agent uses a distinct keypair (`id_agent_ddos`), never a personal administrator key.
   - Authorized key file: `/home/ddos/.ssh/authorized_keys` (`chmod 600`).
   - If an agent connection must be terminated, deleting the single entry in `authorized_keys` instantly revokes access without affecting personal administrative access.

### 15.3 Containerization & Hard Resource Limits (Cgroups)
To guarantee that runaway simulation loops or memory leaks never starve Canvas LMS or take down the Gentoo kernel, the application runs inside Docker with strict cgroup constraints:
1. **Production Compose Definition (`docker-compose.prod.yml`):**
   ```yaml
   services:
     cle-ddos:
       build: .
       container_name: cle_ddos
       restart: unless-stopped
       ports:
         - "127.0.0.1:8000:8000"
       environment:
         - ENVIRONMENT=prod
         - HOST=0.0.0.0
         - PORT=8000
         - DATABASE_URL=sqlite:////data/dronedash.db
       volumes:
         - ./data:/data
       deploy:
         resources:
           limits:
             cpus: '1.0'
             memory: 512M
           reservations:
             memory: 128M
   ```
2. **Docker Privilege Boundary:**
   To prevent host root escalation via the Docker socket, `ddos` is managed either via:
   - **Rootless Docker:** Daemon runs inside user namespace; container root maps strictly to `ddos` UID on Gentoo.
   - **Scoped Sudo:** If using host Docker daemon, grant sudo access *only* to the specific compose file via `/etc/sudoers.d/ddos`:
     ```sudoers
     ddos ALL=(root) NOPASSWD: /usr/bin/docker compose -f /home/ddos/se-ddos/docker-compose.prod.yml *
     ```

### 15.4 Ingress Routing via Cloudflare Tunnel
1. **Cloudflare Tunnel Ingress Rule:**
   Add ingress mapping in the host `cloudflared` configuration:
   ```yaml
   ingress:
     - hostname: ddos.nathanchappie.com
       service: http://127.0.0.1:8000
     - hostname: canvas.nathanchappie.com
       service: http://127.0.0.1:3000
     - service: http_status:404
   ```
2. **Zero Port Exposure:** No external router ports are opened; traffic is securely proxied over the outbound tunnel.

### 15.5 Health Monitoring & Log Observability
1. **Dozzle Auto-Discovery:**
   - Because `container_name: cle_ddos` is labeled, Dozzle at `http://100.115.243.43:8888/` automatically attaches to container logs. Real-time simulation ticks, exception logs, and API requests are visible immediately.
2. **Uptime Kuma Synthetic Monitor:**
   - Monitor URL: `https://ddos.nathanchappie.com/api/health`
   - Method: HTTP GET (expects status code 200)
   - Interval: 60 seconds
   - Failure Alert: Configured through existing Uptime Kuma notification channels to alert immediately if the service stops responding.

---

## 16. Observability, Telemetry Auditing & Health Monitoring Architecture

Given that `CLE_DDOS` is a simulation-driven system governed by continuous state machine transitions, standard HTTP-level monitoring is insufficient. This section formalizes the application's internal observability, deep health contracts, forensic telemetry buffers, and structured logging.

### 16.1 Deep Health Check Specification (`/api/health`)
To ensure monitoring tools (specifically Uptime Kuma) detect silent background simulation freezes rather than just web server connectivity, the `/api/health` endpoint evaluates three composite operational subsystems:
1. **HTTP/ASGI Layer:** Basic process responsiveness.
2. **Database Engine:** Active SQLite read/write session verification (`SELECT 1`).
3. **Simulation Engine Liveness & Clock Drift:**
   - Validates that the background `asyncio` simulation loop is actively ticking.
   - Calculates **tick drift latency**: $\Delta t_{\text{lag}} = \text{now}() - \text{last\_tick\_timestamp}$.
   - **Contract Invariant:** If the simulation loop has terminated or $\Delta t_{\text{lag}} > 3.0\text{ seconds}$ (missed 3 consecutive 1 Hz ticks), the endpoint unconditionally returns **`503 Service Unavailable`** with an error payload.

#### Response Payload Schema (HTTP 200 OK):
```json
{
  "status": "healthy",
  "environment": "prod",
  "timestamp_utc": "2026-10-07T20:35:00Z",
  "uptime_seconds": 86400,
  "database": {
    "status": "connected",
    "engine": "sqlite"
  },
  "simulation": {
    "is_alive": true,
    "total_ticks": 86400,
    "last_tick_lag_ms": 14,
    "active_flights": 3,
    "drones_in_air": ["DR-17", "DR-04", "DR-09"]
  }
}
```

### 16.2 Structured JSON Logging for Dozzle
To enable rapid incident triage in Dozzle (`http://100.115.243.43:8888/`), the application outputs machine-readable JSON log events to `stdout`. Every log line includes standardized correlation keys for instant full-text and regex filtering:
- **Standard Schema:**
  ```json
  {
    "timestamp": "2026-10-07T20:35:12.104Z",
    "level": "INFO",
    "event": "DRONE_DISPATCHED",
    "order_id": "ORD-20481",
    "drone_id": "DR-17",
    "battery_pct": 94.5,
    "pickup_coords": [41.5075, -81.6083],
    "dest_coords": [41.5034, -81.6550],
    "message": "Drone DR-17 cleared pre-flight checks and departed Station 2 for order ORD-20481"
  }
  ```
- **Standardized Event Tags:**
  `ORDER_ACCEPTED`, `ORDER_SCHEDULED`, `DRONE_ASSIGNED`, `DRONE_DISPATCHED`, `DELIVERY_TOUCHDOWN`, `IN_FLIGHT_EXCEPTION`, `RTB_INITIATED`, `DOCK_RESERVED`, `DRONE_MAINTENANCE_QUARANTINE`, `DRONE_RELEASED`.

### 16.3 In-Flight "Black Box" Forensic Buffer
To support post-incident analysis for dispatchers and course evaluators, the simulation engine maintains a forensic flight recorder:
1. **Circular Ring Buffer:** Each active drone maintains an in-memory ring buffer storing its last **60 telemetry packets** (representing the trailing 60 seconds of flight at 1 Hz).
2. **Freeze on Exception:** When an in-flight anomaly occurs (battery advisory, pop-up restricted airspace, or hardware fault):
   - The ring buffer for that drone is immediately frozen and copied.
   - The trailing 60-second coordinate, altitude, and battery history is serialized into JSON and permanently stored in the `DeliveryException` record.
3. **Forensic UI Inspection:**
   - In the Dispatcher UI and audit logs, clicking an exception renders the exact breadcrumb trajectory leading directly to the abort decision point on the Leaflet map.

### 16.4 Operational KPI & Metrics Endpoint (`/api/stats`)
A lightweight, unauthenticated (or internal) metrics endpoint provides real-time fleet state counters for UI header widgets and monitoring scrapers:
- **Fleet Allocation:** Count of drones currently in `AVAILABLE`, `ASSIGNED`, `IN_FLIGHT`, `CHARGING`, `MAINTENANCE`, `OUT_OF_SERVICE`.
- **Queue Backlog:** Pending order count split by `EXPRESS` and `STANDARD`.
- **Cumulative KPIs:** Total completed deliveries, total RTB aborts, average delivery duration (minutes), and total flight miles logged.

### 16.5 WebSocket Telemetry Drops & Backpressure Policy
1. **Connection Lifecycle Tracking:**
   - System logs client connect/disconnect events to `/ws/telemetry` with remote IP and session identifier.
2. **Drop-Stale Backpressure Policy:**
   - If a connected web browser or mobile client encounters network congestion, the WebSocket broadcaster drops intermediate stale ticks rather than queueing unbounded packets.
   - *Invariant:* Connecting or lagging clients always receive the *most recent* 1 Hz coordinate tick immediately; drones never "rubber-band" across the map upon client reconnection.
