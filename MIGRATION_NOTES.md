# Architecture migration notes

This migration removes the former utility and embed implementation paths in the same change; no deprecated re-exports are retained.

| Old path | New path |
| --- | --- |
| `hmwz.utils.fetch_channel` | `hmwz.utils.fetchers.fetch_channel` |
| `hmwz.utils.fetch_member` | `hmwz.utils.fetchers.fetch_member` |
| `hmwz.utils.fetch_message` | `hmwz.utils.fetchers.fetch_message` |
| `hmwz.utils.fetch_role` | `hmwz.utils.fetchers.fetch_role` |
| `hmwz.utils.log_interaction`, `hmwz.utils.log_guild` | `hmwz.utils.interactions` |
| `hmwz.hm_models.botembed.BotEmbed` | `hmwz.ui.embeds.create_embed` |
| `hmwz.modules.hs.ephemeral_view.EphemeralView` | `hmwz.ui.components.ephemeral_view.EphemeralView` |
| Temporary message deletion and send mechanics | `hmwz.ui.messages` |
| Repeated donation temporary-response implementations | `hmwz.modules.donation.responses` policy wrapper over `hmwz.ui.messages.send_temporary_response` |

`hmwz.utils.log_decorator` was unused and has been removed. Internal consumers were migrated directly, so the former root `utils.py`, `hm_models.botembed`, and module-local ephemeral view path are removed now rather than kept for a two-release deprecation window. Consumers outside this repository should migrate before taking this release.

Registration keeps its five-second confirmation lifetime as module policy in `modules.registration.responses`; that helper delegates sending and deletion to the central UI API. Future confirmation timing remains a use-case decision, not a UI default.
