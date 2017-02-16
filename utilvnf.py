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
import json
import os
import re
import requests
import yaml
from git import Repo

from novaclient import client as novaclient

VROUTER_CONFIG_YAML = "vRouter_config.yaml"

with open(VROUTER_CONFIG_YAML) as f:
    vrouter_config_yaml = yaml.safe_load(f)
f.close()

TEST_DATA = vrouter_config_yaml.get("vRouter").get(
    "general").get("test_data")

RESULT_SPRIT_INDEX = {
    "transfer": 8,
    "bandwidth": 6,
    "jitter": 4,
    "los_total": 2,
    "pkt_loss": 1
}

BIT_PER_BYTE = 8

NOVA_CLIENT_API_VERSION = '2'
NOVA_CILENT_NETWORK_INFO_INDEX = 0
CFY_INFO_OUTPUT_FILE = "output.txt"

CIDR_NETWORK_SEGMENT_INFO_INDEX = 0
PACKET_LOST_INFO_INDEX = 0
PACKET_TOTAL_INFO_INDEX = 1

NUMBER_OF_DIGITS_FOR_AVG_TRANSFER = 0
NUMBER_OF_DIGITS_FOR_AVG_BANDWIDTH = 0
NUMBER_OF_DIGITS_FOR_AVG_JITTER = 3
NUMBER_OF_DIGITS_FOR_AVG_PKT_LOSS = 1

