#!/usr/bin/env bash

HMWZ_DEFAULT_SERVICE_NAME="discordbot-test"

hmwz_service_config_file() {
    local config_home="${XDG_CONFIG_HOME:-${HOME:-}}"
    if [[ -z "$config_home" ]]; then
        echo "Error: HOME or XDG_CONFIG_HOME must be set to store the service name." >&2
        return 1
    fi
    printf '%s/hsbot/service_name' "${config_home%/}"
}

hmwz_normalize_service_name() {
    local name="${1%.service}"
    if [[ ! "$name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
        echo "Error: Invalid service name '$1'. Use letters, numbers, dots, underscores, or hyphens." >&2
        return 1
    fi
    printf '%s.service' "$name"
}

hmwz_resolve_service_name() {
    local requested="${1:-${HMWZ_SERVICE_NAME:-}}"
    local config_file

    config_file="$(hmwz_service_config_file)" || return 1
    if [[ -z "$requested" && -f "$config_file" ]]; then
        IFS= read -r requested < "$config_file" || true
    fi
    if [[ -z "$requested" ]]; then
        requested="$HMWZ_DEFAULT_SERVICE_NAME"
    fi
    hmwz_normalize_service_name "$requested"
}

hmwz_save_service_name() {
    local service_name="$1"
    local config_file
    config_file="$(hmwz_service_config_file)" || return 1

    mkdir -p -- "$(dirname -- "$config_file")"
    printf '%s\n' "$service_name" > "$config_file"
}
