#!/usr/bin/env python
#
# Copyright (C) 2018 Linus Jahn <lnj@kaidan.im>
# Copyright (C) 2019-2021 Hiroshi Miura <miurahr@linux.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import xml.etree.ElementTree as ElementTree
from logging import getLogger
import packaging.version
from packaging.version import Version
import posixpath

from typing import Optional, Tuple
from aqt.exceptions import ArchiveListError, NoPackageFound
from aqt.helper import Settings, getUrl, satifiesVersion


class TargetConfig:
    def __init__(self, version, target, arch, os_name):
        self.version = str(version)
        self.target = target
        self.arch = arch
        self.os_name = os_name

    def __str__(self):
        print(f'TargetConfig(version={self.version}, target={self.target}, '
              f'arch={self.arch}, os_name={self.os_name}')

    def __repr__(self):
        print(f'({self.version}, {self.target}, {self.arch}, {self.os_name})')


class QtPackage:
    """
    Hold package information.
    """

    def __init__(self, name: str , archive_url: str, archive: str,
                 package_desc: str, hashurl: str,
                 version: Optional[Version] = None):
        self.name = name
        self.url = archive_url
        self.archive = archive
        self.desc = package_desc
        self.hashurl = hashurl
        self.version = version

    def __repr__(self):
        v_info = f', version={self.version}' if self.version else ''
        return (
            f'QtPackage(name={self.name}, archive={self.archive}{v_info})'
        )

    def __str__(self):
        v_info = f', version={self.version}' if self.version else ''
        return (f'QtPackage(name={self.name}, url={self.url}, '
                f'archive={self.archive}, desc={self.desc}'
                f'hashurl={self.hashurl}{v_info})')


class ListInfo:
    """
    Hold list information
    """

    def __init__(self, name, display_name, desc, virtual):
        self.name = name
        self.display_name = display_name
        self.desc = desc
        self.virtual = virtual


class PackagesList:
    """
    Hold packages list information.
    """

    def __init__(self, version_str, os_name, target, base, timeout=(5, 5)):
        self.version_str = version_str
        self.version = packaging.version.parse(version_str)
        self.os_name = os_name
        self.target = target
        self.archives = []
        self.base = posixpath.join(self.base, "online", "qtsdkrepository")
        self.timeout = timeout
        self.logger = getLogger("aqt")
        self._get_archives()

    def _get_archives(self):
        # Get packages index
        if self.version.major == 6 and self.target == "android":
            arch_ext = ["_armv7/", "_x86/", "_x86_64/", "_arm64_v8a/"]
        elif ((self.target == 'desktop') and
              (self.version >= Version('5.13.0')) and
              (self.version < Version('6.0.0'))):
            arch_ext = ["/", "_wasm/"]
        else:
            arch_ext = ["/"]
        for ext in arch_ext:
            archive_path = "{0}{1}{2}/qt{3}_{3}{4}{5}{6}".format(
                self.os_name,
                "_x86/" if self.os_name == "windows" else "_x64/",
                self.target,
                self.version.major,
                self.version.minor,
                self.version.micro,
                ext,
            )
            update_xml_url = posixpath.join(self.base, archive_path, "Updates.xml")
            xml_text = getUrl(update_xml_url, self.timeout, self.logger)
            self.update_xml = ElementTree.fromstring(xml_text)
            for packageupdate in self.update_xml.iter("PackageUpdate"):
                name = packageupdate.find("Name").text
                if packageupdate.find("DownloadableArchives").text is not None:
                    package_desc = packageupdate.findtext("Description")
                    display_name = packageupdate.findtext("DisplayName")
                    virtual_str = packageupdate.findtext("Virtual")
                    if virtual_str == "true":
                        virtual = True
                    else:
                        virtual = False
                    self.archives.append(
                        ListInfo(name, display_name, package_desc, virtual)
                    )
        if len(self.archives) == 0:
            self.logger.error("Error while parsing package information!")
            exit(1)

    def get_list(self):
        return self.archives


