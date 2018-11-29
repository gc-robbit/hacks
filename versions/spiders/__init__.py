import os.path
import re
import subprocess

import requests
import yaml
from lxml import html

"""
Various 'spiders' that know how to retrieve version information from different sources.

"""


class BitbucketReleaseSpider(object):
    """
    Retrieve version from a Bitbucket tags (only looking at top two ones, discarding latest)
    Assumes tag list is sorted in a meaningful manner when it relates to versions
    """
    def __init__(self, owner, repository):
        api = "https://api.bitbucket.org/2.0/repositories/{owner}/{repository}/refs/tags?sort=-name"
        self.url = api.format(owner=owner, repository=repository)

    def get_version(self):
        response = requests.get(self.url)
        response.raise_for_status()
        data = response.json()
        candidate = data['values'][0]
        if candidate['name'] == 'latest':
            candidate = data['values'][1]

        return candidate['name']


class DockerfileSpider(object):
    """
    Retrieve version from a local Dockerfile (parse the Dockerfile FROM entry)
    """
    def __init__(self, path):
        self.path = path
        self.re = re.compile('^FROM .*:v?(\d+.*)$')
 
    def get_version(self):
        """
        Expects a Dockerfile with this format:
        FROM jada/jada:1.2.3
        """
        with open(os.path.expanduser(self.path)) as f:
            for line in f:
                match = self.re.match(line)
                if match:
                    return match.group(1)

        raise ValueError("No version found in {path}".format(path=self.path))


class DockerHubSpider(object):
    """
    Retrieve version from Docker hub tags list (only look at the top two ones, discarding latest)
    """
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name
        api = "https://registry.hub.docker.com/v2/repositories/{owner}/{name}/tags/"
        self.url = api.format(owner=self.owner, name=self.name)

    def get_version(self):
        response = requests.get(self.url)
        response.raise_for_status()

        data = response.json()
        candidate = data['results'][0]
        if candidate['name'] == 'latest':
            candidate = data['results'][1]

        return candidate['name']


class GithubReleaseSpider(object):
    """
    Retrieve version for the latest release of a Github project using the Github API
    """
    def __init__(self, owner, repository):
        api = 'https://api.github.com/repos/{owner}/{repository}/releases/latest'
        self.url = api.format(owner=owner, repository=repository)

    def get_version(self):
        """Response contains a Github release API response and since we request latest the tag_name will correspond
        to the actual latest available version"""
        response = requests.get(self.url)
        response.raise_for_status()
        return response.json()['tag_name'].lstrip('v')


class JenkinsStableSpider(object):
    """
    Retrieve version for the latest stable Jenkins release (parse the published LTS changelog)
    """
    def __init__(self):
        self.url = "https://jenkins.io/changelog-stable/"

    def get_version(self):
        """
        XPath version scanner for the Jenkins Stable/LTS change log page
        Usually the version there begins with a v
        """
        response = requests.get(self.url)
        response.raise_for_status()
        tree = html.fromstring(response.content)
        version_list = tree.xpath('//div[@class="ratings"]/h3[1]/@id')
        return version_list[0].lstrip('v')


class KubernetesVersionLabelSpider(object):
    """
    Retrieve version from a running k8s deployment assuming it's been labeled with app.kubernetes.io/version
    """
    def __init__(self, item, name, namespace):
        self.item = item
        self.name = name
        self.namespace = namespace

    def get_version(self):
        kubectl_command = "kubectl get {item} {name} -n {namespace} -o yaml".format(
            item=self.item, name=self.name, namespace=self.namespace
        )
        result = subprocess.run(kubectl_command, shell=True, check=True, stdout=subprocess.PIPE, encoding='utf-8')
        data = yaml.load(result.stdout)
        return data['metadata']['labels']['app.kubernetes.io/version'].lstrip('v')


class KubernetesImageVersionSpider(object):
    """
    Retrieves version from a running k8s resource using the provided pattern to boil down to the resource image spec
    For a stateful set the pattern could be: spec.template.spec.containers.0.image
    This spider does support numeric indexes used for list items.
    """
    def __init__(self, item, name, namespace, pattern):
        self.item = item
        self.name = name
        self.namespace = namespace
        self.pattern = pattern

    def get_version(self):
        kubectl_command = "kubectl -n {namespace} get {item} {name} -o yaml".format(
            namespace=self.namespace, item=self.item, name=self.name
        )
        result = subprocess.run(kubectl_command, shell=True, check=True, stdout=subprocess.PIPE, encoding='utf-8')
        data = yaml.load(result.stdout)
        section = data
        for p in self.pattern.split('.'):
            if isinstance(section, list):
                p = int(p)

            section = section[p]

        # Here we expect section to contain the image only, e.g. "quay.io/prometheus/prometheus:v2.2.1"
        (_, version) = section.split(':')
        return version.lstrip('v')
