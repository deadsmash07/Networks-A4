import socket
import time
import json
import argparse
import logging
import math

# Configure logging to display the congestion control process
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MSS = 1400  # Maximum Segment Size in bytes
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds
DUP_ACK_THRESHOLD = 3

# RTT estimation parameters
ALPHA = 0.125
BETA = 0.25
MIN_RTT = 0.0001  # Minimum RTT value to prevent zero RTT

class TCPCubic:
    def __init__(self, beta=0.5, C=0.4, MSS=1400):
        # Initialize congestion window parameters
        self.MSS = MSS  # Maximum Segment Size in bytes
        self.cwnd = 1 * MSS  # Congestion window size in bytes
        self.Wmax = 0  # Last max window size in bytes
        self.beta = beta  # Multiplicative decrease factor
        self.C = C  # CUBIC parameter

        # Internal tracking variables
        self.epoch_start = None
        self.K = 0  # Time period to increase cwnd to Wmax
        self.ack_count = 0
        self.last_congestion_event_time = time.perf_counter()

    def on_ack_received(self):
        # Called on each acknowledgment to adjust cwnd
        self.ack_count += 1
        current_time = time.perf_counter()
        if self.epoch_start is None:
            # Start of a new epoch
            self.epoch_start = current_time
            self.K = self.calculate_K()
            self.origin_point = self.cwnd

        # Time since epoch start
        t = current_time - self.epoch_start

        # Calculate the new cwnd using the CUBIC function
        cwnd_target = self.cubic_function(t)
        if cwnd_target > self.cwnd:
            cwnd_inc = cwnd_target - self.cwnd
            self.cwnd += cwnd_inc
        else:
            # Ensure cwnd increases minimally to prevent stalling
            self.cwnd += self.MSS * (1.0 / self.cwnd)

        # Ensure cwnd is at least 1 MSS
        self.cwnd = max(self.cwnd, self.MSS)

    def on_packet_loss(self):
        # Packet loss detected, reducing cwnd
        self.Wmax = self.cwnd
        self.cwnd = self.cwnd * self.beta
        self.cwnd = max(self.cwnd, self.MSS)
        self.epoch_start = None  # Reset epoch start for new epoch
        self.last_congestion_event_time = time.perf_counter()

    def calculate_K(self):
        # Calculate time period K to reach Wmax
        if self.Wmax > 0:
            return ((self.Wmax * (1 - self.beta) / self.C) ** (1.0 / 3))
        else:
            return 0

    def cubic_function(self, t):
        # CUBIC growth function: W(t) = C * (t - K)^3 + Wmax
        return self.C * ((t - self.K) ** 3) + self.Wmax

