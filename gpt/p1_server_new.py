import socket
import time
import argparse

# Constants
MSS = 1400  # Maximum Segment Size for each packet
WINDOW_SIZE = 5  # Number of packets in flight
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "sample_file.txt"  # Path to the file to be sent
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds

# Variables for RTT calculation and RTO (adaptive timeout) based on RFC 6298
SRTT = None  # Smoothed RTT
RTTVAR = None  # RTT variance
RTO = INITIAL_TIMEOUT  # Retransmission timeout

def send_file(server_ip, server_port, enable_fast_recovery):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    global SRTT, RTTVAR, RTO

    # Initialize UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = None
    seq_num = 0
    window_base = 0
    unacked_packets = {}
    duplicate_ack_counts = {}
    last_ack_received = -1
    fast_recovery_mode = False

    # Read the entire file into memory (for simplicity)
    with open(FILE_PATH, 'rb') as file:
        data = file.read()
        total_packets = (len(data) + MSS - 1) // MSS

    while True:
        # Handle initial connection
        if not client_address:
            try:
                message, addr = server_socket.recvfrom(1024)
                if message.startswith(b"START"):
                    client_address = addr
                    print(f"Connection established with client {client_address}.")
                    server_socket.sendto(b"ACK_START", client_address)
            except socket.timeout:
                continue

        # Send packets within the window
        while seq_num < window_base + WINDOW_SIZE and seq_num < total_packets:
            if seq_num not in unacked_packets:
                start = seq_num * MSS
                end = start + MSS
                chunk = data[start:end]
                packet = create_packet(seq_num, chunk)
                server_socket.sendto(packet, client_address)
                unacked_packets[seq_num] = (packet, time.time())
                print(f"Sent packet {seq_num}.")
            seq_num += 1

        try:
            ack_packet, _ = server_socket.recvfrom(1024)
            ack_seq_num = get_ack_num(ack_packet)

            # Handle new ACKs and update RTT
            if ack_seq_num > last_ack_received:
                print(f"Received cumulative ACK for packet {ack_seq_num}.")
                last_ack_received = ack_seq_num
                update_rtt(ack_seq_num, unacked_packets)  # Update RTT and calculate new RTO

                # Slide the window forward and remove acknowledged packets
                for s_num in list(unacked_packets):
                    if s_num < ack_seq_num:
                        del unacked_packets[s_num]
                        if s_num in duplicate_ack_counts:
                            del duplicate_ack_counts[s_num]

                # Reset duplicate ACK counts
                duplicate_ack_counts = {}
                fast_recovery_mode = False
            else:
                # Duplicate ACK received
                duplicate_ack_counts[ack_seq_num] = duplicate_ack_counts.get(ack_seq_num, 0) + 1
                print(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_counts[ack_seq_num]}.")

                if enable_fast_recovery and duplicate_ack_counts[ack_seq_num] == DUP_ACK_THRESHOLD:
                    print("Threshold reached for duplicate ACKs, entering fast recovery mode.")
                    fast_recovery(server_socket, client_address, ack_seq_num, unacked_packets)
                    fast_recovery_mode = True

        except socket.timeout:
            # Timeout occurred, retransmit all unacknowledged packets
            print("Timeout occurred, retransmitting all unacknowledged packets.")
            retransmit_unacked_packets(server_socket, client_address, unacked_packets)

        # Check if all packets have been acknowledged
        if window_base >= total_packets and not unacked_packets:
            # Send END signal to the client
            end_packet = b"END|END"
            server_socket.sendto(end_packet, client_address)
            print("All packets sent and acknowledged. Sent END signal.")
            break

def create_packet(seq_num, data):
    """
    Create a packet with the sequence number and data.
    """
    packet = f"{seq_num}|".encode() + data
    return packet

def get_ack_num(ack_packet):
    """
    Extract the acknowledgment number from the ACK packet.
    """
    try:
        ack_num_str, ack_type = ack_packet.split(b'|', 1)
        if ack_type == b"ACK":
            return int(ack_num_str.decode())
        else:
            return -1
    except ValueError:
        print("Malformed ACK packet received.")
        return -1

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, timestamp) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        unacked_packets[seq_num] = (packet, time.time())
        print(f"Retransmitted packet {seq_num}.")

def fast_recovery(server_socket, client_address, ack_num, unacked_packets):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    if ack_num in unacked_packets:
        packet, _ = unacked_packets[ack_num]
        server_socket.sendto(packet, client_address)
        unacked_packets[ack_num] = (packet, time.time())
        print(f"Fast Recovery: Resent packet {ack_num}.")

def update_rtt(ack_seq_num, unacked_packets):
    """
    Update RTT and RTO based on RFC 6298 when receiving an ACK.
    """
    global SRTT, RTTVAR, RTO
    sent_time = unacked_packets[ack_seq_num][1]
    sample_rtt = time.time() - sent_time

    if SRTT is None:  # First RTT measurement
        SRTT = sample_rtt
        RTTVAR = sample_rtt / 2
        RTO = SRTT + max(0.1, 4 * RTTVAR)
    else:
        RTTVAR = (1 - 0.25) * RTTVAR + 0.25 * abs(SRTT - sample_rtt)
        SRTT = (1 - 0.125) * SRTT + 0.125 * sample_rtt
        RTO = SRTT + max(0.1, 4 * RTTVAR)
    
    # Ensure RTO is no less than 1 second as per RFC 6298
    RTO = max(1.0, RTO)

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast_recovery', type=int, choices=[0,1], help='Enable fast recovery (1) or disable (0)')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, bool(args.fast_recovery))
