import socket
import json
import argparse
import logging

# Configure logging to monitor the client's operations
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port, pref_outfile):
    # Create a UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(1.0)  # Set a timeout for socket operations

    server_address = (server_ip, server_port)

    # Initialize connection (Three-way handshake)
    while True:
        # Send "SYN" to initiate the connection
        client_socket.sendto(b"SYN", server_address)
        try:
            # Wait for "SYN-ACK" from server
            response, _ = client_socket.recvfrom(1024)
            if response == b"SYN-ACK":
                # Send "ACK" back to server
                client_socket.sendto(b"ACK", server_address)
                logger.info("Connection established with server.")
                break
        except socket.timeout:
            # If timeout occurs, resend "SYN"
            continue

    # Receiving file data
    last_received_seq = -1
    expected_seq_num = 0  # Initialize expected sequence number
    buffer = {}  # Buffer to store out-of-order packets
    file_done = False  # Flag to indicate file transfer completion

    # Open the file to write the received data
    filename = f"{pref_outfile}received_file.txt"
    with open(filename, 'wb') as file:
        while not file_done:
            try:
                # Receive a packet from the server
                packet, _ = client_socket.recvfrom(65535)  # Max UDP packet size
                if packet == b"FIN":
                    logger.info("Received FIN from server.")
                    # Send ACK to server
                    client_socket.sendto(b"ACK", server_address)
                    # Proceed to send FIN to server
                    client_socket.sendto(b"FIN", server_address)
                    logger.info("Sent FIN to server.")
                    # Wait for server's ACK
                    while True:
                        try:
                            data, _ = client_socket.recvfrom(1024)
                            if data == b"ACK":
                                logger.info("Received ACK from server. Connection closed.")
                                file_done = True
                                break
                        except socket.timeout:
                            # Resend FIN if ACK not received
                            client_socket.sendto(b"FIN", server_address)
                    break
                else:
                    # Decode the JSON packet
                    try:
                        packet_data = json.loads(packet.decode('utf-8'))
                        seq_num = packet_data['seq_num']
                        data_len = packet_data['data_len']
                        data = packet_data['data'].encode('latin1')  # Re-encode data to bytes

                        if seq_num == expected_seq_num:
                            # Write data to file
                            file.write(data)
                            last_received_seq = expected_seq_num
                            expected_seq_num += data_len

                            # Check for any buffered packets that can now be written
                            while expected_seq_num in buffer:
                                buffered_data = buffer.pop(expected_seq_num)
                                file.write(buffered_data)
                                last_received_seq = expected_seq_num
                                expected_seq_num += len(buffered_data)

                            # Send ACK for the last received in-order packet
                            ack_packet = json.dumps({'ack_num': expected_seq_num}).encode('utf-8')
                            client_socket.sendto(ack_packet, server_address)
                            logger.info(f"Received and acknowledged packet with seq_num {seq_num}")
                        elif seq_num > expected_seq_num:
                            # Out-of-order packet received, buffer it
                            buffer[seq_num] = data
                            # Send ACK for the last received in-order packet
                            ack_packet = json.dumps({'ack_num': expected_seq_num}).encode('utf-8')
                            client_socket.sendto(ack_packet, server_address)
                            logger.info(f"Received out-of-order packet with seq_num {seq_num}, expected {expected_seq_num}")
                        else:
                            # Duplicate or old packet received, resend ACK
                            ack_packet = json.dumps({'ack_num': expected_seq_num}).encode('utf-8')
                            client_socket.sendto(ack_packet, server_address)
                            logger.info(f"Received duplicate packet with seq_num {seq_num}")
                    except json.JSONDecodeError:
                        logger.warning("Received non-JSON data; ignoring.")
            except socket.timeout:
                # If timeout occurs, continue to the next iteration
                continue

    logger.info(f"File '{filename}' received successfully.")
    client_socket.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    parser.add_argument('--pref_outfile', default='', help='Prefix for the output filename')
    args = parser.parse_args()

    receive_file(args.server_ip, args.server_port, args.pref_outfile)
