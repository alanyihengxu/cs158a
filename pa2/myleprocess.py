import socket
import threading
import uuid
import json
from pathlib import Path

CONFIG = "config.txt"
BUFFER_SIZE = 1024

class Message:
    uuid: uuid.UUID # indicating the sender’s UUID
    flag: int # representing if the leader is already elected

    def __init__(self, uuid, flag):
        self.uuid = uuid
        self.flag = flag

    def to_json(self) -> str:
        return json.dumps({"uuid": str(self.uuid), "flag": self.flag})

    @staticmethod
    def from_json(json_str: str) -> 'Message':
        data = json.loads(json_str)
        return Message(uuid.UUID(data["uuid"]), data["flag"])

def read_config():
    with open(CONFIG, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError("Config file must contain at least two lines: self and peer.")
        self_entry = lines[0].split(",")
        peer_entry = lines[1].split(",")
        return (self_entry[0].strip(), int(self_entry[1])), (peer_entry[0].strip(), int(peer_entry[1]))

def log(log_path, message: str) -> None:
    path = Path(log_path)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")

def handle_server_thread(server_sock, HOST, PORT):
    # Allow reusing the port immediately after the server stops.
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_sock.bind((HOST, PORT)) 

    # Only expect one client connection, so only need backlog of 1
    server_sock.listen(1)

    print(f"[TCP Server] Listening on port {PORT} ...")

    # Block until client connects, then do not accept new connections (from assignment description)
    global conn # For use in main thread
    conn, addr = server_sock.accept()
    print(f"[TCP Server] Connected by {addr}")

def handle_client_thread(client_sock, HOST, PORT):
    # Only ask for one connection, once established do not ask for a new connection (from assignment description)
    client_sock.connect((HOST, PORT))
    print(f"[TCP Client] Connected to {HOST}:{PORT}")


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_sock:
         # Generate a unique ID
        unique_id = uuid.uuid4()

        # Seperate log file for each process in local demo
        log_path = Path(input("Enter the log file path: ").strip())

        # When a process starts, it should log its id first.
        log(log_path, f"Node started: uuid={unique_id}")

        # Read the server and client host and port from the config file
        server_host, server_port = read_config()[0]
        client_host, client_port = read_config()[1]

        # Spawn separate server and client threads to avoid deadlock when establishing connections
        server_thread = threading.Thread(
            target=handle_server_thread, 
            args=(server_sock, "", server_port) # empty string for host = listen on all network interfaces
        )
        client_thread = threading.Thread(
            target=handle_client_thread, 
            args=(client_sock, client_host, client_port)
        )

        server_thread.start()
        input("press Enter when everyone is ready.") # intentional blocking between .accept() and .connect() for convenience
        client_thread.start()

        # Wait for both threads to finish
        server_thread.join()
        client_thread.join()

        with conn:
            self_flag = 0 # whether this process is still trying to find a leader or knows the leader’s ID
            leader_id = uuid.NIL
            full_data = ""

            # Send uuid as the initial message
            message = Message(unique_id, self_flag)
            client_sock.sendall(message.to_json().encode())

            while self_flag == 0: # No need to continue sending once leader is found
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    print(f"[TCP Server] Client disconnected.")
                    break

                full_data += data.decode()
                if not full_data[-1] == '}': # Check for teminating character
                    continue

                message = Message.from_json(full_data)
                full_data = "" # Reset for next message
                compare_result = "greater" if message.uuid > unique_id else "less" if message.uuid < unique_id else "equal"
                log(log_path, f"Recieved: uuid={message.uuid}, flag={message.flag}, {compare_result}, {self_flag}")

                if compare_result == "equal" or message.flag == 1:
                    # If this process's uuid is able to make it around the full circle, it must have the greatest uuid and thus be the leader
                    # Otherwise, find leader based on message flag
                    self_flag = 1
                    leader_id = message.uuid
                    log(log_path, f"Leader is decided to {message.uuid}.")
                    message = Message(message.uuid, self_flag)
                    client_sock.sendall(message.to_json().encode()) # Send leader to next with flag set to 1
                    log(log_path, f"Sent: uuid={message.uuid}, flag={self_flag}")
                elif compare_result == "greater":
                    # Forward the message
                    client_sock.sendall(message.to_json().encode()) 
                    log(log_path, f"Sent: uuid={message.uuid}, flag={message.flag}")                    
                else:
                    # Ignore message
                    # When a process ignores the message, it should clearly show, on a log file, that the received message was ignored. (from assignment description)
                    log(log_path, f"Ignored: uuid={message.uuid}, flag={message.flag}")   

            # Print leader id when terminating
            print(f"leader is {leader_id}")
