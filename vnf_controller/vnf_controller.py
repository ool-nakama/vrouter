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
from vrouter.vnf_controller.checker import Checker
from vrouter.vnf_controller.ssh_client import SSH_Client
from vrouter.vnf_controller.vm_controller import vm_controller


""" logging configuration """
logger = ft_logger.Logger("vRouter.vnf_controller").getLogger()

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


class VNF_controller():

    def __init__(self, util_info):
        logger.debug("init vnf controller")
        self.vm_controller = vm_controller(util_info)

    def config_vnf(self, source_vnf, destination_vnf, test_cmd_file_path,
                   parameter_file_path, prompt_file_path):
        parameter_file = open(parameter_file_path,
                              'r')
        cmd_input_param = yaml.safe_load(parameter_file)
        parameter_file.close()

        cmd_input_param["macaddress"] = source_vnf["data_plane_network_mac"]
        cmd_input_param["source_ip"] = source_vnf["data_plane_network_ip"]
        cmd_input_param["destination_ip"] = destination_vnf[
                                                "data_plane_network_ip"]

        return self.vm_controller.config_vm(source_vnf,
                                            test_cmd_file_path,
                                            cmd_input_param,
                                            prompt_file_path)

    def result_check(self, target_vnf, reference_vnf,
                     check_rule_file_path_list, parameter_file_path,
                     prompt_file_path):
        parameter_file = open(parameter_file_path,
                              'r')
        cmd_input_param = yaml.safe_load(parameter_file)
        parameter_file.close()

        cmd_input_param["source_ip"] = target_vnf["data_plane_network_ip"]
        cmd_input_param["destination_ip"] = reference_vnf[
                                                "data_plane_network_ip"]

        prompt_file = open(prompt_file_path,
                           'r')
        prompt = yaml.safe_load(prompt_file)
        prompt_file.close()
        terminal_mode_prompt = prompt["terminal_mode"]

        ssh = SSH_Client(target_vnf["floating_ip"],
                         target_vnf["user"],
                         target_vnf["pass"])

        result = ssh.connect(SSH_CONNECT_TIMEOUT,
                             SSH_CONNECT_RETRY_COUNT)
        if not result:
            return False

        checker = Checker()

        status = True
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
                                        terminal_mode_prompt)
            res_data_list.append(res_data)
            if not res:
                status = False
                break
            checker.regexp_information(res_data,
                                       check_rules)
            time.sleep(COMMAND_WAIT)

        ssh.close()

        self.output_chcke_result_detail_data(res_data_list)

        return status

    def output_chcke_result_detail_data(self, res_data_list):
        for res_data in res_data_list:
            logger.debug(res_data)
