#!/usr/bin/python
# coding: utf8
#######################################################################
#
# Copyright (c) 2017 Okinawa Open Laboratory
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
########################################################################
import os
import yaml

import functest.utils.functest_logger as ft_logger
from vrouter.utilvnf import utilvnf
from vrouter.vnf_controller.tester_controller import tester_controller

""" logging configuration """
logger = ft_logger.Logger("vRouter.performance_test_exec").getLogger()

OPNFV_VNF_DATA_DIR = "opnfv-vnf-data/"
COMMAND_TEMPLATE_DIR = "command_template/"
TEST_ENV_CONFIG_YAML_FILE = "test_env_config.yaml"
TEST_CMD_MAP_YAML_FILE = "test_cmd_map.yaml"

with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
    functest_yaml = yaml.safe_load(f)
f.close()

VNF_DATA_DIR = functest_yaml.get("general").get(
    "dir").get("dir_vRouter_data") + "/"

TEST_ENV_CONFIG_YAML = VNF_DATA_DIR + \
                       OPNFV_VNF_DATA_DIR + \
                       TEST_ENV_CONFIG_YAML_FILE


class Performance_test_exec():

    def __init__(self, util_info):
        logger.debug("init performance test exec")
        self.credentials = util_info["credentials"]
        self.tester_ctrl = tester_controller(util_info)

        test_cmd_map_file = open(VNF_DATA_DIR +
                                 OPNFV_VNF_DATA_DIR +
                                 COMMAND_TEMPLATE_DIR +
                                 TEST_CMD_MAP_YAML_FILE,
                                 'r')
        self.test_cmd_map_yaml = yaml.safe_load(test_cmd_map_file)
        test_cmd_map_file.close()

        self.util = utilvnf(logger)
        self.util.set_credentials(self.credentials["username"],
                                  self.credentials["password"],
                                  self.credentials["auth_url"],
                                  self.credentials["tenant_name"],
                                  self.credentials["region_name"])

    def config_send_tester_vm(self, target_vnf, send_tester_vm,
                              receive_tester_vm, input_parameter):
        logger.debug("Configuration to send tester vm")
        test_info = self.test_cmd_map_yaml[send_tester_vm["os_type"]]
        pre_test_cmd_file_path = \
            test_info["performance"]["performance_pre_command"]
        test_cmd_file_path = test_info["performance"]["performance_send"]
        prompt_file_path = test_info["prompt"]

        return self.tester_ctrl.config_send_tester(
                                         send_tester_vm,
                                         receive_tester_vm,
                                         target_vnf,
                                         pre_test_cmd_file_path,
                                         test_cmd_file_path,
                                         prompt_file_path,
                                         input_parameter)

    def config_receive_tester_vm(self, target_vnf, send_tester_vm,
                                 receive_tester_vm, input_parameter):
        logger.debug("Configuration to send tester vm")
        test_info = self.test_cmd_map_yaml[receive_tester_vm["os_type"]]
        test_cmd_file_path = test_info["performance"]["performance_receive"]
        prompt_file_path = test_info["prompt"]

        return self.tester_ctrl.config_receive_tester(
                                         receive_tester_vm,
                                         send_tester_vm,
                                         target_vnf,
                                         test_cmd_file_path,
                                         prompt_file_path,
                                         input_parameter)

    def result_check(self, ssh, send_tester_vm, receive_tester_vm,
                     test_kind, test_list, input_parameter):
        test_info = self.test_cmd_map_yaml[send_tester_vm["os_type"]]
        prompt_file_path = test_info["prompt"]
        check_rule_file_path_list = []

        for test in test_list:
            check_rule_file_path_list.append(test_info[test_kind][test])

        return self.tester_ctrl.result_check(ssh,
                                             send_tester_vm,
                                             receive_tester_vm,
                                             check_rule_file_path_list,
                                             prompt_file_path,
                                             input_parameter)

    def run(self, target_vnf, send_tester_vm,
            receive_tester_vm, input_parameter):
        logger.debug("Start config command for performance test")

        receive_tester_ssh = self.config_receive_tester_vm(
                                      target_vnf, send_tester_vm,
                                      receive_tester_vm, input_parameter)
        if receive_tester_ssh is None:
            return False

        result = self.config_send_tester_vm(target_vnf, send_tester_vm,
                                            receive_tester_vm, input_parameter)
        if not result:
            return False

        logger.debug("Finish config command.")

        logger.debug("Start check method")

        test_list = ["receive_check_iperf_stop", "receive_check_iperf_result"]

        result = self.result_check(receive_tester_ssh,
                                   receive_tester_vm,
                                   send_tester_vm,
                                   "performance",
                                   test_list,
                                   input_parameter)

        receive_tester_ssh.close()

        logger.debug("Finish check method.")

        return True
