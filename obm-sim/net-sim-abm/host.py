# The code is subject to Purdue University copyright policies.
# Do not share, distribute, or post online.

import sys
import math
import queue
from packet import Packet
from dataclasses import dataclass
from math import fabs
from collections import defaultdict

class Host:
    """Host class"""

    def __init__(self, addr):
        """Inititalize parameters"""
        self.addr = addr
        self.link = None
        
        self.flow_track = {}
        self.reordering_count = 0
        self.initial_seq = 0
        self.reordering_cnt = defaultdict(int)        # per-flow cumulative count
        self._reorder_events_outbox = defaultdict(list)


        self.priority = {}  # a dictionary storing state for active flows sourced at this host
                            # key: 3-tuple (dst addr, src port, dst port)
                            # value: [flow size (in number of packets), next seq num to send, last ack num recvd, timer]
        
        self.sFlows = {}    # a dictionary storing state for active flows sourced at this host
                            # key: 3-tuple (dst addr, src port, dst port)
                            # value: [flow size (in number of packets), next seq num to send, last ack num recvd, timer]

        self.rFlows = {}    # a dictionary storing state for active flows destined to this host
                            # key: 3-tuple (src addr, src port, dst port)
                            # value: [id, flow size (in number of packets), next expected seq num, flow start time, time last pkt sent, dup ack sent]

        self.rrSched = []   # stores the list of active flows sourced at this host
                            # for round-robin scheduling

        self.rrPointer = 0  # points to the flow to be scheduled according to round-robin

        self.cwnd = {}      # a dictionary storing the congestion window for active flows
                            # key: 3-tuple (dst addr, src port, dst port)
                            # value: congestion window

        self.alpha = {}     # a dictionary storing the alpha value for active flows
                            # key: 3-tuple (dst addr, src port, dst port)
                            # value: alpha

        self.numPktSentInCurrWin = {}   # key: 3-tuple (dst addr, src port, dst port)
                                        # value: number of packets sent in current window

        self.packetLogFile = None

        self.numAckRecvdInCurrWin = {}     # key: 3-tuple (dst addr, src port, dst port)
                                           # value: number of acks received in current window

        self.numECNAckRecvdInCurrWin = {}  # key: 3-tuple (dst addr, src port, dst port)
                                           # value: number of acks received in current window with ECN flag set

        self.RTO = 1000  # in unit of timeslots


    def logPacket(self, packet):
        self.packetLogFile.write("src: " + packet.srcAddr + ", dst: " + packet.dstAddr)
        self.packetLogFile.write(", sport: " + str(packet.srcPort) + ", dport: " + str(packet.dstPort))
        self.packetLogFile.write(", seqNum: " + str(packet.seqNum) + ", ackNum: " + str(packet.ackNum))
        self.packetLogFile.write(", ackFlag: " + str(packet.ackFlag) + ", ecnFlag: " + str(packet.ecnFlag))
        self.packetLogFile.write(", route: ")
        self.packetLogFile.write('->'.join('(%s,%s,%s)' % x for x in packet.route))
        self.packetLogFile.write("\n\n")
        self.packetLogFile.flush()

    def _key(self, pkt):
        return (pkt.dstAddr, pkt.srcAddr, pkt.dstPort, pkt.srcPort)

    def on_packet(self, pkt) -> bool:
        key = self._key(pkt)
        st = self.flow_track.get(key)
        if st is None:
            st = {"next_expected": self.initial_seq, "ooo_set": set()}
            self.flow_track[key] = st

        seq = pkt.seqNum
        ne  = st["next_expected"]
        oset = st["ooo_set"]

        if seq == ne:
            ne += 1
            while ne in oset:
                oset.remove(ne)
                ne += 1
            st["next_expected"] = ne
            return False

        if seq < ne:
            return False

        # Out-of-order (first time for this early seq)
        if seq not in oset:
            oset.add(seq)
            self.reordering_cnt[key] += 1
            self._reorder_events_outbox[key].append((ne, seq, pkt.priority))  # ← store (next_expected, received)
            return True

        return False
    
    def runHost(self, currTimeslot, flowLogFile, ackQueues, totalPktSent, totalPktRecvd, totalFlowsFinished):
        """Main loop of host"""

        self.sendPacket(currTimeslot, totalPktSent)  # in each timeslot, send a
                                                     # packet (if any) out on the link

        self.handleRecvdAcks(ackQueues[self.addr], totalFlowsFinished,currTimeslot)  # handle received ACKs

        if self.link:  # in each timeslot, receive a
                       # packet (if any) from the link
                       # and handle it
            packet = self.link.recv(self.addr, currTimeslot)
            if packet:
                if packet.dstAddr != self.addr:
                    sys.stdout.write("Routing Error: Packet with dst " + packet.dstAddr + " was received at " + self.addr + "\n")
                    return
                packet.route.append((packet.node, packet.entryTimeslot, '-'))
                self.logPacket(packet)

                if packet.ackFlag == 0:
                    if (packet.srcAddr,packet.srcPort,packet.dstPort) not in self.rFlows:
                        pass
                    elif packet.seqNum < self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2]:
                        pass
                    elif packet.seqNum == self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2]:
                        totalPktRecvd[0] += 1
                        if packet.seqNum == self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][1] - 1: # last packet
                            timeLastPktSent = int(packet.route[0][2])
                            self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][4] = timeLastPktSent
                        self.handleRecvdPacket(packet, ackQueues,currTimeslot)
                        self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2] += 1
                        self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][5] = 0
                        # log finished flow
                        Id = self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][0]
                        flowsize = self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][1]
                        starttime = self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][3]
                        timeLastPktSent = self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][4]
                        if self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2] == flowsize:
                            flowLogFile.write(str(Id) + ", ")
                            flowLogFile.write("src: " + packet.srcAddr + ", dst: " + packet.dstAddr)
                            flowLogFile.write(", sport: " + str(packet.srcPort) + ", dport: " + str(packet.dstPort))
                            flowLogFile.write(", flowsize: " + str(flowsize))
                            flowLogFile.write(", starttime: " + str(starttime))
                            flowLogFile.write(", finishtime: " + str(currTimeslot))
                            fct = currTimeslot - starttime
                            flowLogFile.write(", fct: " + str(fct))
                            recvTput = (flowsize * 1500 * 8)/(fct * 120.0)
                            flowLogFile.write(", recvtput: " + str(round(recvTput,2)) + " Gbps")
                            assert(timeLastPktSent >= starttime)
                            timeToSendFlow = timeLastPktSent - starttime + 1
                            sendTput = (flowsize * 1500 * 8)/(timeToSendFlow * 120.0)
                            flowLogFile.write(", sendtput: " + str(round(sendTput,2)) + " Gbps")
                            flowLogFile.write("\n\n")
                            flowLogFile.flush()
                            # delete finished flow
                            del self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)]
                    elif packet.seqNum > self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2]:
                        self.on_packet(packet) 
                    elif self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][5] == 0:
                        self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][5] = 1
                        ackPacket = Packet(packet.dstAddr, packet.srcAddr, packet.dstPort, packet.srcPort, 0, self.rFlows[(packet.srcAddr,packet.srcPort,packet.dstPort)][2], 1, packet.ecnFlag)
                        ackQueues[packet.srcAddr].put(ackPacket)
        return self.reordering_cnt,self._reorder_events_outbox

    def sendPacket(self, currTimeslot, totalPktSent):
        """Strict-priority scheduler with RR within each priority."""

        if len(self.rrSched) > 0:
            dst = "0"
            sport = 0
            dport = 0

            i = 0
            schedFlow = 0
            while i < len(self.rrSched):
                i += 1
                dst, sport, dport = self.rrSched[self.rrPointer]
                if self.numPktSentInCurrWin[(dst,sport,dport)] < self.cwnd[(dst,sport,dport)] and self.sFlows[(dst,sport,dport)][1] < self.sFlows[(dst,sport,dport)][0]:
                    schedFlow = 1
                    if self.numPktSentInCurrWin[(dst,sport,dport)] == 0:
                        self.numAckRecvdInCurrWin[(dst,sport,dport)] = 0
                        self.numECNAckRecvdInCurrWin[(dst,sport,dport)] = 0
                    break
                elif currTimeslot - self.sFlows[(dst,sport,dport)][3] >= self.RTO: # timer expired
                    self.sFlows[(dst,sport,dport)][1] = self.sFlows[(dst,sport,dport)][2]
                    self.numPktSentInCurrWin[(dst,sport,dport)] = self.numAckRecvdInCurrWin[(dst,sport,dport)]
                    assert(self.numPktSentInCurrWin[(dst,sport,dport)] >= 0)
                    #print("Timer expired!")
                else:
                    self.rrPointer = (self.rrPointer + 1) % len(self.rrSched)

            
            if schedFlow == 1:
                # Send exactly one packet
                seqNum = self.sFlows[(dst, sport, dport)][1]
                packet = Packet(self.addr, dst, sport, dport, seqNum, 0, 0, 0)
                packet.priority = self.priority[(dst, sport, dport)]
                self.link.send(packet, self.addr, currTimeslot)
                # if packet.dstAddr == 'h1' and packet.srcAddr == 'h140':
                #     print(currTimeslot)
                #     breakpoint()
                if packet.dstAddr == '1' and packet.dstPort == 157:
                    print(f"sending packet to {packet.dstAddr} and seq_num = {packet.seqNum}")
                    print(f"numPacketsentInCurrWin = {self.numPktSentInCurrWin[(dst, sport, dport)]} , cwnd = {self.cwnd[(dst, sport, dport)]} ")
                    print(f"time = {currTimeslot}")
                    #breakpoint()
                self.sFlows[(dst, sport, dport)][1] += 1
                self.sFlows[(dst, sport, dport)][3] = currTimeslot  # (re)set timer
                totalPktSent[0] += 1
                self.numPktSentInCurrWin[(dst, sport, dport)] += 1

                # Advance pointer so RR within the same priority progresses
                self.rrPointer = (self.rrPointer + 1) % len(self.rrSched)
                return


    def handleRecvdPacket(self, packet, ackQueues,currTimeslot):
        """Handle the packet received on the link
           and send an ack packet for the received packet
           by enqueuing the ack packet into the right ackQueue"""
        ackPacket = Packet(packet.dstAddr, packet.srcAddr, packet.dstPort, packet.srcPort, 0, packet.seqNum+1, 1, packet.ecnFlag)
        ackQueues[packet.srcAddr].put(ackPacket)
        self.on_packet(packet)
        


    def handleRecvdAcks(self, ackQueue, totalFlowsFinished,currTimeslot):
        """Handle the received acks"""
        while not ackQueue.empty():
            ackPacket = ackQueue.get()
            assert(ackPacket.ackFlag == 1)

            # log recvd ACKs
            self.logPacket(ackPacket)

            dst = ackPacket.srcAddr
            sport = ackPacket.dstPort
            dport = ackPacket.srcPort

            assert(ackPacket.ackNum == self.sFlows[(dst,sport,dport)][2] or ackPacket.ackNum == self.sFlows[(dst,sport,dport)][2]+1)

            if ackPacket.ackNum == self.sFlows[(dst,sport,dport)][2]+1:
                self.sFlows[(dst,sport,dport)][2] += 1
                # if ackPacket.dstAddr == 'h13' and ackPacket.srcPort == 943 and ackPacket.dstPort == 943:
                #     print(currTimeslot)
                #     breakpoint()
                if (dst,sport,dport) in self.rrSched: # the flow exists
                    self.numPktSentInCurrWin[(dst,sport,dport)] -= 1
                    assert(self.numPktSentInCurrWin[(dst,sport,dport)] >= 0)
                    self.numAckRecvdInCurrWin[(dst,sport,dport)] += 1
                    if (ackPacket.ecnFlag == 1):
                        self.numECNAckRecvdInCurrWin[(dst,sport,dport)] += 1
                    if self.numAckRecvdInCurrWin[(dst,sport,dport)] == self.cwnd[(dst,sport,dport)]: # received all the acks for curr window of sent data
                        # Update the cwnd value below according to DCTCP algorithm
                        F = self.numECNAckRecvdInCurrWin[(dst,sport,dport)] / self.numAckRecvdInCurrWin[(dst,sport,dport)]
                        if F == 0:
                            self.cwnd[(dst,sport,dport)] += 1
                        else:
                            self.alpha[(dst,sport,dport)] = 0.25 * self.alpha[(dst,sport,dport)] + 0.75 * F
                            assert(self.alpha[(dst,sport,dport)] >= 0 and self.alpha[(dst,sport,dport)] <= 1)
                            self.cwnd[(dst,sport,dport)] = math.ceil(self.cwnd[(dst,sport,dport)] * (1 - (self.alpha[(dst,sport,dport)]/2)))
                        # reset the values at the end
                        self.numAckRecvdInCurrWin[(dst,sport,dport)] = 0
                        self.numECNAckRecvdInCurrWin[(dst,sport,dport)] = 0
            elif ackPacket.ackNum == self.sFlows[(dst,sport,dport)][2]: # dup ack
                self.sFlows[(dst,sport,dport)][1] = self.sFlows[(dst,sport,dport)][2]
                self.numPktSentInCurrWin[(dst,sport,dport)] = self.numAckRecvdInCurrWin[(dst,sport,dport)]
                assert(self.numPktSentInCurrWin[(dst,sport,dport)] >= 0)
                #print("Dup ack recvd!")

            """delete scheduled flow if acks for all packets from the flow have been received"""
            if self.sFlows[(dst,sport,dport)][0] == self.sFlows[(dst,sport,dport)][2]:
                del self.sFlows[(dst,sport,dport)]
                del self.cwnd[(dst,sport,dport)]
                del self.alpha[(dst,sport,dport)]
                del self.numPktSentInCurrWin[(dst,sport,dport)]
                self.rrSched.remove((dst,sport,dport))
                if self.rrPointer >= len(self.rrSched):
                    self.rrPointer = 0
                if self.priority[(dst,sport,dport)] == 3:
                    totalFlowsFinished[0] += 1
                if self.priority[(dst,sport,dport)] == 1:
                    totalFlowsFinished[1] += 1
                # print(f"flows left = {len(self.rrSched)}:{self.addr}")
                    # message = f"flow completion time for {(dst,sport,dport)} = {currTimeslot} \n" 
                    # with open("/home/dan/LQD/obm-sim/obm-sim/short_flow_completion_time_abm.txt", "a") as f:
                    #     f.write(message)
                    # print(f"flow completion time = {currTimeslot}")
                    

        
