from __future__ import annotations
# -*- coding: utf-8 -*-
"""
TPI Command Validator for Envisalink
Validates commands sent via proxy to the Envisalink module (TPI v1.09 compliant)
"""

import re
from core import logger


def to_chars(string: str) -> list[int]:
    """Convert string to list of ASCII values"""
    return [ord(char) for char in string]


def get_checksum(code: str, data: str) -> str:
    """Calculate TPI checksum (same logic as in envisalink.py)"""
    return ("%02X" % sum(to_chars(code) + to_chars(data)))[-2:]


# Supported Application Commands that can be sent TO Envisalink
APPLICATION_COMMANDS = {
    '000': {'min_len': 0, 'max_len': 0, 'desc': 'Poll'},
    '001': {'min_len': 0, 'max_len': 0, 'desc': 'Status Report'},
    '008': {'min_len': 0, 'max_len': 0, 'desc': 'Dump Zone Timers'},
    '005': {'min_len': 1, 'max_len': 10, 'desc': 'Network Login'},
    '010': {'min_len': 10, 'max_len': 10, 'desc': 'Set Time & Date'},
    '020': {'min_len': 2, 'max_len': 2, 'desc': 'Command Output Control'},
    '030': {'min_len': 1, 'max_len': 1, 'desc': 'Arm Away'},
    '031': {'min_len': 1, 'max_len': 1, 'desc': 'Arm Stay'},
    '032': {'min_len': 1, 'max_len': 1, 'desc': 'Arm Zero Entry Delay'},
    '033': {'min_len': 5, 'max_len': 7, 'desc': 'Arm with Code'},
    '040': {'min_len': 5, 'max_len': 7, 'desc': 'Disarm'},
    '055': {'min_len': 1, 'max_len': 1, 'desc': 'Time Stamp Control'},
    '056': {'min_len': 1, 'max_len': 1, 'desc': 'Time Broadcast Control'},
    '057': {'min_len': 1, 'max_len': 1, 'desc': 'Temperature Broadcast Control'},
    '060': {'min_len': 1, 'max_len': 1, 'desc': 'Trigger Panic'},
    '070': {'min_len': 1, 'max_len': 1, 'desc': 'Single Keystroke (Partition 1)'},
    '071': {'min_len': 2, 'max_len': 7, 'desc': 'Send Keystroke String'},
    '072': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Code Programming'},
    '073': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Programming'},
    '074': {'min_len': 1, 'max_len': 1, 'desc': 'Keep Alive'},
    '080': {'min_len': 0, 'max_len': 0, 'desc': 'Request Interior HVAC'},
    '200': {'min_len': 4, 'max_len': 6, 'desc': 'Code Send'},
}


def validate_tpi_command(raw_input: str) -> tuple[bool, str, dict]:
    """
    Main validation function for TPI commands sent to Envisalink.

    Returns:
        (is_valid: bool, error_message: str, info: dict)
    """
    if not raw_input:
        return False, "Empty command", {}

    cmd_str = raw_input.strip()

    # Remove optional timestamp prefix (e.g. "12:34:56 ")
    if re.match(r'^\d{2}:\d{2}:\d{2} ', cmd_str):
        cmd_str = cmd_str[9:]

    # Remove trailing line endings
    cmd_str = cmd_str.rstrip('\r\n')

    # Must contain only hexadecimal characters
    if not re.match(r'^[0-9A-Fa-f]+$', cmd_str):
        return False, f"Invalid characters (hex digits only): {cmd_str[:30]}", {}

    if len(cmd_str) < 5:
        return False, f"Command too short: {cmd_str}", {}

    code = cmd_str[:3]
    rest = cmd_str[3:]

    if code not in APPLICATION_COMMANDS:
        return False, f"Unknown or unsupported command: {code}", {'code': code}

    if len(rest) < 2:
        return False, "Missing checksum", {'code': code}

    data = rest[:-2]
    provided_cksum = rest[-2:].upper()
    expected_cksum = get_checksum(code, data)

    if provided_cksum != expected_cksum:
        return False, (
            f"Checksum mismatch for command {code}. "
            f"Provided: {provided_cksum}, expected: {expected_cksum} "
            f"(data='{data}')"
        ), {'code': code, 'data': data}

    data_len = len(data)
    cmd_info = APPLICATION_COMMANDS[code]

    if not (cmd_info['min_len'] <= data_len <= cmd_info['max_len']):
        return False, (
            f"Invalid data length for {code} ({cmd_info['desc']}): "
            f"got {data_len}, expected {cmd_info['min_len']}-{cmd_info['max_len']}"
        ), {'code': code, 'data': data}

    # Additional content validation
    content_error = _validate_content(code, data)
    if content_error:
        return False, content_error, {'code': code, 'data': data}

    return True, "Valid", {
        'code': code,
        'data': data,
        'checksum': provided_cksum,
        'description': cmd_info['desc']
    }


def _validate_content(code: str, data: str) -> str | None:
    """Performs additional validation of command data content"""

    if code in ['030', '031', '032', '040', '072', '073', '074']:
        if not data or not data[0].isdigit():
            return f"{code}: Partition must be a digit"
        part = int(data[0])
        if not (1 <= part <= 8):
            return f"{code}: Invalid partition {part} (must be 1-8)"

    if code == '020':
        if len(data) != 2:
            return "Command 020 requires exactly 2 data bytes"
        if not (data[0].isdigit() and 1 <= int(data[0]) <= 8):
            return "020: Invalid partition"
        if not (data[1].isdigit() and 1 <= int(data[1]) <= 4):
            return "020: Invalid output number (must be 1-4)"

    if code == '060':
        if data not in ('1', '2', '3'):
            return "Command 060: Panic type must be 1, 2 or 3"

    if code in ['055', '056', '057']:
        if data not in ('0', '1'):
            return f"Command {code} must be 0 or 1"

    if code == '071':
        if not data or not data[0].isdigit():
            return "071: Must start with partition number (1-8)"
        part = int(data[0])
        if not (1 <= part <= 8):
            return f"071: Invalid partition {part}"
        keys = data[1:]
        if not all(k in '0123456789*#' for k in keys):
            return "071: Invalid characters (only 0-9 * # allowed)"

    if code == '070':
        if not all(k in '0123456789*#' + 'A' for k in data):
            return "070: Invalid characters (only 0-9 * # A allowed)"

    if code == '200':
        if not data.isdigit() or not (4 <= len(data) <= 6):
            return "200: Access code must be 4-6 digits long"

    if code == '010':
        if not data.isdigit() or len(data) != 10:
            return "010: Time must be exactly 10 digits in format hhmmMMDDYY"

    if code == '005':
        if len(data) < 1:
            return "005: Password cannot be empty"

    return None
