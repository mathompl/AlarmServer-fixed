# -*- coding: utf-8 -*-
"""
TPI Command Validator
- Checks command existence
- Checks data length
- Verifies checksum (CRC) when it is present
"""

from __future__ import annotations

import re


def to_chars(string: str) -> list[int]:
    return [ord(char) for char in string]


def get_checksum(code: str, data: str) -> str:
    """Calculate expected TPI checksum"""
    return ("%02X" % sum(to_chars(code) + to_chars(data)))[-2:]


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
    '070': {'min_len': 1, 'max_len': 1, 'desc': 'Single Keystroke'},
    '071': {'min_len': 2, 'max_len': 20, 'desc': 'Send Keystroke String'},
    '072': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Code Programming'},
    '073': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Programming'},
    '074': {'min_len': 1, 'max_len': 1, 'desc': 'Keep Alive'},
    '080': {'min_len': 0, 'max_len': 0, 'desc': 'Request Interior HVAC'},
    '200': {'min_len': 0, 'max_len': 6, 'desc': 'Code Send'},
}


def validate_tpi_command(raw_input: str) -> tuple[bool, str, dict]:
    if not raw_input:
        return False, "Empty command", {}

    cmd_str = raw_input.strip().rstrip('\r\n')

    # Remove optional timestamp
    if re.match(r'^\d{2}:\d{2}:\d{2} ', cmd_str):
        cmd_str = cmd_str[9:]

    if len(cmd_str) < 3:
        return False, "Command too short", {}

    code = cmd_str[:3]
    rest = cmd_str[3:]

    if code not in APPLICATION_COMMANDS:
        return False, f"Unknown command: {code}", {'code': code}

    cmd_info = APPLICATION_COMMANDS[code]
    expected_len = cmd_info['max_len']

    # === Check if checksum is present (last 2 characters) ===
    has_checksum = False
    data = rest
    provided_checksum = None

    if len(rest) == expected_len + 2:
        # Likely command with checksum
        data = rest[:-2]
        provided_checksum = rest[-2:].upper()
        has_checksum = True

    data_len = len(data)

    # Length validation
    if not (cmd_info['min_len'] <= data_len <= cmd_info['max_len']):
        return False, (
            f"{code}: Invalid data length "
            f"(got {data_len}, expected {cmd_info['min_len']}-{cmd_info['max_len']})"
        ), {'code': code}

    # === Verify checksum if it was provided ===
    if has_checksum:
        expected_checksum = get_checksum(code, data)
        if provided_checksum != expected_checksum:
            return False, (
                f"{code}: Checksum mismatch "
                f"(got {provided_checksum}, expected {expected_checksum})"
            ), {'code': code}

    return True, "Valid", {
        'code': code,
        'data': data,
        'description': cmd_info['desc'],
        'has_checksum': has_checksum
    }
