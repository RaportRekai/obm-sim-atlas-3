# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import queue
import hashlib
from link import Link
import math
import copy


class Switch():
    """Switch class"""

    def __init__(self, addr, load, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr  # address of switch
        self.links = {}   # links indexed by port
        
        # ### CHANGED: Queues structure ###
        # Old: self.queues = {port: [queue, queue, queue]}
        # New: self.queues = {port: queue} (Single FIFO queue)
        self.queues = {}  
        
        self.voq_rr = {}  
        self.per_port_max_qsize = 5  
        self.K = 25                   

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack
        self.tor_buff_size = self.per_port_max_qsize * self.num_tor_ports 
        self.agg_buff_size = self.per_port_max_qsize * self.num_agg_ports 
        self.packet_dropped = 0
        self.port_qsize = {}  # number of packets queued per port
        self.priority_classes = 3 

        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize * num_tor_ports
            self.N = self.ports
            # ### CHANGED: Removed self.voq_port_qsize initialization ###
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize * num_agg_ports
            self.N = self.ports
            # ### CHANGED: Removed self.voq_port_qsize initialization ###
            print(num_agg_ports)

        self.total_usage = 0 
        self.final_add = [0 for i in range(self.N)]
        
        # ### CHANGED: Threshold and Alpha ###
        # We now treat all packets equally, so we only need one Threshold (T) and one Alpha.
        self.T = self.total_buffer_size / self.ports 
        self.sent = 0
        self.alpha = 16  # Using a single alpha value for the shared buffer
        
        self.t = 0
        self.track = 0

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t += 1
        
        for port in self.links.keys():  
            # ### CHANGED: Scheduling Logic ###
            # Old: Loop through range(priority_classes), find first non-empty.
            # New: Just check the single queue for the port (FIFO).
            
            if not self.queues[port].empty():
                # We process as many packets as the link allows (usually 1 per timeslot)
                # The logic below allows clearing the queue if needed, but typically link sends 1.
                # Keeping your original inner loop structure for "get_nowait" logic:
                
                packet = self.queues[port].get_nowait()
                
                if packet.invalid == 0:
                    self.links[port].send(packet, self.addr, currTimeslot)
                    
                    self.port_qsize[port] -= 1
                    self.sent += 1
                    self.total_usage -= 1 
                    # ### CHANGED: Removed update to self.voq_port_qsize ###
                    
                    assert(self.port_qsize[port] >= 0)
            else:
                continue

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

    # ### CHANGED: Threshold Calculation ###
    def threshold_calculate(self):
        # Old: Updated T[0], T[1], T[2] individually.
        # New: Updates single global T based on remaining buffer space.
        self.T = self.alpha * (self.total_buffer_size - self.total_usage)

    def handleRecvdPacket(self, packet, arrivalTime):
        """Handle the packet received on the specified input port"""
        outPort = self.getOutPort(self.addr, packet) 
        
        # Ensure queue exists (safety check for init)
        if outPort not in self.queues:
             self.queues[outPort] = queue.Queue()
             self.port_qsize[outPort] = 0

        # ### CHANGED: Admission Control ###
        if self.total_buffer_size > self.total_usage:
            
            # Old: Used packet.priority to index into T[] and checked voq_port_qsize.
            # New: Check global port_qsize against single T.
            
            if self.port_qsize[outPort] < self.T:
                self.total_usage += 1
                self.queues[outPort].put(packet) # Put into the single FIFO queue
                self.port_qsize[outPort] += 1
                # ### CHANGED: Removed self.voq_port_qsize update ###
                
                self.setECNFlag(packet, outPort)
            else:
                # Dropping logic matches your request: drop if full, regardless of priority
                if packet.priority == 1:
                    print("dropping packet 1 priority (due to threshold)")
                self.packet_dropped += 1
        else:
            if packet.priority == 1:
                print("dropping packet 1 priority (due to full buffer)")
            self.packet_dropped += 1
        
        self.threshold_calculate()