class QtArchives:
    """Download and hold Qt archive packages list.
    It access to download.qt.io site and get Update.xml file.
    It parse XML file and store metadata into list of QtPackage object.
    """

    def __init__(
        self,
        os_name,
        target,
        version_str,
        arch,
        base,
        subarchives=None,
        modules=None,
        all_extra=False,
        timeout=(5, 5),
    ):
        self.version_str = version_str
        self.version = packaging.version.parse(version_str) if version_str is not None else None
        self.target = target
        self.arch = arch
        self.os_name = os_name
        self.all_extra = all_extra
        self.arch_list = [item.get("arch") for item in Settings.qt_combinations]
        all_archives = subarchives is None
        self.base = base + "/online/qtsdkrepository/"
        self.logger = getLogger("aqt.archives")
        self.archives = []
        self.mod_list = []
        if all_extra:
            self.all_extra = True
        else:
            for m in modules if modules is not None else []:
                self.mod_list.append(
                    "qt.qt{0}.{0}{1}{2}.{3}.{4}".format(
                        self.version.major,
                        self.version.minor,
                        self.version.micro,
                        m,
                        arch,
                    )
                )
                self.mod_list.append(
                    "qt.{0}{1}{2}.{3}.{4}".format(
                        self.version.major,
                        self.version.minor,
                        self.version.micro,
                        m,
                        arch,
                    )
                )
        self.timeout = timeout
        self._get_archives()
        if not all_archives:
            self.archives = list(filter(lambda a: a.name in subarchives, self.archives))

    def _get_archives(self):
        # Get packages index
        if self.arch == "wasm_32":
            arch_ext = "_wasm"
        elif self.arch.startswith("android_") and self.version.major == 6:
            arch_ext = "{}".format(self.arch[7:])
        else:
            arch_ext = ""
        archive_path = "{0}{1}{2}/qt{3}_{3}{4}{5}{6}/".format(
            self.os_name,
            "_x86/" if self.os_name == "windows" else "_x64/",
            self.target,
            self.version.major,
            self.version.minor,
            self.version.micro,
            arch_ext,
        )
        update_xml_url = "{0}{1}Updates.xml".format(self.base, archive_path)
        archive_url = "{0}{1}".format(self.base, archive_path)
        target_packages = []
        target_packages.append(
            "qt.qt{0}.{0}{1}{2}.{3}".format(
                self.version.major,
                self.version.minor,
                self.version.micro,
                self.arch,
            )
        )
        target_packages.append(
            "qt.{0}{1}{2}.{3}".format(
                self.version.major, self.version.minor, self.version.micro, self.arch
            )
        )
        target_packages.extend(self.mod_list)
        self.logger.debug('QtArchives::_get_archives')
        self.logger.debug(f'{update_xml_url=}')
        self.logger.debug(f'{target_packages=}')

        self._download_update_xml(update_xml_url)
        self._parse_update_xml(archive_url, target_packages)

    def _download_update_xml(self, update_xml_url):
        """Hook for unit test."""
        self.update_xml_text = getUrl(update_xml_url, self.timeout, self.logger)

    def _parse_update_xml(self, archive_url, target_packages):
        try:
            self.update_xml = ElementTree.fromstring(self.update_xml_text)
        except ElementTree.ParseError as perror:
            self.logger.error("Downloaded metadata is corrupted. {}".format(perror))
            raise ArchiveListError("Downloaded metadata is corrupted.")

        for packageupdate in self.update_xml.iter("PackageUpdate"):
            name = packageupdate.find("Name").text
            # Need to filter archives to download when we want all extra modules
            if self.all_extra:
                # Check platform
                name_last_section = name.split(".")[-1]
                if (
                    name_last_section in self.arch_list
                    and self.arch != name_last_section
                ):
                    continue
                # Check doc/examples
                if self.arch in ["doc", "examples"]:
                    if self.arch not in name:
                        continue
            if self.all_extra or name in target_packages:
                if packageupdate.find("DownloadableArchives").text is not None:
                    downloadable_archives = packageupdate.find(
                        "DownloadableArchives"
                    ).text.split(", ")
                    full_version = packageupdate.find("Version").text
                    # keep only '5.15.2' in '5.15.2-0-202011130724'
                    parsed_version = packaging.version.parse(full_version.split('-')[0])
                    package_desc = packageupdate.find("Description").text
                    for archive in downloadable_archives:
                        archive_name = archive.split("-", maxsplit=1)[0]
                        package_url = posixpath.join(
                            # https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/qt5_5150/
                            archive_url,
                            # qt.qt5.5150.gcc_64/
                            name,
                            # 5.15.0-0-202005140804qtbase-Linux-RHEL_7_6-GCC-Linux-RHEL_7_6-X86_64.7z
                            full_version + archive
                        )
                        hashurl = package_url + ".sha1"
                        self.archives.append(
                            QtPackage(
                                archive_name,
                                package_url,
                                archive,
                                package_desc,
                                hashurl,
                                parsed_version
                            )
                        )
        if len(self.archives) == 0:
            self.logger.error(
                "Specified packages are not found while parsing XML of package information!"
            )
            raise NoPackageFound
        self.logger.debug(f'Archives: {self.archives}')

    def get_archives(self):
        """
         It returns an archive package list.

        :return package list
        :rtype: List[QtPackage]
        """
        return self.archives

    def get_target_config(self) -> TargetConfig:
        """Get target configuration

        :return: configured target and its version with arch
        :rtype: TargetConfig object
        """
        return TargetConfig(self.version, self.target, self.arch, self.os_name)


