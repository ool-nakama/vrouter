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
import time
import yaml

import functest.utils.functest_logger as ft_logger
from vrouter.utilvnf import utilvnf
from vrouter.vnf_controller.vnf_controller import VNF_controller

""" logging configuration """
logger = ft_logger.Logger("vRouter.test_exec").getLogger()


class Function_test_exec():

    def __init__(self, util_info):
        logger.debug("init test exec")
        self.util = utilvnf(logger)
        self.credentials = util_info["credentials"]
        self.vnf_ctrl = VNF_controller(util_info)

        test_cmd_map_file = open(self.util.VNF_DATA_DIR +
                                 self.util.OPNFV_VNF_DATA_DIR +
                                 self.util.COMMAND_TEMPLATE_DIR +
                                 self.util.TEST_CMD_MAP_YAML_FILE,
                                 'r')
        self.test_cmd_map_yaml = yaml.safe_load(test_cmd_map_file)
        test_cmd_map_file.close()

        self.util.set_credentials(self.credentials["username"],
                                  self.credentials["password"],
                                  self.credentials["auth_url"],
                                  self.credentials["tenant_name"],
                                  self.credentials["region_name"])

        with open(self.util.TEST_ENV_CONFIG_YAML) as f:
            test_env_config_yaml = yaml.safe_load(f)
        f.close()

        self.protocol_stable_wait = test_env_config_yaml.get("general").get(
            "protocol_stable_wait")


    def config_target_vnf(self, target_vnf, reference_vnf, test_kind):
        logger.debug("Configuration to target vnf")
        test_info = self.test_cmd_map_yaml[target_vnf["os_type"]]
        test_cmd_file_path = test_info[test_kind]["pre_command_target"]
        target_parameter_file_path = test_info[test_kind]["parameter_target"]
        prompt_file_path = test_info["prompt"]

        return self.vnf_ctrl.config_vnf(target_vnf,
                                        reference_vnf,
                                        test_cmd_file_path,
                                        target_parameter_file_path,
                                        prompt_file_path)

    def config_reference_vnf(self, target_vnf, reference_vnf, test_kind):
        logger.debug("Configuration to reference vnf")
        test_info = self.test_cmd_map_yaml[reference_vnf["os_type"]]
        test_cmd_file_path = test_info[test_kind]["pre_command_reference"]
        reference_parameter_file_path = test_info[test_kind][
                                            "parameter_reference"]
        prompt_file_path = test_info["prompt"]

        return self.vnf_ctrl.config_vnf(reference_vnf,
                                        target_vnf,
                                        test_cmd_file_path,
                                        reference_parameter_file_path,
                                        prompt_file_path)

    def result_check(self, target_vnf, reference_vnf, test_kind, test_list):
        test_info = self.test_cmd_map_yaml[target_vnf["os_type"]]
        target_parameter_file_path = test_info[test_kind]["parameter_target"]
        prompt_file_path = test_info["prompt"]
        check_rule_file_path_list = []

        for test in test_list:
            check_rule_file_path_list.append(test_info[test_kind][test])

        return self.vnf_ctrl.result_check(target_vnf,
                                          reference_vnf,
                                          check_rule_file_path_list,
                                          target_parameter_file_path,
                                          prompt_file_path)

    def run(self, target_vnf, reference_vnf_list, test_info, test_list):
        test_result_data = {}
        test_kind = test_info["protocol"]
        for reference_vnf in reference_vnf_list:
            logger.debug("Start config command " + target_vnf["vnf_name"] +
                         " and " + reference_vnf["vnf_name"])

            result = self.config_target_vnf(target_vnf,
                                            reference_vnf,
                                            test_kind)
            if not result:
                return False, test_result_data

            result = self.config_reference_vnf(target_vnf,
                                               reference_vnf,
                                               test_kind)
            if not result:
                return False, test_result_data

            logger.debug("Finish config command.")

            logger.debug("Waiting for protocol stable.")
            time.sleep(self.protocol_stable_wait)

            logger.debug("Start check method")

            (result, res_dict_data_list) = self.result_check(target_vnf,
                                                             reference_vnf,
                                                             test_kind,
                                                             test_list)

            test_result_data = {"test_kind" : test_info["test_kind"],
                                "protocol" : test_info["protocol"],
                                "result" : res_dict_data_list}

            if not result:
                logger.debug("Error check method.")
                return False, test_result_data

            logger.debug("Finish check method.")

        return True, test_result_data
