import socket
import time
import argparse
import random


MSS = 1400 
INITIAL_SSTHRESH = 1400*50 
INITIAL_CWND = MSS  
DUP_ACK_THRESHOLD = 3 
ALPHA = 0.125  
BETA = 0.25  
INITIAL_TIMEOUT = 1.0  
cwnd_vs_time = []
throughput = []
start_time = time.time()

def cwnd_graph(cwnd,seq_no,current_phase):
    cwnd_vs_time.append((cwnd/MSS, time.time(),seq_no,current_phase))


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
        
    def handle_timeout(self,seq_no):
        #print(f"Timeout occurred! Reducing window - Old cwnd: {self.cwnd/MSS:.1f}")
        self.ssthresh = max(self.cwnd // 2, 2 * MSS)
        self.cwnd = MSS
        self.in_fast_recovery = False
        self.dup_ack_count = 0
        self.timeout_interval = min(60.0, self.timeout_interval * 2)
        cwnd_graph(self.cwnd,seq_no,"SS")
        #print(f"New cwnd: {self.cwnd/MSS:.1f}, New ssthresh: {self.ssthresh/MSS:.1f}")
        
    def handle_new_ack(self, ack_num, sample_rtt,seq_no):
        phase = "CAV"
        if self.in_fast_recovery:
            #print("Exiting fast recovery")
            self.cwnd = self.ssthresh
            self.in_fast_recovery = False
            cwnd_graph(self.cwnd,seq_no,phase)

        else:
            if self.cwnd < self.ssthresh:
                self.cwnd += MSS
                #print(f"Slow start: increased cwnd to {self.cwnd/MSS:.1f}")
                phase = "SS"
                cwnd_graph(self.cwnd,seq_no,phase)

            else:
                self.cwnd += MSS * MSS / self.cwnd
                #print(f"Congestion avoidance: increased cwnd to {self.cwnd/MSS:.1f}")
        
                cwnd_graph(self.cwnd,seq_no,phase)
        self.update_rtt(sample_rtt)
        self.dup_ack_count = 0
        self.last_ack = ack_num
        
    def handle_duplicate_ack(self, enable_fast_recovery,seq_no):
        self.dup_ack_count += 1
        #print(f"Duplicate ACK #{self.dup_ack_count} for seq {self.last_ack/MSS}")
        
        if enable_fast_recovery and self.dup_ack_count == DUP_ACK_THRESHOLD:
            #print("Triple duplicate ACK - entering fast recovery")
            self.ssthresh = max(self.cwnd // 2, 2 * MSS)
            self.cwnd = self.ssthresh + 3 * MSS
            self.in_fast_recovery = True
            ##print(f"New cwnd: {self.cwnd/MSS:.1f}, New ssthresh: {self.ssthresh/MSS:.1f}")


        elif self.in_fast_recovery:
            self.cwnd += MSS
            #print(f"In Fast recovery  - no need for duplicate ack ")

    def update_rtt(self, sample_rtt):
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
        
        self.timeout_interval = max(0.5, min(60.0, self.estimated_rtt + 4 * self.dev_rtt))
        #print(f"Updated RTT - EstimatedRTT: {self.estimated_rtt:.3f}s, Timeout: {self.timeout_interval:.3f}s")



def send_file(server_ip, server_port, enable_fast_recovery):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))
    cc = TCPCongestionControl()
    def send_data_to_client(packet, client_address,msg,times):
        # if(random.random()>0.025):
        #     server_socket.sendto(packet, client_address)
        #     #print(msg + " time :"+ str(time) )
        # else:
        #     #print("failed to send packet --> ",msg+" time :"+ str(time) )
        throughput.append(time.time())

        server_socket.sendto(packet, client_address)
        #print(msg + " time :"+ str(time) )


    #print(f"Server listening on {server_ip}:{server_port}")
    
    while True:
        data, client_address = server_socket.recvfrom(1024)
        if data == b"START":
            #print(f"Client connected from {client_address}")
            start_time = time.time()
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
                #print("Timer expired!")
                cc.handle_timeout(seq_num)

                retransmit_base = send_base
                while retransmit_base < send_base + cc.cwnd and retransmit_base in unacked_packets:
                    
                    send_data_to_client(unacked_packets[retransmit_base][0], client_address,f"Timeout retransmit packet {retransmit_base/MSS}",1000*(time.time()))
                   
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
                    
                    packet = f"{seq_num}|".encode() + chunk
                    send_data_to_client(packet, client_address,f"Sent packet {seq_num/MSS}, cwnd={cc.cwnd/MSS:.1f}, window=[{send_base/MSS:.1f}-{send_window_end/MSS:.1f}] ",1000*(time.time()))

                    unacked_packets[seq_num] = (packet, current_time)

                seq_num += MSS
                last_transmit_time = current_time
            

            server_socket.settimeout(0.1)
            try:
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_num = int(ack_packet.split(b'|')[0])
                
                if ack_num > cc.last_ack:

                    #print(f"Received new cumulative ACK: {ack_num/MSS}")

                    if send_base in unacked_packets:
                        sample_rtt = time.time() - unacked_packets[send_base][1]
                        cc.handle_new_ack(ack_num, sample_rtt,seq_num)
                    

                    unacked_packets = {seq: pkt for seq, pkt in unacked_packets.items() 
                                    if seq >= ack_num}
                    send_base = ack_num
                    last_transmit_time = time.time()
                else:

                    cc.handle_duplicate_ack(enable_fast_recovery,seq_num)
                    if cc.dup_ack_count == DUP_ACK_THRESHOLD and enable_fast_recovery:

                        if send_base in unacked_packets:
                            send_data_to_client(unacked_packets[send_base][0], client_address , f"Fast retransmit packet {send_base/MSS}",1000*(time.time()))

                            last_transmit_time = time.time()
                
            except socket.timeout:
                continue
                

            if file_done and not unacked_packets:
                #print("Transfer complete - sending END signal")
                server_socket.sendto(b"END", client_address)

                try:
                    server_socket.settimeout(5)
                    final_ack, _ = server_socket.recvfrom(1024)
                   # print(cc.estimated_rtt)
                    #print("Received final ACK")
                except socket.timeout:
                    continue
                    #print("No final ACK received, but transfer assumed complete")
                break
    with open("rtt.txt",'a') as f:
        f.write(cc.estimated_rtt)
      
    server_socket.close()
    #print("Server closed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('server_ip', help='Server IP address')
    parser.add_argument('server_port', type=int, help='Server port number')
    parser.add_argument('--fast-recovery', type=int, default=1, 
                      help='Enable fast recovery (1=Yes, 0=No)')
    args = parser.parse_args()
    
    send_file(args.server_ip, args.server_port, args.fast_recovery)
    
    # with open("graph.csv", 'w') as f:
    #     f.write("cwnd,time,seq_no,phase\n")
    #     for cwnd, time,seq_no,phase in cwnd_vs_time:
    #         f.write(f"{cwnd},{time},{int(seq_no/MSS)},{phase}\n")
    # with open("throughput.csv",'w') as f:
    #     f.write("time\n")
    #     for tIME in throughput:
    #         f.write(f"{tIME}\n")

    #print("Graph data saved to graph.csv")
    #print("Throughtput data saved to throughput.csv")