class SrcDocExamplesArchives(QtArchives):
    """Hold doc/src/example archive package list."""

    def __init__(
        self,
        flavor,
        os_name,
        target,
        version,
        base,
        subarchives=None,
        modules=None,
        all_extra=False,
        timeout=(5, 5),
    ):
        self.flavor = flavor
        self.target = target
        self.os_name = os_name
        self.base = base
        self.logger = getLogger("aqt.archives")
        super(SrcDocExamplesArchives, self).__init__(
            os_name,
            target,
            version,
            self.flavor,
            base,
            subarchives=subarchives,
            modules=modules,
            all_extra=all_extra,
            timeout=timeout,
        )

    def _get_archives(self):
        archive_path = "{0}{1}{2}/qt{3}_{3}{4}{5}{6}".format(
            self.os_name,
            "_x86/" if self.os_name == "windows" else "_x64/",
            self.target,
            self.version.major,
            self.version.minor,
            self.version.micro,
            "_src_doc_examples/",
        )
        archive_url = "{0}{1}".format(self.base, archive_path)
        update_xml_url = "{0}/Updates.xml".format(archive_url)
        target_packages = []
        target_packages.append(
            "qt.qt{0}.{0}{1}{2}.{3}".format(
                self.version.major,
                self.version.minor,
                self.version.micro,
                self.flavor,
            )
        )
        target_packages.extend(self.mod_list)
        self._download_update_xml(update_xml_url)
        self._parse_update_xml(archive_url, target_packages)

    def get_target_config(self) -> TargetConfig:
        """Get target configuration.

        :return tuple of three parameter, "src_doc_examples", target and arch
        """
        return TargetConfig("src_doc_examples", self.target, self.arch, self.os_name)


