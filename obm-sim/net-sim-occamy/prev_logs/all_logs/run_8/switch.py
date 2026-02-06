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
        self.queues = {}  # virtual output queues per port
        self.per_port_max_qsize = 5  # Max size in Bytes
        self.K = 30       # ECN threshold

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack
        
        # Buffer sizes in packets
        self.tor_buff_size = self.per_port_max_qsize * self.num_tor_ports 
        self.agg_buff_size = self.per_port_max_qsize * self.num_agg_ports 
        
        self.packet_dropped = 0
        self.port_qsize = {}  # number of packets queued per port
        self.priority_classes = 3

        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize * num_tor_ports
            self.N = self.ports
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize * num_agg_ports
            self.N = self.ports
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]
            print(num_agg_ports)

        #########################################################################################################
        # OCCAMY INIT
        #########################################################################################################
        self.total_usage = 0 
        self.sent = 0
        self.t = 0
        
        # Per-Priority Thresholds
        self.T = [self.total_buffer_size / (self.ports * self.priority_classes) for _ in range(self.priority_classes)]
        
        # Alpha values
        self.alpha_set = [[18,16,12],[18,16,12],[18,16,12]]#[18,16,12] 
        self.alpha = self.alpha_set[int(float(load)/0.3)-1]
        
        # Occamy Expulsion tracking
        self.drop_timer = 0       
        self.expulsion_rr_idx = 0  # Global Round-Robin Index for Drop Selection

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t += 1
        
        # ---------------------------------------------------------------------

        # 1. OCCAMY EXPULSION LOGIC (Drop Lowest Priority First)

        # ---------------------------------------------------------------------

        self.drop_timer += 1

       

        if self.drop_timer % 2 == 0:

            # Drop logic remains the same:

            # Search Priority 3 -> 1 (Index 2 -> 0)

            # Search Port 1 -> N

            priority_order_drop = range(self.priority_classes - 1, -1, -1)

            sorted_ports = sorted(list(self.links.keys()))

           

            packet_expelled = False

           

            for prio_idx in priority_order_drop:

                for port_key in sorted_ports:

                    if self.voq_port_qsize[port_key-1][prio_idx] > self.T[prio_idx]:

                        pq = self.queues[port_key][prio_idx]

                        if hasattr(pq, 'queue') and len(pq.queue) > 0:

                            head_packet = pq.queue[0]

                            if head_packet.invalid == 0:

                                head_packet.invalid = 1

                                self.total_usage -= 1

                                self.port_qsize[port_key] -= 1

                                self.voq_port_qsize[port_key-1][prio_idx] -= 1

                                self.packet_dropped += 1

                                packet_expelled = True

                                break

                if packet_expelled:

                    break
        # ---------------------------------------------------------------------
        # 2. SENDING LOGIC (Strict Priority: High Prio First)
        # ---------------------------------------------------------------------
        for port in self.links.keys():
            flag_1 = 0
            
            # STRICT PRIORITY SCHEDULING
            # Always iterate 0 -> 1 -> 2 (High -> Med -> Low)
            # We do NOT use round robin (voq_rr) here.
            for prio_idx in range(self.priority_classes):
                
                # Check if this priority queue has packets
                if not self.queues[port][prio_idx].empty():
                    
                    # Drain invalid (dropped) packets from the head
                    while not self.queues[port][prio_idx].empty():
                        packet = self.queues[port][prio_idx].get_nowait()
                        
                        if packet.invalid == 1:
                            # Packet was dropped by Occamy, ignore and get next
                            continue
                        else:
                            # Valid packet found! Send it.
                            self.links[port].send(packet, self.addr, currTimeslot)
                            
                            self.port_qsize[port] -= 1
                            self.sent += 1
                            self.total_usage -= 1 
                            self.voq_port_qsize[port-1][prio_idx] -= 1
                            
                            flag_1 = 1
                            assert(self.port_qsize[port] >= 0)
                            
                            # Break inner while loop (packet sent)
                            break
                    
                    # If we sent a packet (flag_1), we must stop this port's timeslot.
                    # Because we are Strict Priority, we do NOT check lower priorities.
                    if flag_1:
                        break

        # ---------------------------------------------------------------------
        # 3. RECEIVING LOGIC
        # ---------------------------------------------------------------------
        for port in self.links.keys(): 
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                packet.invalid = 0 
                self.handleRecvdPacket(packet, currTimeslot)
        
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

    # ########################################################################
    # SHARED BUFFER MANAGEMENT HELPERS
    # ########################################################################

    def threshold_calculate(self):
        # Calculate T per priority class
        remaining_buffer = self.total_buffer_size - self.total_usage
        for n in range(self.priority_classes):
            self.T[n] = self.alpha[n] * remaining_buffer

    def handleRecvdPacket(self, packet, arrivalTime):
        """Handle the packet received on the specified input port"""
        outPort = self.getOutPort(self.addr, packet)
        prio_idx = packet.priority - 1 # 0-based index
        
        # ---------------------------------------------------------
        # OCCAMY ADMISSION CONTROL
        # ---------------------------------------------------------
        
        if self.total_buffer_size > self.total_usage:
            
            # Check VOQ specific size against VOQ specific Threshold
            if self.voq_port_qsize[outPort-1][prio_idx] < self.T[prio_idx]:
                self.total_usage += 1
                
                self.queues[outPort][prio_idx].put(packet)
                
                self.port_qsize[outPort] += 1
                self.voq_port_qsize[outPort-1][prio_idx] += 1
                
                self.setECNFlag(packet, outPort)
            else:
                # Threshold for this priority exceeded
                self.packet_dropped += 1
        else:
            # Global Buffer Full
            self.packet_dropped += 1
        
        # Recalculate Thresholds
        self.threshold_calculate()