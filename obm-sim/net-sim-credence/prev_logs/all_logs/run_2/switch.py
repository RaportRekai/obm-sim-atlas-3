# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import queue
import hashlib
from link import Link
import math
import copy
import joblib
import numpy as np
import re
import os
import joblib
# Import the class we just wrote
# If you put it in the same file, skip this.
# If you put it in fast_forest.py:
from FastForest import FastForest
class Switch():
    """Switch class with CREDENCE Buffer Sharing"""

    def __init__(self, addr, load, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr
        self.links = {}
        self.queues = {}
        self.voq_rr = {}
        self.per_port_max_qsize = 4
        self.K = 25

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack
        self.tor_buff_size = self.per_port_max_qsize * self.num_tor_ports
        self.agg_buff_size = self.per_port_max_qsize * self.num_agg_ports
        self.packet_dropped = 0
        self.port_qsize = {}  # Physical Queue Length per port
        self.priority_classes = 3
        
        # --- CREDENCE INITIALIZATION ---
        # Load the pre-trained Random Forest Model
        # Assuming the model is in the same directory.
        # We try to load a generic name or specific based on ports if passed in args.
        try:
            # Adjust the filename pattern if your training script outputs differently
            jobfile = re.compile(f"model_ports{num_tor_ports}_")
            for filename in os.listdir('.'):
                if jobfile.match(filename):
                    self.model = joblib.load(filename)
                    print("CREDENCE: Loaded ML Model successfully.")
                    break
            #self.model = joblib.load(f"model_ports{num_tor_ports}_trees4_depth4.joblib")
            #print("CREDENCE: Loaded ML Model successfully.")
        except:
            print("WARNING: Model not found. Make sure .joblib file is in directory.")
            self.model = None

        # EWMA Parameters (User Input 3)
        self.ewma_alpha = 2 / (30 + 1)
        self.avg_q_len = {}          # Moving average of Queue Length per port
        self.avg_shared_occ = 0.0    # Moving average of Shared Buffer Occupancy
        
        # Virtual LQD State (Paper Section 3.1)
        # T_i: Virtual Thresholds tracking optimal queue lengths
        self.virtual_T = {} 
        self.virtual_gamma = 0       # Sum of all virtual thresholds
        # -------------------------------

        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize * num_tor_ports
            self.N = self.ports
            self.per_port_buffer = [[0 for _ in range(self.priority_classes)] for i in range(self.ports)]
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize * num_agg_ports
            self.N = self.ports
            self.per_port_buffer = [[0 for _ in range(self.priority_classes)] for i in range(self.ports)]
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]

        # Initialize tracking dicts for N ports
        # Note: Ports are usually 1-indexed in this simulator based on usage below
        for i in range(1, self.N + 1):
            self.virtual_T[i] = 0
            self.avg_q_len[i] = 0.0
            
        self.total_usage = 0 
        self.final_add = [0 for i in range(self.N)]
        self.sent = 0
        self.t = 0
        self.track = 0


        # Initialize
        self.model = None

        try:
            # Find the file
            jobfile = re.compile(f"model_ports{num_tor_ports}_")
            for filename in os.listdir('.'):
                if jobfile.match(filename):
                    print(f"Loading raw model: {filename}...")
                    raw_model = joblib.load(filename)
                    
                    # --- MAGIC HAPPENS HERE ---
                    # Convert heavy sklearn model to lightweight python lists
                    self.model = FastForest(raw_model)
                    
                    # Delete the raw model to free up RAM
                    del raw_model 
                    print("CREDENCE: Optimized model ready.")
                    break
        except Exception as e:
            print(f"Error loading model: {e}")

    def _update_virtual_lqd(self, port_idx, event_type):
        """
        Updates the virtual thresholds T according to LQD logic.
        Implements Algorithm 1 (lines 11-17) from the paper [cite: 320-321].
        """
        if event_type == 'arrival':
            # If Virtual Buffer is full
            if self.virtual_gamma == self.total_buffer_size:
                # Find queue j with largest threshold (Push-out candidate)
                # We iterate over keys 1..N
                j = max(self.virtual_T, key=self.virtual_T.get)
                
                # Decrease T_j (Push out)
                self.virtual_T[j] -= 1
                
                # Increase T_i (Accept new)
                self.virtual_T[port_idx] += 1
                # Gamma remains constant (one in, one out)
                
            else:
                # Virtual Buffer has space
                self.virtual_T[port_idx] += 1
                self.virtual_gamma += 1
                
        elif event_type == 'departure':
            # If the virtual queue is not empty, drain it
            if self.virtual_T[port_idx] > 0:
                self.virtual_T[port_idx] -= 1
                self.virtual_gamma -= 1

    def _update_ewma(self, port_idx):
        """Updates exponentially weighted moving averages for ML features"""
        curr_q = self.port_qsize[port_idx]
        curr_occ = self.total_usage
        
        # Update specific port average
        self.avg_q_len[port_idx] = (self.ewma_alpha * curr_q) + \
                                   ((1 - self.ewma_alpha) * self.avg_q_len[port_idx])
        
        # Update global occupancy average
        self.avg_shared_occ = (self.ewma_alpha * curr_occ) + \
                              ((1 - self.ewma_alpha) * self.avg_shared_occ)

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t += 1
        
        # --- SENDING PHASE (DEPARTURES) ---
        for port in self.links.keys():
            flag_1 = 0
            for i in range(self.priority_classes):
                if not self.queues[port][i].empty():
                    for j in range(0, self.queues[port][i].qsize()):
                        packet = self.queues[port][i].get_nowait()
                        if packet.invalid == 0:
                            #packet.hops +=1
                            if packet.prvt == 1:
                                if self.per_port_buffer[port-1][i]==1:
                                    self.per_port_buffer[port-1][i] = 0
                                else:
                                    breakpoint()
                            else:
                                if self.port_qsize[port] <=0:
                                    breakpoint()
                                self.port_qsize[port] -= 1
                                self.total_usage-=1 
                                self.voq_port_qsize[port-1][i]-=1
                            
                            

                            packet.prvt = 0
                            self.links[port].send(packet, self.addr, currTimeslot)
                            # print(f"sending packet from {i} when other prioritites have length = {self.voq_port_qsize[port-1]}")
                            # if i == 0:
                            #     breakpoint()
                            
                            self.sent+=1
                            
                            flag_1 = 1
                            try:
                                assert(self.port_qsize[port] >= 0)
                            except AssertionError:
                                print(f"Port {port} has negative queue size")
                                breakpoint()
                            break
                    if flag_1:
                        break
                else:
                    continue

        # --- RECEIVING PHASE (ARRIVALS) ---
        for port in self.links.keys():
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(packet, currTimeslot)
            else:
                self.final_add[port-1] = 0
        
        return self.packet_dropped
        
    def setECNFlag(self, packet, outPort):
        if self.port_qsize[outPort] > self.K:
            packet.ecnFlag = 1

    def ecmp(self, packet):
        flowid = packet.srcAddr + packet.dstAddr + str(packet.srcPort) + str(packet.dstPort)
        outPort = int(hashlib.sha256(flowid.encode('utf-8')).hexdigest(), 16) % (self.num_tor_ports - self.hosts_per_rack) + (self.hosts_per_rack + 1)
        return outPort

    def getOutPort(self, switchId, packet):
        if switchId[0] == 't':
            if int(packet.dstAddr[1:]) >= int(switchId[1])*16-15 and int(packet.dstAddr[1:]) <= int(switchId[1])*16:
                return int(packet.dstAddr[1:])-((int(switchId[1])-1)*16)
            else:
                return self.ecmp(packet)
        elif switchId[0] == 'a':
            return int((int(packet.dstAddr[1:])-1)/16)+1

    def handleRecvdPacket(self, packet, arrivalTime):
        """
        Handle the packet received.
        Implements CREDENCE logic:
        1. Update Virtual Thresholds
        2. Safeguard Check (Accept if < B/N)
        3. Threshold Check (Drop if > T)
        4. Prediction (Consult ML)
        """
        outPort = self.getOutPort(self.addr, packet)
        if self.per_port_buffer[outPort-1][packet.priority-1] == 0:
            self.per_port_buffer[outPort-1][packet.priority-1] = 1
            # we have to introduce a new field for packet.py
            packet.prvt = 1
            self.queues[outPort][packet.priority-1].put(packet)
        else:
            # 1. Update Virtual Thresholds (Algorithm 1, Line 4)
            self._update_virtual_lqd(outPort, 'arrival')
            
            # Update Stats for Prediction Features
            self._update_ewma(outPort)
            
            decision = "DROP" # Default
            
            # --- CREDENCE LOGIC START ---
            
            # Calculate max queue length for Safeguard
            # Note: self.port_qsize contains current physical lengths
            longest_queue_len = 0
            if len(self.port_qsize) > 0:
                longest_queue_len = max(self.port_qsize.values())

            # Safeguard Condition [cite: 308-309]
            # "If the longest queue length is less than B/N... always accept"
            safeguard_threshold = self.total_buffer_size / self.N
            
            if longest_queue_len < safeguard_threshold:
                decision = "ACCEPT"
            
            else:
                # Threshold Check [cite: 305]
                # Compare physical queue length (q_i) vs virtual threshold (T_i)
                # Using Option A: q_i is the total port occupancy
                current_q_len = self.port_qsize.get(outPort, 0)
                virtual_threshold = self.virtual_T[outPort]
                
                # If q_i < T_i, we *might* accept, check prediction
                if current_q_len < virtual_threshold:
                    
                    # Physical Capacity Check
                    if self.total_usage < self.total_buffer_size:
                        
                        # Prepare Features for Oracle [cite: 397]
                        # Order: queueLength, sharedOccupancy, averageQueueLength, averageOccupancy
                        prediction = self.model.predict(
                            current_q_len, 
                            self.total_usage, 
                            self.avg_q_len[outPort], 
                            self.avg_shared_occ
                        )
                        
                        if prediction == 0:
                            decision = "ACCEPT"
                        else:
                            decision = "DROP"
                    else:
                        decision = "DROP" # Physically full
                else:
                    decision = "DROP" # Exceeds virtual threshold
                    
            # --- EXECUTE DECISION ---
            
            if decision == "ACCEPT":
                # Sanity check for physical space (Safeguard implies accept, but physics is physics)
                if self.total_usage < self.total_buffer_size:
                    inPort_priority = packet.priority
                    self.total_usage += 1
                    self.queues[outPort][inPort_priority-1].put(packet)
                    self.port_qsize[outPort] += 1
                    self.voq_port_qsize[outPort-1][inPort_priority-1] += 1
                    self.setECNFlag(packet, outPort)
                else:
                    self.packet_dropped += 1
            else:
                # Drop packet
                self.packet_dropped += 1