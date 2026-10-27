# Shared bot standards refactor report

## Prioritized audit

| Priority | Area and affected files | Finding | Refactor approach |
| --- | --- | --- | --- |
| High | Interaction responses in `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/donation/{module.py,views.py,setup_views.py,commands/*.py}`, `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/registration/{responses.py,commands/*.py,base.py}`, and `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/hs/ephemeral_view.py` | Temporary responses were implemented independently, while callbacks often assumed the initial response or original message was still available. This could produce duplicate-response or deleted-message errors in callbacks and cleanup paths. | Introduce `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/interactions.py` with response/follow-up selection and best-effort defer, response, edit, delete, and temporary-message helpers. Keep old import paths as compatibility exports and route queue/HS views through the centralized implementation. |
| High | `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/registration/commands/csv.py` | CSV values were interpolated into lines, so semicolons, quotes, and newlines were not escaped. Member lookup repeated for each registration row, including alternate accounts for the same member. | Use Python's CSV writer with `;`, and resolve each distinct member once per export (using cache first and fetching only cache misses). |
| High | `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/donation/views.py`, `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/donation/module.py` | Normal setup parsing limits choices to 25, but existing persisted data could still exceed Discord's component capacity and generate too many buttons. | Enforce the 25-button ceiling when constructing views. On oversized choice sets, present one record button and open the amount modal; existing choice validation remains in force. |
| Medium | `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/queue/{module.py,wizard.py,commands/setup.py}` and HS view callbacks | Queue and HS views shared a useful ephemeral-view base, but its message deletion and temporary-response behavior was separate from registration and donation. | Keep the view API compatible while delegating cleanup and response sending to shared helpers. |
| Medium | `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/snapshots/{json_discord.py,registration.py}` | Startup snapshot deduplication is already guarded by a per-client/per-guild lock. A message deleted between fetch and edit could still fail the export. | Preserve existing lock/deduplication behavior and use safe edit with a fresh-message fallback when a tracked snapshot message is no longer editable. |
| Follow-up | `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/queue/module.py` and broader HS/registration command call sites | Many command-specific response and error branches remain intentionally local because they have different modal/edit semantics; not every Discord API call can safely be replaced by one generic response operation. | Migrate those only when their acknowledgement and message-ownership semantics are clear; audit telemetry/validation and additional API fetches as separate focused changes. |

## Shared APIs introduced

`/home/runner/work/HmDcBot/HmDcBot/src/hmwz/interactions.py` now provides:

- `respond` and `defer_interaction` for acknowledgement-aware response delivery.
- `safe_followup` and `send_temporary_followup` for best-effort follow-ups and timed cleanup.
- `send_temporary_response` for short-lived initial or deferred responses.
- `safe_edit_message`, `safe_edit_original_response`, `safe_delete_message`, and `safe_delete_original_response` for stale/deleted message states.
- `schedule_temporary_delete` and `delete_temporary_message` for non-blocking view cleanup.

## Module migration

- **donation:** Removed duplicate temporary-response implementations; used shared cleanup/follow-up helpers. Choice-button views enforce the Discord limit and use a modal fallback for oversized stored option lists.
- **registration:** `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/modules/registration/responses.py` is now a compatibility re-export; migrated CSV serialization to `csv.writer`; de-duplicated per-member lookups and used shared safe message handling in removal callbacks.
- **hs / queue:** Kept the existing `EphemeralView` API, but delegated its response and message lifecycle operations to the common interaction layer. Queue views inherit the centralized behavior.
- **snapshots:** Retained startup lock-based deduplication; added safe tracked-message edits and a fresh-send fallback.

## Validation and remaining work

Regression tests cover the shared interaction lifecycle, deleted-message cleanup, CSV escaping, and oversized donation views; the focused regression set passes (38 tests). Development dependencies were installed from the existing project declarations. `ruff check src tests` and targeted mypy checks for changed production modules pass. The full test suite currently reports three unrelated failures: the HS command registration test expects command names that do not match the registered commands, and two registration-removal tests fail during test setup because the imported app command has no `utils` attribute. Full `mypy` also reports five errors in the untouched Windows-registry handling in `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/token_storage.py`. Whole-repository format check reports formatting differences in the untouched `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/hm_client/commands/purge.py`, `/home/runner/work/HmDcBot/HmDcBot/src/hmwz/i18n/__init__.py`, and `/home/runner/work/HmDcBot/HmDcBot/tests/test_qs_registration.py`; all changed Python files pass format check.

## Optional follow-ups

- Apply acknowledgement-aware response handling to additional command-specific branches after checking their view/modal state transitions.
- Expand tests for the remaining queue and registration edit/defer/follow-up paths.
- Revisit error-result contracts and detailed observability separately; changing those broadly would exceed a safe shared-helper migration.
