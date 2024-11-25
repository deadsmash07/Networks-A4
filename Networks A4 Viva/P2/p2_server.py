import socket
import time
import json
import argparse
# import logging

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

MSS = 1400 
INITIAL_TIMEOUT = 1.0 
DUP_ACK_THRESHOLD = 3

# RTT estimation parameters
ALPHA = 0.125
BETA = 0.25

class ReliableServer:
    def __init__(self, server_ip, server_port):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((server_ip, server_port))

        # RTT estimation variables
        self.estimated_rtt = None
        self.dev_rtt = None
        self.timeout_interval = INITIAL_TIMEOUT

        # Congestion control variables
        self.cwnd = MSS  # Congestion window size in bytes (starts at 1 MSS)
        self.ssthresh = 64 * MSS  # Slow start threshold
        self.state = 'slow_start'  # TCP Reno states: 'slow_start', 'congestion_avoidance', 'fast_recovery'
        self.dup_ack_count = 0  # Duplicate ACK counter

        # Packet tracking
        self.packet_map = {}
        self.last_ack = 0
        self.seq_num = 0  # Sequence number for the next packet

        # File transfer status
        self.file_done = False

    def calculate_timeout(self, sample_rtt):
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
        self.timeout_interval = self.estimated_rtt + 4 * self.dev_rtt
        # logger.info(f"Timeout interval updated to {self.timeout_interval:.3f} seconds")

    def send_packet(self, seq_num, data, client_address):
        packet = json.dumps({
            "seq_num": seq_num,
            "data_len": len(data),
            "data": data.decode('latin1')  
        }).encode('utf-8')
        self.server_socket.sendto(packet, client_address)
        self.packet_map[seq_num] = {
            "sent_time": time.time(),
            "retransmission_count": 0,
            "packet": packet
        }
        # logger.info(f"Sent packet with seq_num {seq_num}")

    def resend_packet(self, seq_num, client_address):
        packet_info = self.packet_map.get(seq_num)
        if not packet_info:
            # logger.warning(f"Packet with seq_num {seq_num} not found. Cannot resend.")
            return
        self.server_socket.sendto(packet_info["packet"], client_address)
        packet_info["sent_time"] = time.time()
        packet_info["retransmission_count"] += 1
        # logger.info(f"Resent packet with seq_num {seq_num} (Retransmission count: {packet_info['retransmission_count']})")

    def receive_ack(self):
        try:
            ack_data, _ = self.server_socket.recvfrom(1024)
            ack_info = json.loads(ack_data.decode('utf-8'))
            # logger.info(f"Received ACK for seq_num {ack_info['ack_num']}")
            return ack_info["ack_num"]
        except socket.timeout:
            return None
        except Exception as e:
            # logger.error(f"Error receiving ACK: {e}")
            return None

    def handle_ack(self, ack_num, client_address):
        if ack_num > self.last_ack:
            # New ACK received
            self.dup_ack_count = 0
            self.last_ack = ack_num
            # Remove acknowledged packets from packet_map
            for seq in list(self.packet_map):
                if seq < ack_num:
                    sample_rtt = time.time() - self.packet_map[seq]["sent_time"]
                    if self.packet_map[seq]["retransmission_count"] == 0:
                        self.calculate_timeout(sample_rtt)
                    del self.packet_map[seq]
            # Congestion control adjustments
            if self.state == 'slow_start':
                self.cwnd += MSS
                # logger.info(f"Slow Start: Increased cwnd to {self.cwnd}")
                if self.cwnd >= self.ssthresh:
                    self.state = 'congestion_avoidance'
                    # logger.info("Transitioned to Congestion Avoidance")
            elif self.state == 'congestion_avoidance':
                increment = int(MSS * (MSS / self.cwnd))
                increment = max(increment, 1)  # Ensure at least 1 byte increase
                self.cwnd += increment
                # logger.info(f"Congestion Avoidance: Increased cwnd to {self.cwnd}")
            elif self.state == 'fast_recovery':
                self.cwnd = self.ssthresh
                self.state = 'congestion_avoidance'
                # logger.info(f"Fast Recovery: Set cwnd to ssthresh {self.ssthresh} and transitioned to Congestion Avoidance")
        elif ack_num == self.last_ack:
            # Duplicate ACK received
            self.dup_ack_count += 1
            # logger.info(f"Duplicate ACK for seq_num {ack_num}. dup_ack_count = {self.dup_ack_count}")
            if self.dup_ack_count >= DUP_ACK_THRESHOLD:
                # Fast Retransmit
                self.ssthresh = max(int(self.cwnd / 2), MSS)
                self.cwnd = self.ssthresh + 3 * MSS
                # logger.info(f"Fast Retransmit: ssthresh set to {self.ssthresh}, cwnd set to {self.cwnd}")
                self.resend_packet(ack_num, client_address)
                self.state = 'fast_recovery'
        else:
            # Old ACK, ignore
            pass

    def check_timeouts(self, client_address):
        for seq in list(self.packet_map):
            if time.time() - self.packet_map[seq]["sent_time"] > self.timeout_interval:
                # logger.warning(f"Timeout occurred for seq_num {seq}")
                # Congestion control adjustments on timeout
                self.ssthresh = max(int(self.cwnd / 2), MSS)
                self.cwnd = MSS
                self.state = 'slow_start'
                self.dup_ack_count = 0
                # logger.info(f"Timeout: ssthresh set to {self.ssthresh}, cwnd reset to {self.cwnd}, state set to Slow Start")
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
                        # logger.info("File read complete.")
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
                # Check if transfer is complete
                if self.file_done and not self.packet_map:
                    break

        # Send multiple END messages at intervals
        for _ in range(5):
            self.server_socket.sendto(b"END", client_address)
            # logger.info("Sent END to client.")
            time.sleep(0.1)

        # logger.info("File transfer complete. Closing connection.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server_ip", help="Server IP address")
    parser.add_argument("server_port", type=int, help="Server port")
    args = parser.parse_args()

    server = ReliableServer(args.server_ip, args.server_port)
    # logger.info(f"Server is listening on {args.server_ip}:{args.server_port}")

    while True:
        data, client_address = server.server_socket.recvfrom(1024)
        if data == b"START":
            # logger.info(f"Received START from {client_address}")
            server.run("example.txt", client_address)
            break
