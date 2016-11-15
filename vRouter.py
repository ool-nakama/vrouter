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

import argparse
import datetime
import os
import pprint
import time
import yaml


from git import Repo

import glanceclient.client as glclient
import keystoneclient.v2_0.client as ksclient
import novaclient.client as nvclient
from neutronclient.v2_0 import client as ntclient


import functest.utils.functest_utils as functest_utils
import functest.utils.openstack_utils as os_utils

from test_controller.test_exec import Test_exec
from orchestrator import orchestrator
from topology import topology
from utilvnf import utilvnf

pp = pprint.PrettyPrinter(indent=4)


parser = argparse.ArgumentParser()
parser.add_argument("-d",
                    "--debug",
                    help="Debug mode",
                    action="store_true")
parser.add_argument("-r",
                    "--report",
                    help="Create json result file",
                    action="store_true")
parser.add_argument("-n",
                    "--noclean",
                    help="Don't clean the created resources for this test.",
                    action="store_true")

with open(os.environ["CONFIG_FUNCTEST_YAML"]) as f:
    functest_yaml = yaml.safe_load(f)
f.close()

# Cloudify parameters
VNF_DIR = functest_yaml.get("general").get("directories").get(
          "dir_repo_vRouter") + "/"
VNF_DATA_DIR = functest_yaml.get("general").get(
    "directories").get("dir_vRouter_data") + "/"
DB_URL = functest_yaml.get("results").get("test_db_url")

TENANT_NAME = functest_yaml.get("vRouter").get("general").get("tenant_name")
TENANT_DESCRIPTION = functest_yaml.get("vRouter").get(
    "general").get("tenant_description")
IMAGES = functest_yaml.get("vRouter").get("general").get("images")
TEST_DATA = functest_yaml.get("vRouter").get("general").get("test_data")

CFY_MANAGER_BLUEPRINT = functest_yaml.get(
    "vRouter").get("cloudify").get("blueprint")
CFY_MANAGER_REQUIERMENTS = functest_yaml.get(
    "vRouter").get("cloudify").get("requierments")
CFY_INPUTS = functest_yaml.get("vRouter").get("cloudify").get("inputs")


TPLGY_BLUEPRINT = functest_yaml.get("vRouter").get(
    "vnf_topology").get("blueprint")
TPLGY_DEPLOYMENT_NAME = functest_yaml.get("vRouter").get(
    "vnf_topology").get("deployment-name")
TPLGY_INPUTS = functest_yaml.get("vRouter").get(
    "vnf_topology").get("inputs")
TPLGY_REQUIERMENTS = functest_yaml.get("vRouter").get(
    "vnf_topology").get("requierments")

TPLGY_TGT_FLAVOR_ID = functest_yaml.get("vRouter").get(
    "vnf_topology").get("inputs").get("target_vnf_flavor_id")
TPLGY_TGT_IMAGE_ID = functest_yaml.get("vRouter").get(
    "vnf_topology").get("inputs").get("target_vnf_image_id")

TPLGY_REF_FLAVOR_ID = functest_yaml.get("vRouter").get(
    "vnf_topology").get("inputs").get("reference_vnf_flavor_id")
TPLGY_REF_IMAGE_ID = functest_yaml.get("vRouter").get(
    "vnf_topology").get("inputs").get("reference_vnf_image_id")

TPLGY_IMAGE_NAME = functest_yaml.get("vRouter").get(
    "vnf_topology").get("requierments").get("os_image")

TPLGY_DEPLOY_NAME = functest_yaml.get("vRouter").get(
    "vnf_topology").get("blueprint").get("deployment_name")

TPLGY_BP_NAME = functest_yaml.get("vRouter").get("vnf_topology").get(
    "blueprint").get("blueprint_name")

REBOOT_WAIT = functest_yaml.get("vRouter").get(
    "general").get("reboot_wait")