class ToolArchives(QtArchives):
    """Hold tool archive package list
    when installing mingw tool, argument would be
    ToolArchive(windows, desktop, 4.9.1-3, mingw)
    when installing ifw tool, argument would be
    ToolArchive(linux, desktop, 3.1.1, ifw)
    """
    def __init__(self,
                 os_name: str,
                 tool_name: str,
                 base: str,
                 version_str: Optional[str] = None,
                 arch: Optional[str] = None,
                 timeout: Tuple[int, int] = (5, 5)):
        self.tool_name = tool_name
        self.os_name = os_name
        self.logger = getLogger("aqt.archives")
        super(ToolArchives, self).__init__(
            os_name=os_name, target="desktop",
            version_str=version_str, arch=arch,
            base=base, timeout=timeout,
        )

    def __str__(self):
        return f'ToolArchives(tool_name={self.tool_name}, version={self.version_str}, arch={self.arch})'

    def _get_archives(self):
        _a = "_x64"
        if self.os_name == "windows":
            _a = "_x86"

        archive_url = posixpath.join(
            # https://download.qt.io/online/qtsdkrepository/
            self.base,
            # linux_x64/
            self.os_name + _a,
            # desktop/
            self.target,
            # tools_ifw/
            self.tool_name
        )
        update_xml_url = posixpath.join(archive_url, "Updates.xml")
        self._download_update_xml(update_xml_url)  # call super method.
        self._parse_update_xml(archive_url, [])

    def _parse_update_xml(self, archive_url, target_packages):
        try:
            self.update_xml = ElementTree.fromstring(self.update_xml_text)
        except ElementTree.ParseError as perror:
            self.logger.error("Downloaded metadata is corrupted. {}".format(perror))
            raise ArchiveListError("Downloaded metadata is corrupted.")

        versions = []

        for packageupdate in self.update_xml.iter("PackageUpdate"):
            name = packageupdate.find("Name").text
            full_version = packageupdate.find("Version").text
            # keep only '4.1.1' in '4.1.1-20210526113'
            parsed_version = packaging.version.parse(full_version.split('-')[0])
            versions.append((name, str(parsed_version)))

            # Filter out on version first
            parsed_version = packaging.version.parse(full_version.split('-')[0])

            if self.version:
                if not satifiesVersion(self.version, parsed_version):
                    self.logger.warning(
                        "Base Version of {} is different from requested version {} -- skip.".format(
                            full_version, self.version
                        )
                    )
                    continue

            # Filter out on arch next
            if self.arch and name != self.arch:
                self.logger.warning(
                    f'Arch of {name} is different from requested '
                    f'arch {self.arch} -- skip.'
                )
                continue

            _archives = packageupdate.find("DownloadableArchives").text
            if _archives is not None:
                downloadable_archives = _archives.split(", ")
            else:
                downloadable_archives = []

            package_desc = packageupdate.find("Description").text
            for archive in downloadable_archives:
                package_url = posixpath.join(
                    # https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/tools_ifw/
                    archive_url,
                    # qt.tools.ifw.41/
                    name,
                    #  4.1.1-202105261130ifw-linux-x64.7z
                    f'{full_version}{archive}'
                )
                hashurl = package_url + ".sha1"
                self.archives.append(
                    QtPackage(name, package_url, archive, package_desc,
                              hashurl, parsed_version)
                )

        if self.archives:
            self.logger.debug(f'ToolArchives: {self.archives}')
        else:
            msg = f"{self} did not match any available tools. "
            if versions:
                msg += 'Available tools\n'
                msg += f'[(version, arch)] = {versions}'
            else:
                url = posixpath.join(archive_url, "Updates.xml")
                msg += f"Zero tools where found to be available in {url}"
            raise NoPackageFound(msg)

        if len(self.archives) > 1:
            self.logger.info(
                f"Found {len(self.archives)} potential archives. "
                "Returning the max.")
            archive_max = max(self.archives,
                              key=lambda package: package.version
                              if package.version
                              else packaging.version.Version('0'))
            self.archives = [archive_max]

    def get_target_config(self) -> TargetConfig:
        """Get target configuration.

        :return tuple of three parameter, "Tools", target and arch
        """
        return TargetConfig("Tools", self.target, self.arch, self.os_name)