class ReliableServer:
    def __init__(self, server_ip, server_port):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((server_ip, server_port))
        self.MSS = MSS
        # RTT estimation variables
        self.estimated_rtt = None
        self.dev_rtt = None
        self.timeout_interval = INITIAL_TIMEOUT

        # Congestion control variables
        self.cubic = TCPCubic(MSS=MSS)
        self.cwnd = self.cubic.cwnd  # Congestion window size in bytes
        self.dup_ack_count = 0  # Duplicate ACK counter

        # Packet tracking
        self.packet_map = {}
        self.last_ack = 0
        self.seq_num = 0  # Sequence number for the next packet

        # File transfer status
        self.file_done = False

    def calculate_timeout(self, sample_rtt):
        sample_rtt = max(sample_rtt, MIN_RTT)
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
        self.timeout_interval = self.estimated_rtt + 4 * self.dev_rtt
        logger.info(f"Timeout interval updated to {self.timeout_interval:.6f} seconds")

    def send_packet(self, seq_num, data, client_address):
        packet = json.dumps({
            "seq_num": seq_num,
            "data_len": len(data),
            "data": data.decode('latin1')  # Use 'latin1' to preserve byte values
        }).encode('utf-8')
        self.server_socket.sendto(packet, client_address)
        self.packet_map[seq_num] = {
            "sent_time": time.perf_counter(),
            "retransmission_count": 0,
            "packet": packet
        }
        logger.info(f"Sent packet with seq_num {seq_num}")

    def resend_packet(self, seq_num, client_address):
        packet_info = self.packet_map.get(seq_num)
        if not packet_info:
            logger.warning(f"Packet with seq_num {seq_num} not found. Cannot resend.")
            return
        self.server_socket.sendto(packet_info["packet"], client_address)
        packet_info["sent_time"] = time.perf_counter()
        packet_info["retransmission_count"] += 1
        logger.info(f"Resent packet with seq_num {seq_num} (Retransmission count: {packet_info['retransmission_count']})")

    def receive_ack(self):
        try:
            ack_data, _ = self.server_socket.recvfrom(1024)
            ack_info = json.loads(ack_data.decode('utf-8'))
            logger.info(f"Received ACK for seq_num {ack_info['ack_num']}")
            return ack_info["ack_num"]
        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Error receiving ACK: {e}")
            return None

    def handle_ack(self, ack_num, client_address):
        if ack_num > self.last_ack:
            # New ACK received
            self.dup_ack_count = 0
            self.last_ack = ack_num
            # Remove acknowledged packets from packet_map
            for seq in list(self.packet_map):
                if seq < ack_num:
                    sample_rtt = time.perf_counter() - self.packet_map[seq]["sent_time"]
                    if self.packet_map[seq]["retransmission_count"] == 0:
                        self.calculate_timeout(sample_rtt)
                    del self.packet_map[seq]
            # Congestion control adjustments using CUBIC
            self.cubic.on_ack_received()
            self.cwnd = self.cubic.cwnd
            logger.info(f"CUBIC: Updated cwnd to {self.cwnd} bytes")
        elif ack_num == self.last_ack:
            # Duplicate ACK received
            self.dup_ack_count += 1
            logger.info(f"Duplicate ACK for seq_num {ack_num}. dup_ack_count = {self.dup_ack_count}")
            if self.dup_ack_count >= DUP_ACK_THRESHOLD:
                # Fast Retransmit
                logger.info("Triple duplicate ACKs received. Performing fast retransmit.")
                self.cubic.on_packet_loss()
                self.cwnd = self.cubic.cwnd
                logger.info(f"CUBIC: Updated cwnd to {self.cwnd} bytes after packet loss.")
                self.resend_packet(ack_num, client_address)
                self.dup_ack_count = 0  # Reset duplicate ACK count
        else:
            # Old ACK, ignore
            pass

    def check_timeouts(self, client_address):
        current_time = time.perf_counter()
        for seq in list(self.packet_map):
            if current_time - self.packet_map[seq]["sent_time"] > self.timeout_interval:
                # Timeout detected
                logger.warning(f"Timeout occurred for seq_num {seq}")
                # Congestion control adjustments using CUBIC
                self.cubic.on_packet_loss()
                self.cwnd = self.cubic.cwnd
                logger.info(f"CUBIC: Updated cwnd to {self.cwnd} bytes after timeout.")
                self.resend_packet(seq, client_address)
                break  # Only handle one timeout per cycle

    def run(self, file_path, client_address):
        with open(file_path, 'rb') as file:
            while True:
                # Calculate unacknowledged data
                unacked_data = self.seq_num - self.last_ack
                # Send packets if window allows
                while unacked_data < self.cwnd and not self.file_done:
                    data = file.read(MSS)
                    if not data:
                        self.file_done = True
                        logger.info("File read complete.")
                        break
                    self.send_packet(self.seq_num, data, client_address)
                    self.seq_num += len(data)
                    unacked_data = self.seq_num - self.last_ack
                # Receive ACKs and handle them
                try:
                    self.server_socket.settimeout(0.1)
                    ack_num = self.receive_ack()
                    if ack_num is not None:
                        self.handle_ack(ack_num, client_address)
                except socket.timeout:
                    # Handle timeouts
                    self.check_timeouts(client_address)
                # Update cwnd from cubic (in case time has passed without ACKs)
                self.cubic.cwnd = max(self.cubic.cwnd, self.MSS)
                self.cwnd = self.cubic.cwnd
                # Check if transfer is complete
                if self.file_done and not self.packet_map:
                    break

        # Connection termination
        self.server_socket.sendto(b"FIN", client_address)
        logger.info("Sent FIN to client.")
        while True:
            try:
                data, _ = self.server_socket.recvfrom(1024)
                if data == b"ACK":
                    logger.info("Received ACK for FIN from client.")
                    break
            except socket.timeout:
                self.server_socket.sendto(b"FIN", client_address)
                continue
        while True:
            try:
                data, _ = self.server_socket.recvfrom(1024)
                if data == b"FIN":
                    logger.info("Received FIN from client.")
                    self.server_socket.sendto(b"ACK", client_address)
                    logger.info("Connection closed successfully.")
                    break
            except socket.timeout:
                continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server_ip", help="Server IP address")
    parser.add_argument("server_port", type=int, help="Server port")
    args = parser.parse_args()

    server = ReliableServer(args.server_ip, args.server_port)
    logger.info(f"Server is listening on {args.server_ip}:{args.server_port}")

    while True:
        data, client_address = server.server_socket.recvfrom(1024)
        if data == b"SYN":
            logger.info(f"Received SYN from {client_address}")
            server.server_socket.sendto(b"SYN-ACK", client_address)
            server.server_socket.settimeout(1.0)
            try:
                data, _ = server.server_socket.recvfrom(1024)
                if data == b"ACK":
                    logger.info(f"Connection established with {client_address}")
                    server.run("example.txt", client_address)
                    break
            except socket.timeout:
                continue
