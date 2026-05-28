# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import queue
import hashlib
from link import Link
import math
import copy

MAX_K = 100
class Switch():
    """Switch class"""

    def __init__(self, addr, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr  # address of switch
        self.links = {}   # links indexed by port, i.e., {port:link, ......, port:link}
        self.queues = {}  # list of virtual output queues (of type queue.Queue) per port
                          # indexed by port, i.e., {port:[queue], ......, port:[queue]}
                          # each virtual output queue is a FIFO queue of infinite size
        self.voq_rr = {}  # stores the VOQ per port to be serviced next
        self.per_port_max_qsize = 4  # in terms of number of 1500B packets
                                       # threshold for ECN marking (in terms of number of packets)
        self.flag = 0
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
            self.N = 1 if num_tor_ports < 1 else 2 ** ((num_tor_ports - 1).bit_length())
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range(self.N)]
            self.per_port_buffer = [[0 for _ in range(self.priority_classes)] for i in range(self.ports)]
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize*num_agg_ports
            self.N = 1 if num_agg_ports < 1 else 2 ** ((num_agg_ports - 1).bit_length())
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range (self.N)]
            self.per_port_buffer = [[0 for _ in range(self.priority_classes)] for i in range(self.ports)]
            print(num_agg_ports)
            

        #########################################################################################################
        self.total_usage = 0 
        self.final_add = [0 for i in range(self.N)]
        self.T = self.total_buffer_size
        self.sent = 0
        self.alpha = 2
        self.t = 0
        self.k = 0
        self.t_track = 0
        self.buffer = [[-1,-1] for i in range(self.N)]
        self.priority_packet_count = [0,0,0]
        self.priority_max_q_l = 0
        self.K = 30
        


    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t+=1
        self.l_uni = []
       
        
        for port in self.links.keys():  # in each timeslot, send a packet
                                        # at the head of a VOQ at each port.
                                        # VOQs at each port are scheduled in
                                        # round robin manner
            flag_1 = 0
            for i in range(self.priority_classes):
                if not self.queues[port][i].empty():
                    for j in range(0,self.queues[port][i].qsize()):
                        packet = self.queues[port][i].get_nowait()
                        if packet.invalid == 0:
                            #packet.hops +=1
                            if packet.prvt == 1:
                                if self.per_port_buffer[port-1][packet.priority-1]==1:
                                    self.per_port_buffer[port-1][packet.priority-1] = 0
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

                else:
                    continue
        self.k = 0
        self.buffer = [[-1,-1] for i in range(self.N)]
        self.largest_index = max(self.port_qsize, key=self.port_qsize.get)
        #print(f"The largest q is {self.largest_index}")
        #print(f"port qsize = {self.port_qsize}")
        for port in self.links.keys():  # in each timeslot, receive a
                                        # pa cket (if any) on each input
                                        # port and handle it
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)
        
        # for different priority classes coming into picture the conditions for priority encoder check becomes a little different
        if self.k>0:
            self.lvoq = self.priority_encoder(self.largest_index,self.k)
            #print(f"self.lvoq = {self.lvoq}")
            #breakpoint()
            mem = self.fetch()
            self.allct(mem)
        
        #if self.t > self.t_track:
        #    self.t_track+=200
        #    if self.addr == 't9':
        #        print(f"switch {self.addr}, usage = {self.total_usage}, total = {self.total_buffer_size}")


    def setECNFlag(self, packet, outPort):
        if self.port_qsize[outPort] > self.K:
            packet.ecnFlag = 1
            # if packet.srcAddr == 'h85' and packet.dstPort == 943:
            #     print(f"switch marking congestion - {self.addr}")
                #breakpoint()


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

    def find_index_of_largest(self):
        elements = []
        queue_instance = self.port_qsize
        
        # Dequeue all elements and keep them in a list
        while not queue_instance.empty():
            elements.append(queue_instance.get())
        
        # Find the index of the largest element
        index_of_largest = elements.index(max(elements))
        
        # Restore the elements back to the queue
        for item in elements:
            queue_instance.put(item)
        
        return index_of_largest

    def find_lowest_prio(self):
        priority_list = [self.buffer[i][0].priority for i in range(len(self.buffer)) if self.buffer[i][1] != -1]
        prio = max(priority_list)
        for i in range(self.priority_classes-1,prio-2,-1):
            for j in range(self.N):
                if self.voq_port_qsize[j][i]>0:
                    return i
        return -1
    
    def find_port_lowest_prio(self,prio):
        q_len = 0
        port_ind = -1
        for i in range(len(self.port_qsize)):
            try:
                if q_len < self.port_qsize[i+1] and self.voq_port_qsize[i][prio]>0 :
                    q_len = self.port_qsize[i+1]
                    port_ind = i+1
            except:
                print(prio)
                breakpoint()

        return port_ind
    
    def fetch(self):
        # find out the lowest priority queue
        mem_loc = []
        priot = self.find_lowest_prio()
        port = self.find_port_lowest_prio(priot)

        for ind,i in enumerate(self.buffer):
            if i[1] != -1:
                
                    if priot != -1:

                        # find the longest port of the lowest priority
                        # port = self.find_port_lowest_prio(prio)
                        # if port == i[0] and port!=-1:
                        #     port = -1
                        #     print("packet belongs to the longest queue")
                        # remove a packet from that queue
                        target_queue = self.queues[port][priot]
                        if port != -1:
                            if not target_queue.empty():
                                c=0

                                if self.flag == 1:
                                    if self.buffer[ind][0].priority == 1:
                                        print("Unfortunately Dropping priority 1 packet")
                                    #self.buffer[ind] = [-1,-1]
                                
                                while ((target_queue.queue[target_queue.qsize()-c-1].invalid ==1 and c!=target_queue.qsize()) or (c!=target_queue.qsize() and target_queue.queue[target_queue.qsize()-c-1].prvt == 1)):
                                    c+=1
                                
                                if c==target_queue.qsize(): 
                                    self.flag = 1
                                    break
                                
                                target_queue.queue[target_queue.qsize()-c-1].invalid = 1

                                if target_queue.queue[target_queue.qsize()-c-1].priority == 1:  
                                #     #breakpoint()
                                    print("dropping priority 1 packets --inversion")
                                    print("total usage = ", self.total_usage)
                                
                                mem_loc.append(1)
                                self.port_qsize[port] -= 1
                                self.voq_port_qsize[port-1][priot] -= 1
                                self.total_usage -= 1
                                
                            else:
                                print("critical error: target queue empty when trying to fetch for LQD")
                                breakpoint()
                        else:
                            if i[0].priority == 1:  
                                breakpoint()
                                print("dropping priority 1 packets -- couldnt find a port with lesser prio")
                                print("total usage = ", self.total_usage)
                            self.buffer[ind] = [-1,-1]            
                    else:
                        if i[0].priority == 1:  
                            print("dropping priority 1 packets -- no lesser prio found for drop")
                           # breakpoint()
                            print("total usage = ", self.total_usage)
                        self.buffer[ind] = [-1,-1]
        
        if self.flag == 1:
            #print("Unfortunately some packets were dropped due to lack of space in longest queue")
            self.flag = 0
        
        return mem_loc
                

    
    def allct(self,mem):
        space = sum(mem)
        trk = 0
        for prio in range(self.priority_classes):
            for ind,i in enumerate(self.buffer):
                if i[1] != -1 and i[0].priority == prio+1:
                        self.queues[i[1]][i[0].priority-1].put(i[0])
                        trk +=1
                        self.total_usage +=1
                        self.port_qsize[i[1]] += 1
                        self.setECNFlag(i[0], i[1])
                        self.voq_port_qsize[i[1]-1][i[0].priority-1]+=1
                        self.buffer[ind] = [-1,-1]
                if trk == space:
                    break
            if trk == space:
                break
            # if trk == space:
            #     break
        
        for i in range(len(self.buffer)):
            self.buffer[i] = [-1,-1]
        
        

