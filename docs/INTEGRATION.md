
# Integration Framework – FoundryL10n

## 1. Overview

FoundryL10n is a local CAT (Computer-Assisted Translation) workstation designed to bridge the gap between web-based community platforms and local LLM workflows.

The app uses a **Provider Plugin Architecture**. Instead of hardcoding website logic, the app loads small configuration files (JSON/JS) that define how to communicate with specific community backends (e.g., the generic POC provider defined in `src/plugins/generic_example.json`).

## 2. The Plugin System

To support a website, a plugin must be added to the `src/plugins` directory. Users can contribute these via Pull Request to the official GitHub repository.

**Canonical schema location**
* **Source of truth:** `src/plugins/schema.json`.
* **Docs copy:** `docs/draft_provider_schema.json` (kept in sync for reference and review).

### Plugin Capabilities

* **Identity:** Name, Website URL, and API Base URL.
* **Authentication:** Defines if the site uses OAuth2, Bearer Tokens, or Session Cookies.
* **Data Mapping:** Maps remote JSON fields (like `original_text`) to local FoundryL10n fields (like `source`).

---

## 3. Architecture Flow (Text Diagram)

```
UI Actions (Fetch / Submit Suggestions / Select Provider)
  ↓
Integration Manager (validates plugin JSON, coordinates sync + offline cache)
  ↓
Active Provider (from plugin config; auth + endpoints + field mapping)
  ↓
Remote API (segments + suggestions endpoints; source of truth)
```

**Behavioral notes**
* **Suggestions-only submissions:** FoundryL10n only posts suggestions, never approves or overrides server decisions.
* **Explicit user-triggered sync:** Fetching and submitting are manual UI actions, not background tasks.
* **Offline-first:** Local edits, drafts, and TM persist offline; sync occurs only when explicitly requested.

**Legend (layer responsibilities + validation)**
* **UI Actions:** User-initiated commands that start fetch/submit flows.
* **Integration Manager:** Validates plugin JSON on load and enforces sync policy (manual-only, suggestions-only).
* **Active Provider:** The currently selected plugin that defines auth, endpoints, and field mapping.
* **Remote API:** External service that stores authoritative translations and accepts suggestions.

## 4. UI/UX – Manual Sync Controls + Segment Status

**Where the actions live**
* **Fetch** and **Submit Suggestions** live in the main toolbar next to the Provider selector, and are duplicated in the **Provider** menu for discoverability.
* Actions are visually grouped with provider state (selector + login) so users understand they are remote operations, not local editing tools.

**When the actions are enabled**
* **Fetch** is enabled only when a valid provider is selected **and** the user is authenticated; it remains disabled for invalid plugins or logged-out states.
* **Submit Suggestions** is enabled only when a provider is active, the user is authenticated, and the current segment has a local draft (or changed target) to submit.
* Both actions are **explicit sync only**: no background fetch, no auto-submit, and no periodic polling.

**Keyboard-first editing protection**
* Sync actions do **not** steal focus from the segment editor or change the active segment.
* Fetch/submit runs are non-modal and report status in the status bar to avoid blocking keyboard navigation.
* Shortcuts (if present) are optional and never override core CAT navigation keys (e.g., segment next/prev, confirm, tag navigation).

**Segment status indicators (remote vs local)**
* Segments originating from a provider show a **remote-synced** indicator (e.g., cloud/check icon) and include the last sync timestamp in tooltip text.
* Segments created locally or without provider metadata show a **local-only** indicator (e.g., local badge); they remain fully editable and are never auto-synced.
* After a successful **Submit Suggestions**, the segment remains editable and retains its local draft state until the next explicit Fetch refreshes remote status.

## 5. Project Context (Provider + Project State Model)

**Provider selection (what it does)**
* Selecting a provider binds the UI to the provider config (auth + endpoints + mapping) and unlocks remote-only actions.
* The selection does **not** mutate local content; it only sets the **remote context** used by manual fetch/submit.
* Provider selection is always explicit; there is no implicit "last-used" reconnect without user action.

**Project context (local-only vs remote)**
* **Local-only project:** No provider is selected; segments are fully local with no remote metadata (`provider_id`/`remote_id` unset).
* **Remote project:** A provider is selected and authenticated; segments can be fetched and carry remote metadata.
* The active project context is reflected in the UI (provider selector state + status bar), but **editing remains available** in both modes.

**Switching between contexts**
* Switching **from local-only → remote** enables fetch/submit actions but does **not** auto-fetch; the segment list remains unchanged until explicit Fetch.
* Switching **from remote → local-only** disables fetch/submit actions and keeps current local edits intact; remote context is cleared from the session, not from stored segments.
* Switching providers (remote → different remote) resets the active remote context and requires an explicit Fetch to avoid mixing segment sets.

**Explicit sync requirements**
* **No auto-sync**: Fetch and Submit Suggestions are **only** triggered by user action.
* Sync status updates happen only after explicit Fetch/Submit completes; no background polling.

