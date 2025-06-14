import abc
import os.path
import re
import subprocess

from natsort import natsorted
import requests
import yaml
from lxml import html

"""
Various 'spiders' that know how to retrieve version information from different sources.

"""


def _beautify_version(version, beautify) -> str:
    """
    Attempts to return the numerical part of a version by stripping away common prefix and postfix notation
    Strings stripped can be release-, v or x.y.z-just-some-annoying-text
    """
    if not beautify:
        return version

    beautiful_version = version.lstrip('v')
    if beautiful_version.startswith('release-'):
        beautiful_version = beautiful_version[len('release-'):]

    if '-' in beautiful_version:
        parts = beautiful_version.split('-')
        beautiful_version = parts[0]

    return beautiful_version


def _contains_version(candidate):
    beautified = _beautify_version(candidate, True)
    return re.match(r'[\d+.]+', beautified)


def _get_version_from_metadata_label(yaml_data) -> str:
    if 'labels' not in yaml_data['metadata']:
        raise ValueError('Key: labels not found in metadata for {name}'.format(name=yaml_data['metadata']['name']))

    labels = yaml_data['metadata']['labels']

    if 'app.kubernetes.io/version' in labels:
        return labels['app.kubernetes.io/version']
    elif 'apps.kubernetes.io/version' in labels:
        return labels['apps.kubernetes.io/version']
    else:
        raise ValueError('Key: app.kubernetes.io/version not found in labels for {name}'.format(
            name=yaml_data['metadata']['name'])
        )


class AbstractSpider(abc.ABC):

    """
    Base class for all spiders
    """
    @abc.abstractmethod
    def get_version(self, beautify: bool) -> str:
        pass


class AlpinePackageSpider(AbstractSpider):
    """
    Grab the latest (only?) version for an alpine package that exists for specific alpine version
    """
    def __init__(self, name, branch) -> None:
        url = "https://pkgs.alpinelinux.org/packages?name={name}&branch={branch}&arch=x86_64"
        self.url = url.format(name=name, branch=branch)

    def get_version(self, beautify: bool) -> str:
        response = requests.get(self.url)
        response.raise_for_status()
        tree = html.fromstring(response.content)
        version_list = tree.xpath('//td[@class="version"]/text()')
        return _beautify_version(version_list[0], beautify)


class BitbucketReleaseSpider(AbstractSpider):
    """
    Retrieve version from Bitbucket tags. Assumes x.y.z tags are used!
    """
    def __init__(self, owner: str, repository: str) -> None:
        self.url = f'https://api.bitbucket.org/2.0/repositories/{owner}/{repository}/refs/tags?sort=-name&pagelen=100'
        self.version_pattern = re.compile(r'^\d+.\d+.\d+$')

    def get_version(self, beautify: bool) -> str:
        response = requests.get(self.url)
        response.raise_for_status()
        data = response.json()

        versions = [x['name'] for x in data['values'] if self.version_pattern.match(x['name'])]
        return _beautify_version(versions[0], beautify)


class DockerfileSpider(AbstractSpider):
    """
    Retrieve version from a local Dockerfile (parse the Dockerfile FROM entry)
    """
    def __init__(self, path: str) -> None:
        self.path = path
        self.re = re.compile(r'^FROM .*:v?(\d+.*)$')

    def get_version(self, beautify: bool) -> str:
        """
        Expects a Dockerfile with this format:
        FROM jada/jada:1.2.3
        """
        with open(os.path.expanduser(self.path)) as f:
            for line in f:
                match = self.re.match(line)
                if match:
                    return _beautify_version(match.group(1), beautify)

        raise ValueError("No version found in {path}".format(path=self.path))


class DockerHubSpider(AbstractSpider):
    """
    Retrieve version from Docker hub tags list, sorting all versions using natsort to find the highest one.
    Assumes the tag names only contains versions!
    """
    def __init__(self, owner: str, name: str) -> None:
        self.owner = owner
        self.name = name
        self.url = f'https://registry.hub.docker.com/v2/repositories/{owner}/{name}/tags?page_size=100'
        self.version_pattern = re.compile(r'^\d+.\d+.\d+(-\d)?$')

    def get_version(self, beautify: bool) -> str:
        response = requests.get(self.url)
        response.raise_for_status()

        data = response.json()
        unsorted = [x['name'] for x in data['results'] if self.version_pattern.match(x['name'])]
        versions = natsorted(unsorted, reverse=True)
        return _beautify_version(versions[0], beautify)


class GithubLatestReleaseSpider(AbstractSpider):
    """
    Retrieve version for the latest release of a GitHub project using the GitHub API
    """
    def __init__(self, owner: str, repository: str) -> None:
        self.url = f'https://api.github.com/repos/{owner}/{repository}/releases/latest'

    def get_version(self, beautify: bool) -> str:
        """Response contains a GitHub release API response, and since we request latest the tag_name will correspond
        to the actual latest available version"""
        response = requests.get(self.url)
        response.raise_for_status()
        return _beautify_version(response.json()['tag_name'], beautify)


