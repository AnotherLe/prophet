# -*- coding=utf8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2019 OnePro Cloud (Shanghai) Ltd.
#
# Authors: Ray <ray.sun@oneprocloud.com>
#
# Copyright (c) 2019 This file is confidential and proprietary.
# All Rights Resrved, OnePro Cloud (Shanghai) Ltd (http://www.oneprocloud.com).

"""Batch job for running mix host type collection"""

import logging
import os
import shutil
import time

import pandas as pd

from prophet.controller.linux_host import LinuxHostController
from prophet.controller.windows_host import WindowsHostCollector
from prophet.controller.vmware import VMwareHostController

REPORT_PATH_NAME = "host_collection_info"
REPORT_PREFIX = "host_collection_info"

LINUX_REPORT_PATH_NAME = "linux_hosts"
WINDOWS_REPORT_PATH_NAME = "windows_hosts"
VMWARE_REPORT_PATH_NAME = "vmware_hosts"

# os types
LINUX = "LINUX"
WINDOWS = "WINDOWS"
VMWARE = "VMWARE"

# VMware
DEFAULT_VMWARE_PORT = 443

class BatchJob(object):

    def __init__(self, host_file, output_path, force_check):
        if not os.path.exists(host_file):
            raise OSError("Input path %s is not exists." % host_file)

        if not os.path.exists(output_path):
            raise OSError("Output path %s is not exists." % output_path)

        self.host_file = host_file
        self.output_path = output_path
        self.force_check = force_check

        self._prepare()

    @property
    def report_full_path(self):
        return os.path.join(self.output_path, self.report_filename)

    @property
    def report_filename(self):
        return self.report_basename + ".zip"

    @property
    def report_basename(self):
        timestamp = time.strftime(
            "%Y%m%d%H%M%S",
            time.localtime(time.time())
        )
        return REPORT_PREFIX + "_" + timestamp

    @property
    def linux_report_path(self):
        return os.path.join(self.coll_path, LINUX_REPORT_PATH_NAME)

    @property
    def windows_report_path(self):
        return os.path.join(self.coll_path, WINDOWS_REPORT_PATH_NAME)

    @property
    def vmware_report_path(self):
        return os.path.join(self.coll_path, VMWARE_REPORT_PATH_NAME)

    @property
    def coll_path(self):
        return os.path.join(self.output_path, REPORT_PATH_NAME)

    def collect(self):
        """Collect host information

        Host with check status and do status is not success will be
        collected. If force check is given, do status is ignored.
        """
        logging.info("Collecting hosts information "
                     "from %s, generate report "
                     "in %s..." % (self.host_file, self.report_filename))
        hosts = self._parse_host_file()
        for index, row in hosts.iterrows():
            logging.debug("Current row is\n%s" % row)
            try:
                hostname     = self._to_empty_or_int(row["hostname"])
                host_ip      = self._to_empty_or_int(row["ip"])
                username     = self._to_empty_or_int(row["username"])
                password     = self._to_empty_or_int(row["password"])
                ssh_port     = self._to_empty_or_int(row["ssh_port"])
                key_path     = self._to_empty_or_int(row["key_path"])
                host_mac     = self._to_empty_or_int(row["mac"])
                vendor       = self._to_empty_or_int(row["vendor"])
                check_status = self._to_empty_or_int(row["check_status"])
                os_type      = self._to_empty_or_int(row["os"])
                version      = self._to_empty_or_int(row["version"])
                tcp_ports    = self._to_empty_or_int(row["tcp_ports"])
                do_status    = self._to_empty_or_int(row["do_status"])

                if not self._is_need_check(check_status, do_status):
                    logging.info("Skip to check host %s." % host_ip)
                    logging.debug("Host %s status: "
                                 "check status is %s, do status "
                                 "is %s, force check is %s" % (
                                     host_ip, check_status,
                                     do_status, self.force_check))
                    continue

                if not self._can_check(
                        host_ip, username, password, key_path):
                    continue

                logging.info("Beginning to collect %s "
                             "information..." % host_ip)
                if os_type.upper() == LINUX:
                    host_info = LinuxHostController(
                        host_ip, ssh_port, username,
                        password, key_path, self.linux_report_path)
                    host_info.get_linux_host_info()
                elif os_type.upper() == WINDOWS:
                    host_info = WindowsHostCollector(
                        host_ip, username, password,
                        self.windows_report_path)
                    host_info.get_windows_host_info()
                elif os_type.upper() == VMWARE:
                    if not ssh_port:
                        ssh_port = 443
                    host_info = VMwareHostController(
                        host_ip, ssh_port, username, password,
                        self.vmware_report_path)
                    host_info.get_all_info()
                else:
                    raise OSError("Unsupport os type %s "
                                  "if host %s" % (os_type, host_ip))
                hosts.loc[index, "do_status"] = "success"
                hosts.to_csv(self.host_file, index=False)
                logging.info("Sucessfully collect %s "
                             "information." % host_ip)
            except Exception as e:
                logging.exception(e)
                logging.error("Check %s failed, please check it host info."
                              % host_ip)
                hosts.loc[index, "do_status"] = "failed"
                hosts.to_csv(self.host_file, index=False)
        logging.info("Sucessfully collect hosts info.")

    def package(self):
        logging.info("Packing of collection info path %s to %s..."
                     % (self.coll_path, self.report_full_path))
        os.chdir(self.output_path)
        shutil.make_archive(self.report_basename, "zip", self.coll_path)

    def _prepare(self):
        for report_path in [self.linux_report_path,
                            self.windows_report_path,
                            self.vmware_report_path]:
            if not os.path.exists(report_path):
                logging.info("Creating directory %s..." % report_path)
                os.makedirs(report_path)

    def _clean(self):
        """Remove senstive files"""
        pass

    def _parse_host_file(self):
        data = pd.read_csv(self.host_file)
        return data

    def _to_empty_or_int(self, value):
        """Convert to none or int

        Convert float nan to None
        Convert float type to integer
        Return string as it is
        """
        if pd.isnull(value):
            return ""
        elif isinstance(value, float):
            return int(value)
        else:
            return value

    def _is_need_check(self, check_status, do_status):
        if check_status.upper() == "CHECK":
            if do_status.upper() == "SUCCESS" and not self.force_check:
                return False
            else:
                return True
        else:
            return False

    def _can_check(self, host_ip, username, password, key_path):
        """Return True if authentication fields is enough"""
        if not username:
            logging.warn("Skip to collect %s information due to "
                         "username is not given." % (host_ip, username))
            return False

        if not password and not key_path:
            logging.warn("Skip to collect %s information due to "
                         "password or key is not given." % host_ip)
            return False

        return True