**Expected UX behavior**
* Provider switches must **not steal focus** from the segment editor or change the active segment.
* No modal prompts during provider switches; use non-blocking status messaging.
* Fetch/Submit actions never interrupt keyboard-driven navigation (segment next/prev, confirm, tag navigation).

**Workflow risks to avoid**
* **Segment context drift:** Mixing segments from different providers without a clear Fetch boundary can lead to editing the wrong content.
* **Accidental remote assumptions:** Auto-sync or implicit provider switching can cause translators to assume data is shared remotely when it is local-only.
* **Focus loss during navigation:** Any focus change can disrupt fast segment workflows and introduce editing errors.

## 6. Plugin Lifecycle (Discovery → Validation → UI Enablement → Runtime Use)

1. **Discovery**
   * On startup (or refresh), the app scans the `src/plugins` directory for provider JSON files.
   * Each plugin file is paired with the canonical schema at `src/plugins/schema.json`.

2. **Schema Validation**
   * The Integration Manager validates every discovered plugin against the schema.
   * Validation errors are recorded with the plugin name + file path and surfaced in the UI as a non-blocking alert.

3. **Enable/Disable in UI**
   * Valid plugins appear in the provider selector.
   * Invalid plugins are **listed but disabled** (grayed out with a warning icon) and cannot be selected.
   * The UI prevents activation until the plugin passes schema validation.

4. **Runtime Use**
   * Selecting a valid plugin instantiates the provider configuration (auth + endpoints + field mapping).
   * Runtime fetch/submit actions always use the active, validated provider; invalid plugins are never executed.

## 7. Core Implementation Boundaries

### FoundryL10n (The Client)

* **Local Storage:** Manages a local DB for segments, LLM drafts, and Translation Memory.
* **LLM Orchestration:** Handles prompts and tag safety via local models (Ollama).
* **Submission:** Acts as a **Contributor Client**. It submits *Suggestions* only and never attempts to bypass the website’s editorial review.
* **Tag/placeholder protection:** Before LLM calls, tags are masked into `@@PLACEHOLDER_n@@` tokens and the response is validated to ensure all placeholders remain. Missing placeholders trigger a `[TAG ERROR]` prefix in the draft. This behavior is identical for remote-synced segments because only local drafts are masked; fetched remote text is left unchanged.

### External Website (The Server)

* **Authority:** Remains the "Source of Truth" for official translations.
* **User Management:** Handles accounts, reputation, and permissions.
* **API Requirements:** To be compatible, a website should provide:

1. `POST /login`: Returns a token.
2. `GET /segments`: Returns a list of strings for a game/project.
3. `POST /suggestions`: Accepts a translation draft associated with the user's token.

---

## 8. BaseProvider Contract (Abstract Methods + Mapping)

The runtime provider interface is implemented by a **BaseProvider** contract. Plugin JSON defines the concrete endpoints and mapping paths, while the BaseProvider enforces the shape of inputs/outputs so the rest of the app can treat all providers uniformly.

### A. `auth_login`

**Purpose:** Authenticate a user and return an access token (or equivalent session material).

**Inputs**
* `credentials`: object from the login UI (e.g., `username`/`password`, API key).
* `auth.type`: one of `bearer`, `basic`, `oauth2` from the plugin.
* `auth.login_endpoint`: relative or absolute URL used for login.

**Outputs**
* `token`: string (or token payload if provider requires more than a raw string).
* `metadata`: optional details needed by the provider (e.g., token type, expiry).

**Notes**
* Token extraction uses `auth.token_path` when provided.
* Storage is handled by the client (not the provider), but the provider must return a token value.

### B. `fetch_projects`

**Purpose:** List available projects/workspaces on the remote service (when supported).

**Inputs**
* `token`
* `endpoints.fetch_projects` (optional)

**Outputs**
* List of project records, each containing:
  * `project_id` (string)
  * `name` (string)
  * `metadata` (optional)

**Notes**
* If a provider does not support projects, this method returns an empty list and the UI treats it as a single implicit project.

### C. `fetch_segments`

**Purpose:** Retrieve translatable segments for a project or scope.

**Inputs**
* `token`
* `project_id` (optional, depending on provider)
* `endpoints.fetch_segments` (required)
* `pagination` (optional, e.g., `page`)

**Outputs**
* List of local segment records with **mapped fields**:
  * `segment_id`
  * `source`
  * `target`
  * `local_draft` (initialized empty unless provider returns a draft)

**Mapping rules**
* `mapping.source_text` → local `source`
* `mapping.target_text` → local `target`
* `mapping.segment_id` → local `segment_id`

The mapping values are JSON paths (or dot paths) into the provider response. If a mapping key is omitted, the defaults from the schema apply.

### D. `submit_suggestion`

**Purpose:** Submit a translation **suggestion** for a segment.

**Inputs**
* `token`
* `segment_id`
* `suggestion_text` (from local `local_draft` or user edit)
* `endpoints.submit_suggestion` (required)

**Outputs**
* Success indicator and optional server response payload.

**Contract restriction (mandatory)**
* **Suggestions-only:** The provider must submit suggestions only. It must **not** call any endpoint that approves, publishes, or overwrites the server’s accepted translation. The server remains the authority for acceptance.

