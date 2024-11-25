from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time, re, os
import hashlib

class DumbbellTopo(Topo):    
    def build(self, delay_sw2_s2='50ms'):
        # Create hosts
        c1 = self.addHost('c1')
        c2 = self.addHost('c2')
        s1 = self.addHost('s1')
        s2 = self.addHost('s2')

        # Create switches
        sw1 = self.addSwitch('sw1')
        sw2 = self.addSwitch('sw2')

        # Add links with specified parameters
        self.addLink(c1, sw1, delay='5ms')
        self.addLink(c2, sw1, delay='5ms')
        self.addLink(s1, sw2, delay='5ms')

        buffer_size = 500
        # Link between sw1 and sw2 (bottleneck link)
        self.addLink(sw1, sw2, bw=100, delay='5ms', max_queue_size=buffer_size)
        
        # Link between sw2 and s2 with specified latency
        self.addLink(s2, sw2, delay=delay_sw2_s2)

def jain_fairness_index(allocations):
    n = len(allocations)
    sum_of_allocations = sum(allocations)
    sum_of_squares = sum(x ** 2 for x in allocations)
    
    jfi = (sum_of_allocations ** 2) / (n * sum_of_squares)
    return jfi

def compute_md5(file_path):
    """Compute the MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as file:
            while chunk := file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None

def run():
    setLogLevel('info')
    
    controller_ip = '127.0.0.1'
    controller_port = 6653
    
    output_file = 'p2_fairness.csv'
    f_out = open(output_file, 'w')
    f_out.write("delay,md5_hash_1,md5_hash_2,ttc1,ttc2,jfi\n")

    SERVER_IP1 = "10.0.0.3"
    SERVER_PORT1 = 6555
    SERVER_IP2 = "10.0.0.4"
    SERVER_PORT2 = 6556
    
    NUM_ITERATIONS = 1
    OUTFILE = 'received_file.txt'
    delay_list = [x for x in range(0, 101, 20)]
    
    for DELAY in delay_list:
        for i in range(NUM_ITERATIONS):
            os.system("mn -c")
            os.system("cd ../../../ && source py_3.9.6/bin/activate && ryu-manager ryu.app.simple_switch_13 --ofp-tcp-listen-port 6653 &")
            print(f"\n--- Running topology with {DELAY}ms delay ---")

            topo = DumbbellTopo(delay_sw2_s2=f"{DELAY}ms")
            net = Mininet(topo=topo, link=TCLink, controller=None)
            remote_controller = RemoteController('c0', ip=controller_ip, port=controller_port)
            net.addController(remote_controller)

            net.start()
            
            c1 = net.get('c1')
            c2 = net.get('c2')
            s1 = net.get('s1')
            s2 = net.get('s2')
            
            pref_c1 = "1"
            pref_c2 = "2"
            
            s1_cmd = f"python3 p2_server.py {SERVER_IP1} {SERVER_PORT1} &"
            s2_cmd = f"python3 p2_server.py {SERVER_IP2} {SERVER_PORT2} &"
            c1_cmd = f"python3 p2_client.py {SERVER_IP1} {SERVER_PORT1} --pref_outfile {pref_c1} &"
            c2_cmd = f"python3 p2_client.py {SERVER_IP2} {SERVER_PORT2} --pref_outfile {pref_c2} &"
            s1.cmd(s1_cmd)
            s2.cmd(s2_cmd)
            time.sleep(1)

            start_time_c1 = time.time()
            c1.cmd(c1_cmd)
            print("Client 1 command executed")
            c1_pid_raw = c1.cmd('ps').strip()
            pid_parts = c1_pid_raw.split()
            if pid_parts:
                c1_pid = pid_parts[-8]
                print(f"Started client 1 with PID: {c1_pid}")

            start_time_c2 = time.time()
            c2.cmd(c2_cmd)
            print("Client 2 command executed")
            c2_pid_raw = c2.cmd('ps').strip()
            pid_parts = c2_pid_raw.split()
            if pid_parts:
                c2_pid = pid_parts[-8]
                print(f"Started client 2 with PID: {c2_pid}")

            end_time_c1 = None
            end_time_c2 = None
            
            while end_time_c1 is None or end_time_c2 is None:
                if end_time_c1 is None:
                    result_c1 = c1.cmd(f'ps')
                    if not result_c1 or str(c1_pid) not in result_c1:
                        end_time_c1 = time.time()

                if end_time_c2 is None:
                    result_c2 = c2.cmd(f'ps')
                    if not result_c2 or str(c2_pid) not in result_c2:
                        end_time_c2 = time.time()

            net.stop()
                
            dur_c1 = end_time_c1 - start_time_c1
            dur_c2 = end_time_c2 - start_time_c2
            jfi = jain_fairness_index([1/dur_c1, 1/dur_c2])
            
            print(dur_c1, dur_c2, jfi)
            hash1 = compute_md5(f"{pref_c1}received_file.txt")
            hash2 = compute_md5(f"{pref_c2}received_file.txt")

            f_out.write(f"{DELAY},{hash1},{hash2},{dur_c1},{dur_c2},{jfi}\n")
    
    time.sleep(1)
    f_out.close()
    print("\n--- Completed all tests ---")

if __name__ == "__main__":
    run()
