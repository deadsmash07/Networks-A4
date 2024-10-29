import socket
import argparse

# Constants
MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port, pref_outfile):
    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """
    # Initialize UDP socket
    
    ## Add logic for handling packet loss while establishing connection
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Set timeout for server response

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = f"{pref_outfile}received_file.txt"  # Default file name

    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Send initial connection request to server
                client_socket.sendto(b"START", server_address)

                # Receive the packet
                packet, _ = client_socket.recvfrom(MSS + 100)  # Allow room for headers
                
                # Logic to handle end of file

                if end_signal:
                    print("Received END signal from server, file transfer complete")
                    break
                
                seq_num, data = parse_packet(packet)

                # If the packet is in order, write it to the file
                if seq_num == expected_seq_num:
                    file.write(data)
                    print(f"Received packet {seq_num}, writing to file")
                    
                    # Update expected seq number and send cumulative ACK for the received packet
                    send_ack(client_socket, server_address, seq_num)
                elif seq_num < expected_seq_num:
                    # Duplicate or old packet, send ACK again
                    send_ack(client_socket, server_address, seq_num)
                else:
                    i = 1
                    # packet arrived out of order
                    # handle_pkt()
            except socket.timeout:
                print("Timeout waiting for data")
                

def parse_packet(packet):
    """
    Parse the packet to extract the sequence number and data.
    """
    seq_num, data = packet.split(b'|', 1)
    return int(seq_num), data

def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{seq_num}|ACK".encode()
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent cumulative ACK for packet {seq_num}")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('--pref_outfile', default='', help='Prefix for the output file')

args = parser.parse_args()
print(args.pref_outfile)

# Run the client
receive_file(args.server_ip, args.server_port, args.pref_outfile)

