#!/usr/bin/python
# coding: utf8
#######################################################################
#
# Copyright (c) 2016 Okinawa Open Laboratory
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
########################################################################
import os
import re
import requests
import yaml

from novaclient import client as novaclient

with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
    functest_yaml = yaml.safe_load(f)
f.close()

VNF_DATA_DIR = functest_yaml.get("general").get(
    "directories").get("dir_vRouter_data") + "/"

TEST_ENV_CONFIG_YAML = VNF_DATA_DIR + "opnfv-vnf-data/test_env_config.yaml"
with open(TEST_ENV_CONFIG_YAML) as f:
    test_env_config_yaml = yaml.safe_load(f)
f.close()

IMAGE = test_env_config_yaml.get("general").get("images").get("vyos")
TESTER_IMAGE = test_env_config_yaml.get("general").get("images").get("tester_vm_os")

RESULT_SPRIT_INDEX = {
    "transfer": 8,
    "bandwidth": 6,
    "jitter": 4,
    "los_total": 2,
    "pkt_loss": 1
}

BIT_PER_BYTE = 8


class utilvnf:

    def __init__(self, logger=None):
        self.logger = logger
        self.username = ""
        self.password = ""
        self.auth_url = ""
        self.tenant_name = ""
        self.region_name = ""

    def set_credentials(self, username, password, auth_url,
                        tenant_name, region_name):
        self.username = username
        self.password = password
        self.auth_url = auth_url
        self.tenant_name = tenant_name
        self.region_name = region_name

    def get_nova_credentials(self):
        d = {}
        d['version'] = '2'
        d['username'] = self.username
        d['api_key'] = self.password
        d['auth_url'] = self.auth_url
        d['project_id'] = self.tenant_name
        d['region_name'] = self.region_name
        return d

    def get_address(self, server_name, network_name):
        creds = self.get_nova_credentials()
        nova_client = novaclient.Client(**creds)
        servers_list = nova_client.servers.list()

        for s in servers_list:
            if s.name == server_name:
                break

        address = s.addresses[network_name][0]["addr"]

        return address

    def get_mac_address(self, server_name, network_name):
        creds = self.get_nova_credentials()
        nova_client = novaclient.Client(**creds)
        servers_list = nova_client.servers.list()

        for s in servers_list:
            if s.name == server_name:
                break

        mac_address = s.addresses[network_name][0]["OS-EXT-IPS-MAC:mac_addr"]

        return mac_address

    def reboot_vm(self, server_name):
        creds = self.get_nova_credentials()
        nova_client = novaclient.Client(**creds)
        servers_list = nova_client.servers.list()

        for s in servers_list:
            if s.name == server_name:
                break

        s.reboot()

        return

    def delete_vm(self, server_name):
        creds = self.get_nova_credentials()
        nova_client = novaclient.Client(**creds)
        servers_list = nova_client.servers.list()

        for s in servers_list:
            if s.name == server_name:
                nova_client.servers.delete(s)
                break

        return

    def get_cfy_manager_address(self, cfy, testcase_dir):
        script = "set -e; "
        script += ("source " + testcase_dir +
                   "venv_cloudify/bin/activate; ")
        script += "cd " + testcase_dir + "; "
        script += "cfy status; "
        cmd = "/bin/bash -c '" + script + "'"
        error = cfy.exec_cmd(cmd)
        if error is not False:
            return None

        f = open("output.txt",
                 'r')
        output_data = f.read()
        f.close()

        manager_address = None
        pattern = r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"
        match = re.search(pattern,
                          output_data)
        if match:
            manager_address = match.group()

        return manager_address

    def get_blueprint_outputs(self, cfy_manager_ip, deployment_name):
        url = "http://" + cfy_manager_ip + "/deployments/" + \
              deployment_name + "/outputs"

        response = requests.get(url)

        resp_data = response.json()
        data = resp_data["outputs"]
        return data

    def get_blueprint_outputs_vnfs(self, cfy_manager_ip, deployment_name):
        outputs = self.get_blueprint_outputs(cfy_manager_ip,
                                             deployment_name)
        vnfs = outputs["vnfs"]
        vnf_list = []
        for vnf_name in vnfs:
            vnf_list.append(vnfs[vnf_name])
        return vnf_list

    def get_blueprint_outputs_networks(self, cfy_manager_ip, deployment_name):
        outputs = self.get_blueprint_outputs(cfy_manager_ip,
                                             deployment_name)
        networks = outputs["networks"]
        network_list = []
        for network_name in networks:
            network_list.append(networks[network_name])
        return network_list

    def get_vnf_info_list(self, cfy_manager_ip, topology_deploy_name,
                          target_vnf_name):
        network_list = self.get_blueprint_outputs_networks(
                                                        cfy_manager_ip,
                                                        topology_deploy_name)
        vnf_info_list = self.get_blueprint_outputs_vnfs(cfy_manager_ip,
                                                        topology_deploy_name)
        for vnf in vnf_info_list:
            vnf_name = vnf["vnf_name"]
            vnf["os_type"] = IMAGE["os_type"]
            vnf["user"] = IMAGE["user"]
            vnf["pass"] = IMAGE["pass"]

            if vnf_name == target_vnf_name:
                vnf["target_vnf_flag"] = True
            else:
                vnf["target_vnf_flag"] = False

            self.logger.debug("vnf name : " + vnf_name)
            self.logger.debug(vnf_name + " floating ip address : " +
                              vnf["floating_ip"])

            for network in network_list:
                network_name = network["network_name"]
                ip = self.get_address(vnf["vnf_name"],
                                      network["network_name"])
                vnf[network_name + "_ip"] = ip
                mac = self.get_mac_address(vnf["vnf_name"],
                                           network["network_name"])
                vnf[network_name + "_mac"] = mac

                self.logger.debug(network_name + "_ip of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_ip"])
                self.logger.debug(network_name + "_mac of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_mac"])

        return vnf_info_list

    def get_vnf_info_list_for_performance_test(self, cfy_manager_ip,
                                               topology_deploy_name,
                                               performance_test_config):
        network_list = self.get_blueprint_outputs_networks(
                                               cfy_manager_ip,
                                               topology_deploy_name)
        vnf_info_list = self.get_blueprint_outputs_vnfs(
                                               cfy_manager_ip,
                                               topology_deploy_name)
        for vnf in vnf_info_list:
            vnf_name = vnf["vnf_name"]
            if vnf_name == "target_vnf":
                target_vnf = self.get_vnf_info(
                                      performance_test_config["vnf_list"],
                                      "target_vnf")
                vnf["target_vnf_flag"] = True
                vnf["os_type"] = target_vnf["os_type"]
                vnf["user"] = IMAGE["user"]
                vnf["pass"] = IMAGE["pass"]
            else:
                tester_vm = self.get_vnf_info(
                                      performance_test_config["vnf_list"],
                                      "tester_vm")
                vnf["target_vnf_flag"] = False
                vnf["os_type"] = tester_vm["os_type"]
                vnf["user"] = TESTER_IMAGE["user"]
                vnf["key_path"] = TESTER_IMAGE["key_path"]

            self.logger.debug("vnf name : " + vnf_name)
            self.logger.debug(vnf_name + " floating ip address : " +
                              vnf["floating_ip"])

            for network in network_list:
                if vnf_name == "send_tester_vm":
                    if network["network_name"] == \
                       "receive_data_plane_network":
                        continue
                elif vnf_name == "receive_tester_vm":
                    if network["network_name"] == \
                       "send_data_plane_network":
                        continue

                ip = self.get_address(vnf["vnf_name"],
                                      network["network_name"])
                mac = self.get_mac_address(vnf["vnf_name"],
                                           network["network_name"])
                network_name = network["network_name"]
                vnf[network_name + "_ip"] = ip
                vnf[network_name + "_mac"] = mac
                self.logger.debug(network_name + "_ip of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_ip"])
                self.logger.debug(network_name + "_mac of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_mac"])

        return vnf_info_list

    def get_target_vnf(self, vnf_info_list):
        for vnf in vnf_info_list:
            if vnf["target_vnf_flag"]:
                return vnf

        return None

    def get_reference_vnf_list(self, vnf_info_list):
        reference_vnf_list = []
        for vnf in vnf_info_list:
            if not vnf["target_vnf_flag"]:
                reference_vnf_list.append(vnf)

        return reference_vnf_list

    def get_send_tester_vm(self, vnf_info_list):
        return self.get_vnf_info(vnf_info_list, "send_tester_vm")

    def get_receive_tester_vm(self, vnf_info_list):
        return self.get_vnf_info(vnf_info_list, "receive_tester_vm")

    def request_vnf_reboot(self, vnf_info_list):
        for vnf in vnf_info_list:
            self.logger.debug("reboot the " + vnf["vnf_name"])
            self.reboot_vm(vnf["vnf_name"])

    def request_vm_delete(self, vnf_info_list):
        for vnf in vnf_info_list:
            self.logger.debug("delete the " + vnf["vnf_name"])
            self.delete_vm(vnf["vnf_name"])

    def get_vnf_info(self, vnf_info_list, vnf_name):
        for vnf in vnf_info_list:
            if vnf["vnf_name"] == vnf_name:
                return vnf

        return None

    def result_parser(self, data):
        length = len(re.split(" +", data))
        res_data = {}
        for key in RESULT_SPRIT_INDEX.keys():
            index = length - int(RESULT_SPRIT_INDEX[key])
            res_data.update({key: re.split(" +", data)[index]})

            if key == "los_total":
                lost = re.split(" +", data)[index].split("/")[0]
                res_data.update({"pkt_lost": lost})
                total = re.split(" +", data)[index].split("/")[1]
                res_data.update({"pkt_total": total})
            elif key == "pkt_loss":
                pkt_loss = re.split(" +", data)[index]
                pkt_loss = pkt_loss.lstrip("(")
                pkt_loss = pkt_loss.rstrip("%)\r\n")
                res_data.update({key: float(pkt_loss)})

        return res_data

    def calc_avg(self, result_data_list):
        count = 0
        res_data = {}
        transfer = 0
        bandwidth = 0
        jitter = 0
        pkt_lost = 0
        pkt_total = 0
        pkt_loss = 0

        for data in result_data_list:
            transfer = transfer + float(data["transfer"])
            bandwidth = bandwidth + float(data["bandwidth"])
            jitter = jitter + float(data["jitter"])
            pkt_lost = pkt_lost + float(data["pkt_lost"])
            pkt_total = pkt_total + float(data["pkt_total"])
            pkt_loss = pkt_loss + float(data["pkt_loss"])
            count = count + 1

        if count == 0:
            return None

        avg_transfer = float(transfer) / float(count)
        res_data.update({"avg_transfer": avg_transfer})

        avg_bandwidth = float(bandwidth) / float(count)
        res_data.update({"avg_bandwidth": avg_bandwidth})

        avg_jitter = float(jitter) / float(count)
        res_data.update({"avg_jitter": avg_jitter})

        res_data.update({"pkt_lost": pkt_lost})

        res_data.update({"pkt_total": pkt_total})

        avg_pkt_loss = float(pkt_loss) / float(count)
        res_data.update({"avg_pkt_loss": avg_pkt_loss})

        detect_cnt = count
        res_data.update({"detect_cnt": detect_cnt})

        return res_data

    def output_result_data(self, logger, input_param, avg_data):
        client_ip = input_param["client_ip"]
        server_ip = input_param["server_ip"]
        packet_size = str(input_param["packet_size"])
        bandwidth = str(input_param["bandwidth"])
        port = str(input_param["udp_port"])
        duration = str(input_param["duration"])
        count = str(input_param["count"])

        detect_cnt = str(avg_data["detect_cnt"])
        avg_transfer = str(int(round(avg_data["avg_transfer"], 0)))
        avg_bandwidth = str(int(round(avg_data["avg_bandwidth"], 0)))
        avg_jitter = str(round(avg_data["avg_jitter"], 3))
        pkt_lost = str(int(avg_data["pkt_lost"]))
        pkt_total = str(int(avg_data["pkt_total"]))
        avg_pkt_loss = str(round(avg_data["avg_pkt_loss"], 1))

        logger.info("====================================" +
                    "====================================")
        logger.info(" Performance test result")
        logger.info("  Input Parameter:")
        logger.info("    client_ip=" + client_ip + ", server_ip=" + server_ip)
        logger.info("    udp, packet_size=" + packet_size +
                    "byte, bandwidth=" + bandwidth +
                    "M, port=" + port +
                    ", duration=" + duration +
                    ", count=" + count)
        logger.info("")
        logger.info("  Average:")
        logger.info("    Transfer     Bandwidth        Jitter      Loss rate")
        logger.info("    " + avg_transfer + " MBytes" + "   " +
                    avg_bandwidth + "Mbits/sec     " +
                    avg_jitter + " ms    " +
                    avg_pkt_loss + "%")
        logger.info("")
        logger.info("  Total:")
        logger.info("    number of tests=" + detect_cnt)
        logger.info("")
        logger.info("    Lost/Total Datagrams")
        logger.info("    " + pkt_lost + "/" + pkt_total)
        logger.info("====================================" +
                    "====================================")

        return
