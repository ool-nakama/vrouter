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
from vrouter.vnf_controller.command_generator import Command_generator
from vrouter.vnf_controller.ssh_client import SSH_Client

""" logging configuration """
logger = ft_logger.Logger("vRouter.vm_controller").getLogger()

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


class vm_controller():

    def __init__(self, util_info):
        logger.debug("init vm controller")
        self.command_gen = Command_generator()
        self.credentials = util_info["credentials"]

        self.util = utilvnf(logger)
        self.util.set_credentials(self.credentials["username"],
                                  self.credentials["password"],
                                  self.credentials["auth_url"],
                                  self.credentials["tenant_name"],
                                  self.credentials["region_name"])

    def command_gen_from_template(self, command_file_path, cmd_input_param):
        (command_file_dir, command_file_name) = os.path.split(
                                                    command_file_path)
        template = self.command_gen.load_template(command_file_dir,
                                                  command_file_name)
        return self.command_gen.command_create(template,
                                               cmd_input_param)

    def config_vm(self, vm_info, test_cmd_file_path,
                  cmd_input_param, prompt_file_path):
        ssh = self.connect_ssh_and_config_vm(vm_info,
                                             test_cmd_file_path,
                                             cmd_input_param,
                                             prompt_file_path)
        if ssh is None:
            return False

        ssh.close()

        return True

    def connect_ssh_and_config_vm(self, vm_info, test_cmd_file_path,
                                  cmd_input_param, prompt_file_path):

        key_filename = None
        if "key_path" in vm_info:
            key_filename = vm_info["key_path"]

        ssh = SSH_Client(ip=vm_info["floating_ip"],
                         user=vm_info["user"],
                         password=vm_info["pass"],
                         key_filename=key_filename)

        result = ssh.connect(SSH_CONNECT_TIMEOUT,
                             SSH_CONNECT_RETRY_COUNT)
        if not result:
            logger.debug("try to vm reboot.")
            self.util.reboot_vm(vm_info["vnf_name"])
            time.sleep(REBOOT_WAIT)
            result = ssh.connect(SSH_CONNECT_TIMEOUT,
                                 SSH_CONNECT_RETRY_COUNT)
            if not result:
                return None

        (result, res_data_list) = self.command_create_and_execute(
                                           ssh,
                                           test_cmd_file_path,
                                           cmd_input_param,
                                           prompt_file_path)
        if not result:
            ssh.close()
            return None

        return ssh

    def command_create_and_execute(self, ssh, test_cmd_file_path,
                                   cmd_input_param, prompt_file_path):
        prompt_file = open(prompt_file_path,
                           'r')
        prompt = yaml.safe_load(prompt_file)
        prompt_file.close()
        config_mode_prompt = prompt["config_mode"]

        logger.info("config_mode_prompt : " + config_mode_prompt)

        commands = self.command_gen_from_template(test_cmd_file_path,
                                                  cmd_input_param)
        return self.command_list_execute(ssh,
                                         commands,
                                         config_mode_prompt)

    def command_list_execute(self, ssh, command_list, prompt):
        res_data_list = []
        for command in command_list:
            logger.debug("Command : " + command)
            (res, res_data) = self.command_execute(ssh,
                                                   command,
                                                   prompt)
            logger.debug("Response : " + res_data)
            res_data_list.append(res_data)
            if not res:
                return res, res_data_list

            time.sleep(COMMAND_WAIT)

        return True, res_data_list

    def command_execute(self, ssh, command, prompt):
        res_data = ssh.send(command, prompt)
        if res_data is None:
            logger.info("retry send command : " + command)
            res_data = ssh.send(command,
                                prompt)
            if not ssh.error_check(res_data):
                    return False, res_data

        return True, res_data