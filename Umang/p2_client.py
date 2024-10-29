import socket
import argparse
import time

# Constants
MSS = 1400  # Maximum Segment Size
start_time = time.time()
def receive_file(server_ip, server_port):

    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """

    # Initialize UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(5)  # Set timeout for server response

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = "received_file.txt"  # Default file name
    received_packets = {}  # Buffer for out-of-order packets

    # *** Initiate connection and retry until the server responds ***
    while True:
        try:
            client_socket.sendto(b"START", server_address)
            #print("Sent START Message to server, waiting for response...")

            # Wait for the first packet from the server
            packet, _ = client_socket.recvfrom(MSS + 100)  # Receive first data packet
            #print("Received first packet from server, connection established.")
            break  # Exit the loop if the packet is received (successful connection)

        except socket.timeout:
            continue
            # Timeout occurred, resend the "START" message
            #print("Timeout waiting for server response, resending START...")

    # After receiving the first packet, continue receiving the file
    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Process the first packet received (which was already captured)
                seq_num, data = parse_packet(packet)

                # Check if seq_num is None, meaning the packet was empty or malformed
                if seq_num is None:
                    #print("Received an empty or malformed packet, skipping...")
                    continue  # Skip further processing for this packet

                # If the packet is in order, write it to the file
                if seq_num == expected_seq_num:
                    if data:  # Only write non-empty data
                        file.write(data)
                    #print(f"Received packet {seq_num/MSS}, writing to file")

                    # Update expected seq number and send cumulative ACK for the received packet
                    expected_seq_num += len(data)
                    #send_ack(client_socket, server_address, expected_seq_num)

                    # Check if buffered packets can now be written to file
                    while expected_seq_num in received_packets:
                        next_data = received_packets.pop(expected_seq_num)
                        file.write(next_data)
                        #print(f"Writing buffered packet {expected_seq_num} to file")
                        expected_seq_num += len(next_data)

                    send_ack(client_socket, server_address, expected_seq_num)

                elif seq_num > expected_seq_num:
                    # Packet arrived out of order, buffer it for future processing
                    #print(f"Out-of-order packet {seq_num/MSS} received, buffering it.")
                    received_packets[seq_num] = data
                    # Still send an ACK for the last in-order packet
                    send_ack(client_socket, server_address, expected_seq_num)

                else:
                    # Duplicate or old packet, send ACK again
                    #print(f"Duplicate packet {seq_num/MSS} received, sending ACK again.")
                    send_ack(client_socket, server_address, expected_seq_num) 

                # Continue receiving the rest of the packets
                packet, _ = client_socket.recvfrom(MSS + 100)  # Receive the next packet 

                # Logic to handle end of file
                if b"END" in packet:
                    #print("Received END signal from server, file transfer complete")
                    send_ack(client_socket, server_address, expected_seq_num)  # Send final ACK
                    break

            except socket.timeout:
                continue
                #print("Timeout waiting for data")

def parse_packet(packet):
    """
    Parse the packet to extract the sequence number and data.
    """
    # Check if the packet is empty or doesn't contain the expected delimiter
    if not packet or b'|' not in packet:
        #print("Received malformed or empty packet")
        return None, b''  # Return None for seq_num and empty data
    
    # If the packet is valid, split it
    seq_num, data = packet.split(b'|', 1)
    return int(seq_num), data

def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{seq_num}|ACK".encode()
    
        
    client_socket.sendto(ack_packet, server_address)
    #print(f"Sent cumulative ACK for packet {seq_num/MSS}  ")


# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the client
receive_file(args.server_ip, args.server_port)
