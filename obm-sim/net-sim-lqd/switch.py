# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import queue
import hashlib
from link import Link
import math
import copy
import os


class Switch:
    """Switch class"""

    def __init__(self, addr, num_tor_ports, num_agg_ports, hosts_per_rack):
        """Initialize parameters"""
        self.addr = addr  # address of switch
        self.links = {}   # links indexed by port
        self.queues = {}  # list of virtual output queues per port
        self.voq_rr = {}  # stores the VOQ per port to be serviced next

        self.per_port_max_qsize = 5  # in terms of number of 1500B packets
        self.K = 25                  # threshold for ECN marking
        self.flag = 0

        self.num_tor_ports = num_tor_ports
        self.num_agg_ports = num_agg_ports
        self.hosts_per_rack = hosts_per_rack

        self.packet_dropped = 0
        self.port_qsize = {}  # number of packets queued per port
        self.priority_classes = 3

        # Buffer Sizing
        if self.addr[0] == 't':
            self.ports = num_tor_ports
            self.total_buffer_size = self.per_port_max_qsize * num_tor_ports
            self.N = 1 if num_tor_ports < 1 else 2 ** ((num_tor_ports - 1).bit_length())
            self.voq_port_qsize = [[0 for _ in range(self.priority_classes)] for _ in range(self.N)]
        elif self.addr[0] == 'a':
            self.ports = num_agg_ports
            self.total_buffer_size = self.per_port_max_qsize * num_agg_ports
            self.N = 1 if num_agg_ports < 1 else 2 ** ((num_agg_ports - 1).bit_length())
            self.voq_port_qsize = [[0 for _ in range(self.priority_classes)] for _ in range(self.N)]
        else:
            # Fallback (should not happen in your topology)
            self.ports = 0
            self.total_buffer_size = 0
            self.N = 1
            self.voq_port_qsize = [[0 for _ in range(self.priority_classes)] for _ in range(self.N)]

        # Operational Variables
        self.total_usage = 0
        self.sent = 0
        self.t = 0
        self.k = 0
        self.buffer = [[-1, -1] for _ in range(self.N)]
        self.dropped = []
        self.largest_index = None

        # --- CREDENCE / RF MODEL TRAINING VARIABLES ---
        self.avg_q_len = 0.0
        self.avg_occ = 0.0
        # Alpha for EWMA. Fixed RTT = 30 timestamps.
        self.alpha = 2 / (30 + 1)

        # Switch-assigned unique ID for packet arrivals (per switch)
        self.arrival_uid = 0

        # The Master Log for Training Data
        # Format: { "switch_uid": [queueLength, sharedOccupancy, avgQ, avgOcc, drop_status] }
        self.packet_history = {}
        self.weights = [3,2,1]
        self.current_prio_idx = {port+1: 0 for port in range(self.N)}
        self.tokens = {port+1: self.weights[0] for port in range(self.N)}

    def runSwitch(self, currTimeslot):
        """Main loop of switch"""
        self.t += 1
        self.dropped = []

        # 1. SENDING LOGIC (Round Robin-ish over ports and priorities)
        for port in self.links.keys():
             for _ in range(self.priority_classes):
                prio = self.current_prio_idx[port]
                
                # 1. Refill Logic: If tokens are exhausted, move pointer and refill
                if self.tokens[port] <= 0:
                    self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                    prio = self.current_prio_idx[port]
                    self.tokens[port] = self.weights[prio]

                # 2. Check Queue
                if not self.queues[port][prio].empty():
                    # Get the single packet at the head of the line
                    packet = self.queues[port][prio].get_nowait()
                    
                    if packet.invalid == 0:
                        # --- VALID PACKET ---
                        
                        self.links[port].send(packet, self.addr, currTimeslot)
                        
                        # Update Stats
                        self.port_qsize[port] -= 1
                        self.sent += 1
                        self.total_usage -= 1 
                        self.voq_port_qsize[port-1][prio] -= 1
                        
                        # WRR: Consume token & Success
                        self.tokens[port] -= 1
                        sent_in_this_slot = True
                        assert(self.port_qsize[port] >= 0)

                        # Post-send: If tokens done or queue empty, prep next prio for NEXT slot
                        if self.tokens[port] <= 0 or self.queues[port][prio].empty():
                            self.tokens[port] = 0
                            self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                        
                        break # Packet sent! Stop processing this port.

                    else:
                        # --- INVALID PACKET ---
                        # Log the drop
                        self.dropped.append((packet.dstAddr, packet.srcAddr, packet.srcPort, packet.dstPort, packet.seqNum))
                        
                        # WRR: Consume token (penalty for processing invalid packet)
                        self.tokens[port] -= 1
                        
                        # Check for exhaustion
                        if self.tokens[port] <= 0 or self.queues[port][prio].empty():
                            self.tokens[port] = 0
                        
                        # Move Pointer Immediately
                        self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                        
                        # Continue the loop to check the NEXT priority immediately
                        continue 

                else:
                    # 3. EMPTY QUEUE
                    # "Waste" tokens and move to next priority to keep searching
                    self.tokens[port] = 0
                    self.current_prio_idx[port] = (prio + 1) % self.priority_classes
                    continue
                
        # 2. LQD PREPARATION
        self.k = 0
        self.buffer = [[-1, -1] for _ in range(self.N)]

        # Identify the port with the longest queue (Victim Port)
        if self.port_qsize:
            self.largest_index = max(self.port_qsize, key=self.port_qsize.get)
        else:
            self.largest_index = None

        # 3. RECEIVING PACKETS
        for port in self.links.keys():
            packet = self.links[port].recv(self.addr, currTimeslot)
            if packet:
                self.handleRecvdPacket(port, packet, currTimeslot)

        # 4. EXECUTE LQD (If k > 0, we need to free space)
        if self.k > 0:
            mem = self.fetch()
            self.allct(mem, currTimeslot)

        return self.packet_dropped, self.dropped

    def handleRecvdPacket(self, inPort, packet, currTimeslot):
        """Handle incoming packet and Log State for RF Training"""
        outPort = self.getOutPort(self.addr, packet)

        # --- CREDENCE LOGGING START ---
        # 1. Update Moving Averages (based on target outPort state)
        current_q = self.port_qsize.get(outPort, 0)
        current_occ = self.total_usage

        self.avg_q_len = (1 - self.alpha) * self.avg_q_len + (self.alpha * current_q)
        self.avg_occ = (1 - self.alpha) * self.avg_occ + (self.alpha * current_occ)

        # 2. Generate Switch-Assigned Unique ID (per arrival event)
        self.arrival_uid += 1
        unique_id = f"{self.addr}_{self.arrival_uid}"
        # Persist on the packet so fetch() can update the correct row later
        packet.switch_uid = unique_id

        # 3. Log Initial State (Default drop = 0)
        # Record the state *before* we make the drop/enqueue decision
        self.packet_history[unique_id] = [
            current_q,
            current_occ,
            round(self.avg_q_len, 4),
            round(self.avg_occ, 4),
            0
        ]
        # --- CREDENCE LOGGING END ---

        # Buffer Management Logic
        if self.total_buffer_size > self.total_usage:
            # Buffer has space
            self.total_usage += 1
            packet.ArrivalTimeOnSwitch = currTimeslot
            self.queues[outPort][packet.priority - 1].put(packet)
            self.port_qsize[outPort] += 1
            self.voq_port_qsize[outPort - 1][packet.priority - 1] += 1
            self.setECNFlag(packet, outPort)
        else:
            # Buffer Full - Attempt LQD or Drop
            if self.largest_index is not None and outPort != self.largest_index:
                # Congestion is elsewhere; park packet in temp buffer and increment k to trigger LQD
                self.buffer[inPort - 1] = [packet, outPort]
                self.k += 1
            else:
                # Immediate Tail Drop (Congestion is here, or can't swap)
                self.packet_dropped += 1
                self.dropped.append((packet.dstAddr, packet.srcAddr, packet.srcPort, packet.dstPort, packet.seqNum))

                # --- UPDATE LOG: PACKET DIED IMMEDIATELY ---
                self.packet_history[unique_id][4] = 1

    def fetch(self):
        """
        Selects packets to drop (victim selection) based on timestamp (LIFO).
        Marks victims invalid and updates 'packet_history' (drop=1) using packet.switch_uid.
        """
        mem_loc = []
        DEBUG = getattr(self, "debug_fetch", False)  # Set True if you want extra checks

        if self.largest_index is None:
            return mem_loc

        # The dict 'self.queues' is keyed by port number; we expect largest_index to be a valid port key
        if self.largest_index not in self.queues:
            return mem_loc

        C = getattr(self, "priority_classes", 1)
        port_queues = self.queues[self.largest_index]  # list of per-priority queues

        # Init pointers for all priority classes
        ts = [None] * C
        pos = [None] * C
        ptr = [-1] * C

        for i in range(C):
            if i >= len(port_queues):
                continue
            q = port_queues[i]
            n = q.qsize()
            j = n - 1
            # Find newest valid packet in this priority queue
            while j >= 0:
                pkt = q.queue[j]
                if not getattr(pkt, "invalid", 0):
                    ts[i] = pkt.ArrivalTimeOnSwitch
                    pos[i] = j
                    ptr[i] = j - 1
                    break
                j -= 1
            if j < 0:
                ptr[i] = -1

        selected = 0
        while selected < self.k:
            best_i = None
            best_ts = None

            # Tournament: Find newest packet across all classes
            for i in range(C):
                if ts[i] is None:
                    continue
                if best_ts is None or ts[i] > best_ts:
                    best_ts = ts[i]
                    best_i = i

            if best_i is None:
                break

            # Mark packet as invalid (Virtual Drop)
            q_best = port_queues[best_i]
            idx = pos[best_i]
            pkt = q_best.queue[idx]
            pkt.invalid = 1

            self.packet_dropped += 1
            mem_loc.append(1)

            # --- UPDATE LOG: PACKET WAS EVICTED ---
            victim_id = getattr(pkt, "switch_uid", None)
            if victim_id is not None and victim_id in self.packet_history:
                self.packet_history[victim_id][4] = 1
            # --------------------------------------

            # Update switch counters
            self.port_qsize[self.largest_index] -= 1
            self.voq_port_qsize[self.largest_index - 1][best_i] -= 1
            self.total_usage -= 1

            # Advance pointer for the chosen class
            j = ptr[best_i]
            found = False
            while j >= 0:
                pkt2 = q_best.queue[j]
                if not getattr(pkt2, "invalid", 0):
                    ts[best_i] = pkt2.ArrivalTimeOnSwitch
                    pos[best_i] = j
                    ptr[best_i] = j - 1
                    found = True
                    break
                j -= 1
            if not found:
                ts[best_i] = None
                pos[best_i] = None
                ptr[best_i] = -1

            selected += 1

        return mem_loc

    def allct(self, mem, currTimeslot):
        """Move packets from temp buffer to real queue after space is made"""
        space = sum(mem)
        trk = 0
        for _, entry in enumerate(self.buffer):
            if entry[1] != -1:
                # Reset timestamp because it is entering the real queue now
                entry[0].ArrivalTimeOnSwitch = currTimeslot
                self.queues[entry[1]][entry[0].priority - 1].put(entry[0])
                trk += 1
                self.total_usage += 1
                self.port_qsize[entry[1]] += 1
                self.setECNFlag(entry[0], entry[1])
                self.voq_port_qsize[entry[1] - 1][entry[0].priority - 1] += 1
            if trk == space:
                break

    def setECNFlag(self, packet, outPort):
        if self.port_qsize[outPort] > self.K:
            packet.ecnFlag = 1

    def ecmp(self, packet):
        flowid = packet.srcAddr + packet.dstAddr + str(packet.srcPort) + str(packet.dstPort)
        outPort = (
            int(hashlib.sha256(flowid.encode('utf-8')).hexdigest(), 16)
            % (self.num_tor_ports - self.hosts_per_rack)
            + (self.hosts_per_rack + 1)
        )
        return outPort

    def getOutPort(self, switchId, packet):
        if switchId[0] == 't':
            if int(packet.dstAddr[1:]) >= int(switchId[1]) * 16 - 15 and int(packet.dstAddr[1:]) <= int(switchId[1]) * 16:
                return int(packet.dstAddr[1:]) - ((int(switchId[1]) - 1) * 16)
            else:
                return self.ecmp(packet)
        elif switchId[0] == 'a':
            return int((int(packet.dstAddr[1:]) - 1) / 16) + 1

    def export_training_data(self, filename="training_data.csv"):
        """Call this at the end of the simulation to dump the CSV (space-separated)."""
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
