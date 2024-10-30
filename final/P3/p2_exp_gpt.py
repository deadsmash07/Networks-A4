from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time, os, sys
import hashlib
import json
import socket
import matplotlib.pyplot as plt
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CustomTopo(Topo):
    def build(self, loss, delay):
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        self.addLink(h1, s1, loss=loss, delay=f'{delay}ms')
        self.addLink(h2, s1, loss=0)

def compute_md5(file_path):
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as file:
            while chunk := file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None

def run(expname):
    setLogLevel('info')
    
    controller_ip = '127.0.0.1'
    controller_port = 6653
    output_file = f'reliability_{expname}.csv'
    
    with open(output_file, 'w') as f_out:
        f_out.write("loss,delay,fast_recovery,md5_hash,ttc,Estimated_RTT\n")

        SERVER_IP = "10.0.0.1"
        SERVER_PORT = 1571
        NUM_ITERATIONS = 1
        delay_list, loss_list = [], []
        if expname == "loss":
            loss_list = [x * 0.5 for x in range(0, 4)]
            delay_list = [20]
        elif expname == "delay":
            delay_list = [x for x in range(0, 201, 20)]
            loss_list = [1]
        print(loss_list, delay_list)

        ttc_values_fast_recovery_1 = []
        loss_or_delay_values = []
        
        for LOSS in loss_list:
            for DELAY in delay_list:
                for FAST_RECOVERY in [1]:
                    for i in range(0, NUM_ITERATIONS):
                        print(f"\n--- Running topology with {LOSS}% packet loss, {DELAY}ms delay and fast recovery {FAST_RECOVERY}")

                        topo = CustomTopo(loss=LOSS, delay=DELAY)
                        net = Mininet(topo=topo, link=TCLink, controller=None)
                        remote_controller = RemoteController('c0', ip=controller_ip, port=controller_port)
                        net.addController(remote_controller)

                        net.start()
                        h1 = net.get('h1')
                        h2 = net.get('h2')

                        start_time = time.time()

                        # Start server on h1
                        print(f"Starting server on h1 with command: python3 p2_server.py {SERVER_IP} {SERVER_PORT} &")
                        h1_output = h1.cmd(f"sudo python3 p3_server_new.py {SERVER_IP} {SERVER_PORT} > server_output.log 2>&1 &")
                        
                        # Start client on h2
                        print(f"Starting client on h2 with command: python3 p2_client.py {SERVER_IP} {SERVER_PORT}")
                        h2_output = h2.cmd(f"sudo python3 p3_client_new.py {SERVER_IP} {SERVER_PORT} > client_log.log 2>&1 ")
                        print(f"Client output (h2): {h2_output}")

                        end_time = time.time()
                        print(f"Server output (h1): {h1_output}")
                        
                        ttc = end_time - start_time
                        md5_hash = compute_md5('received_file.txt')
                        print(f"MD5 Hash of received file: {md5_hash}")

                        if FAST_RECOVERY == 1:
                            ttc_values_fast_recovery_1.append(665022 / ttc)

                        # Record loss or delay value without condition
                        if expname == "loss":
                            loss_or_delay_values.append(LOSS)
                        else:
                            loss_or_delay_values.append(DELAY)

                        # Write the result to a file
                        f_out.write(f"{LOSS},{DELAY},{FAST_RECOVERY},{md5_hash},{(8 * 0.665022) / ttc},{h1_output}\n")
                        net.stop()
                        time.sleep(1)

        print("ttc_values_fast_recovery_1:", ttc_values_fast_recovery_1)
        print("loss_or_delay_values:", loss_or_delay_values)
        print("Lengths of lists for plotting:", len(ttc_values_fast_recovery_1), len(loss_or_delay_values))

        if len(loss_or_delay_values) == len(ttc_values_fast_recovery_1):
            plt.figure(figsize=(10, 6))
            if expname == "loss":
                plt.plot(loss_or_delay_values, ttc_values_fast_recovery_1, marker='o', label="Fast Recovery")
                plt.title('Throughput vs Loss')
                plt.xlabel('Packet Loss (%)')
            elif expname == "delay":
                plt.plot(loss_or_delay_values, ttc_values_fast_recovery_1, marker='o', label="Fast Recovery")
                plt.title('Time to Completion (TTC) vs Throughput')
                plt.xlabel('Network Delay (ms)')

            plt.ylabel('Throughput (s)')
            plt.legend()
            plt.grid(True)
            plt.savefig(f'ttc_vs_{expname}_{expname}.png')
            plt.show()

    print("\n--- Completed all tests and plotted the results ---")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python experiment.py <expname>")
    else:
        expname = sys.argv[1].lower()
        run(expname)
