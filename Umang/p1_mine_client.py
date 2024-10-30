import socket
import json
import argparse

def receive_file(server_ip, server_port):
    # Create a UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(1.0)  # Set a timeout for socket operations

    server_address = (server_ip, server_port)

    # Send "START" message to initiate the file transfer
    client_socket.sendto(b"START", server_address)

    Last_received_seq = -1
    expected_seq_num = 0  # Initialize expected sequence number
    buffer = {}  # Buffer to store out-of-order packets
    file_done = False  # Flag to indicate file transfer completion

    with open("received_file.txt", 'wb') as file:
        while not file_done:
            try:
                # Receive a packet from the server
                packet, _ = client_socket.recvfrom(65535)  # Max UDP packet size
                if packet == b"END":
                    file_done = True
                    print("Received END signal from server.")
                    # Send final ACK for the last received packet
                    ack_packet = json.dumps({'ack_num': expected_seq_num - 1}).encode('utf-8')
                    client_socket.sendto(ack_packet, server_address)
                    break
                else:
                    # Decode the JSON packet
                    packet_data = json.loads(packet.decode('utf-8'))
                    seq_num = packet_data['seq_num']
                    data_len = packet_data['data_len']
                    data = packet_data['data'].encode('latin1')  # Re-encode data to bytes

                    if seq_num == expected_seq_num:
                        # Write data to file
                        file.write(data)
                        Last_received_seq = expected_seq_num
                        expected_seq_num += data_len

                        # Check for any buffered packets that can now be written
                        while expected_seq_num in buffer:
                            buffered_data = buffer.pop(expected_seq_num)
                            file.write(buffered_data)
                            Last_received_seq = expected_seq_num
                            expected_seq_num += len(buffered_data)
                        # Send ACK for the last received packet
                        ack_packet = json.dumps({'ack_num': Last_received_seq}).encode('utf-8')
                        client_socket.sendto(ack_packet, server_address)
                        print(f"Received and acknowledged packet with seq_num {Last_received_seq}")
                    elif seq_num > expected_seq_num:
                        # Out-of-order packet received, buffer it
                        buffer[seq_num] = data
                        # Send ACK for the last in-order packet
                        ack_packet = json.dumps({'ack_num': Last_received_seq}).encode('utf-8')
                        client_socket.sendto(ack_packet, server_address)
                        print(f"Received out-of-order packet with seq_num {seq_num}, expected {expected_seq_num}")
                        print(f"Sent ACK for last received packet with seq_num {Last_received_seq}")
                    else:
                        # Duplicate or old packet received, resend ACK
                        ack_packet = json.dumps({'ack_num': Last_received_seq}).encode('utf-8')
                        client_socket.sendto(ack_packet, server_address)
                        print(f"Received duplicate packet with seq_num {seq_num}")
                        print(f"Sent ACK for last received packet with seq_num {Last_received_seq}")
            except socket.timeout:
                # If timeout occurs, continue to the next iteration
                continue

    print("File received successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    args = parser.parse_args()

    receive_file(args.server_ip, args.server_port)
