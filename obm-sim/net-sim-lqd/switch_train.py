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
        self.links = {}   # links indexed by port
        self.queues = {}  # list of virtual output queues
        self.voq_rr = {}  # stores the VOQ per port to be serviced next
        self.per_port_max_qsize = 3  # in terms of number of 1500B packets
        self.flag = 0
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

        # ### --- CREDENCE / RF MODEL TRAINING VARIABLES ---
        self.avg_q_len = 0.0
        self.avg_occ = 0.0
        # Alpha for EWMA. Fixed RTT = 30 timestamps.
        self.alpha_ewma = 2 / (30 + 1)

        # Switch-assigned unique ID for packet arrivals (per switch)
        self.arrival_uid = 0

        # The Master Log for Training Data
        # Format: { "switch_uid": [queueLength, sharedOccupancy, avgQ, avgOcc, drop_status] }
        self.packet_history = {}


    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t+=1
        self.l_uni = []
       
        # 1. SENDING LOGIC
        for port in self.links.keys():  
            flag_1 = 0
            for i in range(self.priority_classes):
                if not self.queues[port][i].empty():
                    for j in range(0,self.queues[port][i].qsize()):
                        packet = self.queues[port][i].get_nowait()
                        
                        # Check validity (LQD may have marked it invalid)
                        if getattr(packet, "invalid", 0) == 0:
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
                        else:
                            # ### --- CREDENCE LOGGING ---
                            # Packet was virtually dropped. We already logged this in fetch(), 
                            # but we strictly discard it here.
                            pass

                    if flag_1:
                        break

                else:
                    continue
        
        self.k = 0
        
        # Determine congestion
        if self.port_qsize:
            self.largest_index = max(self.port_qsize, key=self.port_qsize.get)
        else:
            self.largest_index = None # Handle empty switch case

        # 2. RECEIVING PACKETS
        for port in self.links.keys(): 
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)
        
        # Calculate K (how many slots needed)
        for b in self.buffer:
            if b[1] != -1:
                self.k+=1
        
        # 3. EXECUTE LQD / BIT MAPPER EVICTION
        if self.k > 0 and self.largest_index is not None:
            self.lvoq = self.priority_encoder(self.largest_index, self.k)
            mem = self.fetch()
            self.allct(mem)


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
        while not queue_instance.empty():
            elements.append(queue_instance.get())
        index_of_largest = elements.index(max(elements))
        for item in elements:
            queue_instance.put(item)
        return index_of_largest

    def priority_encoder(self,longest_ind,k):
        # Safety check if queue is empty
        if longest_ind not in self.voq_port_qsize: 
             return self.priority_classes-1
             
        for p_index in range(self.priority_classes):
            if self.voq_port_qsize[longest_ind-1][self.priority_classes-1-p_index]>0:
                return self.priority_classes-1-p_index
            
        for p_index in range(self.priority_classes):
            if self.voq_port_qsize[longest_ind-1][self.priority_classes-1-p_index]>=1:
                return self.priority_classes-1-p_index
            
        return self.priority_classes-1
    
    def fetch(self):
        """
        Eviction Logic: Marks packets as invalid to make space.
        Updates Credence history to 'drop = 1'.
        """
        mem_loc = []
        if self.largest_index is None: return mem_loc

        target_queue = self.queues[self.largest_index][self.lvoq]
        
        for h in range(self.k):
            if not target_queue.empty():  
                # Find the newest valid packet (scanning from back)
                c = 0
                q_len = target_queue.qsize()
                
                # Check for bounds and validity
                while ((target_queue.queue[target_queue.qsize()-c-1].invalid ==1 and c!=target_queue.qsize()) or (target_queue.queue[target_queue.qsize()-c-1].prvt == 1 and c!=target_queue.qsize())):
                    c += 1
                
                if c == q_len: 
                    self.flag = 1
                    break
                
                # Mark invalid
                victim_pkt = target_queue.queue[q_len-c-1]
                victim_pkt.invalid = 1
                mem_loc.append(1) 

                # ### --- CREDENCE LOGGING UPDATE ---
                # The packet was evicted. Update its log entry to drop=1.
                v_uid = getattr(victim_pkt, "switch_uid", None)
                if v_uid is not None and v_uid in self.packet_history:
                    self.packet_history[v_uid][4] = 1
                # -----------------------------------

                self.port_qsize[self.largest_index] -= 1
                self.voq_port_qsize[self.largest_index-1][self.lvoq] -= 1
                self.total_usage -= 1 
                
            else:
                break 
        
        return mem_loc
    
    def allct(self, mem):
        space = sum(mem)
        trk = 0
        for ind, i in enumerate(self.buffer):
            if i[1] != -1:
                # Move from temp buffer to real queue
                self.queues[i[1]][i[0].priority-1].put(i[0])
                trk += 1
                self.total_usage += 1
                self.port_qsize[i[1]] += 1
                self.setECNFlag(i[0], i[1])
                self.voq_port_qsize[i[1]-1][i[0].priority-1] += 1
                self.buffer[ind] = [-1, -1]
            if trk == space:
                break
        for i in self.buffer:
            if i[0]!=-1:
                unique_id = i[0].switch_uid
                self.packet_history[unique_id][4] = 1 
                if i[0].priority == 1:
                    print("dropping priority 1 packets --no space")
        self.buffer = [[-1,-1] for _ in range(len(self.buffer))]
        
    ###############################################################################################################################################################

    def handleRecvdPacket(self, inPort, packet, arrivalTime):
        """Handle the packet received on the specified input port 'inPort'.
           arrivalTime is the timeslot in which the packet was received"""
        
        outPort = self.getOutPort(self.addr, packet)

        # ### --- CREDENCE LOGGING START ---
        # 1. Update Moving Averages based on the target outPort
        current_q = self.port_qsize.get(outPort, 0)
        current_occ = self.total_usage

        self.avg_q_len = (1 - self.alpha_ewma) * self.avg_q_len + (self.alpha_ewma * current_q)
        self.avg_occ = (1 - self.alpha_ewma) * self.avg_occ + (self.alpha_ewma * current_occ)

        # 2. Generate Switch-Assigned Unique ID
        self.arrival_uid += 1
        unique_id = f"{self.addr}_{self.arrival_uid}"
        packet.switch_uid = unique_id # Tag packet

        # 3. Log Initial State (Default drop = 0)
        self.packet_history[unique_id] = [
            current_q,
            current_occ,
            round(self.avg_q_len, 4),
            round(self.avg_occ, 4),
            0 # Initially not dropped
        ]
        # ### --- CREDENCE LOGGING END ---
        
        ################################################################################ BIT MAPPER ########################################################################################
        
        # CASE 1: Buffer has space, slot is empty. Admit directly.
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
        
        # CASE 2: Buffer has space, but slot occupied. Perform swap if needed, queue buffer content.
        elif self.buffer[inPort-1][1] != -1 and self.total_buffer_size > self.total_usage:
            if packet.priority < self.buffer[inPort-1][0].priority:
                # Swap: Current packet goes to buffer, old buffer packet goes to queue
                temp = self.buffer[inPort-1]
                self.buffer[inPort -1] = [packet,outPort]
                
                # Admit the old packet
                self.total_usage +=1
                self.queues[temp[1]][temp[0].priority-1].put(temp[0])
                self.port_qsize[temp[1]] += 1
                self.voq_port_qsize[temp[1]-1][temp[0].priority-1]+=1
            else:
                # No swap, admit current packet
                self.total_usage +=1
                self.queues[outPort][packet.priority-1].put(packet)
                self.port_qsize[outPort] += 1
                self.voq_port_qsize[outPort-1][packet.priority-1]+=1
                self.setECNFlag(packet, outPort)
        
        # CASE 3: Buffer Full. Slot Occupied.
        elif self.buffer[inPort-1][1] != -1:
            enter = 0
            if outPort == self.largest_index:
                for p in range(3,packet.priority,-1):
                    if self.voq_port_qsize[outPort-1][p - 1]>0:
                        enter = 1
            
            if packet.priority < self.buffer[inPort-1][0].priority and enter == 1:
                # We overwrite the buffer with higher priority packet. 
                # The packet previously in the buffer is DROPPED.
                # However, for Credence training, we are tracking the *current* packet's fate.
                # If current overwrites buffer, current is saved (for now).
                
                # Mark the overwritten packet as dropped in history
                overwritten_pkt = self.buffer[inPort-1][0]
                o_uid = getattr(overwritten_pkt, "switch_uid", None)
                if o_uid and o_uid in self.packet_history:
                    self.packet_history[o_uid][4] = 1

                self.buffer[inPort -1] = [packet,outPort]
            
            else:
                # Current packet cannot dislodge buffer. Current packet is DROPPED.
                print("strt drop") 
                self.packet_dropped += 1
                self.packet_history[unique_id][4] = 1 # Log drop

        # CASE 4: Buffer Full. Slot Empty.
        elif self.buffer[inPort-1][1] == -1:
            enter = 0
            if outPort == self.largest_index:
                for p in range(3,packet.priority,-1):
                    if self.voq_port_qsize[outPort-1][p - 1]>0:
                        enter = 1
                    
            if outPort != (self.largest_index) or (enter == 1):
                # Place in temp buffer, trigger LQD later
                self.buffer[inPort-1] = [packet,outPort]
            else:
                # Tail Drop
                print("strt drop")
                self.packet_dropped += 1
                self.packet_history[unique_id][4] = 1 # Log drop

    def export_training_data(self, filename="training_data.csv"):
        """Call this at the end of the simulation to dump the CSV."""
        print(f"Exporting {len(self.packet_history)} records to {filename}...")
        try:
            with open(filename, "w") as f:
                # Header (space-separated)
                f.write("queueLength sharedOccupancy averageQueueLength averageOccupancy drop\n")
                # Rows
                for _, data in self.packet_history.items():
                    f.write(" ".join(map(str, data)) + "\n")
            print("Export complete.")
        except Exception as e:
            print(f"Failed to export data: {e}")