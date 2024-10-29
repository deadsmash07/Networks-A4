import socket
import time
import argparse
import json
"""Checklist:
1. Make packet class (done)
2. Update json format (done)
3. Retransmit the only packet for which time out has occured when 3 acks are not recieverd 
4. update RTT values based on packet which is last acked (dont include retransmitted packets)
5. Update RTO based on RTT values

"""


# Constants
MSS = 1400  # Maximum Segment Size for each packet
WINDOW_SIZE = 5  # Number of packets in flight
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "sample_file.txt"  # Path to the file to be sent
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds
ALPHA=0.125
BETA=0.25

# Variables for RTT calculation and RTO (adaptive timeout) based on RFC 6298
SRTT = None  # Smoothed RTT
RTTVAR = None  # RTT variance
RTO = INITIAL_TIMEOUT  # Retransmission timeout

class Packet:
    """
    Represents a packet with sequence number, data, data length, 
    time sent, and retransmission status.
    """
    def __init__(self, seq_num, data, time_sent=None, is_retransmission=False):
        self.seq_num = seq_num
        self.data = data
        self.data_len = len(data)
        self.time_sent = time_sent or time.time()
        self.is_retransmission = is_retransmission

    def to_bytes(self):
        """
        Serialize packet to JSON format for transmission.
        """
        packet_dict = {
            "seq_num": self.seq_num,
            "data": self.data.decode(),
            "data_len": self.data_len,
            "time_sent": self.time_sent,
            "is_retransmission": self.is_retransmission
        }
        return json.dumps(packet_dict).encode()

    @staticmethod
    def from_bytes(packet_bytes):
        """
        Deserialize packet from JSON format.
        """
        packet_dict = json.loads(packet_bytes.decode())
        return Packet(
            packet_dict["seq_num"],
            packet_dict["data"].encode(),
            packet_dict["time_sent"],
            packet_dict["is_retransmission"]
        )

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
                packet = Packet(seq_num, chunk)  # Create a Packet instance
                server_socket.sendto(packet.to_bytes(), client_address)
                unacked_packets[seq_num] = packet
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

                # Use the updated RTO as the timeout value
                server_socket.settimeout(RTO)

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
    for seq_num, packet in unacked_packets.items():
        packet.is_retransmission = True  # Mark as retransmission
        server_socket.sendto(packet.to_bytes(), client_address)
        packet.time_sent = time.time()  # Update the time sent
        print(f"Retransmitted packet {seq_num}.")

def fast_recovery(server_socket, client_address, ack_num, unacked_packets):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    if ack_num in unacked_packets:
        packet = unacked_packets[ack_num]
        packet.is_retransmission = True  # Mark as retransmission
        server_socket.sendto(packet.to_bytes(), client_address)
        packet.time_sent = time.time()  # Update the time sent
        print(f"Fast Recovery: Resent packet {ack_num}.")

def update_rtt(ack_seq_num, unacked_packets):
    """
    Update RTT and RTO based on RFC 6298 when receiving an ACK.
    """
    global SRTT, RTTVAR, RTO
    packet = unacked_packets[ack_seq_num]
    
    # Calculate the measured RTT
    sample_rtt = time.time() - packet.time_sent

    # Initial measurement for SRTT and RTTVAR
    if SRTT is None:
        SRTT = sample_rtt
        RTTVAR = sample_rtt / 2
        RTO = SRTT + max(0.1, 4 * RTTVAR)  # 0.1 represents clock granularity G

    else:
        # Update RTTVAR and SRTT using the ALPHA and BETA parameters
        RTTVAR = (1 - BETA) * RTTVAR + BETA * abs(SRTT - sample_rtt)
        SRTT = (1 - ALPHA) * SRTT + ALPHA * sample_rtt
        RTO = SRTT + max(0.1, 4 * RTTVAR)

    # Enforce minimum RTO of 1 second
    RTO = max(1.0, RTO)

    print(f"Updated RTT values: SRTT={SRTT:.3f}, RTTVAR={RTTVAR:.3f}, RTO={RTO:.3f}")


# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast_recovery', type=int, choices=[0,1], help='Enable fast recovery (1) or disable (0)')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, bool(args.fast_recovery))