class utilvnf:

    def __init__(self, logger=None):
        self.logger = logger
        self.username = ""
        self.password = ""
        self.auth_url = ""
        self.tenant_name = ""
        self.region_name = ""

        with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
            functest_yaml = yaml.safe_load(f)
        f.close()

        self.VNF_DIR = functest_yaml.get("general").get("dir").get(
            "repo_vrouter") + "/"

        self.VNF_DATA_DIR_NAME = "data/"
        self.VNF_DATA_DIR = self.VNF_DIR + self.VNF_DATA_DIR_NAME
        self.OPNFV_VNF_DATA_DIR = "opnfv-vnf-data/"
        self.COMMAND_TEMPLATE_DIR = "command_template/"
        self.TEST_SCENATIO_YAML = "test_scenario.yaml"
        self.TEST_ENV_CONFIG_YAML_FILE = "test_env_config.yaml"
        self.TEST_CMD_MAP_YAML_FILE = "test_cmd_map.yaml"
        self.TEST_ENV_CONFIG_YAML = self.VNF_DATA_DIR + \
                                    self.OPNFV_VNF_DATA_DIR + \
                                    self.TEST_ENV_CONFIG_YAML_FILE

        if not os.path.exists(self.VNF_DATA_DIR):
            os.makedirs(self.VNF_DATA_DIR) 

        self.logger.debug("Downloading the test data.")
        vRouter_data_path = self.VNF_DATA_DIR + self.OPNFV_VNF_DATA_DIR

        if not os.path.exists(vRouter_data_path):
            Repo.clone_from(TEST_DATA['url'],
                            vRouter_data_path,
                            branch=TEST_DATA['branch'])

        with open(self.TEST_ENV_CONFIG_YAML) as f:
            test_env_config_yaml = yaml.safe_load(f)
        f.close()

        self.TEST_SCENATIO_YAML_FILE = self.VNF_DATA_DIR + \
                                       self.OPNFV_VNF_DATA_DIR + \
                                       self.TEST_SCENATIO_YAML

        self.IMAGE = test_env_config_yaml.get("general").get("images").get("vyos")
        self.TESTER_IMAGE = test_env_config_yaml.get("general").get("images").get("tester_vm_os")

        self.TEST_RESULT_JSON_FILE = "test_result.json"
        if os.path.isfile(self.TEST_RESULT_JSON_FILE):
            os.remove(self.TEST_RESULT_JSON_FILE)
            self.logger.debug("removed %s" % self.TEST_RESULT_JSON_FILE)

    def set_credentials(self, username, password, auth_url,
                        tenant_name, region_name):
        self.username = username
        self.password = password
        self.auth_url = auth_url
        self.tenant_name = tenant_name
        self.region_name = region_name

    def get_nova_credentials(self):
        d = {}
        d['version'] = NOVA_CLIENT_API_VERSION
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

        address = \
            s.addresses[network_name][NOVA_CILENT_NETWORK_INFO_INDEX]["addr"]

        return address

    def get_mac_address(self, server_name, network_name):
        creds = self.get_nova_credentials()
        nova_client = novaclient.Client(**creds)
        servers_list = nova_client.servers.list()

        for s in servers_list:
            if s.name == server_name:
                break

        mac_address = \
            s.addresses[network_name][NOVA_CILENT_NETWORK_INFO_INDEX]["OS-EXT-IPS-MAC:mac_addr"]

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

        f = open(CFY_INFO_OUTPUT_FILE,
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
        url = "http://%s/deployments/%s/outputs" % (cfy_manager_ip, deployment_name)

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
            vnf["os_type"] = self.IMAGE["os_type"]
            vnf["user"] = self.IMAGE["user"]
            vnf["pass"] = self.IMAGE["pass"]

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
                vnf["user"] = self.IMAGE["user"]
                vnf["pass"] = self.IMAGE["pass"]
            else:
                tester_vm = self.get_vnf_info(
                                      performance_test_config["vnf_list"],
                                      "tester_vm")
                vnf["target_vnf_flag"] = False
                vnf["os_type"] = tester_vm["os_type"]
                vnf["user"] = self.TESTER_IMAGE["user"]
                vnf["key_path"] = self.TESTER_IMAGE["key_path"]

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
                subnet_info = network["subnet_info"]
                cidr = subnet_info["cidr"] \
                           .split("/")[CIDR_NETWORK_SEGMENT_INFO_INDEX]
                vnf[network_name + "_ip"] = ip
                vnf[network_name + "_mac"] = mac
                vnf[network_name + "_cidr"] = cidr
                self.logger.debug(network_name + "_ip of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_ip"])
                self.logger.debug(network_name + "_mac of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_mac"])
                self.logger.debug(network_name + "_cidr of " + vnf["vnf_name"] +
                                  " : " + vnf[network_name + "_cidr"])

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
                lost = re.split(" +", data)[index].split("/")[PACKET_LOST_INFO_INDEX]
                res_data.update({"pkt_lost": lost})
                total = re.split(" +", data)[index].split("/")[PACKET_TOTAL_INFO_INDEX]
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
        avg_transfer = str(int(round(avg_data["avg_transfer"],
                                     NUMBER_OF_DIGITS_FOR_AVG_TRANSFER)))
        avg_bandwidth = str(int(round(avg_data["avg_bandwidth"],
                                      NUMBER_OF_DIGITS_FOR_AVG_BANDWIDTH)))
        avg_jitter = str(round(avg_data["avg_jitter"],
                               NUMBER_OF_DIGITS_FOR_AVG_JITTER))
        pkt_lost = str(int(avg_data["pkt_lost"]))
        pkt_total = str(int(avg_data["pkt_total"]))
        avg_pkt_loss = str(round(avg_data["avg_pkt_loss"],
                                 NUMBER_OF_DIGITS_FOR_AVG_PKT_LOSS))

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

    def test_scenario_validation_check(self, test_scenario_yaml):
        res = {
            "status" : False,
            "message" : "Test scenario format error : "
        }

        if not isinstance(test_scenario_yaml, dict):
            res["message"] += "test_scenario.yaml is not yaml format."
            return res

        if "test_scenario_list" not in test_scenario_yaml:
            res["message"] += "test_scenario_list key not found."
            return res

        test_scenario_list = test_scenario_yaml["test_scenario_list"]

        if not isinstance(test_scenario_list, list):
            res["message"] += "test_scenario_list is not list type."
            return res

        for test_scenario in test_scenario_list:

            if "test_type" not in test_scenario:
                res["message"] += "test_type key not found."
                return res

            if "vnf_list" not in test_scenario:
                res["message"] += "vnf_list key not found."
                return res

            vnf_list = test_scenario["vnf_list"]

            if not isinstance(vnf_list, list):
                res["message"] += "vnf_list is not list type."
                return res

            for vnf_info in vnf_list:

                if "vnf_name" not in vnf_info:
                    res["message"] += "vnf_name key not found."
                    return res

            if test_scenario["test_type"] == "function_test":

                if "function_test_list" not in test_scenario:
                    res["message"] += "function_test_list key not found."
                    return res

                function_test_list = test_scenario["function_test_list"]

                if not isinstance(function_test_list, list):
                    res["message"] += "function test is not list type."
                    return res

                for function_test in function_test_list:

                    if "target_vnf_name" not in function_test:
                        res["message"] += "target_vnf_name key not found."
                        return res

                    if "test_list" not in function_test:
                        res["message"] += "test_list key not found."
                        return res

                    test_list = function_test["test_list"]

                    if not isinstance(test_list, list):
                        res["message"] += "test list is not list type."
                        return res

                    for test_info in test_list:

                        if "test_kind" not in test_info:
                            res["message"] += "test_kind key not found."
                            return res

                        if "protocol" not in test_info:
                            res["message"] += "protocol key not found."
                            return res

                        test_protocol = test_info["protocol"]

                        if test_protocol not in test_info:
                            res["message"] += "%s key not found." % test_protocol
                            return res

                        protocol_test_list = test_info[test_protocol]

                        if not isinstance(protocol_test_list, list):
                            res["message"] += "%s test list is not list type." % test_protocol
                            return res

            elif test_scenario["test_type"] == "performance_test":

                if "performance_test_list" not in test_scenario:
                    res["message"] += "performance_test_list key not found."
                    return res

                performance_test_list = test_scenario["performance_test_list"]

                if not isinstance(performance_test_list, list):
                    res["message"] += "performance_test_list is not list type."
                    return res

                for performance_test in performance_test_list:

                    if "input_parameter" not in performance_test:
                        res["message"] += "input_parameter key not found."
                        return res

            else:
                res["message"] += "%s is the unknown test type." % test_scenario["test_type"]
                return res

        res["status"] = True
        res["message"] = "success"

        return res

    def write_result_data(self, result_data):
        test_result = []
        if not os.path.isfile(self.TEST_RESULT_JSON_FILE):
            f = open(self.TEST_RESULT_JSON_FILE, "w")
            f.close()
        else:
            f = open(self.TEST_RESULT_JSON_FILE, "r")
            test_result = json.load(f)
            f.close()

        test_result.append(result_data)

        f = open(self.TEST_RESULT_JSON_FILE, "w")
        json.dump(test_result ,f)
        f.close()

    def output_test_result_json(self):
        if os.path.isfile(self.TEST_RESULT_JSON_FILE):
            f = open(self.TEST_RESULT_JSON_FILE, "r")
            test_result = json.load(f)
            f.close()
            output_json_data = json.dumps(test_result, sort_keys = True, indent = 4) 
            self.logger.debug("test_result %s" % output_json_data)
        else:
            self.logger.debug("Not found %s" % self.TEST_RESULT_JSON_FILE)
