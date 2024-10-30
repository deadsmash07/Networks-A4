from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time, re, os
import sys
import hashlib
import matplotlib.pyplot as plt  # Add this for plotting

class CustomTopo(Topo):
    def build(self, loss, delay):
        # Add two hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        # Add a single switch
        s1 = self.addSwitch('s1')

        # Add links
        # Link between h1 and s1 with the specified packet loss
        self.addLink(h1, s1, loss=loss, delay=f'{delay}ms')

        # Link between h2 and s1 with no packet loss
        self.addLink(h2, s1, loss=0)

def compute_md5(file_path):
    """Compute the MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as file:
            # Read the file in chunks to avoid using too much memory for large files
            while chunk := file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None

def run(expname):
    # Set the log level to info to see detailed output
    setLogLevel('info')
    
    # IP and port of the remote controller
    controller_ip = '127.0.0.1'  # Change to the controller's IP address if not local
    controller_port = 6653       # Default OpenFlow controller port
    
    # Output file 
    output_file = f'reliability_{expname}.csv'
    f_out = open(output_file, 'w')
    f_out.write("loss,delay,fast_recovery,md5_hash,ttc,Estimated_RTT\n")

    SERVER_IP = "10.0.0.1"
    SERVER_PORT = 1571
            
    NUM_ITERATIONS = 1
    OUTFILE = 'received_file.txt'
    delay_list, loss_list = [], []
    if expname == "loss":
        loss_list = [x*0.5 for x in range (0, 4)]
        delay_list = [20]
    elif expname == "delay":
        delay_list = [x for x in range(0, 201, 20)]
        loss_list = [1]
    print(loss_list, delay_list)
    
    # To store the results for plotting
    ttc_values_fast_recovery_0 = []
    ttc_values_fast_recovery_1 = []
    loss_or_delay_values = []
    
    # Loop to create the topology with varying loss or delay
    for LOSS in loss_list:
        for DELAY in delay_list:
            for FAST_RECOVERY in [1]:
                #SERVER_PORT += 4
                for i in range(0, NUM_ITERATIONS):
                    print(f"\n--- Running topology with {LOSS}% packet loss, {DELAY}ms delay and fast recovery {FAST_RECOVERY}")

                    # Create the custom topology with the specified loss
                    topo = CustomTopo(loss=LOSS, delay=DELAY)

                    # Initialize the network with the custom topology and TCLink for link configuration
                    net = Mininet(topo=topo, link=TCLink, controller=None)
                    # Add the remote controller to the network
                    remote_controller = RemoteController('c0', ip=controller_ip, port=controller_port)
                    net.addController(remote_controller)

                    # Start the network
                    net.start()

                    # Get references to h1 and h2
                    h1 = net.get('h1')
                    h2 = net.get('h2')

                    start_time = time.time()

                    # Run the server on h1 in the background, but redirect output to a log file
                    print(f"Starting server on h1 with command: python3 p2_server.py {SERVER_IP} {SERVER_PORT} &")
                    h1_output = h1.cmd(f"sudo python3 p2_server.py {SERVER_IP} {SERVER_PORT}  > server_output.log 2>&1 &")
                    

                    # Run the client on h2
                    print(f"Starting client on h2 with command: python3 p2_client.py {SERVER_IP} {SERVER_PORT}")
                    h2_output = h2.cmd(f"sudo python3 p2_client.py {SERVER_IP} {SERVER_PORT} > client_log.log 2>&1 ")
                    print(f"Client output (h2): {h2_output}")

                    end_time = time.time()
                    print(f"Server output (h1): {h1_output}")
                    
                    ttc = end_time - start_time
                    md5_hash = compute_md5('received_file.txt')
                    print(f"MD5 Hash of received file: {md5_hash}")

                    # Store results for plotting
                    if FAST_RECOVERY == 0:
                        ttc_values_fast_recovery_0.append(665022/ttc)
                    else:
                        ttc_values_fast_recovery_1.append(665022/ttc)

                    # Record loss or delay value only once since it's the same for both recovery modes
                    if len(ttc_values_fast_recovery_0) == len(ttc_values_fast_recovery_1):
                        if expname == "loss":
                            loss_or_delay_values.append(LOSS)
                        else:
                            loss_or_delay_values.append(DELAY)

                    # Write the result to a file
                    f_out.write(f"{LOSS},{DELAY},{FAST_RECOVERY},{md5_hash},{(8*0.665022)/ttc},{h1_output}\n")

                    # Stop the network
                    net.stop()

                    # Wait a moment before starting the next iteration
                    time.sleep(1)

    # Close the output file
    f_out.close()

    # # Plotting the results (TTC vs Loss/Delay) for both fast recovery modes
    # plt.figure(figsize=(10, 6))
    # if expname == "loss":
    #     plt.plot(loss_or_delay_values, ttc_values_fast_recovery_1, marker='o', label="Fast Recovery")
    #     plt.title('Throughput vs Loss')
    #     plt.xlabel('Packet Loss (%)')
    # elif expname == "delay":
    #     plt.plot(loss_or_delay_values, ttc_values_fast_recovery_1, marker='o', label="Fast Recovery")
    #     plt.title('Time to Completion (TTC) vs THroughput')
    #     plt.xlabel('Network Delay (ms)')

    # plt.ylabel('Throughput (s)')
    # plt.legend()
    # plt.grid(True)
    # plt.savefig(f'ttc_vs_{expname}_{expname}.png')  # Save the plot as a PNG image
    # plt.show()  # Display the plot

    print("\n--- Completed all tests and plotted the results ---")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python experiment.py <expname>")
    else:
        expname = sys.argv[1].lower()
        run(expname)
