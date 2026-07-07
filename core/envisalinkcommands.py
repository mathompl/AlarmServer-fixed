evl_ClientCommands = {
    "000": "Poll / Keep-Alive",
    "001": "Status Report",
    "008": "Dump Zone Timers",
    "005": "Network Login",
    "010": "Set Time/Date",
    "020": "Command Output Control",
    "030": "Arm Partition",
    "031": "Arm Partition Stay",
    "032": "Arm Partition Zero Entry Delay",
    "033": "Arm Partition With Code",
    "040": "Disarm Partition",
    "055": "Time Stamp Control",
    "056": "Time Broadcast Control",
    "057": "Temperature Broadcast Control",
    "060": "Trigger Panic Alarm",
    "070": "Single Keystroke (Partition 1)",
    "071": "Send Keystroke String",
    "072": "Enter User Code Programming",
    "073": "Enter User Programming",
    "074": "Keep Alive",
    "080": "Request Interior HVAC Broadcast",
    "200": "Send Code",
    "998": "Malformed command",
    "999": "No connection to EVL"
}


def get_command_name(command: str) -> str:
    if not command:
        return "Empty"
    core = command[:3]
    return evl_ClientCommands.get(core, f"Unknown command ({core})")