---

## 9. Data Model (Universal Mapping)

Regardless of the website, FoundryL10n maps data into this internal structure:

| Field | Type | Description |
| --- | --- | --- |
| `provider_id` | string | Unique ID of the website (e.g., `example-provider`) |
| `segment_id` | string | Local segment identifier |
| `remote_id` | string | The server-assigned ID for the string |
| `source` | string | The original text to be translated |
| `target` | string | The current "Accepted" translation on the server |
| `local_draft` | string | The user's current work-in-progress |

**Mapping plan (segments table)**
* Add new nullable columns: `provider_id` and `remote_id`.
* For local-only projects, leave both columns `NULL` by default—local projects remain fully functional without provider metadata.
* Migration note: create the columns with `NULL` defaults and avoid backfilling to prevent breaking existing local data.

---

## 9. Standard API Assumptions

Plugins generally follow this flow:

### A. Authentication

```http
POST /api/login
{ "username": "...", "password": "..." }

```

*App stores the returned `token` securely.*

### B. Fetching Work

```http
GET /api/projects/{id}/segments?page=1

```

The app converts the server's response into the local segment list.

### C. Submitting Progress

```http
POST /api/segments/{id}/suggestions
{
  "text": "Translated text here",
  "metadata": { "tool": "FoundryL10n", "engine": "Llama3" }
}

```

---

## 10. Local Workflow & Safety

* **Explicit Actions:** No background syncing. Users must manually click "Fetch" and "Submit Suggestions."
* **TSV Fallback:** If a website does not have an API, the app provides a high-quality **TSV Import/Export** mode compatible with standard game translation formats.

---

## 11. Project Context State Model (Design)

This section describes how the UI models provider selection and project context, emphasizing offline-first expectations and explicit sync triggers.

### A. Provider Selection (None vs `provider_id`)

* **None (no provider_id):**
  * **Meaning:** The project is local-only. No remote context is attached.
  * **UI affordances:** Provider selector remains available; provider-specific controls are hidden/disabled (login, project picker, fetch/submit buttons, sync badges).
  * **Offline-first expectation:** Local segments and drafts remain fully usable without network access.
* **Provider selected (`provider_id` set):**
  * **Meaning:** The project is bound to a provider plugin and can be connected to a remote service.
  * **UI affordances:** Provider-specific controls appear (login/auth panel, project picker if supported, manual sync actions).
  * **Offline-first expectation:** Selecting a provider does **not** trigger network calls; data remains local until the user explicitly syncs.

### B. Context Switching (Provider/Project Changes)

* **Switching provider:** Clears the active remote context and resets provider-scoped UI (auth state, project selection, sync status). Local edits remain intact and stay in the local DB until explicitly submitted under the new provider context.
* **Switching project (within the same provider):** Updates the active project context; UI shows the new project name and resets segment list to a "not yet fetched" state until the user fetches.
* **UI affordances that appear/disappear:**
  * Project picker only appears if the provider supports projects.
  * Login/auth controls only appear after provider selection.
  * Fetch/Submit buttons are enabled only when a provider is selected and auth is valid.
  * Sync status badges are shown only for provider-bound contexts.

### C. State Transitions and Explicit Sync Triggers

```
No Provider
  └─(Select Provider)─> Provider Selected (Unauthenticated)
        └─(Login/Auth)─> Provider Selected (Authenticated)
              └─(Select Project)─> Project Context Ready (No Data)
                    ├─(Fetch Segments)─> Project Context Active (Local Cache Updated)
                    └─(Import TSV)─> Local Cache Updated (Offline)
Project Context Active
  ├─(Submit Suggestions)─> Remote Suggestion Sync (Manual)
  └─(Switch Provider/Project)─> Context Reset (Local data preserved)
```

**Explicit sync triggers (only):**
* **Fetch Segments** (manual action) → pulls from remote into local cache.
* **Submit Suggestions** (manual action) → sends local drafts as suggestions.
* **Import/Export TSV** (manual action) → offline-first data exchange without remote calls.

**Offline-first expectations:**
* Local drafts are always editable, even when unauthenticated or offline.
* Switching contexts never auto-syncs or discards local work; it only changes which remote context the UI is targeting.
* Sync buttons clearly reflect their manual nature (no background polling).

---

## 12. Security & Credential Storage

FoundryL10n integrates with the host OS keyring/secret storage (Keychain, Credential Manager, Secret Service) for provider credentials. This keeps tokens out of project files while preserving a streamlined login flow.

**Key naming convention**
* Keys are scoped by provider and account: `provider_id + account`.
* `provider_id` matches the plugin identifier (e.g., `example-provider`).
* `account` is the user-facing login identifier (e.g., username or email).

**Fallback behavior**
* If the system keyring is unavailable or blocked, the app falls back to an in-memory session cache for the current runtime only.
* Users must re-authenticate after restart in fallback mode.

**Plain-text storage**
* Tokens are **never** stored in plain text project files or exported data.
