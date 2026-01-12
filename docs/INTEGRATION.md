
# Integration Framework – FoundryL10n

## 1. Overview

FoundryL10n is a local CAT (Computer-Assisted Translation) workstation designed to bridge the gap between web-based community platforms and local LLM workflows.

The app uses a **Provider Plugin Architecture**. Instead of hardcoding website logic, the app loads small configuration files (JSON/JS) that define how to communicate with specific community backends (e.g., AdventurersBG).

## 2. The Plugin System

To support a website, a plugin must be added to the `/plugins` directory. Users can contribute these via Pull Request to the official GitHub repository.

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

## 4. Core Implementation Boundaries

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

## 5. Data Model (Universal Mapping)

Regardless of the website, FoundryL10n maps data into this internal structure:

| Field | Type | Description |
| --- | --- | --- |
| `provider_id` | string | Unique ID of the website (e.g., `adventurers_bg`) |
| `segment_id` | string | The server-assigned ID for the string |
| `source` | string | The original text to be translated |
| `target` | string | The current "Accepted" translation on the server |
| `local_draft` | string | The user's current work-in-progress |

---

## 6. Standard API Assumptions

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

## 7. Local Workflow & Safety

* **Explicit Actions:** No background syncing. Users must manually click "Fetch" and "Submit Suggestions."
* **TSV Fallback:** If a website does not have an API, the app provides a high-quality **TSV Import/Export** mode compatible with standard game translation formats.

---
