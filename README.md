# Multi-Cloud Management Platform

Unified multi-cloud management platform for provisioning and managing resources across AWS and Azure with Terraform, a Python API layer, and GraphQL interface.

Personal project, built to explore a single provisioning abstraction over AWS and Azure. It is not production software — see **Status** below for exactly what is and isn't implemented.

## Status

**Implemented**

- Provider abstraction with concrete AWS and Azure implementations
- Cloud manager dispatching to the right provider
- Terraform for both clouds

**Not implemented / known limitations**

- No GraphQL layer despite `graphene`/`flask-graphql` being declared as dependencies
- Covers compute and resource groups only — no storage, networking or IAM
- No tests

## Built with

- **Python** — boto3, azure-mgmt-compute, azure-mgmt-resource, graphene, flask, flask-graphql, PyYAML

## Running it

```bash
pip install -r requirements.txt
python src/cloud_manager.py
```

## Layout

```
requirements.txt
src/
  cloud_manager.py
  providers/
    aws_provider.py
    azure_provider.py
terraform/
  main.tf
```

