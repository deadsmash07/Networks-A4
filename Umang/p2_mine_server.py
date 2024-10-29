import socket
import time
import argparse
import json

MSS = 1400  # Maximum Segment Size
INITIAL_SSTHRESH = 1400 * 50
INITIAL_CWND = MSS
DUP_ACK_THRESHOLD = 3
ALPHA = 0.125
BETA = 0.25
INITIAL_TIMEOUT = 1.0
packet_times = {}  # Dictionary to track sent and ACK times

class TCPCongestionControl:
    def __init__(self):
        self.cwnd = INITIAL_CWND
        self.ssthresh = INITIAL_SSTHRESH
        self.dup_ack_count = 0
        self.in_fast_recovery = False
        self.last_ack = 0
        self.estimated_rtt = None
        self.dev_rtt = None
        self.timeout_interval = INITIAL_TIMEOUT

    def handle_timeout(self, seq_no):
        """Handles timeout events by reducing the congestion window and updating timeout interval."""
        self.ssthresh = max(self.cwnd // 2, 2 * MSS)
        self.cwnd = MSS
        self.in_fast_recovery = False
        self.dup_ack_count = 0
        self.timeout_interval = min(60.0, self.timeout_interval * 2)
        if seq_no in packet_times:
            packet_times[seq_no]["retransmission_count"] += 1
        else:
            packet_times[seq_no] = {"sent_time": time.time(), "retransmission_count": 1}

    def handle_new_ack(self, ack_num, sample_rtt, seq_no):
        """Updates RTT and adjusts cwnd based on new cumulative ACKs."""
        if self.in_fast_recovery:
            self.cwnd = self.ssthresh
            self.in_fast_recovery = False

        # Update congestion window for new ACKs only (retransmissions not included)
        if self.cwnd < self.ssthresh:
            # Slow start phase
            self.cwnd += MSS
        else:
            # Congestion avoidance phase
            self.cwnd += (MSS * MSS) / self.cwnd

        # RTT and timeout updates
        self.update_rtt(sample_rtt)
        self.dup_ack_count = 0
        self.last_ack = ack_num
        if seq_no in packet_times:
            packet_times[seq_no]["ack_time"] = time.time()

    def handle_duplicate_ack(self, enable_fast_recovery, seq_no):
        """Handles duplicate ACKs and triggers fast retransmission if necessary."""
        self.dup_ack_count += 1
        if enable_fast_recovery and self.dup_ack_count == DUP_ACK_THRESHOLD:
            self.ssthresh = max(self.cwnd // 2, 2 * MSS)
            self.cwnd = self.ssthresh + 3 * MSS
            self.in_fast_recovery = True
            if seq_no in packet_times:
                packet_times[seq_no]["retransmission_count"] += 1
            else:
                packet_times[seq_no] = {"sent_time": time.time(), "retransmission_count": 1}
        elif self.in_fast_recovery:
            self.cwnd += MSS

    def update_rtt(self, sample_rtt):
        """Calculates and updates the timeout interval based on the sample RTT."""
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
        self.timeout_interval = max(0.5, min(60.0, self.estimated_rtt + 4 * self.dev_rtt))

def send_file(server_ip, server_port, enable_fast_recovery):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))
    cc = TCPCongestionControl()

    def send_data_to_client(packet_data, client_address):
        """Helper function to send data packets and log transmission time."""
        server_socket.sendto(packet_data, client_address)
        packet = json.loads(packet_data)
        seq_no = packet["seq_num"]
        packet_times[seq_no] = {"sent_time": time.time(), "retransmission_count": 0}

    while True:
        data, client_address = server_socket.recvfrom(1024)
        if data == b"START":
            break
    
    with open("file_to_send.txt", 'rb') as file:
        seq_num = 0
        send_base = 0
        unacked_packets = {}
        file_done = False
        last_transmit_time = time.time()

        while True:
            current_time = time.time()

            if unacked_packets and (current_time - last_transmit_time) > cc.timeout_interval:
                cc.handle_timeout(seq_num)
                retransmit_base = send_base
                while retransmit_base < send_base + cc.cwnd and retransmit_base in unacked_packets:
                    send_data_to_client(unacked_packets[retransmit_base][0], client_address)
                    retransmit_base += MSS
                last_transmit_time = current_time
                continue

            send_window_end = send_base + cc.cwnd
            while seq_num < send_window_end and not file_done:
                if seq_num not in unacked_packets:
                    chunk = file.read(MSS)
                    if not chunk:
                        file_done = True
                        break
                    
                    packet_dict = {
                        "seq_num": seq_num,
                        "data_len": len(chunk),
                        "data": chunk.decode('latin1')
                    }
                    packet_data = json.dumps(packet_dict).encode('utf-8')
                    send_data_to_client(packet_data, client_address)
                    unacked_packets[seq_num] = (packet_data, current_time)
                seq_num += MSS
                last_transmit_time = current_time

            server_socket.settimeout(0.1)
            try:
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_num = int(ack_packet.split(b'|')[0])
                
                if ack_num > cc.last_ack:
                    if send_base in unacked_packets:
                        sample_rtt = time.time() - unacked_packets[send_base][1]
                        cc.handle_new_ack(ack_num, sample_rtt, seq_num)
                    unacked_packets = {seq: pkt for seq, pkt in unacked_packets.items() if seq >= ack_num}
                    send_base = ack_num
                    last_transmit_time = time.time()
                else:
                    cc.handle_duplicate_ack(enable_fast_recovery, seq_num)
                    if cc.dup_ack_count == DUP_ACK_THRESHOLD and enable_fast_recovery:
                        if send_base in unacked_packets:
                            send_data_to_client(unacked_packets[send_base][0], client_address)
                            last_transmit_time = time.time()
                
            except socket.timeout:
                continue

            if file_done and not unacked_packets:
                server_socket.sendto(b"END", client_address)
                try:
                    server_socket.settimeout(5)
                    server_socket.recvfrom(1024)
                except socket.timeout:
                    pass
                break

    server_socket.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('server_ip', help='Server IP address')
    parser.add_argument('server_port', type=int, help='Server port number')
    parser.add_argument('--fast-recovery', type=int, default=1, help='Enable fast recovery (1=Yes, 0=No)')
    args = parser.parse_args()
    
    send_file(args.server_ip, args.server_port, args.fast_recovery)
