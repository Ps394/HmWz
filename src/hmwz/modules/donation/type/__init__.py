"""Type-specific credit and Rush donation implementations."""


def reset_result_key(
    reset_done: bool, messages_updated: bool, *, export_failed: bool = False
) -> str:
    """Select the shared response for a cycle reset of either donation type."""
    if export_failed:
        return "donation.error.reset_export"
    if not reset_done:
        return "donation.error.reset"
    if messages_updated:
        return "donation.success.reset"
    return "donation.success.reset_overview_failed"
