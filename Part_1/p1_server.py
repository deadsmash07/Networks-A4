import socket
import time
import json
import argparse
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MSS = 1400  # Maximum Segment Size
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds
DUP_ACK_THRESHOLD = 3

# RTT calculation parameters
ALPHA = 0.125
BETA = 0.25

class ReliableServer:
    def __init__(self, server_ip, server_port, enable_fast_recovery):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((server_ip, server_port))
        self.enable_fast_recovery = enable_fast_recovery

        # RTT variables
        self.estimated_rtt = None
        self.dev_rtt = None
        self.timeout_interval = INITIAL_TIMEOUT
        self.last_ack = -1
        self.dup_ack_count = 0

        # Dictionary to store packet details
        self.packet_map = {}
        
        # File transfer status
        self.file_done = False
        
        # Sliding window
        self.window_size = 5
        self.window_base = 0

    def calculate_timeout(self, sample_rtt):
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
        self.timeout_interval = max(1.0, self.estimated_rtt + 4 * self.dev_rtt)

    def send_packet(self, seq_num, data, client_address):
        packet = json.dumps({
            "seq_num": seq_num,
            "data_len": len(data),
            "data": data.decode('latin1')
        }).encode('utf-8')
        self.server_socket.sendto(packet, client_address)
        self.packet_map[seq_num] = {
            "sent_time": time.time(),
            "ack_time": None,
            "retransmission_count": 0,
            "packet": packet
        }
        logger.info(f"Sent packet with seq_num {seq_num}")

    def resend_packet(self, seq_num, client_address):
        if seq_num not in self.packet_map:
            logger.warning(f"Packet with seq_num {seq_num} not found in packet_map. Cannot resend.")
            return
        
        packet_info = self.packet_map[seq_num]
        self.server_socket.sendto(packet_info["packet"], client_address)
        packet_info["sent_time"] = time.time()
        packet_info["retransmission_count"] += 1
        self.packet_map[seq_num] = packet_info
        logger.info(f"Resent packet with seq_num {seq_num} (retransmission count: {packet_info['retransmission_count']})")

    def receive_ack(self):
        try:
            ack_data, _ = self.server_socket.recvfrom(2*MSS)
            ack_info = json.loads(ack_data.decode('utf-8'))
            logger.info(f"Received ACK for seq_num {ack_info['ack_num']}")
            return ack_info["ack_num"]
        except socket.timeout:
            return None

    def handle_ack(self, ack_num, client_address):
        if ack_num > self.last_ack:
            logger.info(f"Received new ACK for seq_num {ack_num}")
            self.last_ack = ack_num
            self.dup_ack_count = 0
            self.window_base = ack_num + MSS  # Adjust as per requirements

            for seq in list(self.packet_map):
                if seq <= ack_num:
                    self.packet_map[seq]["ack_time"] = time.time()
                    del self.packet_map[seq]
                    logger.info(f"Removed packet with seq_num {seq} from packet_map")
        else:
            # Handle duplicate ACKs
            self.dup_ack_count += 1
            logger.info(f"Received duplicate ACK for seq_num {ack_num}")
            if self.enable_fast_recovery and self.dup_ack_count >= DUP_ACK_THRESHOLD:
                logger.info("Fast recovery triggered")
                self.resend_packet(ack_num + MSS, client_address)

    def perform_rtt_measurement(self, client_address):
        timestamp = time.time()
        ping_message = json.dumps({'type': 'PING', 'timestamp': timestamp}).encode('utf-8')
        self.server_socket.sendto(ping_message, client_address)
        logger.info("Sent PING for RTT measurement.")
        self.server_socket.settimeout(2.0)
        i = 0
        
        try:
            data, _ = self.server_socket.recvfrom(1024)
            pong_data = json.loads(data.decode('utf-8'))
            if pong_data.get('type') == 'PONG' and pong_data.get('timestamp') == timestamp:
                rtt = time.time() - timestamp
                logger.info(f"RTT measured: {rtt} seconds")
                self.set_window_size(rtt)
                
        except socket.timeout:
            # self.server_socket.sendto(ping_message, client_address)
            # continue
            self.window_size = 10

    def set_window_size(self, rtt):
        link_speed_bps = 50 * 1024 * 1024  # 50 Mbps in bits per second
        link_speed_Bps = link_speed_bps / 8
        window_size_in_bytes = int(rtt * link_speed_Bps)
        self.window_size = max(1, window_size_in_bytes // MSS)
        logger.info(f"Window size set to {self.window_size} segments.")

    def run(self, file_path, client_address):
        seq_num = self.window_base
        with open(file_path, 'rb') as file:
            while True:
                while seq_num < self.window_base + self.window_size * MSS and not self.file_done:
                    if seq_num not in self.packet_map:
                        chunk = file.read(MSS)
                        if not chunk:
                            self.file_done = True
                            logger.info("File Read complete.")
                            break
                        # time.sleep(0.001)
                        self.send_packet(seq_num, chunk, client_address)
                        seq_num += len(chunk)
                    else:
                        seq_num += MSS

                self.server_socket.settimeout(0.001)
                ack_num = self.receive_ack()
                if ack_num is not None:
                    if ack_num in list(self.packet_map):
                        sample_rtt = time.time() - self.packet_map[ack_num]["sent_time"]
                        self.calculate_timeout(sample_rtt)
                        
                    self.handle_ack(ack_num, client_address)

                for seq in list(self.packet_map):
                    if time.time() - self.packet_map[seq]["sent_time"] > self.timeout_interval:
                        logger.warning(f"Timeout occurred for seq_num {seq}")
                        # time.sleep(0.001)
                        self.resend_packet(seq, client_address)
                
                if self.file_done and not self.packet_map:
                    break

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
    parser.add_argument("enable_fast_recovery", type=int, choices=[0, 1], help="Enable fast recovery (1=yes, 0=no)")
    args = parser.parse_args()

    server = ReliableServer(args.server_ip, args.server_port, args.enable_fast_recovery)
    logger.info("Server is ready to receive.")

    while True:
        data, client_address = server.server_socket.recvfrom(1024)
        if data == b"SYN":
            logger.info(f"Received SYN from {client_address}")
            server.server_socket.sendto(b"SYN-ACK", client_address)
            server.server_socket.settimeout(1.0)
            try:
                data, _ = server.server_socket.recvfrom(1024)
                if data == b"ACK":
                    logger.info("Connection established with client.")
                    server.perform_rtt_measurement(client_address)
                    server.run("example2.txt", client_address)
                    break
            except socket.timeout:
                continue
