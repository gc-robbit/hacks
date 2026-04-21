# Versions

A little tool to keep track of current and upstream versions. 

The result is output in a nice little colored table.

## Configuration

Edit config.yaml and list what you want to track.

If a Spider is missing, please submit a PR.

E.g.

```yaml
versions:
  - name: Karpenter
    current:
      name: StaticSpider
      params:
        version: 1.2.0
    latest:
      name: GithubReleaseSpider
      params:
        owner: aws
        repository: karpenter-provider-aws

```

## Spiders

All spiders must inherit from AbstractSpider and implement the `get_version(beautify: bool) -> str:` method.

Some spiders parse the web and can fail when those pages change.

The current list of spiders:

- AlpinePackageSpider
- BitbucketReleaseSpider
- DockerfileSpider
- DockerHubSpider
- GithubLatestReleaseSpider
- GithubPrefixReleaseSpider
- GithubReleaseSpider
- JenkinsStableSpider
- KubernetesImageVersionSpider
- SonarQubeReleaseSpider
- NASpider
- StaticSpider

## Usage

```bash
uv run versions.py
```

## Testing

```bash
uv run pytest
```