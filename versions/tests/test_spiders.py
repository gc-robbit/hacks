import unittest
from unittest.mock import patch, MagicMock, mock_open
import yaml
from spiders import (
    _beautify_version,
    _contains_version,
    _get_version_from_metadata_label,
    AlpinePackageSpider,
    BitbucketReleaseSpider,
    DockerfileSpider,
    DockerHubSpider,
    GithubLatestReleaseSpider,
    GithubPrefixReleaseSpider,
    GithubReleaseSpider,
    JenkinsStableSpider,
    KubernetesVersionLabelSpider,
    KubernetesImageVersionSpider,
    SonarQubeReleaseSpider,
    NASpider,
    StaticSpider
)

class TestHelperFunctions(unittest.TestCase):
    def test_beautify_version(self):
        self.assertEqual(_beautify_version('v1.2.3', True), '1.2.3')
        self.assertEqual(_beautify_version('release-1.2.3', True), '1.2.3')
        self.assertEqual(_beautify_version('1.2.3-beta', True), '1.2.3')
        self.assertEqual(_beautify_version('v1.2.3', False), 'v1.2.3')

    def test_contains_version(self):
        self.assertTrue(_contains_version('1.2.3'))
        self.assertTrue(_contains_version('v1.2.3'))
        self.assertFalse(_contains_version('noversion'))

    def test_get_version_from_metadata_label(self):
        yaml_data = {
            'metadata': {
                'name': 'test-pod',
                'labels': {
                    'app.kubernetes.io/version': '1.2.3'
                }
            }
        }
        self.assertEqual(_get_version_from_metadata_label(yaml_data), '1.2.3')

        yaml_data2 = {
            'metadata': {
                'name': 'test-pod',
                'labels': {
                    'apps.kubernetes.io/version': '4.5.6'
                }
            }
        }
        self.assertEqual(_get_version_from_metadata_label(yaml_data2), '4.5.6')

        with self.assertRaises(ValueError):
            _get_version_from_metadata_label({'metadata': {'name': 'test', 'labels': {}}})

class TestSpiders(unittest.TestCase):

    @patch('requests.get')
    def test_alpine_package_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'<html><table><td class="version">3.14.0</td></table></html>'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = AlpinePackageSpider('nginx', 'cool-branch')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '3.14.0')
        self.assertIn('nginx', spider.url)
        self.assertIn('cool-branch', spider.url)
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_bitbucket_release_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'values': [
                {'name': '1.0.0'},
                {'name': 'v2.0.0'}, # Should be ignored by version_pattern
                {'name': '1.1.0'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = BitbucketReleaseSpider('owner', 'repo')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.0.0') # First matching in data['values']

    @patch('requests.get')
    def test_bitbucket_release_spider_no_beautify(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'values': [
                {'name': '1.0.0'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = BitbucketReleaseSpider('owner', 'repo')
        version = spider.get_version(beautify=False)
        self.assertEqual(version, '1.0.0')

    def test_dockerfile_spider(self):
        m = mock_open(read_data="FROM nginx:v1.2.3\n")
        with patch('builtins.open', m):
            spider = DockerfileSpider('Dockerfile')
            version = spider.get_version(beautify=True)
            self.assertEqual(version, '1.2.3')

        m = mock_open(read_data="FROM nginx:1.2.3-alpine\n")
        with patch('builtins.open', m):
            spider = DockerfileSpider('Dockerfile')
            version = spider.get_version(beautify=True)
            self.assertEqual(version, '1.2.3')

        m = mock_open(read_data="EXPOSE 80\n")
        with patch('builtins.open', m):
            spider = DockerfileSpider('Dockerfile')
            with self.assertRaises(ValueError):
                spider.get_version(beautify=True)

    @patch('requests.get')
    def test_docker_hub_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'results': [
                {'name': '1.0.0'},
                {'name': '1.2.0'},
                {'name': '1.1.0'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = DockerHubSpider('library', 'nginx')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.2.0')

    @patch('requests.get')
    def test_github_latest_release_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {'tag_name': 'v1.5.0'}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = GithubLatestReleaseSpider('owner', 'repo')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.5.0')

    @patch('requests.get')
    def test_github_prefix_release_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'tag_name': 'v2.0.0'},
            {'tag_name': 'v1.1.0'},
            {'tag_name': 'v1.0.0'}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = GithubPrefixReleaseSpider('owner', 'repo', '1.')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.1.0')

        with self.assertRaises(ValueError):
            spider = GithubPrefixReleaseSpider('owner', 'repo', '3.')
            spider.get_version(beautify=True)

    @patch('requests.get')
    def test_github_release_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'tag_name': '1.0.0'},
            {'tag_name': '1.2.0'},
            {'tag_name': '1.1.0'}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = GithubReleaseSpider('owner', 'repo')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.2.0')

    @patch('requests.get')
    def test_jenkins_stable_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'<html><div class="ratings"><h3 id="2.289.1"></h3></div></html>'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = JenkinsStableSpider()
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '2.289.1')

    @patch('subprocess.run')
    def test_kubernetes_version_label_spider(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "metadata:\n  name: test\n  labels:\n    app.kubernetes.io/version: 1.2.3"
        mock_run.return_value = mock_result

        spider = KubernetesVersionLabelSpider('deployment', 'test', 'default')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.2.3')

    @patch('subprocess.run')
    def test_kubernetes_image_version_spider(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "spec:\n  template:\n    spec:\n      containers:\n      - image: nginx:1.19.0"
        mock_run.return_value = mock_result

        spider = KubernetesImageVersionSpider('deployment', 'test', 'default', 'spec.template.spec.containers.0.image')
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '1.19.0')

    @patch('requests.get')
    def test_sonarqube_release_spider(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'<html><a href="sonarqube-8.9.0.zip"></a><a href="sonarqube-9.0.0.zip"></a></html>'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        spider = SonarQubeReleaseSpider()
        version = spider.get_version(beautify=True)
        self.assertEqual(version, '9.0.0')

        # Test failure case
        mock_response.content = b'<html></html>'
        with self.assertRaises(ValueError):
            spider.get_version(beautify=True)

    def test_na_spider(self):
        spider = NASpider()
        self.assertEqual(spider.get_version(beautify=True), "N/A")

    def test_static_spider(self):
        spider = StaticSpider("1.2.3")
        self.assertEqual(spider.get_version(beautify=True), "1.2.3")
        self.assertEqual(spider.get_version(beautify=False), "1.2.3")

if __name__ == '__main__':
    unittest.main()
