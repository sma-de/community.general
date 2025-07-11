#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2024, Stanislav Shamilov <shamilovstas@protonmail.com>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: android_sdk
short_description: Manages Android SDK packages
description:
  - Manages Android SDK packages.
  - Allows installation from different channels (stable, beta, dev, canary).
  - Allows installation of packages to a non-default SDK root directory.
author: Stanislav Shamilov (@shamilovstas)
extends_documentation_fragment:
  - community.general.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
version_added: 10.2.0
options:
  accept_licenses:
    description:
      - If this is set to V(true), the module attempts to accept license prompts generated by C(sdkmanager) during package
        installation. Otherwise, every license prompt is rejected.
    type: bool
    default: false
  name:
    description:
      - A name of an Android SDK package (for instance, V(build-tools;34.0.0)).
    aliases: ['package', 'pkg']
    type: list
    elements: str
  state:
    description:
      - Indicates the desired package(s) state.
      - V(present) ensures that package(s) is/are present.
      - V(absent) ensures that package(s) is/are absent.
      - V(latest) ensures that package(s) is/are installed and updated to the latest version(s).
    choices: ['present', 'absent', 'latest']
    default: present
    type: str
  sdk_root:
    description:
      - Provides path for an alternative directory to install Android SDK packages to. By default, all packages are installed
        to the directory where C(sdkmanager) is installed.
    type: path
  channel:
    description:
      - Indicates what channel must C(sdkmanager) use for installation of packages.
    choices: ['stable', 'beta', 'dev', 'canary']
    default: stable
    type: str
requirements:
  - C(java) >= 17
  - C(sdkmanager) Command line tool for installing Android SDK packages.
notes:
  - For some of the packages installed by C(sdkmanager) is it necessary to accept licenses. Usually it is done through command
    line prompt in a form of a Y/N question when a licensed package is requested to be installed. If there are several packages
    requested for installation and at least two of them belong to different licenses, the C(sdkmanager) tool prompts for these
    licenses in a loop. In order to install packages, the module must be able to answer these license prompts. Currently,
    it is only possible to answer one license prompt at a time, meaning that instead of installing multiple packages as a
    single invocation of the C(sdkmanager --install) command, it is done by executing the command independently for each package.
    This makes sure that at most only one license prompt needs to be answered. At the time of writing this module, a C(sdkmanager)'s
    package may belong to at most one license type that needs to be accepted. However, if this changes in the future, the
    module may hang as there might be more prompts generated by the C(sdkmanager) tool which the module is unable to answer.
    If this becomes the case, file an issue and in the meantime, consider accepting all the licenses in advance, as it is
    described in the C(sdkmanager) L(documentation,https://developer.android.com/tools/sdkmanager#accept-licenses), for instance,
    using the M(ansible.builtin.command) module.
seealso:
  - name: sdkmanager tool documentation
    description: Detailed information of how to install and use sdkmanager command line tool.
    link: https://developer.android.com/tools/sdkmanager
"""

EXAMPLES = r"""
- name: Install build-tools;34.0.0
  community.general.android_sdk:
    name: build-tools;34.0.0
    accept_licenses: true
    state: present

- name: Install build-tools;34.0.0 and platform-tools
  community.general.android_sdk:
    name:
      - build-tools;34.0.0
      - platform-tools
    accept_licenses: true
    state: present

- name: Delete build-tools;34.0.0
  community.general.android_sdk:
    name: build-tools;34.0.0
    state: absent

- name: Install platform-tools or update if installed
  community.general.android_sdk:
    name: platform-tools
    accept_licenses: true
    state: latest

- name: Install build-tools;34.0.0 to a different SDK root
  community.general.android_sdk:
    name: build-tools;34.0.0
    accept_licenses: true
    state: present
    sdk_root: "/path/to/new/root"

- name: Install a package from another channel
  community.general.android_sdk:
    name: some-package-present-in-canary-channel
    accept_licenses: true
    state: present
    channel: canary
"""

RETURN = r"""
installed:
  description: A list of packages that have been installed.
  returned: when packages have changed
  type: list
  sample: ["build-tools;34.0.0", "platform-tools"]

removed:
  description: A list of packages that have been removed.
  returned: when packages have changed
  type: list
  sample: ["build-tools;34.0.0", "platform-tools"]
"""

from ansible_collections.community.general.plugins.module_utils.mh.module_helper import StateModuleHelper
from ansible_collections.community.general.plugins.module_utils.android_sdkmanager import Package, AndroidSdkManager


class AndroidSdk(StateModuleHelper):
    module = dict(
        argument_spec=dict(
            state=dict(type='str', default='present', choices=['present', 'absent', 'latest']),
            package=dict(type='list', elements='str', aliases=['pkg', 'name']),
            sdk_root=dict(type='path'),
            channel=dict(type='str', default='stable', choices=['stable', 'beta', 'dev', 'canary']),
            accept_licenses=dict(type='bool', default=False)
        ),
        supports_check_mode=True
    )

    def __init_module__(self):
        self.sdkmanager = AndroidSdkManager(self.module)
        self.vars.set('installed', [], change=True)
        self.vars.set('removed', [], change=True)

    def _parse_packages(self):
        arg_pkgs = set(self.vars.package)
        if len(arg_pkgs) < len(self.vars.package):
            self.do_raise("Packages may not repeat")
        return set([Package(p) for p in arg_pkgs])

    def state_present(self):
        packages = self._parse_packages()
        installed = self.sdkmanager.get_installed_packages()
        pending_installation = packages.difference(installed)

        self.vars.installed = AndroidSdk._map_packages_to_names(pending_installation)
        if not self.check_mode:
            rc, stdout, stderr = self.sdkmanager.apply_packages_changes(pending_installation, self.vars.accept_licenses)
            if rc != 0:
                self.do_raise("Could not install packages: %s" % stderr)

    def state_absent(self):
        packages = self._parse_packages()
        installed = self.sdkmanager.get_installed_packages()
        to_be_deleted = packages.intersection(installed)
        self.vars.removed = AndroidSdk._map_packages_to_names(to_be_deleted)
        if not self.check_mode:
            rc, stdout, stderr = self.sdkmanager.apply_packages_changes(to_be_deleted)
            if rc != 0:
                self.do_raise("Could not uninstall packages: %s" % stderr)

    def state_latest(self):
        packages = self._parse_packages()
        installed = self.sdkmanager.get_installed_packages()
        updatable = self.sdkmanager.get_updatable_packages()
        not_installed = packages.difference(installed)
        to_be_installed = not_installed.union(updatable)
        self.vars.installed = AndroidSdk._map_packages_to_names(to_be_installed)

        if not self.check_mode:
            rc, stdout, stderr = self.sdkmanager.apply_packages_changes(to_be_installed, self.vars.accept_licenses)
            if rc != 0:
                self.do_raise("Could not install packages: %s" % stderr)

    @staticmethod
    def _map_packages_to_names(packages):
        return [x.name for x in packages]


def main():
    AndroidSdk.execute()


if __name__ == '__main__':
    main()
