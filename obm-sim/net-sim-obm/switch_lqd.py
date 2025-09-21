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

    def __init__(self, addr, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr  # address of switch
        self.links = {}   # links indexed by port, i.e., {port:link, ......, port:link}
        self.queues = {}  # list of virtual output queues (of type queue.Queue) per port
                          # indexed by port, i.e., {port:[queue], ......, port:[queue]}
                          # each virtual output queue is a FIFO queue of infinite size
        self.voq_rr = {}  # stores the VOQ per port to be serviced next
        self.per_port_max_qsize = 5  # in terms of number of 1500B packets
        self.K = 25                   # threshold for ECN marking (in terms of number of packets)
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
        self.priority_max_q_l = 0
        self.dropped = []

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t+=1
        self.dropped = []
        # if self.addr == 't9':
        #     print(f"usage - {self.addr} - {self.total_usage/self.total_buffer_size}")
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
                            
                            self.links[port].send(packet, self.addr, currTimeslot)
                            
                            # print(f"sending packet from {i} when other prioritites have length = {self.voq_port_qsize[port-1]}")
                            # if i == 0:
                            #     breakpoint()
                            self.port_qsize[port] -= 1
                            self.sent+=1
                            self.total_usage-=1 
                            self.voq_port_qsize[port-1][i]-=1
                            flag_1 = 1
                            assert(self.port_qsize[port] >= 0)
                            break
                        else:
                            self.dropped.append((packet.dstAddr,packet.srcAddr,packet.srcPort,packet.dstPort,packet.seqNum))

                    if flag_1:
                        break

                else:
                    continue
            # start = self.voq_rr[port]
            # flag_1 = 0
            # for i in range(0,len(self.queues[port])+1):
            #     if self.queues[port][(start+i)%len(self.queues[port])].empty():
            #         continue
            #     else:
                    
            #         # if self.addr == 't1' and port-1 == 11:
            #         #     print(self.voq_port_qsize[port-1])
            #         #print(packet)
            #         for j in range(0,self.queues[port][(start+i)%len(self.queues[port])].qsize()):
            #             packet = self.queues[port][(start+i)%len(self.queues[port])].get_nowait()
            #             if packet.invalid == 0:
            #                 #print("packetsent")
            #                 #print(self.voq_port_qsize[port-1])
            #                 # if self.priority_max_q_l<self.voq_port_qsize[port-1][0]:
            #                 #     self.priority_max_q_l = self.voq_port_qsize[port-1][0]
            #                 #     print(self.priority_max_q_l)
            #                 #     with open("/home/dan/obm-sim/obm-sim/max_q_len.txt", "a", encoding="utf-8") as f:
            #                 #         f.write(f"{self.priority_max_q_l},{self.voq_port_qsize[port-1][1]},{self.voq_port_qsize[port-1][2]}\n")
            #                 self.voq_rr[port] = (start+i+1)%len(self.queues[port])
            #                 # if self.addr == 't1' and port-1 == 11:
            #                 #     print(f"serving {(start+i)%len(self.queues[port])}")
            #                 packet.hops +=1
            #                 # if packet.srcAddr == 'h106':
            #                 #     print(f'packet has reached switch - {self.addr}')
            #                 self.links[port].send(packet, self.addr, currTimeslot)
            #                 self.port_qsize[port] -= 1
            #                 self.sent+=1
            #                 #print(f"I - {self.addr} have {self.total_usage}/{self.total_buffer_size} packets in buffer")
            #                 #print(f"Packet sent = {self.addr} at {port-1} {(start+i)%len(self.queues[port])} at time {self.t}")
            #                 self.total_usage-=1 
            #                 self.voq_port_qsize[port-1][(start+i)%len(self.queues[port])]-=1
            #                 flag_1 = 1
            #                 assert(self.port_qsize[port] >= 0)
            #                 break
            #             # else:
            #             #     if self.addr == 't1' and port-1 == 11:
            #             #         print(f"Invalid packet!! for {(start+i)%len(self.queues[port])}")
                        
            #         if flag_1:
            #             break

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
        if self.k>0:
            #self.lvoq = self.priority_encoder(self.largest_index,self.k)
            mem = self.fetch()
            self.allct(mem,currTimeslot)
        
        #if self.t > self.t_track:
        #    self.t_track+=200
        #    if self.addr == 't9':
        #        print(f"switch {self.addr}, usage = {self.total_usage}, total = {self.total_buffer_size}")
        return self.packet_dropped,self.dropped
        
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
        for inPort in range(self.priority_classes):
            
            if self.voq_port_qsize[longest_ind-1][inPort]>=k:
                #print(f"got {k} locations")
                return inPort
        ##print(f"Not able to get {k} locations")
        #gjhg
        #print(f"voq {longest_ind-1}  = {self.voq_port_qsize[longest_ind-1]}")

        return 0
    
    def fetch(self):
        """
        Select up to self.k packets across per-class VOQs at self.largest_index.
        Debug prints show per-iteration candidates and the chosen (max timestamp) packet.
        """
        mem_loc = []
        DEBUG = getattr(self, "debug_fetch", True)
        DO_BREAK = (getattr(self, "k", 0) > 0)  # ← breakpoints only if k>0

        if self.largest_index is None or self.largest_index >= len(self.queues):
            if DEBUG:
                print("[fetch] no queues at largest_index:", self.largest_index)
            return mem_loc

        C = getattr(self, "priority_classes", 1)
        port_queues = self.queues[self.largest_index]  # list/array of class queues

        # Per-class candidate: timestamp + position (index inside the deque)
        ts  = [None] * C
        pos = [None] * C
        # Per-class search pointer (start at tail index for each class)
        ptr = [-1] * C

        # Initialize candidates by scanning from tail for each class queue
        if DEBUG:
            print(f"[fetch:init] port={self.largest_index}, classes={C}")
        for i in range(C):
            if i >= len(port_queues):
                if DEBUG:
                    print(f"  [init] class {i}: queue missing")
                continue
            q = port_queues[i]
            n = q.qsize()
            j = n - 1
            while j >= 0:
                pkt = q.queue[j]  # direct access to underlying deque
                if not getattr(pkt, "invalid", 0):
                    ts[i] = pkt.ArrivalTimeOnSwitch
                    pos[i] = j
                    ptr[i] = j - 1  # next search for this class continues leftward
                    break
                j -= 1
            if j < 0:
                ptr[i] = -1  # no valid candidate in this class
            if DEBUG:
                if ts[i] is not None:
                    print(f"  [init] class {i}: candidate idx={pos[i]} ts={ts[i]}")
                else:
                    print(f"  [init] class {i}: no candidate")

        selected = 0
        iter_no = 0
        while selected < self.k:
            iter_no += 1
            # Pick the class with the largest timestamp among available candidates
            best_i = None
            best_ts = None
            for i in range(C):
                if ts[i] is None:
                    continue
                if (best_ts is None) or (ts[i] > best_ts):
                    best_ts = ts[i]
                    best_i = i

            if DEBUG:
                cand_str = ", ".join(
                    [f"c{i}:(idx={pos[i]},ts={ts[i]})" if ts[i] is not None else f"c{i}:(none)"
                    for i in range(C)]
                )
                print(f"[iter {iter_no}] candidates: {cand_str}")
                if best_i is not None:
                    print(f"[iter {iter_no}] -> choose class {best_i} idx={pos[best_i]} ts={ts[best_i]}")

            if best_i is None:
                if DEBUG:
                    print(f"[iter {iter_no}] no candidates left; stopping (selected={selected})")
                break

            # Sanity check: chosen is indeed max among candidates
            if any(t is not None and t > best_ts for t in ts):
                print(f"[iter {iter_no}] ERROR: found candidate ts > chosen best_ts "
                    f"(best_ts={best_ts}, ts={ts})")
                # if DO_BREAK:
                #     breakpoint()

            # Commit exactly one packet: mark invalid, update counters, record mem_loc
            q_best = port_queues[best_i]
            idx    = pos[best_i]
            pkt    = q_best.queue[idx]
            pkt.invalid = 1
            self.packet_dropped+=1
            mem_loc.append(1)
            # if best_i == 0:
            #     breakpoint()

            # Counter updates
            self.port_qsize[self.largest_index] -= 1
            self.voq_port_qsize[self.largest_index - 1][best_i] -= 1
            self.total_usage -= 1

            if DEBUG:
                print(f"[iter {iter_no}] committed: class {best_i}, idx={idx}, ts={best_ts}")
                print(f"             counters: port_qsize[{self.largest_index}]={self.port_qsize[self.largest_index]}, "
                    f"voq_port_qsize[{self.largest_index-1}][{best_i}]={self.voq_port_qsize[self.largest_index-1][best_i]}, "
                    f"total_usage={self.total_usage}")

            # Refresh ONLY the chosen class's candidate (continue leftward)
            j = ptr[best_i]
            found = False
            while j >= 0:
                pkt2 = q_best.queue[j]
                if not getattr(pkt2, "invalid", 0):
                    ts[best_i]  = pkt2.ArrivalTimeOnSwitch
                    pos[best_i] = j
                    ptr[best_i] = j - 1
                    found = True
                    break
                j -= 1
            if not found:
                ts[best_i]  = None
                pos[best_i] = None
                ptr[best_i] = -1

            if DEBUG:
                if found:
                    print(f"[iter {iter_no}] next for class {best_i}: idx={pos[best_i]} ts={ts[best_i]}")
                else:
                    print(f"[iter {iter_no}] class {best_i}: no more candidates")

            selected += 1

        # Post-conditions / sanity checks
        if DEBUG:
            print(f"[fetch:end] selected={selected}, mem_loc_len={len(mem_loc)}, k={self.k}")
        if self.k != sum(mem_loc):
            print(f"[fetch:end] WARNING: k({self.k}) != sum(mem_loc)({sum(mem_loc)}).")
            # if DO_BREAK:
            #     breakpoint()
        if selected != len(mem_loc):
            print(f"[fetch:end] ERROR: selected({selected}) != len(mem_loc)({len(mem_loc)}).")
            # if DO_BREAK:
            #     breakpoint()
        
        # if self.k>8:
        #     breakpoint()
        return mem_loc


    
    def allct(self,mem,currTimeslot):
        space = sum(mem)
        trk = 0
        for ind,i in enumerate(self.buffer):
            if i[1] != -1:
                i[0].ArrivalTimeOnSwitch = currTimeslot
                self.queues[i[1]][i[0].priority - 1].put(i[0])
                trk +=1
                self.total_usage +=1
                self.port_qsize[i[1]] += 1
                self.setECNFlag(i[0], i[1])
                self.voq_port_qsize[i[1]-1][i[0].priority - 1]+=1
            if trk == space:
                break
        
        

###############################################################################################################################################################

    def handleRecvdPacket(self, inPort, packet, currTimeslot):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        outPort = self.getOutPort(self.addr, packet)  # output port the packet needs to be sent out on
        
################################################################################ BIT MAPPER ########################################################################################
        if self.total_buffer_size > self.total_usage:

            self.total_usage +=1
            packet.ArrivalTimeOnSwitch = currTimeslot
            self.queues[outPort][packet.priority - 1].put(packet)
            self.port_qsize[outPort] += 1
            self.voq_port_qsize[outPort-1][packet.priority - 1]+=1
            self.setECNFlag(packet, outPort)
            #if packet.srcAddr == 'h106':
                #print(f'packet is sitting in buffer in switch - {self.addr}')
            #print(f"Packet placed = {self.addr} at {outPort-1} {inPort-1} at time {self.t}")
            #print(f"port qsize = {self.port_qsize}")
        #print("Packets scheduled via final add")
        else:
            if outPort != (self.largest_index):
                self.buffer[inPort-1] = [packet,outPort]
                self.k +=1   
                #breakpoint()
                 
                #print("Initiated LQD")
            else:
                self.packet_dropped+=1
                self.dropped.append((packet.dstAddr,packet.srcAddr,packet.srcPort,packet.dstPort,packet.seqNum)) 
            #breakpoint()      


        
                
            
            
####################################################################################################################################################################################
                


