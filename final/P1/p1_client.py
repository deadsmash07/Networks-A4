import socket
import json
import argparse
import logging
import os 
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def receive_file(server_ip, server_port):
    # Create a UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2.0)  # Set a timeout for socket operations

    server_address = (server_ip, server_port)

    # Initialize connection
    while True:
        # Send "SYN" message to initiate the connection
        client_socket.sendto(b"SYN", server_address)
        try:
            # Wait for "SYN-ACK" from server
            response, _ = client_socket.recvfrom(1024)
            if response == b"SYN-ACK":
                # Send "ACK" back to server
                # time.sleep(0.001)
                client_socket.sendto(b"ACK", server_address)
                logger.info("Connection established with server.")
                break
        except socket.timeout:
            # If timeout occurs, resend "SYN"
            continue

    # Wait for "PING" message from server for RTT measurement
    client_socket.settimeout(2.0)
    
    try:
        packet, _ = client_socket.recvfrom(1024)
        ping_data = json.loads(packet.decode('utf-8'))
        if ping_data.get('type') == 'PING':
            # Send back "PONG" with same timestamp
            pong_data = json.dumps({'type': 'PONG', 'timestamp': ping_data['timestamp']}).encode('utf-8')
            client_socket.sendto(pong_data, server_address)
            logger.info("RTT measurement done.")
            
    except socket.timeout:
        # If timeout occurs, continue to wait
        logger.info("Cannot perform RTT measurement. Default size of 10 used.")

    Last_received_seq = -1
    expected_seq_num = 0  # Initialize expected sequence number
    buffer = {}  # Buffer to store out-of-order packets
    file_done = False  # Flag to indicate file transfer completion

    with open("received_file.txt", 'wb') as file:
        while not file_done:
            try:
                # Receive a packet from the server
                packet, _ = client_socket.recvfrom(65535)  # Max UDP packet size
                if packet == b"FIN":
                    file_done = True
                    logger.info("Received FIN from server.")
                    # Send ACK to server
                    client_socket.sendto(b"ACK", server_address)
                    # Send FIN to server
                    client_socket.sendto(b"FIN", server_address)
                    # Wait for ACK from server
                    while True:
                        try:
                            response, _ = client_socket.recvfrom(1024)
                            if response == b"ACK":
                                logger.info("Connection closed successfully.")
                                break
                        except socket.timeout:
                            # If timeout occurs, resend FIN
                            client_socket.sendto(b"FIN", server_address)
                            continue
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
                        # time.sleep(0.01)  
                        client_socket.sendto(ack_packet, server_address)
                        logger.info(f"Received and acknowledged packet with seq_num {Last_received_seq}")
                    elif seq_num > expected_seq_num:
                        # Out-of-order packet received, buffer it
                        buffer[seq_num] = data
                        # Send ACK for the last in-order packet
                        ack_packet = json.dumps({'ack_num': Last_received_seq}).encode('utf-8')
                        # time.sleep(0.01)
                        client_socket.sendto(ack_packet, server_address)
                        logger.info(f"Received out-of-order packet with seq_num {seq_num}, expected {expected_seq_num}")
                        logger.info(f"Sent ACK for last received packet with seq_num {Last_received_seq}")
                    else:
                        # Duplicate or old packet received, resend ACK
                        ack_packet = json.dumps({'ack_num': Last_received_seq}).encode('utf-8')
                        # time.sleep(0.01)
                        client_socket.sendto(ack_packet, server_address)
                        logger.info(f"Received duplicate packet with seq_num {seq_num}")
                        logger.info(f"Sent ACK for last received packet with seq_num {Last_received_seq}")
            except socket.timeout:
                # If timeout occurs, continue to the next iteration
                continue

    logger.info("File received successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    args = parser.parse_args()

    receive_file(args.server_ip, args.server_port)
