Да, това е много разумен план:

* за екипа → кратко, човешко описание на български;
* за Codex → по-технически, структурирано EN `INTEGRATION.md`, което да му подаваш като контекст.

Ще ти дам и двете версии. После спокойно можеш да кажеш на Codex: “прочети `INTEGRATION.md` и предложи архитектура/стъбове за AdventurersBG интеграция”.

---

## 1) English – `docs/INTEGRATION_ADVENTURERSBG.md` (for Codex / devs)

````md
# AdventurersBG Integration – Concept

## Overview

FoundryL10n is a local CAT (Computer-Assisted Translation) workstation that:
- loads game text locally (TSV, TXT, JSON),
- uses local LLMs (e.g. Ollama) to draft translations,
- keeps translation memory and history in a local database,
- provides a translator-friendly UI (segments, tags, QA tools).

AdventurersBG is a community translation platform with:
- a public web interface for browsing and submitting translations,
- an editorial workflow where editors review and accept user suggestions,
- per-user attribution (they know who suggested which translation),
- no locking or reservations (multiple users can propose translations for the same segment).

**Goal:**  
Connect FoundryL10n to AdventurersBG so that translators can:
- log in with their AdventurersBG account from the desktop app,
- fetch segments/pages for a specific game,
- translate locally using LLM + CAT features,
- submit translation suggestions back to AdventurersBG,
without bypassing the existing editorial process.

FoundryL10n should **never** directly change the “official” accepted translation – only submit suggestions, same as the web UI.

---

## Roles & Responsibilities

### FoundryL10n (client)
- Handles:
  - local storage (DB) of segments and translations,
  - LLM prompts, drafts, and tag safety,
  - UI, themes, and keyboard workflows,
  - explicit import/export of TSV and suggestions.

- Must:
  - authenticate against AdventurersBG,
  - map remote segments to local records via a stable `segment_id`/`segment_key`,
  - submit suggestions with correct user attribution (through the token),
  - **not** attempt to approve or merge translations.

### AdventurersBG (server)
- Handles:
  - user accounts and authentication,
  - storing original text and all user suggestions,
  - editorial decisions (accepting/overriding translations),
  - displaying history and activity via the website.

- Should provide:
  - a small HTTP API (JSON-based is fine) for:
    - authentication,
    - fetching segments,
    - posting suggestions.

---

## Data Model (client-side view)

Minimum fields per segment (as seen by FoundryL10n):

- `game_id: str` – identifier for the game (e.g. `z5Qkld67`)
- `segment_id: str` – stable, server-assigned ID (preferred over client-side hashes)
- `segment_key: str` – optional additional key (e.g. hash or file:line)
- `source: str` – original text
- `current_translation: str` – currently accepted translation, if any
- `suggestions: list[Suggestion]` (optional, read-only)
  - `user: str`
  - `text: str`
  - `created_at: str`

Client local DB can keep:
- `project_name`
- `target_lang`
- `segment_id` (or `segment_key`)
- `source_text`
- `translation` (local working translation)
- `ai_draft`
- `is_verified`
- history, etc.

A segment is uniquely identified by `(project_name, target_lang, segment_id)`.

---

## API Assumptions (to be confirmed with AdventurersBG)

### Authentication

- `POST /api/login`
  - input: `{ "username": "...", "password": "..." }`
  - output: `{ "token": "...", "user": { "id": ..., "name": "..." } }`
- All subsequent requests:
  - `Authorization: Bearer <token>` or `X-API-Key: <token>`

Server uses the token to associate suggestions with the correct user.

### Fetch segments

Examples:

- By page:

  `GET /api/games/{game_id}/segments?page=278`

- Or by chunk size:

  `GET /api/games/{game_id}/segments?limit=200&offset=0`

Response (example):

```json
{
  "game_id": "z5Qkld67",
  "page": 278,
  "segments": [
    {
      "segment_id": "z5Qkld67:278:001",
      "segment_key": "abc123hash",
      "source": "Close",
      "current_translation": "Затвори",
      "suggestions": [
        {
          "user": "UserA",
          "text": "Затвори",
          "created_at": "2026-01-12T12:34:56"
        }
      ]
    }
  ]
}
````

FoundryL10n:

* imports these segments into its local DB,
* maps them using `segment_id` (preferred) or `segment_key`,
* shows `source` and `current_translation` in the UI.

### Submit suggestions

* `POST /api/games/{game_id}/segments/{segment_id}/suggestions`

Body example:

```json
{
  "text": "Затвори вратата.",
  "notes": "LLM draft + manual corrections",
  "meta": {
    "from_llm": true,
    "client": "FoundryL10n"
  }
}
```

Server:

* records suggestion under the authenticated user,
* exposes it in the normal editorial interface,
* editors continue to accept / reject as usual.

No direct “status=accepted” is allowed from the client.

---

## Client Behavior (FoundryL10n)

### Modes

* **Standalone mode** (no AdventurersBG login):

  * works only with local files (TSV/TXT/JSON),
  * exports TSV to disk.
* **AdventurersBG mode** (user logged in):

  * adds a dedicated “AdventurersBG” panel/tab:

    * select game,
    * fetch segments/page,
    * upload suggestions for current page/chunk.

### Required changes

* Add integration settings:

  * base URL
  * username/password or API token
  * “Test connection”
* Add explicit actions:

  * `Export TSV…` (save to file, not auto-write)
  * `Upload suggestions to AdventurersBG` (using the API)

No automatic background uploads: submissions are explicit user actions.

---

## Non-goals

* No direct modification of official/accepted translations from the desktop app.
* No locking / reservations of segments (multiple users can propose translations).
* No requirement to host LLMs or heavy compute on AdventurersBG – all LLM work remains local.

---
