
# Integration Framework – FoundryL10n

## 1. Overview

FoundryL10n is a local CAT (Computer-Assisted Translation) workstation designed to bridge the gap between web-based community platforms and local LLM workflows.

The app uses a **Provider Plugin Architecture**. Instead of hardcoding website logic, the app loads small configuration files (JSON/JS) that define how to communicate with specific community backends (e.g., AdventurersBG).

## 2. The Plugin System

To support a website, a plugin must be added to the `/plugins` directory. Users can contribute these via Pull Request to the official GitHub repository.

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

## 4. Plugin Lifecycle (Discovery → Validation → UI Enablement → Runtime Use)

1. **Discovery**
   * On startup (or refresh), the app scans the `/plugins` directory for provider JSON files.
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

## 5. Core Implementation Boundaries

### FoundryL10n (The Client)

* **Local Storage:** Manages a local DB for segments, LLM drafts, and Translation Memory.
* **LLM Orchestration:** Handles prompts and tag safety via local models (Ollama).
* **Submission:** Acts as a **Contributor Client**. It submits *Suggestions* only and never attempts to bypass the website’s editorial review.

### External Website (The Server)

* **Authority:** Remains the "Source of Truth" for official translations.
* **User Management:** Handles accounts, reputation, and permissions.
* **API Requirements:** To be compatible, a website should provide:

1. `POST /login`: Returns a token.
2. `GET /segments`: Returns a list of strings for a game/project.
3. `POST /suggestions`: Accepts a translation draft associated with the user's token.

---

## 6. BaseProvider Contract (Abstract Methods + Mapping)

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

## 7. Data Model (Universal Mapping)

Regardless of the website, FoundryL10n maps data into this internal structure:

| Field | Type | Description |
| --- | --- | --- |
| `provider_id` | string | Unique ID of the website (e.g., `adventurers_bg`) |
| `segment_id` | string | The server-assigned ID for the string |
| `source` | string | The original text to be translated |
| `target` | string | The current "Accepted" translation on the server |
| `local_draft` | string | The user's current work-in-progress |

---

## 8. Standard API Assumptions

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

## 9. Local Workflow & Safety

* **Explicit Actions:** No background syncing. Users must manually click "Fetch" and "Submit Suggestions."
* **TSV Fallback:** If a website does not have an API, the app provides a high-quality **TSV Import/Export** mode compatible with standard game translation formats.

---
