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
        self.links = {}   # links indexed by port, i.e., {port:link, ......, port:link}
        self.queues = {}  # list of virtual output queues (of type queue.Queue) per port
                          # indexed by port, i.e., {port:[queue], ......, port:[queue]}
                          # each virtual output queue is a FIFO queue of infinite size
        self.voq_rr = {}  # stores the VOQ per port to be serviced next
        self.per_port_max_qsize = 5  # in terms of number of size in Bytes
        self.K = 30                   # threshold for ECN marking (in terms of number of packets)

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack
        self.tor_buff_size = self.per_port_max_qsize * self.num_tor_ports # in terms of number of packets
        self.agg_buff_size = self.per_port_max_qsize * self.num_agg_ports # in terms of number of packets
        self.packet_dropped = 0
        self.port_qsize = {}  # number of packets queued per port
        self.priority_classes = 3

        
        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize*num_tor_ports
            self.N = self.ports
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize*num_agg_ports
            self.N = self.ports
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range (self.N)]
            print(num_agg_ports)
            

        #########################################################################################################
        self.total_usage = 0 
        self.final_add = [0 for i in range(self.N)]
        self.T = [self.total_buffer_size/(self.ports*self.priority_classes) for i in range(self.priority_classes)]
        self.sent = 0
        self.alpha_set = [[10,8,6],[8,6,4],[8,6,4]]
        self.alpha = self.alpha_set[int(float(load)/0.3)-1]#[8,6,4]#[10,8,6] - 0.3 #[16,14,12] - 0.3 #[8,6,4] - 0.6,0.9
        self.t = 0
        self.track = 0
        self.weights = [3,2,1]
        self.current_prio_idx = {port+1: 0 for port in range(self.N)}
        self.tokens = {port+1: self.weights[0] for port in range(self.N)}

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t+=1
        
        for port in self.links.keys():
            sent_in_this_slot = False
            
            # We loop up to 'priority_classes' times to find work.
            # This ensures work-conservation (it won't exit until it finds a packet or checks all).
            for _ in range(self.priority_classes):
                # 1. Get the current priority the scheduler is pointing to
                prio = self.current_prio_idx[port]
                
                # 2. If tokens for this priority are exhausted (0), move to the next priority and refill
                if self.tokens[port] <= 0:
                    self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                    prio = self.current_prio_idx[port]
                    self.tokens[port] = self.weights[prio]
                    
                # 3. Check if the queue at this priority has packets
                if not self.queues[port][prio].empty():
                    flag_1 = 0
                    # Iterate through the queue to find a valid packet
                    for j in range(self.queues[port][prio].qsize()):
                        packet = self.queues[port][prio].get_nowait()
                        if packet.invalid == 0:
                            
                            self.links[port].send(packet, self.addr, currTimeslot)
                            
                            # Update stats
                            self.port_qsize[port] -= 1
                            self.sent += 1
                            self.total_usage -= 1 
                            self.voq_port_qsize[port-1][prio] -= 1
                            
                            # WRR specific: decrement tokens and mark slot as used
                            self.tokens[port] -= 1
                            sent_in_this_slot = True
                            flag_1 = 1
                            assert(self.port_qsize[port] >= 0)
                            break
                    
                    # If the queue is now empty OR tokens are gone, we move the pointer 
                    # for the NEXT timeslot/iteration
                    if self.tokens[port] <= 0 or self.queues[port][prio].empty():
                        self.tokens[port] = 0 # Force exhaustion if queue was empty
                        self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                        # We don't refill yet; it will refill at the start of the next 'prio' check
                    
                    if sent_in_this_slot:
                        break # A packet was sent for this port, move to next port
                        
                else:
                    # 4. WORK-CONSERVING SKIP: Queue is empty.
                    # "Waste" the tokens for this priority and move pointer to check next priority level.
                    self.tokens[port] = 0
                    self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                    # Loop continues to the next '_' iteration to check the new 'current_prio_idx'


        for port in self.links.keys():  # in each timeslot, receive a
                                        # pa cket (if any) on each input
                                        # port and handle it
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(packet, currTimeslot)
            else:
                self.final_add[port-1] = 0
        
        #if self.t > self.track:
        #    self.track +=200
        #    if self.addr == 't9':
        #            print(f"usage = {self.total_usage}/{self.total_buffer_size}")
        #            print(f"dropped = {self.packet_dropped}")
        #            #print(f"nqa = {self.nqa}")
        #            print(f"occupancy = {self.port_qsize}")
        #            print(f"threshold = {self.T}")
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
######################################################################## Additional ######################################################################################

    def threshold_calculate(self):
        
        # self.nqa = [0]*self.N
        # tot_al = 0
        # for n1 in range(0,self.ports):
        #     for n2 in range(0,self.priority_classes):
        #         if self.voq_port_qsize[n1][n2]>0.9*self.T[n2]:
        #             tot_al += self.alpha[n2]
        for n2 in range(self.priority_classes):
            self.T[n2]= self.alpha[n2]*(self.total_buffer_size - self.total_usage)

###############################################################################################################################################################

    def handleRecvdPacket(self, packet, arrivalTime):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        outPort = self.getOutPort(self.addr, packet)  # output port the packet needs to be sent out on
        
################################################################################ BIT MAPPER ########################################################################################
        if self.total_buffer_size > self.total_usage:
            
               ######## WHY??
            #self.queues[outPort][inPort-1].put(packet)  # add packet to the right VOQ at the output port
            inPort = packet.priority
            if self.voq_port_qsize[outPort-1][inPort-1] < self.T[inPort-1]:
                self.total_usage +=1
                self.queues[outPort][inPort-1].put(packet)
                self.port_qsize[outPort] += 1
                self.voq_port_qsize[outPort-1][inPort-1]+=1
                self.setECNFlag(packet, outPort)
                #print(f"Packet placed = {self.addr} at {outPort-1} {inPort-1} at time {self.t}")
            #print("Packets scheduled via final add")
            else:
                if packet.priority == 1:
                    print("dropping packet 1 priority")
                #print("Packet drop due to DT")
                self.packet_dropped += 1
                #print(f"packet dropped = {self.packet_dropped}")
                pass
            
        else:
            if packet.priority == 1:
                print("dropping packet 1 priority")
            #print("Packet drop due to space constraint")
            self.packet_dropped += 1
            pass
        
        self.threshold_calculate()
        
                
            
            
####################################################################################################################################################################################
                

