import socket             
import argparse
import sys
import select

CRLF = "\r\n"
# Track simple state for demo: first/second client info and registered map
client1_ip = None
client1_id = None
client1_port = None

client2_id = None
client2_ip = None
client2_port = None

data = None
waiting_client = None
registered_clients = {}


# Build server responses that match the spec formats
def build_register(client1_id, client1_ip, client1_port):
    return (
        "REGACK" + CRLF +
        f"clientID: {client1_id}" + CRLF +
        f"IP: {client1_ip}" + CRLF +
        f"Port: {client1_port}" + CRLF +
        f"Status: registered" + CRLF + CRLF
    )
def build_bridge(client2_id, client2_ip, client2_port):
    return (
        "BRIDGEACK" + CRLF +
        f"clientID: {client2_id}" + CRLF +
        f"IP: {client2_ip}" + CRLF +
        f"Port: {client2_port}" + CRLF + CRLF
    )
def build_empty_bridge():
    return (
        "BRIDGEACK" + CRLF +
        f"clientID: " + CRLF +
        f"IP: " + CRLF +
        f"Port: " + CRLF + CRLF
    )


# Parse key:value headers out of incoming messages
def parse_headers(msg):
    headers = {}
    lines = msg.split(CRLF)
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers
   

def main():
     parser = argparse.ArgumentParser()
     parser.add_argument("--port", required=True, type=int, help="Server listening port")
     args = parser.parse_args()
     
     global server_port
     server_port = args.port
     
     s = socket.socket()
        
     #print ("Socket successfully created")

        # reserve a port on your computer in our 
        # case it is 12345 but it can be anything 
     port = server_port               

        # Next bind to the port 
        # we have not typed any ip in the ip field 
        # instead we have inputted an empty string 
        # this makes the server listen to requests 
        # coming from other computers on the network 
     try:
        s.bind(('', port))
     except PermissionError:
         print("bind(): Permission denied")
         sys.exit(0)         
     #print ("socket binded to %s" %(port)) 

        # put the socket into listening mode 
     s.listen(2)     
     server_ip = socket.gethostbyname(socket.gethostname())
     print (f"Server listening on {server_ip}:{port}")
    
     global waiting_client
     global client1_id, client1_ip, client1_port
     sockets = [s, sys.stdin]  # watch network socket and stdin for /info
     while True:
         try:
             readable, _, _ = select.select(sockets, [], [])
             for r in readable:
                 if r == s:
                     # Establish connection with client. 
                     c, addr = s.accept()     
                     data = c.recv(4096).decode()
                     datalines = data.splitlines()
                     # REGISTER branch: save info, echo back REGACK
                     if datalines[0].strip() == 'REGISTER':
                         reg_headers = parse_headers(data)
                         
                         client1_id = reg_headers.get("clientID", "")
                         client1_ip = reg_headers.get("IP", "")
                         client1_port = reg_headers.get("Port", "")
                         registered_clients[client1_id] = {"IP": client1_ip,"Port": client1_port }
                         print(f"REGISTER: {client1_id} from {client1_ip}:{client1_port} received")
                         regack = build_register(client1_id, client1_ip, client1_port)
                         c.send(regack.encode())
                         c.close()
                         continue
                        
                        
                     # BRIDGE branch: either stash first requester or return waiting peer
                     elif datalines[0].strip() == 'BRIDGE':
                         
                         bridge_headers = parse_headers(data)
                         global client2_id, client2_ip, client2_port
                         client2_id = bridge_headers.get("clientID", "")
                         peer_info = registered_clients.get(client2_id, {"IP": "", "Port": ""})
                         client2_ip = peer_info.get("IP", "")
                         client2_port = peer_info.get("Port", "")
                         
                         if client2_ip == "" or client2_port == "":
                             print("Client has not registered yet, please do that first")
                             c.close()
                             s.close()
                             sys.exit(1)
                         if waiting_client is None:
                             print(f"BRIDGE: {client2_id} {client2_ip}:{client2_port}")
                             waiting_client = { "clientID": client2_id, "IP": client2_ip, "Port": client2_port}
                             sendEmpty = build_empty_bridge()
                             c.send(sendEmpty.encode())
                             c.close()
                             continue

                         print(f"BRIDGE: {waiting_client.get('clientID','')} {waiting_client.get('IP','')}:{waiting_client.get('Port','')} {client2_id} {client2_ip}:{client2_port} ")
                         sendBridgeack = build_bridge(waiting_client.get("clientID", ""), waiting_client.get("IP", ""), waiting_client.get("Port", ""))
                         waiting_client = None
                         c.send(sendBridgeack.encode())
                         c.close()
                         continue
                     # Anything else is malformed per spec
                     else:
                         sys.stderr.write("Malformed incoming message\n")
                         c.close()
                         s.close()
                         sys.exit(1)
                 else:
                     cmd = sys.stdin.readline()
                     if cmd.strip() == "/info":
                         # Show stored registrations: useful during demo
                         for cid, info in registered_clients.items():
                             print(f"{cid} {info.get('IP','')}:{info.get('Port','')}")
         except KeyboardInterrupt:
            print("Exiting program")
            sys.exit(0)
         


if __name__ == "__main__":
    main()
