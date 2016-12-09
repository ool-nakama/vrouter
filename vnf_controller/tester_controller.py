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
import time
import yaml

import functest.utils.functest_logger as ft_logger
from vrouter.utilvnf import utilvnf
from vrouter.vnf_controller.checker import Checker
from vrouter.vnf_controller.command_generator import Command_generator
from vrouter.vnf_controller.ssh_client import SSH_Client
from vrouter.vnf_controller.vm_controller import vm_controller


""" logging configuration """
logger = ft_logger.Logger("tester_ctlr").getLogger()

REPO_PATH = os.environ['repos_dir'] + '/functest/'
if not os.path.exists(REPO_PATH):
    logger.error("Functest repository directory not found '%s'" % REPO_PATH)
    exit(-1)

with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
    functest_yaml = yaml.safe_load(f)
f.close()

REBOOT_WAIT = functest_yaml.get("vRouter").get("general").get("reboot_wait")
COMMAND_WAIT = functest_yaml.get("vRouter").get("general").get("command_wait")
SSH_CONNECT_TIMEOUT = functest_yaml.get("vRouter").get("general").get(
    "ssh_connect_timeout")
SSH_CONNECT_RETRY_COUNT = functest_yaml.get("vRouter").get("general").get(
    "ssh_connect_retry_count")


class tester_controller():

    def __init__(self, util_info):
        logger.debug("init tester controller")
        self.vm_controller = vm_controller(util_info)

        self.credentials = util_info["credentials"]

        self.util = utilvnf(logger)
        self.util.set_credentials(self.credentials["username"],
                                  self.credentials["password"],
                                  self.credentials["auth_url"],
                                  self.credentials["tenant_name"],
                                  self.credentials["region_name"])

    def config_send_tester(self, source_tester, destination_tester, target_vnf,
                           pre_cmd_file_path, test_cmd_file_path, parameter_file_path,
                           prompt_file_path, input_parameter):
        parameter_file = open(parameter_file_path,
                              'r')
        cmd_input_param = yaml.safe_load(parameter_file)
        parameter_file.close()

        cmd_input_param.update(input_parameter)

        cmd_input_param["macaddress"] = source_tester["send_side_traffic_plane_network_mac"]
        cmd_input_param["dst_ip"] = destination_tester["receive_side_traffic_plane_network_ip"]
        cmd_input_param["gw_ip"] = target_vnf["send_side_traffic_plane_network_ip"]

        source_tester["pass"] = None

        ssh = self.vm_controller.connect_ssh_and_config_vm(
                                             source_tester,
                                             pre_cmd_file_path,
                                             cmd_input_param,
                                             prompt_file_path)

        # execute peformance test command
        count = cmd_input_param["count"]
        for i in range(count):
            (res, res_data_list) = self.vm_controller.command_create_and_execute(
                                            ssh,
                                            test_cmd_file_path,
                                            cmd_input_param,
                                            prompt_file_path)
            if not res:
                break

        ssh.close()
        return res

    def config_receive_tester(self, source_tester, destination_tester, target_vnf,
                   test_cmd_file_path, parameter_file_path, prompt_file_path, input_parameter):
        parameter_file = open(parameter_file_path,
                              'r')
        cmd_input_param = yaml.safe_load(parameter_file)
        parameter_file.close()

        cmd_input_param.update(input_parameter)

        cmd_input_param["macaddress"] = source_tester["receive_side_traffic_plane_network_mac"]
        cmd_input_param["gw_ip"] = target_vnf["receive_side_traffic_plane_network_ip"]

        source_tester["pass"] = None

        return self.vm_controller.connect_ssh_and_config_vm(
                                            source_tester,
                                            test_cmd_file_path,
                                            cmd_input_param,
                                            prompt_file_path)

    def result_check(self, ssh, source_tester, destination_tester,
                     check_rule_file_path_list, parameter_file_path,
                     prompt_file_path, input_parameter):
        parameter_file = open(parameter_file_path,
                              'r')
        cmd_input_param = yaml.safe_load(parameter_file)
        parameter_file.close()

        prompt_file = open(prompt_file_path,
                           'r')
        prompt = yaml.safe_load(prompt_file)
        prompt_file.close()
        config_mode_prompt = prompt["config_mode"]

        checker = Checker()

        res = True
        res_data_list = []
        for check_rule_file_path in check_rule_file_path_list:
            (check_rule_dir, check_rule_file) = os.path.split(
                                                    check_rule_file_path)
            check_rules = checker.load_check_rule(check_rule_dir,
                                                  check_rule_file,
                                                  cmd_input_param)
            (res, res_data) = self.vm_controller.command_execute(
                                        ssh,
                                        check_rules["command"],
                                        config_mode_prompt)
            res_split_data = res_data.split('\n')
            res_data_list.extend(res_split_data)
            if not res:
                break
            time.sleep(COMMAND_WAIT)

        input_parameter["client_ip"] = destination_tester["send_side_traffic_plane_network_ip"]
        input_parameter["server_ip"] = source_tester["receive_side_traffic_plane_network_ip"]

        return self.output_result_data(res_data_list, input_parameter)

    def output_result_data(self, res_data_list, input_parameter):
        data_list = []
        for res_data in res_data_list:
            pattern = r"Mbits/sec"
            if res_data.find(pattern) >= 0:
                data = self.util.result_parser(res_data)
                data_list.append(data)

        if len(data_list) == 0:
            return False

        avg_data = self.util.calc_avg(data_list)
        if avg_data is None:
            return False

        self.util.output_result_data(logger, input_parameter, avg_data)

        return True

