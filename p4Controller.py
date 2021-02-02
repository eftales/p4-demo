#!/usr/bin/env python2
#!encoding=utf-8
import argparse
import grpc
import os
import sys
from time import sleep

import socket

import utils.p4runtime_lib.bmv2
from utils.p4runtime_lib.switch import ShutdownAllSwitchConnections
import utils.p4runtime_lib.helper


# 这个函数的特性
'''
1. 写新的规则的时候会把所有静态的规则覆盖掉
2. 不需要转换字节许
3. 部分 mac 地址无法正确转换 eg 08:00:00:00:04:44 -> \x08\x00\x00\x00\x04D
'''

def writeRules(p4info_helper, ingress_sw, dst_eth_addr, port):

    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.dst_mac_exact",
        match_fields={
            "hdr.ethernet.dstAddr": dst_eth_addr
        },
        action_name="MyIngress.mac_forward",
        action_params={
            "port": port
        })
    ingress_sw.WriteTableEntry(table_entry)
    print "Installed ingress tunnel rule on %s" % ingress_sw.name



def readTableRules(p4info_helper, sw):
    print '\n----- Reading tables rules for %s -----' % sw.name
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # TODO For extra credit, you can use the p4info_helper to translate
            #      the IDs in the entry to names
            table_name = p4info_helper.get_tables_name(entry.table_id)
            print '%s: ' % table_name,
            for m in entry.match:
                print p4info_helper.get_match_field_name(table_name, m.field_id),
                print '%r' % (p4info_helper.get_match_field_value(m),),
            action = entry.action.action
            action_name = p4info_helper.get_actions_name(action.action_id)
            print '->', action_name,
            for p in action.params:
                print p4info_helper.get_action_param_name(action_name, p.param_id),
                print '%r' % p.value,
            print


def printGrpcError(e):
    print "gRPC Error:", e.details(),
    status_code = e.code()
    print "(%s)" % status_code.name,
    traceback = sys.exc_info()[2]
    print "[%s:%d]" % (traceback.tb_frame.f_code.co_filename, traceback.tb_lineno)

def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = utils.p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        # Create a switch connection object for s1 and s2;
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        s2 = utils.p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        s2.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print "Installed P4 Program using SetForwardingPipelineConfig on s2"

        # Write the rules that tunnel traffic from h1 to h2
        writeRules(p4info_helper, ingress_sw=s2, dst_eth_addr="00:00:00:00:00:04", port=2)
        writeRules(p4info_helper, ingress_sw=s2, dst_eth_addr="00:00:00:00:00:03", port=1)
        writeRules(p4info_helper, ingress_sw=s2, dst_eth_addr="00:00:00:00:00:02", port=4)
        writeRules(p4info_helper, ingress_sw=s2, dst_eth_addr="00:00:00:00:00:01", port=3)

        # TODO Uncomment the following two lines to read table entries from s1 and s2
        readTableRules(p4info_helper, s2)


    except KeyboardInterrupt:
        print " Shutting down."
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/main.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print "\np4info file not found: %s\nHave you run 'make'?" % args.p4info
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print "\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json
        parser.exit(1)
    main(args.p4info, args.bmv2_json)
