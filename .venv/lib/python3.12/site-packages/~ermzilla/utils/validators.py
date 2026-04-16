"""Input validation utilities."""

import re
from pathlib import Path


def validate_host(host: str) -> tuple[bool, str]:
    """Validate hostname or IP address.
    
    Returns:
        (is_valid, error_message)
    """
    if not host:
        return False, "Host is required"
    
    # Check if it's a valid IP address
    ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if re.match(ip_pattern, host):
        parts = host.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return True, ""
        return False, "Invalid IP address"
    
    # Basic hostname validation
    if len(host) > 253:
        return False, "Hostname too long"
    
    if host.startswith("-") or host.endswith("-"):
        return False, "Hostname cannot start or end with hyphen"
    
    return True, ""


def validate_port(port: str) -> tuple[bool, str]:
    """Validate port number.
    
    Returns:
        (is_valid, error_message)
    """
    if not port:
        return False, "Port is required"
    
    try:
        port_num = int(port)
        if not (1 <= port_num <= 65535):
            return False, "Port must be between 1 and 65535"
        return True, ""
    except ValueError:
        return False, "Port must be a number"


def validate_username(username: str) -> tuple[bool, str]:
    """Validate SSH username.
    
    Returns:
        (is_valid, error_message)
    """
    if not username:
        return False, "Username is required"
    
    if len(username) > 32:
        return False, "Username too long (max 32 characters)"
    
    # Basic username validation (alphanumeric, dots, hyphens, underscores)
    if not re.match(r"^[a-zA-Z0-9._-]+$", username):
        return False, "Username contains invalid characters"
    
    return True, ""


def validate_ssh_key_path(key_path: str) -> tuple[bool, str]:
    """Validate SSH key file path.
    
    Returns:
        (is_valid, error_message)
    """
    if not key_path:
        return True, ""  # Optional field
    
    path = Path(key_path).expanduser()
    if not path.exists():
        return False, f"Key file not found: {path}"
    
    if not path.is_file():
        return False, "Path is not a file"
    
    return True, ""
