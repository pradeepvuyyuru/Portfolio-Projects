#!/usr/bin/env python3
import argparse
import socket
import sys
import select


# Global state: start in IDLE and move to WAIT/CHAT as commands come in
chat_socket = None
listen_socket = None  # we need when we are in WAIT mode and accepting a peer
peer_id = None
peer_ip = None
peer_port = None
state = "IDLE"
client_id = None



CRLF = "\r\n"

"""Open a TCP connection to the rendezvous server, send one message, leave the socket open to read ACK."""
def send_to_server(server_ip, server_port, message):
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, server_port))
        s.sendall(message.encode())
        #s.close()
        # removed the close here because we need to be able to read REGACK and BRIDGEACK
        return s
    except socket.error as e:
        print(f"Socket error: {e}", file=sys.stderr)
        return None




def build_register(client_id, my_ip, my_port):
    return (
        "REGISTER" + CRLF +
        f"clientID: {client_id}" + CRLF +
        f"IP: {my_ip}" + CRLF +
        f"Port: {my_port}" + CRLF +
        CRLF
    )


def build_bridge(client_id):
    return (
        "BRIDGE" + CRLF +
        f"clientID: {client_id}" + CRLF +
        CRLF
    )
    
def build_chat(client_id):
    return (
        "CHAT" + CRLF + f"clientID: {client_id}" + CRLF + CRLF
        
    )

def chat_loop(sock):
    
    sockets = [sock,sys.stdin]
    
    while True:
        readable, _ , _ = select.select(sockets,[],[]) 
        for s in readable:
            if s is sock:
                # incoming chat data from peer
                data = sock.recv(4096)
                if not data:
                    print("No data")
                    sys.exit(0)
                msg = data.decode().strip()
                if msg == "CHAT_START":
                    print("CHAT_START received")
                    continue
                if msg == "QUIT":
                    print("Peer ended chat")
                    sys.exit(0)
                print(msg)
            elif s is sys.stdin:
                # our turn to type; send to peer
                user_input = sys.stdin.readline().strip()
                
                if user_input == "/quit":
                    sock.sendall(b"QUIT\n")
                    print("Quitting chat.")
                    sys.exit(0)

                msgformat = f"{client_id}> {user_input}"
                sock.sendall(msgformat.encode())
                #print(msg)




# this just parses the incoming headers
# it splits the message up and grabs any lines that look like dictionary values 
# key: value  
def parse_headers(msg):
    headers = {}
    lines = msg.split(CRLF)
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers


# WAIT mode: bind/listen on our port and accept incoming peer connection
def enter_wait_mode(my_port,my_ip,client_id):
    
    global listen_socket, chat_socket, state

    print(f"{client_id} IN WAIT MODE")

    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        listen_socket.bind(("", my_port))
    except OSError as e:
        print("Error binding to port:", e, file=sys.stderr)
        sys.exit(1)

    # Now we start listening. Just 1 connection max for now, thats all we need I think
    listen_socket.listen(1)
    #print(client_id)
    #print("Listening for an incoming peer connection")

    # accept() blocks until someone connects.
    conn, addr = listen_socket.accept()
    #print(client_id)
    #print(f"Accepted connection from {addr}")

    # Now that we have a peer, this cleans the listening socket
    listen_socket.close()
    listen_socket = None

    # Save this new connection so CHAT mode can use it later.
    chat_socket = conn
    state = "CONNECTED"
    
    #this is how we get the chat handshake from our peer
    data = chat_socket.recv(4096)
    msg = data.decode().strip()
    print(msg)
    #print("Received chat request:", msg)
    
    # our chat request should have our clientID

    #print(f"Incoming chat request from {client_id} {my_ip}:{my_port}")

    chat_loop(chat_socket)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Client ID")
    parser.add_argument("--port", required=True, type=int, help="Client listening port")
    parser.add_argument(
        "--server",
        required=True,
        help="Server in form ip:port (e.g. 127.0.0.1:5555)",
    )

    args = parser.parse_args()
    global client_id 
    client_id = args.id
    my_port = args.port

    # Parse server IP and port
    try:
        server_ip, server_port_str = args.server.split(":")
        server_port = int(server_port_str)
        if server_port < 1024:
            print("Known Port, permission failed")
            sys.exit(0)
    except ValueError:
        print("Error: --server must be in format ip:port", file=sys.stderr)
        sys.exit(1)
    
    # Default MAC, I will change when testing on VM
    my_ip = socket.gethostbyname(socket.gethostname())

    print(f"{client_id} running on {my_ip}:{my_port}")
    #while True:
    try:
        for line in sys.stdin:
            cmd = line.strip()

            if cmd == "/id":
                print(client_id)

            elif cmd == "/register":
                # Send REGISTER and read REGACK
                msg = build_register(client_id, my_ip, my_port)
                s = send_to_server(server_ip, server_port, msg)
                if not s:
                    continue
                
                # this it receive a REGACK message from the server
                response = s.recv(4096).decode()
                s.close()
                # this bascially reads the response from the server
                # parses it
                # then prints any debug stuff for us
                #reg_info = parse_headers(response)
                #print("[DEBUG] REGACK:", reg_info)

            elif cmd == "/bridge":
                # Send BRIDGE and either enter WAIT or store peer info
                msg = build_bridge(client_id)
                s = send_to_server(server_ip, server_port, msg)
                if not s:
                    continue
                
                response = s.recv(4096).decode()
                s.close()
            
                
                bridgeinfo = parse_headers(response) #for debugging
                #print("[DEBUG BRIDGEACK]", bridgeinfo)
                
                # update the global variables
                global peer_id, peer_ip, peer_port, state
                peer_id = bridgeinfo.get("clientID", "")
                peer_ip = bridgeinfo.get("IP", "")
                peer_port = bridgeinfo.get("Port", "")
                
                # if our BRIDGEACK didn't give us any peer info, we enter WAIT mode again
                if peer_ip ==  "" or peer_port == "":
                    #print("[DEBUG] Could not find a peer conenction. Entering WAIT mode")
                    enter_wait_mode(my_port, my_ip, client_id)
                #if we did find a peer connection
                    #this lets us receive BRIDGEACK, print the parsed headers and lets us detect wether theres a peer connection or not
            elif cmd == "/chat":
                # Initiate chat to known peer; send a simple handshake line
                chatmsg = f"Incoming chat request from {client_id} {my_ip}:{int(my_port)}"
                print(my_port)
                print(peer_ip)
                print(client_id)
                #chat_socket.sendall(chatmsg.encode())
                
                chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    chat_socket.connect((peer_ip, int(peer_port)))
                    chat_socket.sendall(chatmsg.encode())
                except socket.error as e:
                    print(f"Socket error: {e}", file=sys.stderr)
                    return None
                
                #chat_socket.sendall(b"CHAT_START\n")
                print("IN CHAT MODE")
                print("IN WRITE MODE")
                chat_loop(chat_socket)
                continue
                
                
                

            else:
                print("Incorrect command")
    except KeyboardInterrupt:
        print("Exiting program")
        sys.exit(0)

if __name__ == "__main__":
    main()
