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

import logging
import os
import paramiko
import time
import yaml

import functest.utils.functest_logger as ft_logger

""" logging configuration """
logger = ft_logger.Logger("vRouter.ssh_client").getLogger()
logger.setLevel(logging.INFO)

OPNFV_VNF_DATA_DIR = "opnfv-vnf-data/"
TEST_ENV_CONFIG_YAML_FILE = "test_env_config.yaml"

with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
    functest_yaml = yaml.safe_load(f)
f.close()

VNF_DATA_DIR = functest_yaml.get("general").get(
    "dir").get("dir_vRouter_data") + "/"

TEST_ENV_CONFIG_YAML = VNF_DATA_DIR + \
                       OPNFV_VNF_DATA_DIR + \
                       TEST_ENV_CONFIG_YAML_FILE
RECEIVE_ROOP_WAIT = 1

DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_CONNECT_RETRY_COUNT = 10
DEFAULT_SEND_TIMEOUT = 10


class SSH_Client():

    def __init__(self, ip, user, password=None, key_filename=None):
        self.ip = ip
        self.user = user
        self.password = password
        self.key_filename = key_filename
        self.connected = False

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        with open(TEST_ENV_CONFIG_YAML) as f:
            test_env_config_yaml = yaml.safe_load(f)
        f.close()

        self.ssh_revieve_buff = test_env_config_yaml.get("general").get(
            "ssh_receive_buffer")


    def connect(self, time_out=DEFAULT_CONNECT_TIMEOUT,
                retrycount=DEFAULT_CONNECT_RETRY_COUNT):
        while retrycount > 0:
            try:
                logger.info("SSH connect to %s." % self.ip)
                self.ssh.connect(self.ip,
                                 username=self.user,
                                 password=self.password,
                                 key_filename=self.key_filename,
                                 timeout=time_out,
                                 look_for_keys=False,
                                 allow_agent=False)

                logger.info("SSH connection established to %s." % self.ip)

                self.shell = self.ssh.invoke_shell()

                while not self.shell.recv_ready():
                    time.sleep(RECEIVE_ROOP_WAIT)

                self.shell.recv(self.ssh_revieve_buff)
                break
            except:
                logger.info("SSH timeout for %s..." % self.ip)
                time.sleep(time_out)
                retrycount -= 1

        if retrycount == 0:
            logger.error("Cannot establish connection to IP '%s'. Aborting"
                         % self.ip)
            self.connected = False
            return self.connected

        self.connected = True
        return self.connected

    def send(self, cmd, prompt, timeout=DEFAULT_SEND_TIMEOUT):
        if self.connected is True:
            self.shell.settimeout(timeout)
            logger.debug("Commandset : '%s'", cmd)

            try:
                self.shell.send(cmd + '\n')
            except:
                logger.error("ssh send timeout : Command : '%s'", cmd)
                return None

            res_buff = ''
            while not res_buff.endswith(prompt):
                time.sleep(RECEIVE_ROOP_WAIT)
                try:
                    res = self.shell.recv(self.ssh_revieve_buff)
                except:
                    logger.error("ssh receive timeout : Command : '%s'", cmd)
                    break

                res_buff += res

            logger.debug("Response : '%s'", res_buff)
            return res_buff
        else:
            logger.error("Cannot connected to IP '%s'." % self.ip)
            return None

    def close(self):
        if self.connected is True:
            self.ssh.close()

    def error_check(self, response, err_strs=["error",
                                              "warn",
                                              "unknown command",
                                              "already exist"]):
        for err in err_strs:
            if err in response:
                return False

        return True

