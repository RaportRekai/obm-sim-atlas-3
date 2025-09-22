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
        self.per_port_max_qsize = 5  # in terms of number of 1500B packets
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
            print(num_tor_ports)
        elif self.addr[0] == 'a':
            
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize*num_agg_ports
            self.N = 1 if num_agg_ports < 1 else 2 ** ((num_agg_ports - 1).bit_length())
            self.voq_port_qsize = [[0 for i in range(self.priority_classes)] for _ in range (self.N)]
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
                            # if self.priority_max_q_l<self.voq_port_qsize[port-1][0]:
                            #     self.priority_max_q_l = self.voq_port_qsize[port-1][0]
                            #     print(self.priority_max_q_l)
                            #     with open("/home/dan/LQD/obm-sim/obm-sim/max_q_len.txt", "a", encoding="utf-8") as f:
                            #         f.write(f"{self.priority_max_q_l},{self.voq_port_qsize[port-1][1]},{self.voq_port_qsize[port-1][2]}\n")
                            
                            self.links[port].send(packet, self.addr, currTimeslot)
                            # if self.addr == 't1' and port == 7:
                            #     print(f"sending packet from {i} when other prioritites have length = {self.voq_port_qsize[port-1]}")
                            # # if i == 0:
                            #     breakpoint()
                            self.port_qsize[port] -= 1
                            self.sent+=1
                            self.total_usage-=1 
                            self.voq_port_qsize[port-1][i]-=1
                            flag_1 = 1
                            assert(self.port_qsize[port] >= 0)
                            break

                    if flag_1:
                        break

                else:
                    continue
        self.k = 0
        
        self.largest_index = max(self.port_qsize, key=self.port_qsize.get)
        #print(f"The largest q is {self.largest_index}")
        #print(f"port qsize = {self.port_qsize}")
        for port in self.links.keys():  # in each timeslot, receive a
                                        # pa cket (if any) on each input
                                        # port and handle it
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)
        
        for b in self.buffer:
            if b[1] != -1:
                self.k+=1
        
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

    def priority_encoder(self,longest_ind,k):
        for p_index in range(self.priority_classes):
            
            if self.voq_port_qsize[longest_ind-1][self.priority_classes-1-p_index]>0:
                if self.priority_classes -1 - p_index == 0:
                    breakpoint()
                return self.priority_classes-1-p_index
            
        for p_index in range(self.priority_classes):
            
            if self.voq_port_qsize[longest_ind-1][self.priority_classes-1-p_index]>=1:
                #print(f"got {k} locations")
                #breakpoint()
                return self.priority_classes-1-p_index
            
        #breakpoint()
        return self.priority_classes-1
    
    def fetch(self):
        mem_loc = []
        target_queue = self.queues[self.largest_index][self.lvoq]
        
        # if self.flag == 1:  
        #     print(f"target queue = {target_queue.qsize()}") # actual q size
        #     print(f"maxsize queue = {target_queue.maxsize}")
        #print(k)
        for h in range(self.k):
            if not target_queue.empty():  # Ensure the queue is not empty
                #print(f"Have removed an element from voq [{self.largest_index-1},{self.lvoq}]")
                #print(f"Number of packets available: {self.voq_port_qsize[self.largest_index-1][self.lvoq]}")
                
                # Access the last element directly
                #print(f"In contrast we have only {target_queue.qsize()} packets")
                #last_element = target_queue.queue.pop()  # Access the last element
                #last_element.invalid = 1  # Mark it as invalid (or any custom modification)
                c = 0
                while target_queue.queue[target_queue.qsize()-c-1].invalid ==1 and c!=target_queue.qsize():
                    c+=1
                if c==target_queue.qsize(): 
                    self.flag = 1
                    break
                target_queue.queue[target_queue.qsize()-c-1].invalid = 1
                mem_loc.append(1)  # Log the memory location (example)

                # Optionally remove the last element
                #target_queue.queue.pop()  # Remove the last element if needed
                self.port_qsize[self.largest_index] -= 1
                self.voq_port_qsize[self.largest_index-1][self.lvoq] -= 1
                self.total_usage -= 1 
                
            else:
                #print(f"Queue [{self.largest_index}][{ind}] is empty.")
                break  # Stop if the queue becomes empty
        
        return mem_loc
    
    def allct(self,mem):
        space = sum(mem)
        trk = 0
        for ind,i in enumerate(self.buffer):
            if i[1] != -1:
                self.queues[i[1]][i[0].priority-1].put(i[0])
                trk +=1
                self.total_usage +=1
                self.port_qsize[i[1]] += 1
                self.setECNFlag(i[0], i[1])
                self.voq_port_qsize[i[1]-1][i[0].priority-1]+=1
                self.buffer[ind] = [-1,-1]
            if trk == space:
                break
        
        

###############################################################################################################################################################

    def handleRecvdPacket(self, inPort, packet, arrivalTime):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        outPort = self.getOutPort(self.addr, packet)  # output port the packet needs to be sent out on
        
################################################################################ BIT MAPPER ########################################################################################
        if self.total_buffer_size > self.total_usage and self.buffer[inPort-1][1] == -1:

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
            if packet.priority < self.buffer[inPort-1][0].priority:
                self.buffer[inPort -1] = [packet,outPort]
            self.total_usage +=1
            self.queues[self.buffer[inPort-1][1]][self.buffer[inPort-1][0].priority-1].put(self.buffer[inPort-1][0])
            self.port_qsize[self.buffer[inPort-1][1]] += 1
            self.voq_port_qsize[self.buffer[inPort-1][1]-1][self.buffer[inPort-1][0].priority-1]+=1
            self.buffer[inPort-1] = [-1,-1]
        
        elif self.buffer[inPort-1][1] != -1:
            enter = 0
            if outPort == self.largest_index:
                for p in range(3,packet.priority,-1):
                    if self.voq_port_qsize[outPort-1][p - 1]>0:
                        enter = 1
                        #breakpoint()
            
            if packet.priority < self.buffer[inPort-1][0].priority and enter == 1:
                self.buffer[inPort -1] = [packet,outPort]
            
            elif packet.priority == 1:
                print("strt drop")


        elif self.buffer[inPort-1][1] == -1:
            
            enter = 0
            if outPort == self.largest_index:
                for p in range(3,packet.priority,-1):
                    if self.voq_port_qsize[outPort-1][p - 1]>0:
                        enter = 1
                        #breakpoint()
                    
            if outPort != (self.largest_index) or (enter == 1):
                self.buffer[inPort-1] = [packet,outPort]
                #self.k +=1   
                #breakpoint()
                #print("Initiated LQD")    
            else:
                if packet.priority == 1:
                    print("strt drop")
                    
            #     if packet.dstAddr == 'h29':
            #         #breakpoint()
            


        
                
            
            
####################################################################################################################################################################################
                