class GithubPrefixReleaseSpider(AbstractSpider):
    """
    Retrieve highest version matching a prefix
    """
    def __init__(self, owner: str, repository: str, prefix: str) -> None:
        self.url = f'https://api.github.com/repos/{owner}/{repository}/releases'
        self.prefix = prefix

    def get_version(self, beautify: bool) -> str:
        response = requests.get(self.url)
        response.raise_for_status()
        data = response.json()
        for release in data:
            version = _beautify_version(release['tag_name'], True)
            if version.startswith(self.prefix):
                return version if beautify else release['tag_name']

        raise ValueError(f"Failed to locate a release matching prefix: {self.prefix}")


class GithubReleaseSpider(AbstractSpider):
    def __init__(self, owner, repository) -> None:
        self.url = f'https://api.github.com/repos/{owner}/{repository}/releases'

    def get_version(self, beautify: bool) -> str:
        response = requests.get(self.url)
        response.raise_for_status()
        data = response.json()
        versions = [release['tag_name'] for release in data]
        reverse_versions = natsorted(versions, reverse=True)
        return _beautify_version(reverse_versions[0], beautify)


class JenkinsStableSpider(AbstractSpider):
    """
    Retrieve the version for the latest stable Jenkins release (parse the published LTS changelog)
    """
    def __init__(self) -> None:
        self.url = "https://jenkins.io/changelog-stable/"

    def get_version(self, beautify: bool) -> str:
        """
        XPath version scanner for the Jenkins Stable/LTS change log page
        Usually the version there begins with a v
        """
        response = requests.get(self.url)
        response.raise_for_status()
        tree = html.fromstring(response.content)
        version_list = tree.xpath('//div[@class="ratings"]//h3[1]/@id')
        return _beautify_version(version_list[0], beautify)


class KubernetesVersionLabelSpider(AbstractSpider):
    """
    Retrieve version from a running k8s deployment assuming it's been labeled with app.kubernetes.io/version
    """
    def __init__(self, item: str, name: str, namespace: str) -> None:
        self.item = item
        self.name = name
        self.namespace = namespace

    def get_version(self, beautify: bool) -> str:
        kubectl_command = f"kubectl get {self.item} {self.name} -n {self.namespace} -o yaml"
        result = subprocess.run(kubectl_command, shell=True, check=True, stdout=subprocess.PIPE, encoding='utf-8')
        data = yaml.load(result.stdout, yaml.SafeLoader)
        return _beautify_version(_get_version_from_metadata_label(data), beautify)


class KubernetesImageVersionSpider(AbstractSpider):
    """
    Retrieves version from a running k8s resource using the provided pattern to boil down to the resource image spec
    For a stateful set the pattern could be: spec.template.spec.containers.0.image
    This spider does support numeric indexes used for list items.
    """
    def __init__(self, item: str, name: str, namespace: str, pattern: str) -> None:
        self.item = item
        self.name = name
        self.namespace = namespace
        self.pattern = pattern

    def get_version(self, beautify: bool) -> str:
        kubectl_command = f"kubectl -n {self.namespace} get {self.item} {self.name} -o yaml"
        result = subprocess.run(kubectl_command, shell=True, check=True, stdout=subprocess.PIPE, encoding='utf-8')
        data = yaml.load(result.stdout, yaml.SafeLoader)
        section = data
        for p in self.pattern.split('.'):
            if isinstance(section, list):
                p = int(p)

            section = section[p]

        # Here we expect section to contain the image only, e.g. "quay.io/prometheus/prometheus:v2.2.1"
        (_, version) = section.split(':')
        return _beautify_version(version, beautify)


class SonarQubeReleaseSpider(AbstractSpider):
    """
    Retrieves version using SonarQubes download pages (HTML scrape). Hopefully somewhat stable page.
    """
    def __init__(self) -> None:
        self.url = 'https://binaries.sonarsource.com/Distribution/sonarqube/'

    def get_version(self, beautify: bool) -> str:
        """
        XPath version scanner for the SonarQube Distribution page. Finds all downloads for sonarqube and sorts them
        """
        response = requests.get(self.url)
        response.raise_for_status()
        tree = html.fromstring(response.content)
        download_links = tree.xpath('//a/@href')
        filtered = map(lambda x: x.replace('sonarqube-', '').replace('.zip', ''),
                       filter(lambda x: x.startswith('sonarqube-') and x.endswith('.zip'), download_links))
        sorted_downloads = natsorted(filtered, reverse=True)
        if len(sorted_downloads) == 0:
            raise ValueError("SonarQubeReleaseSpider failed to locate any releases")

        return _beautify_version(sorted_downloads[0], beautify)


class NASpider(AbstractSpider):
    """
    Very crude N/A spider. Mostly useful while developing
    """
    def get_version(self, beautify: bool) -> str:
        return "N/A"

class StaticSpider(AbstractSpider):
    """
    StaticSpider simply returns the version you give as input
    """
    def __init__(self, version: str) -> None:
        self.version = version

    def get_version(self, beautify: bool) -> str:
        return _beautify_version(self.version, beautify)