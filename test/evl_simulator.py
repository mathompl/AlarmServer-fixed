import socket
import threading
import time
import sys

HOST = '127.0.0.1'
PORT = 4026
PASSWORD = "user"          # Password accepted by the simulator

current_conn = None
lock = threading.Lock()


def calculate_checksum(code, data=""):
    """Calculate checksum according to Envisalink TPI protocol"""
    total = sum(ord(c) for c in code + data) & 0xFF
    return f"{total:02X}"


def send_message(conn, code, data=""):
    """Send a message with correct checksum"""
    checksum = calculate_checksum(code, data)
    message = f"{code}{data}{checksum}\r\n"
    try:
        conn.sendall(message.encode())
        print(f"[TX] {message.strip()}")
    except Exception as e:
        print(f"[ERROR] Send failed: {e}")


def handle_client(conn, addr):
    global current_conn

    with lock:
        current_conn = conn

    print(f"\n[SIM] Client connected from {addr}")

    # Step 1: Send login request (password required)
    send_message(conn, "505", "3")

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            msg = data.decode().strip()
            if not msg:
                continue

            print(f"[RX] {msg}")

            if len(msg) < 5:
                continue

            code = msg[:3]
            data_part = msg[3:-2]
            received_checksum = msg[-2:]

            # Verify checksum
            expected_checksum = calculate_checksum(code, data_part)
            if received_checksum != expected_checksum:
                print(f"[SIM] Invalid checksum! Expected: {expected_checksum}")
                send_message(conn, "501")  # Command Error
                continue

            # === Command handling ===

            if code == "005":  # Login command
                if data_part == PASSWORD:
                    print("[SIM] Login successful")
                    send_message(conn, "505", "1")   # Login success
                else:
                    print("[SIM] Login failed - wrong password")
                    send_message(conn, "505", "0")   # Login failure

            elif code == "000":  # Keepalive / Poll
                send_message(conn, "500")            # ACK

            elif code == "001":  # Status Request
                send_message(conn, "500")

            elif code in ["010", "030", "040"]:  # Arm / Disarm commands
                send_message(conn, "500")
                print(f"[SIM] Received control command: {code} (data: {data_part})")

            else:
                send_message(conn, "500")  # Default ACK for unknown commands

    except Exception as e:
        print(f"[SIM] Connection error: {e}")
    finally:
        with lock:
            if current_conn == conn:
                current_conn = None
        conn.close()
        print(f"[SIM] Client disconnected: {addr}\n")


def close_connection():
    """Manually close the current connection"""
    global current_conn
    with lock:
        if current_conn:
            try:
                current_conn.close()
                print("[SIM] Connection closed manually")
            except:
                pass
            current_conn = None
        else:
            print("[SIM] No active connection")


def trigger_event():
    """Manually trigger events"""
    print("\nAvailable events:")
    print("1 - Zone 1 Alarm (601)")
    print("2 - Zone 1 Restore (602)")
    print("3 - Partition 1 Armed Away (650)")
    print("4 - Partition 1 Disarmed (651)")
    print("5 - Partition 1 In Alarm (670)")
    print("0 - Cancel")

    choice = input("Select event: ").strip()

    with lock:
        if not current_conn:
            print("[SIM] No active connection!")
            return

        if choice == "1":
            send_message(current_conn, "601", "01")   # Zone 1 Alarm
        elif choice == "2":
            send_message(current_conn, "602", "01")   # Zone 1 Restore
        elif choice == "3":
            send_message(current_conn, "650", "11")   # Partition 1 Armed (Away)
        elif choice == "4":
            send_message(current_conn, "651", "1")    # Partition 1 Disarmed
        elif choice == "5":
            send_message(current_conn, "670", "1")    # Partition 1 In Alarm


def command_loop():
    print("\n[SIM] Available commands:")
    print("  close  - Force close current connection")
    print("  event  - Send a manual event")
    print("  quit   - Exit simulator\n")

    while True:
        cmd = input("> ").strip().lower()

        if cmd == "close":
            close_connection()
        elif cmd == "event":
            trigger_event()
        elif cmd == "quit":
            print("Shutting down simulator...")
            sys.exit(0)
        else:
            print("Unknown command. Use: close, event, quit")


def start_simulator():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    print(f"[SIM] Envisalink TPI Simulator running on {HOST}:{PORT}")
    print(f"[SIM] Accepted password: {PASSWORD}")

    # Start command listener in background
    threading.Thread(target=command_loop, daemon=True).start()

    while True:
        conn, addr = server.accept()
        client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        client_thread.start()


if __name__ == "__main__":
    start_simulator()
