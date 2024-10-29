import socket
import time
import json
import argparse

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

        # Dictionary to store packet details: sent time, ack time, retransmission count, etc.
        self.packet_map = {}

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
        print(f"Sent packet with seq_num {seq_num}")

    def resend_packet(self, seq_num, client_address):
        packet_info = self.packet_map[seq_num]
        self.server_socket.sendto(packet_info["packet"], client_address)
        packet_info["sent_time"] = time.time()
        packet_info["retransmission_count"] += 1
        print(f"Resent packet with seq_num {seq_num} (retransmission count: {packet_info['retransmission_count']})")

    def receive_ack(self):
        try:
            ack_data, _ = self.server_socket.recvfrom(1024)
            ack_info = json.loads(ack_data.decode('utf-8'))
            return ack_info["ack_num"]
        except socket.timeout:
            return None

    def handle_ack(self, ack_num, client_address):
        if ack_num > self.last_ack:
            print(f"Received new ACK for seq_num {ack_num}")
            self.last_ack = ack_num
            self.dup_ack_count = 0

            # Update ACK time for each acknowledged packet in the map
            for seq in list(self.packet_map):
                if seq < ack_num:
                    self.packet_map[seq]["ack_time"] = time.time()
                    del self.packet_map[seq]  # Remove acknowledged packets

        else:
            # Increment duplicate ACK counter
            self.dup_ack_count += 1
            print(f"Received duplicate ACK for seq_num {ack_num}")
            if self.enable_fast_recovery and self.dup_ack_count >= DUP_ACK_THRESHOLD:
                print("Fast recovery triggered")
                self.resend_packet(ack_num, client_address)

    def run(self, file_path, client_address):
        with open(file_path, 'rb') as file:
            seq_num = 0
            while True:
                if seq_num not in self.packet_map:
                    chunk = file.read(MSS)
                    if not chunk:
                        break
                    self.send_packet(seq_num, chunk, client_address)
                seq_num += MSS

                # Check for ACKs
                self.server_socket.settimeout(self.timeout_interval)
                ack_num = self.receive_ack()
                if ack_num:
                    sample_rtt = time.time() - self.packet_map[ack_num]["sent_time"]
                    self.calculate_timeout(sample_rtt)
                    self.handle_ack(ack_num, client_address)

                # Retransmit packets on timeout
                for seq in list(self.packet_map):
                    if time.time() - self.packet_map[seq]["sent_time"] > self.timeout_interval:
                        print(f"Timeout occurred for seq_num {seq}")
                        self.resend_packet(seq, client_address)

            # Send END packet
            self.server_socket.sendto(b"END", client_address)
            print("File transfer complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server_ip", help="Server IP address")
    parser.add_argument("server_port", type=int, help="Server port")
    parser.add_argument("enable_fast_recovery", type=int, choices=[0, 1], help="Enable fast recovery (1=yes, 0=no)")
    args = parser.parse_args()

    server = ReliableServer(args.server_ip, args.server_port, args.enable_fast_recovery)
    server.run("file_to_send.txt", (args.server_ip, args.server_port))
