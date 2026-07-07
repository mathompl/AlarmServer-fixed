# -*- coding: utf-8 -*-
"""
TPI Command Validator for Envisalink
"""

from __future__ import annotations

import re


def to_chars(string: str) -> list[int]:
    return [ord(char) for char in string]


def get_checksum(code: str, data: str) -> str:
    return ("%02X" % sum(to_chars(code) + to_chars(data)))[-2:]


APPLICATION_COMMANDS = {
    '000': {'min_len': 0, 'max_len': 0, 'desc': 'Poll'},
    '001': {'min_len': 0, 'max_len': 0, 'desc': 'Status Report'},
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
    '071': {'min_len': 2, 'max_len': 20, 'desc': 'Send Keystroke String'},  # zwiększony max
    '072': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Code Programming'},
    '073': {'min_len': 1, 'max_len': 1, 'desc': 'Enter User Programming'},
    '074': {'min_len': 1, 'max_len': 1, 'desc': 'Keep Alive'},
    '080': {'min_len': 0, 'max_len': 0, 'desc': 'Request Interior HVAC'},
    '200': {'min_len': 4, 'max_len': 6, 'desc': 'Code Send'},
}


def validate_tpi_command(raw_input: str) -> tuple[bool, str, dict]:
    if not raw_input:
        return False, "Empty command", {}

    cmd_str = raw_input.strip().rstrip('\r\n')

    # Usuń opcjonalny timestamp
    if re.match(r'^\d{2}:\d{2}:\d{2} ', cmd_str):
        cmd_str = cmd_str[9:]

    code = cmd_str[:3]

    if code not in APPLICATION_COMMANDS:
        return False, f"Unknown command: {code}", {'code': code}

    cmd_info = APPLICATION_COMMANDS[code]
    data_part = cmd_str[3:]

    # === Specjalna obsługa dla komend z klawiszami (070 i 071) ===
    if code in ('070', '071'):
        # Dla 071: pierwszy znak = partition, reszta = klawisze
        if code == '071':
            if not data_part or not data_part[0].isdigit():
                return False, "071: Missing or invalid partition", {'code': code}

            partition = data_part[0]
            keys = data_part[1:]

            if not (1 <= int(partition) <= 8):
                return False, f"071: Invalid partition {partition}", {'code': code}

            # Dozwolone znaki dla 071
            if not all(k in '0123456789*#' for k in keys):
                return False, f"071: Invalid key characters: {keys}", {'code': code}

            return True, "Valid", {
                'code': code,
                'data': data_part,
                'description': cmd_info['desc']
            }

        # 070 - tylko dla partition 1
        if not all(k in '0123456789*#' + 'A' for k in data_part):
            return False, f"070: Invalid characters", {'code': code}

        return True, "Valid", {'code': code, 'data': data_part, 'description': cmd_info['desc']}

    # === Dla pozostałych komend wymagamy hex + checksum ===
    if not re.match(r'^[0-9A-Fa-f]+$', cmd_str):
        return False, f"Invalid characters (hex digits only): {cmd_str[:40]}", {'code': code}

    if len(cmd_str) < 5:
        return False, "Command too short", {'code': code}

    data = cmd_str[3:-2]
    provided_cksum = cmd_str[-2:].upper()
    expected_cksum = get_checksum(code, data)

    if provided_cksum != expected_cksum:
        return False, f"Checksum mismatch for {code}", {'code': code, 'data': data}

    data_len = len(data)
    if not (cmd_info['min_len'] <= data_len <= cmd_info['max_len']):
        return False, (
            f"Invalid data length for {code}: got {data_len}, "
            f"expected {cmd_info['min_len']}-{cmd_info['max_len']}"
        ), {'code': code}

    return True, "Valid", {
        'code': code,
        'data': data,
        'description': cmd_info['desc']
    }
