# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import queue
import hashlib
from link import Link
import math
import copy

PACKET_SIZE = 1500
MAX_K = 100

class Switch():
    """Switch class"""

    def __init__(self, load, addr, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr
        self.links = {}   # links indexed by port
        self.queues = {}  # Single FIFO queue per port
        
        self.per_port_max_qsize = 5  
        self.K = 25                   

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack
        
        self.packet_dropped = 0
        self.port_qsize = {}  # number of packets queued per port
        
        # Determine port counts and total buffer
        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize * num_tor_ports
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize * num_agg_ports
            print(num_agg_ports)
            
        self.total_usage = 0 
        self.final_add = [0 for i in range(self.ports)]
        
        # Initial Threshold set to total buffer (allows initial burst)
        self.T = self.total_buffer_size 
        self.sent = 0
        
        # Simplified Alpha Selection (using first index of your previous sets as baseline)
        # Load 0.2 -> 7, Higher load -> 2
        self.alpha = 32#7 if load == "0.2" else 2
        
        self.t = 0
        self.np = 1 # Number of active ports (starts at 1)

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t += 1
        
        # 1. SENDING LOGIC (Single FIFO Queue)
        for port in self.links.keys(): 
            if port in self.queues and not self.queues[port].empty():
                
                # Dequeue head of line
                packet = self.queues[port].get_nowait()
                
                if packet.invalid == 0:
                    self.links[port].send(packet, self.addr, currTimeslot)
                    
                    self.port_qsize[port] -= 1
                    self.sent += 1
                    self.total_usage -= 1 
                    
                    assert(self.port_qsize[port] >= 0)
                else:
                    pass # Packet invalidated, skip

        # 2. RECEIVING LOGIC
        for port in self.links.keys(): 
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)
            else:
                self.final_add[port-1] = 0
        
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
        
    def threshold_calculate(self): 
        """
        Modified Dynamic Threshold Calculation:
        np = Count of ports where queue_len > 0.9 * T
        T  = alpha * (Total - Usage) / np
        """
        
        # 1. Calculate np (Number of congested ports)
        active_count = 0
        for p in self.port_qsize:
            # Check if this port is utilizing more than 90% of the current threshold
            if self.port_qsize[p] > (0.9 * self.T):
                active_count += 1
        
        # np must be at least 1 to avoid division by zero
        # If no ports are congested, we divide by 1 (giving full access to whoever arrives)
        self.np = max(1, active_count)

        # 2. Calculate New Threshold
        remaining_buffer = self.total_buffer_size - self.total_usage
        if remaining_buffer < 0: remaining_buffer = 0
        
        # The core formula: Alpha * FreeSpace / ActivePorts
        self.T = (self.alpha * remaining_buffer) / self.np

    def handleRecvdPacket(self, inPort, packet, arrivalTime):
        """Handle the packet received on the specified input port"""
        outPort = self.getOutPort(self.addr, packet) 
        
        # Ensure queue exists
        if outPort not in self.queues:
            self.queues[outPort] = queue.Queue()
            self.port_qsize[outPort] = 0

        # --- ADMISSION CONTROL ---
        if self.total_buffer_size > self.total_usage:
            
            # Check against the Global Dynamic Threshold
            if self.port_qsize[outPort] < self.T:
                
                self.final_add[inPort-1] = 1
                self.total_usage += 1
                
                self.queues[outPort].put(packet)
                self.port_qsize[outPort] += 1
                
                self.setECNFlag(packet, outPort)
            else:
                # Dropped due to Dynamic Threshold (Congestion Control)
                self.final_add[inPort-1] = 0
                self.packet_dropped += 1
        else:
            # Dropped due to Physical Buffer Limit
            self.final_add[inPort-1] = 0
            self.packet_dropped += 1
        
        # Recalculate Threshold for the next packet/timeslot
        self.threshold_calculate()