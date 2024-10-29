import socket
import argparse

# Constants
MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port):
    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """
    # Initialize UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Set timeout for server response (2 seconds)

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = "received_file.txt"  # Default file name
    buffer = {}  # Buffer for out-of-order packets

    # Loop to ensure reliable connection establishment with the server
    while True:
        try:
            # Send initial connection request to server
            client_socket.sendto(b"START", server_address)
            print("Sent START request to server.")
            
            # Wait for a response from the server to confirm connection
            message, _ = client_socket.recvfrom(1024)
            if message.startswith(b"ACK_START"):
                print("Connection established with server.")
                break
        except socket.timeout:
            # Resend the START request if no response received
            print("No response from server, resending START request.")

    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Receive the packet
                packet, _ = client_socket.recvfrom(MSS + 100)  # Allow room for headers
                
                # Check for END signal
                if packet.startswith(b"END"):
                    print("Received END signal from server, file transfer complete.")
                    break

                # Parse the packet
                seq_num, data = parse_packet(packet)

                # If the packet is the expected one, write it to the file
                if seq_num == expected_seq_num:
                    file.write(data)
                    print(f"Received packet {seq_num}, writing to file.")
                    expected_seq_num += 1

                    # Check if any buffered packets can now be written
                    while expected_seq_num in buffer:
                        file.write(buffer.pop(expected_seq_num))
                        print(f"Writing buffered packet {expected_seq_num}.")
                        expected_seq_num += 1

                    # Send cumulative ACK for the next expected sequence number
                    send_ack(client_socket, server_address, expected_seq_num)
                elif seq_num > expected_seq_num:
                    # Buffer out-of-order packet
                    if seq_num not in buffer:
                        buffer[seq_num] = data
                        print(f"Received out-of-order packet {seq_num}, buffering.")
                    # Send ACK for the next expected sequence number
                    send_ack(client_socket, server_address, expected_seq_num)
                else:
                    # Duplicate or old packet, resend ACK for the next expected sequence number
                    print(f"Received duplicate/old packet {seq_num}, resending ACK for {expected_seq_num}.")
                    send_ack(client_socket, server_address, expected_seq_num)
            except socket.timeout:
                # On timeout, resend ACK for the next expected sequence number to prompt retransmission
                print("Timeout waiting for data, resending ACK.")
                send_ack(client_socket, server_address, expected_seq_num)

def parse_packet(packet):
    """
    Parse the packet to extract the sequence number and data, we have to fix this according to json format
    """
    try:
        # Split the packet by the delimiter '|'
        seq_num_str, data = packet.split(b'|', 1)
        seq_num = int(seq_num_str.decode())
        return seq_num, data
    except ValueError:
        print("Malformed packet received.")
        return -1, b''

def send_ack(client_socket, server_address, ack_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{ack_num}|ACK".encode()
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent cumulative ACK for packet {ack_num}.")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the client
receive_file(args.server_ip, args.server_port)
