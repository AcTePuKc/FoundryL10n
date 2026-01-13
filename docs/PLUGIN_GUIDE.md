# Provider Plugin Guide (Community)

This short guide explains how to write a provider plugin so FoundryL10n can talk to your community translation platform. Keep plugins **config-only** and focused on mapping remote data into FoundryL10n’s local CAT workflow.

## 1. Start from the schema

* **Canonical schema:** `src/plugins/schema.json`
* **Docs copy:** `docs/draft_provider_schema.json`

Use the schema as your contract for required fields, valid values, and optional sections.

## 2. Create a plugin file

1. Create a new JSON file in `src/plugins/`.
2. Start with the **metadata** object:
   * `id` (lowercase, dash-separated)
   * `name` (friendly display name)
   * `homepage` (the provider’s website URL)

## 3. Define authentication

Choose an auth type supported by your service (case-sensitive, schema-valid options):

* `bearer` or `Bearer`
* `basic` or `Basic`
* `oauth2` or `OAuth2`

Specify the `login_endpoint` and (if needed) a `token_path` to extract the token from the login response payload.

## 4. Configure endpoints

Define the **endpoints** object:

* `base_url` (the API base, previously referred to as `api_base_url`)
* `fetch_segments`
* `submit_suggestion`

If your service supports project selection, also define `fetch_projects`.

## 5. Map fields to FoundryL10n

Provide the `mapping` object to map remote fields into FoundryL10n’s internal model:
* `segment_id`
* `source_text`
* `target_text`

> Keep mappings simple and explicit. The UI and local DB rely on consistent `segment_id` + `source` values for stable keyboard-driven editing.

## 6. Respect CAT workflow guardrails

FoundryL10n is **offline-first** and **suggestions-only**:

* Sync actions are **manual** (Fetch / Submit Suggestions), never background.
* Providers must **not** publish or approve final translations; they submit **suggestions** only.
* Tag/placeholder safety is enforced locally; keep `source_text` intact so placeholders (e.g., `{0}`) can be preserved.

## 7. Quick checklist before PR

* [ ] Plugin validates against `src/plugins/schema.json`.
* [ ] `id` is unique and stable.
* [ ] Endpoints are relative to `base_url` (or absolute URLs if required).
* [ ] Field mappings resolve cleanly for sample API payloads.
* [ ] Provider only **suggests** translations (no publish/approve calls).

## 8. Contributing

Open a PR with your plugin file and a brief summary of the service, auth type, and example endpoints. Use `docs/INTEGRATION.md` as the deeper reference for architecture expectations and UI behavior.