class vRouter:
    def __init__(self, logger):

        """ logging configuration """
        self.logger = logger

        REPO_PATH = os.environ['repos_dir'] + '/functest/'
        if not os.path.exists(REPO_PATH):
            self.logger.error("Repos directory not found '%s'" % REPO_PATH)
            exit(-1)

        self.testcase_start_time = time.time()

        self.results = {
            'init': {
                'duration': 0,
                'result': 'none'
            },
            'making_orchestrator': {
                'duration': 0,
                'result': 'none'
            },
            'making_testTopology': {
                'duration': 0,
                'result': 'none'
            },
            'testing_vRouter': {
                'duration': 0,
                'result': 'none'
            }
        }

        self.ks_cresds = None
        self.nv_cresds = None
        self.nt_cresds = None
        self.glance = None
        self.neutron = None

    def download_and_add_image_on_glance(self, glance, image_name, image_url):
        dest_path = VNF_DATA_DIR + "tmp/"
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
        file_name = image_url.rsplit('/')[-1]

        result = functest_utils.download_url(image_url,
                                             dest_path)
        if not result:
            self.logger.error("Failed to download image %s" % file_name)
            return False

        image = os_utils.create_glance_image(glance,
                                             image_name,
                                             dest_path + file_name)
        if not image:
            self.logger.error("Failed to upload image on glance")
            return False

        return image

    def set_result(self, step_name, duration=0, result=""):
        self.results[step_name] = {
            'duration': duration,
            'result': result
        }

    def set_resultdata(self, start_time, stop_time, status, results):
        result_data = {}
        result_data["start_time"] = start_time
        result_data["stop_time"] = stop_time
        result_data["status"] = status
        result_data["results"] = results

        if status == "PASS":
            self.logger.info(" result_data %s", result_data)

        return result_data

    def step_failure(self, step_name, error_msg):
        stop_time = time.time()
        self.logger.error(error_msg)
        self.set_result(step_name,
                        0,
                        error_msg)
        status = "FAIL"
        # in case of failure starting and stoping time are not correct
        result_data = self.set_resultdata(self.testcase_start_time, stop_time,
                                          status, self.results)
        return result_data

    def test_vRouter(self, cfy):
        credentials = {}
        credentials["username"] = TENANT_NAME
        credentials["password"] = TENANT_NAME
        credentials["tenant_name"] = TENANT_NAME
        credentials["auth_url"] = os.environ['OS_AUTH_URL']
        credentials["region_name"] = os.environ['OS_REGION_NAME']
        util_info = {}
        util_info["credentials"] = credentials
        util_info["cfy"] = cfy
        util_info["vnf_data_dir"] = VNF_DATA_DIR

        util = utilvnf(self.logger)
        util.set_credentials(credentials["username"],
                             credentials["password"],
                             credentials["auth_url"],
                             credentials["tenant_name"],
                             credentials["region_name"])

        self.logger.debug("Downloading the test data.")
        vRouter_data_path = VNF_DATA_DIR + "opnfv-vnf-data/"

        if not os.path.exists(vRouter_data_path):
            Repo.clone_from(TEST_DATA['url'],
                            vRouter_data_path,
                            branch=TEST_DATA['branch'])

        testcfg_yaml_dir = "opnfv-vnf-data/test_config.yaml"
        test_config_file = open(VNF_DATA_DIR + testcfg_yaml_dir,
                                'r')
        test_config_yaml = yaml.safe_load(test_config_file)
        test_config_file.close()

        target_vnf_name = test_config_yaml["target_vnf_name"]
        test_protocol = test_config_yaml["test_protocol_kind"]
        test_list = test_config_yaml[test_protocol]

        cfy_manager_ip = util.get_cfy_manager_address(cfy,
                                                      VNF_DATA_DIR)

        self.logger.debug("cfy manager address : %s" % cfy_manager_ip)

        vnf_info_list = util.get_vnf_info_list(cfy_manager_ip,
                                               TPLGY_DEPLOY_NAME,
                                               target_vnf_name)

        self.logger.debug("request vnf's reboot.")

        util.request_vnf_reboot(vnf_info_list)
        time.sleep(REBOOT_WAIT)

        target_vnf = util.get_target_vnf(vnf_info_list)
        if target_vnf is None:
            return self.step_failure(
                "testing_vRouter",
                "Error : target_vnf is None.")

        reference_vnf_list = util.get_reference_vnf_list(vnf_info_list)
        if len(reference_vnf_list) == 0:
            return self.step_failure(
                "testing_vRouter",
                "Error : reference_vnf_list is empty.")

        test_exec = Test_exec(util_info)

        # start test
        start_time_ts = time.time()
        self.logger.info("vRouter test Start Time:'%s'" % (
            datetime.datetime.fromtimestamp(start_time_ts).strftime(
                '%Y-%m-%d %H:%M:%S')))

        result = test_exec.run(target_vnf,
                               reference_vnf_list,
                               test_protocol,
                               test_list)

        end_time_ts = time.time()
        duration = round(end_time_ts - start_time_ts,
                         1)
        self.logger.info("vRouter test duration :'%s'" % duration)

        if result:
            self.set_result("testing_vRouter",
                            duration,
                            "OK")

            return self.set_resultdata(self.testcase_start_time, end_time_ts,
                                       "PASS", self.results)

        return self.step_failure(
            "testing_vRouter",
            "Error : Faild to test execution.")

    def init(self):

        start_time_ts = time.time()

        if not os.path.exists(VNF_DATA_DIR):
            os.makedirs(VNF_DATA_DIR)

        self.ks_cresds = os_utils.get_credentials("keystone")
        self.nv_cresds = os_utils.get_credentials("nova")
        self.nt_cresds = os_utils.get_credentials("neutron")

        self.logger.info("Prepare OpenStack plateform(create tenant and user)")
        keystone = ksclient.Client(**self.ks_cresds)

        user_id = os_utils.get_user_id(keystone,
                                       self.ks_cresds['username'])
        if user_id == '':
            return self.step_failure("init",
                                     "Error : Failed to get id of " +
                                     self.ks_cresds['username'])

        tenant_id = os_utils.create_tenant(keystone,
                                           TENANT_NAME,
                                           TENANT_DESCRIPTION)
        if tenant_id == '':
            return self.step_failure("init",
                                     "Error : Failed to create " +
                                     TENANT_NAME + " tenant")
        roles_name = [
            "admin",
            "Admin"
        ]
        role_id = ''
        for role_name in roles_name:
            if role_id == '':
                role_id = os_utils.get_role_id(keystone,
                                               role_name)

        if role_id == '':
            self.logger.error("Error : Failed to get id for %s role" %
                              role_name)

        if not os_utils.add_role_user(keystone,
                                      user_id,
                                      role_id,
                                      tenant_id):

            self.logger.error("Error : Failed to add %s on tenant" %
                              self.ks_cresds['username'])

        user_id = os_utils.create_user(keystone,
                                       TENANT_NAME,
                                       TENANT_NAME,
                                       None,
                                       tenant_id)
        if user_id == '':
            self.logger.error("Error : Failed to create %s user" % TENANT_NAME)

        self.logger.info("Update OpenStack creds informations")
        self.ks_cresds.update({
            "username": TENANT_NAME,
            "password": TENANT_NAME,
            "tenant_name": TENANT_NAME,
        })

        self.nt_cresds.update({
            "tenant_name": TENANT_NAME,
        })

        self.nv_cresds.update({
            "project_id": TENANT_NAME,
        })

        self.logger.info("Upload some OS images if it doesn't exist")
        glance_endpoint = keystone.service_catalog.url_for(
                                            service_type='image',
                                            endpoint_type='publicURL')

        self.glance = glclient.Client(1,
                                      glance_endpoint,
                                      token=keystone.auth_token)

        for img in IMAGES.keys():
            image_name = IMAGES[img]['image_name']
            image_url = IMAGES[img]['image_url']

            image_id = os_utils.get_image_id(self.glance,
                                             image_name)

            if image_id == '':
                self.logger.info("""%s image doesn't exist on glance repository. Try
                downloading this image and upload on glance !""" % image_name)
                image_id = self.download_and_add_image_on_glance(self.glance,
                                                                 image_name,
                                                                 image_url)

            if image_id == '':
                return self.step_failure(
                    "init",
                    "Error : Failed to find or upload required OS "
                    "image for this deployment")

        self.logger.info("Update security group quota for this tenant")
        self.neutron = ntclient.Client(**self.nt_cresds)

        result = os_utils.update_sg_quota(self.neutron,
                                          tenant_id,
                                          50,
                                          100)

        if not result:
            return self.step_failure(
                "init",
                "Failed to update security group quota for tenant " +
                TENANT_NAME)

        end_time_ts = time.time()
        duration = round(end_time_ts - start_time_ts,
                         1)

        self.set_result("init",
                        duration,
                        "OK")

        return self.set_resultdata(self.testcase_start_time, "",
                                   "", self.results)

    def deploy_cloudify(self, cfy):

        username = self.ks_cresds['username']
        password = self.ks_cresds['password']
        tenant_name = self.ks_cresds['tenant_name']
        auth_url = self.ks_cresds['auth_url']

        cfy.set_credentials(username,
                            password,
                            tenant_name,
                            auth_url)

        self.logger.info("Collect flavor id for cloudify manager server")

        nova = nvclient.Client("2",
                               **self.nv_cresds)

        flavor_name = "m1.large"
        flavor_id = os_utils.get_flavor_id(nova,
                                           flavor_name)

        for requirement in CFY_MANAGER_REQUIERMENTS:
            if requirement == 'ram_min':
                flavor_id = os_utils.get_flavor_id_by_ram_range(
                                nova,
                                CFY_MANAGER_REQUIERMENTS['ram_min'],
                                320000)

        if flavor_id == '':
            self.logger.error(
                "Failed to find %s flavor. "
                "Try with ram range default requirement !" % flavor_name)
            flavor_id = os_utils.get_flavor_id_by_ram_range(nova,
                                                            4000,
                                                            8196)

        if flavor_id == '':
            return self.step_failure(
                        "making_orchestrator",
                        "Failed to find required flavor for this deployment")

        cfy.set_flavor_id(flavor_id)

        image_name = "centos_7"
        image_id = os_utils.get_image_id(self.glance,
                                         image_name)

        for requirement in CFY_MANAGER_REQUIERMENTS:
            if requirement == 'os_image':
                image_id = os_utils.get_image_id(
                               self.glance,
                               CFY_MANAGER_REQUIERMENTS['os_image'])

        if image_id == '':
            return self.step_failure(
              "making_orchestrator",
              "Error : Failed to find required OS image for cloudify manager")

        cfy.set_image_id(image_id)

        ext_net = os_utils.get_external_net(self.neutron)
        if not ext_net:
            return self.step_failure(
                         "making_orchestrator",
                         "Failed to get external network")

        cfy.set_external_network_name(ext_net)

        ns = functest_utils.get_resolvconf_ns()
        if ns:
            cfy.set_nameservers(ns)

        self.logger.info("Prepare virtualenv for cloudify-cli")
        cmd = "chmod +x " + VNF_DIR + "create_venv.sh"
        functest_utils.execute_command(cmd,
                                       self.logger)
        time.sleep(3)
        cmd = VNF_DIR + "create_venv.sh " + VNF_DATA_DIR
        functest_utils.execute_command(cmd,
                                       self.logger)

        cfy.download_manager_blueprint(
            CFY_MANAGER_BLUEPRINT['url'],
            CFY_MANAGER_BLUEPRINT['branch'])

        # ############### CLOUDIFY DEPLOYMENT ################
        start_time_ts = time.time()
        self.logger.info("Cloudify deployment Start Time:'%s'" % (
            datetime.datetime.fromtimestamp(start_time_ts).strftime(
                '%Y-%m-%d %H:%M:%S')))

        error = cfy.deploy_manager()
        if error:
            return self.step_failure("making_orchestrator",
                                     error)

        end_time_ts = time.time()
        duration = round(end_time_ts - start_time_ts,
                         1)
        self.logger.info("Cloudify deployment duration:'%s'" % duration)

        self.set_result("making_orchestrator",
                        duration,
                        "OK")

        return self.set_resultdata(self.testcase_start_time, "",
                                   "", self.results)

    def init_testToplogy(self, tplgy):
        self.logger.info("Collect flavor id for all topology vm")
        nova = nvclient.Client("2",
                               **self.nv_cresds)

        target_vnf_flavor_id = TPLGY_TGT_FLAVOR_ID
        target_vnf_image_id = TPLGY_TGT_IMAGE_ID
        reference_vnf_flavor_id = TPLGY_REF_FLAVOR_ID
        reference_vnf_image_id = TPLGY_REF_IMAGE_ID

        if target_vnf_flavor_id == '':
            for requirement in TPLGY_REQUIERMENTS:
                if requirement == 'ram_min':
                    target_vnf_flavor_id = os_utils.get_flavor_id_by_ram_range(
                        nova,
                        TPLGY_REQUIERMENTS['ram_min'],
                        8196)

            self.logger.info("target_vnf_flavor_id id search set")

        tplgy.set_reference_vnf_flavor_id(target_vnf_flavor_id)

        if reference_vnf_flavor_id == '':
            for requirement in TPLGY_REQUIERMENTS:
                if requirement == 'ram_min':
                    reference_vnf_flavor_id = \
                        os_utils.get_flavor_id_by_ram_range(
                            nova,
                            TPLGY_REQUIERMENTS['ram_min'],
                            8196)

            self.logger.info("reference_vnf_flavor_id id search set")

        tplgy.set_target_vnf_flavor_id(reference_vnf_flavor_id)

        if reference_vnf_image_id == '' or target_vnf_image_id == '':
            image_name = TPLGY_IMAGE_NAME
            image_id = os_utils.get_image_id(self.glance,
                                             image_name)
            for requirement in TPLGY_REQUIERMENTS:
                if requirement == 'os_image':
                    image_id = os_utils.get_image_id(
                                  self.glance,
                                  TPLGY_REQUIERMENTS['os_image'])

        if image_id == '':
            return self.step_failure(
               "making_testTopology",
               "Error : Failed to find required OS image for cloudify manager")

        if reference_vnf_image_id == '':
            tplgy.set_reference_vnf_image_id(image_id)

        if target_vnf_image_id == '':
            tplgy.set_target_vnf_image_id(image_id)

        tplgy.set_region("RegionOne")

        ext_net = os_utils.get_external_net(self.neutron)
        if not ext_net:
            return self.step_failure(
                   "making_testTopology",
                   "Failed to get external network")

        tplgy.set_external_network_name(ext_net)

        tplgy.set_credentials(username=self.ks_cresds['username'],
                              password=self.ks_cresds['password'],
                              tenant_name=self.ks_cresds['tenant_name'],
                              auth_url=self.ks_cresds['auth_url'])

        return self.set_resultdata(self.testcase_start_time, "",
                                   "", self.results)

    def deploy_testToplogy(self, tplgy):

        start_time_ts = time.time()
        end_time_ts = start_time_ts
        self.logger.info("vRouter VNF deployment Start Time:'%s'" % (
            datetime.datetime.fromtimestamp(start_time_ts).strftime(
                '%Y-%m-%d %H:%M:%S')))

        # deploy
        ret = tplgy.deploy_vnf(TPLGY_BLUEPRINT,
                               TPLGY_BP_NAME,
                               TPLGY_DEPLOY_NAME)
        if ret:
            self.logger.error("Error :deployment testtopology :%s", ret)
            return self.step_failure("making_testTopology",
                                     "Failed to deploy test topology")

        end_time_ts = time.time()
        duration = round(end_time_ts - start_time_ts,
                         1)
        self.logger.info("vRouter VNF deployment duration:'%s'" % duration)
        self.set_result("making_testTopology",
                        duration,
                        "OK")

        return self.set_resultdata(self.testcase_start_time, "",
                                   "", self.results)

    def clean_enviroment(self, cfy):

        # ########### CLOUDIFY UNDEPLOYMENT #############

        cfy.undeploy_manager()

        # ############## TNENANT CLEANUP ################

        self.logger.info("Removing %s tenant .." %
                         CFY_INPUTS['keystone_tenant_name'])

        keystone = ksclient.Client(**self.ks_cresds)
        tenant_id = os_utils.get_tenant_id(keystone,
                                           CFY_INPUTS['keystone_tenant_name'])
        if tenant_id == '':
            self.logger.error(
                         "Error : Failed to get id of %s tenant" %
                         CFY_INPUTS['keystone_tenant_name'])
        else:
            resulut = os_utils.delete_tenant(keystone,
                                             tenant_id)
            if not resulut:
                self.logger.error(
                       "Error : Failed to remove %s tenant" %
                       CFY_INPUTS['keystone_tenant_name'])

        self.logger.info("Removing %s user .." %
                         CFY_INPUTS['keystone_username'])

        user_id = os_utils.get_user_id(keystone,
                                       CFY_INPUTS['keystone_username'])

        if user_id == '':
            self.logger.error("Error : Failed to get id of %s user" %
                              CFY_INPUTS['keystone_username'])
        else:
            result = os_utils.delete_user(keystone,
                                          user_id)
            if not result:
                self.logger.error("Error : Failed to remove %s user" %
                                  CFY_INPUTS['keystone_username'])

        return self.set_resultdata(self.testcase_start_time, "",
                                   "", self.results)

    def main(self):

        # ############### GENERAL INITIALISATION ################

        result_data = self.init()

        if result_data["status"] == "FAIL":
            return result_data

        # ############### CLOUDIFY DEPLOYMENT ################

        cfy = orchestrator(VNF_DATA_DIR,
                           CFY_INPUTS,
                           self.logger)

        result_data = self.deploy_cloudify(cfy)
        if result_data["status"] == "FAIL":
            return result_data

        # ############### VNF TOPOLOGY INITIALISATION  ################

        tplgy = topology(TPLGY_INPUTS,
                         cfy,
                         self.logger)

        result_data = self.init_testToplogy(tplgy)
        if result_data["status"] == "FAIL":
            return result_data

        # ############### VNF TOPOLOGY DEPLOYMENT ################

        result_data = self.deploy_testToplogy(tplgy)
        if result_data["status"] == "FAIL":
            return result_data

        # ############### VNF TEST ################

        result_data = self.test_vRouter(cfy)

        # ############### CLEAN ENVIROMENT ################

        self.clean_enviroment(cfy)

        return result_data