###############################################################################################################################################################

    def handleRecvdPacket(self, inPort, packet, arrivalTime):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        outPort = self.getOutPort(self.addr, packet)  # output port the packet needs to be sent out on
        
################################################################################ BIT MAPPER ########################################################################################
        if self.per_port_buffer[outPort-1][packet.priority-1] == 0:
            self.per_port_buffer[outPort-1][packet.priority-1] = 1
            # we have to introduce a new field for packet.py
            packet.prvt = 1
            self.queues[outPort][packet.priority-1].put(packet)

        elif self.total_buffer_size > self.total_usage and self.buffer[inPort-1][1] == -1:

            self.total_usage +=1
            self.queues[outPort][packet.priority-1].put(packet)
            self.port_qsize[outPort] += 1
            self.voq_port_qsize[outPort-1][packet.priority-1]+=1
            self.setECNFlag(packet, outPort)
            #print(f"voq length = {[self.voq_port_qsize[c][0] for c in range(0,self.N)]}")
            # if packet.dstAddr == 'h13' and packet.srcPort == 943 and packet.dstPort == 943:
            #     print(arrivalTime)
            #     breakpoint()
            #print(f"Packet placed = {self.addr} at {outPort-1} {inPort-1} at time {self.t}")
            #print(f"port qsize = {self.port_qsize}")
        #print("Packets scheduled via final add")
        elif self.buffer[inPort-1][1] != -1 and self.total_buffer_size > self.total_usage:
            self.total_usage +=1
            self.queues[self.buffer[inPort-1][1]][self.buffer[inPort-1][0].priority-1].put(self.buffer[inPort-1][0])
            self.port_qsize[self.buffer[inPort-1][1]] += 1
            self.voq_port_qsize[self.buffer[inPort-1][1]-1][self.buffer[inPort-1][0].priority-1]+=1
            self.buffer[inPort-1] = [-1,-1]
            self.setECNFlag(packet, outPort)

        elif self.buffer[inPort-1][1] == -1:
  
            self.buffer[inPort-1] = [packet,outPort]
            self.packet_dropped+=1
            #self.dropped.append((packet.dstAddr,packet.srcAddr,packet.srcPort,packet.dstPort,packet.seqNum)) 
        # if packet.priority == 1:  
        #     breakpoint()