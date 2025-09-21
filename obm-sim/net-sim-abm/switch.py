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
        self.T = [[self.total_buffer_size/(self.ports*self.priority_classes) for _ in range(self.priority_classes)] for i in range(self.ports)]
        self.sent = 0
        self.alpha = [2,1,0.5]
        self.t = 0
        self.t_track = 0
        self.np = [0]*self.priority_classes
        self.bwu = [[0 for i in range(self.priority_classes)] for _ in range(self.ports)]
        self.nqa = [[1 for i in range(self.priority_classes)] for _ in range(self.ports)]
        self.K = 25
    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t+=1
        
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
                            self.bwu[port-1][packet.priority-1] += 1
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

                    if flag_1:
                        break

                else:
                    continue


        for port in self.links.keys():  # in each timeslot, receive a
                                        # pa cket (if any) on each input
                                        # port and handle it
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)
            else:
                self.final_add[port-1] = 0
        
        #if self.t > self.t_track:
        #    self.t_track+=200
        #    if self.addr == 't1':
        #        print(f"switch {self.addr}, usage = {self.total_usage}, total = {self.total_buffer_size}")
        #        print(f"Threshold output q - 0  = {self.T[0]}")
        #        print(f"Threshold output q - 1= {self.T[13]}")


        
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

    def threshold_calculate(self): # Threshold calculation for ABM - takes alpha into total alpha calculation only if the queue size is > 0 
        self.np = [0]*self.priority_classes
        
        for n2 in range(self.priority_classes):
            for n1 in range(self.ports):
                if self.voq_port_qsize[n1][n2] >= 0.9*self.T[n1][n2]:
                    self.np[n2]+=1
                # if self.voq_port_qsize[n1][n2] >= 1:
                #     self.nqa[n1] += 1
        # for n1 in range(self.ports):
        #     if self.nqa[n1] == 0:
        #         self.nqa[n1] = 4    
        for n1 in range(self.ports):
            if sum(self.bwu[n1]) >= 100:
                for n2 in range(self.priority_classes):
                    self.nqa[n1][n2] = self.bwu[n1][n2]/sum(self.bwu[n1])
                    if self.bwu[n1][n2] < 30:
                        self.nqa[n1][n2] = 1/3
                self.bwu[n1] = [0]*self.priority_classes
                

        
        # for n1 in range(self.ports):
        #     if sum(self.bwu[n1]) >= 10:
        #         for n2 in range(self.priority_classes):
        #             self.nqa[n1][n2] = self.bwu[n1][n2]/sum(self.bwu[n1])
                     
        #             if self.bwu[n1][n2] < 1:
        #                 self.nqa[n1][n2] = 1/10
                        
        #         self.bwu[n1] = [0]*self.priority_classes

            for n2 in range(self.priority_classes):
                if self.np[n2]==0:
                    self.T[n1][n2]= self.alpha[n2]*(self.total_buffer_size - self.total_usage)*(self.nqa[n1][n2])
                else:
                    self.T[n1][n2]= self.alpha[n2]*(self.total_buffer_size - self.total_usage)*(self.nqa[n1][n2])*(1/self.np[n2])
                
        
        
  
 

###############################################################################################################################################################

    def handleRecvdPacket(self, inPort, packet, arrivalTime):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        outPort = self.getOutPort(self.addr, packet)  # output port the packet needs to be sent out on
        
################################################################################ BIT MAPPER ########################################################################################
        if self.total_buffer_size > self.total_usage:
            
            # self.queues[outPort][inPort-1].put(packet)  # add packet to the right VOQ at the output port
            # self.queues have their keys same as the keys for the links but the sublist has its index starting from 0, so does self.port_qsize (first index only)
            # self.voq_port_qsize have their indices starting from 0 (because it doesnt use the keys from the links)
            
            if self.voq_port_qsize[outPort-1][packet.priority-1] < self.T[outPort-1][packet.priority-1]:
                self.final_add[inPort-1] = 1
                self.total_usage += 1
                
                self.queues[outPort][packet.priority-1].put(packet)
                self.port_qsize[outPort] += 1
                self.voq_port_qsize[outPort-1][packet.priority-1]+= 1
                self.setECNFlag(packet, outPort)
                #print(f"voq length = {[self.voq_port_qsize[c][0] for c in range(0,self.N)]}")
                # if packet.dstAddr == 'h13' and packet.srcPort == 943 and packet.dstPort == 943:
                #     print(arrivalTime)
                #     breakpoint()

               
            else:
                
                self.final_add[inPort-1] = 0
                self.packet_dropped += 1
                msg = f"switch {self.addr} - abm drop - {self.packet_dropped} \n"
                #print(f"voq length = {[self.voq_port_qsize[c][0] for c in range(0,self.N)]}")
                with open("/home/dan/LQD/obm-sim/obm-sim/drop_stats_abm.txt", "a") as f:
                    f.write(msg)
                with open("/home/dan/LQD/obm-sim/obm-sim/short_flow_completion_time_abm.txt", "a") as f:
                    f.write(f"dropped packet - {packet.dstAddr,packet.srcPort,packet.dstPort} - from switch - {self.addr} \n")
                pass
            
        else:
            self.final_add[inPort-1] = 0
            #print("Packet drop due to space constraint")
            #breakpoint()
            self.packet_dropped += 1
            msg = f"switch {self.addr} - space constrain drop - {self.packet_dropped} \n"
            with open("/home/dan/LQD/obm-sim/obm-sim/drop_stats_abm.txt", "a") as f:
                f.write(msg)
            pass
        
    
        self.threshold_calculate()

        #print(f"{self.T}/{self.total_buffer_size}")
        
                
            
            
####################################################################################################################################################################################
                


