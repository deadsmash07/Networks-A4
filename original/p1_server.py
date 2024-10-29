import socket
import time
import argparse

# Constants
MSS = 1400  # Maximum Segment Size for each packet
WINDOW_SIZE =   # Number of packets in flight
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = ""
timeout = 1.0  # Initialize timeout to some value but update it as ACK packets arrive
def send_file(server_ip, server_port, enable_fast_recovery):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    # Initialize UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    # Wait for client to initiate connection
    client_address = None
    file_path = FILE_PATH  # Predefined file name

    with open(file_path, 'rb') as file:
        seq_num = 0
        window_base = 0
        unacked_packets = {}
        duplicate_ack_count = 0
        last_ack_received = -1


        while True:
            while <COND>: ## Use window-based sending
                chunk = file.read(MSS)
                if not chunk:
                    # End of file
                    # Send end signal to the client 
                    break

                # Create and send the packet
                packet = create_packet(seq_num, chunk)
                if client_address:
                    server_socket.sendto(packet, client_address)
                else:
                    print("Waiting for client connection...")
                    data, client_address = server_socket.recvfrom(1024)
                    print(f"Connection established with client {client_address}")
                

                ## 
                unacked_packets[seq_num] = (packet, time.time())  # Track sent packets
                print(f"Sent packet {seq_num}")
                seq_num += 1

            # Wait for ACKs and retransmit if needed
            try:
            	## Handle ACKs, Timeout, Fast retransmit
                server_socket.settimeout(TIMEOUT)
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_seq_num = get_seq_no_from_ack_pkt()

                if ack_seq_num > last_ack_received:
                    print(f"Received cumulative ACK for packet {ack_seq_num}")
                    last_ack_received = ack_seq_num
                    # Slide the window forward
                    
                    # Remove acknowledged packets from the buffer 
                    
                else:
                    # Duplicate ACK received
                    
                    print(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count}")

                    if enable_fast_recovery and duplicate_ack_count >= DUP_ACK_THRESHOLD:
                        print("Entering fast recovery mode")
                        fast_recovery(<inputs>)

            except socket.timeout:
                # Timeout handling: retransmit all unacknowledged packets
                print("Timeout occurred, retransmitting unacknowledged packets")
                retransmit_unacked_packets(server_socket, client_address, unacked_packets)

            # Check if we are done sending the file
            if not chunk and len(unacked_packets) == 0:
                print("File transfer complete")
                break

def create_packet(seq_num, data):
    """
    Create a packet with the sequence number and data.
    """
    

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    

def fast_recovery(server_socket, client_address, unacked_packets):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast recovery', type=int, help='Enable fast recovery')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, args.fast_recovery)
