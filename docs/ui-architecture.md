# UI architecture

## Responsibilities and dependencies

- `hmwz.hm_models` contains UI-agnostic domain models, enums, and DTOs. It must not import Discord presentation types or construct embeds.
- `hmwz.ui` owns shared Discord presentation defaults and technical message operations.
- Modules and commands own use-case decisions, text translation, and the choice of when a message or embed is needed. They should use `hmwz.ui` rather than implementing shared styling or message-operation error handling.
- Dependencies flow from modules and commands to `hmwz.ui`; presentation helpers may depend on domain models when needed. Models must not depend on either layer.
- Interaction acknowledgements and followups have Discord-specific response semantics; use the interaction response/followup API for those. Use `hmwz.ui.messages` for ordinary channel messages and persistent-message lifecycle operations.

## Usage

Create embeds through the shared factory so color, footer, and timestamp defaults remain consistent:

```python
from hmwz.ui.embeds import create_embed

embed = create_embed(title=title, description=description)
```

Modules can still choose an explicit color or avatar while the factory supplies the rest of the theme:

```python
embed = create_embed(title=title, color=discord.Color.gold(), client_avatar=avatar)
```

For regular messages, use the wrappers and handle their failure results where the use case needs a fallback:

```python
message = await send_message(channel, embed=embed)
if message is None:
    return False
```

`send_message` and `edit_message` return `None` when Discord reports `NotFound`, `Forbidden`, `RateLimited`, or another `HTTPException`; `delete_message` returns `True` if the message was deleted or was already missing, and `False` for other Discord failures. Interaction responses remain explicit at their call sites.

## Adding UI features

Keep business decisions in the module that owns the use case. Put reusable embed defaults, component behavior, and message mechanics in `hmwz.ui`; pass translated/domain values into those helpers rather than moving business rules into the UI layer. Add or extend UI tests when defaults or Discord error behavior changes.
