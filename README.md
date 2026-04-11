# Multi-Cloud Management Platform

![Project Status](https://img.shields.io/badge/Status-Complete-brightgreen)
![Timeline](https://img.shields.io/badge/Timeline-July%202018%20--%20November%202018-blue)
![Technology](https://img.shields.io/badge/Tech-Terraform%20%7C%20Python%203.7%20%7C%20Kubernetes%20%7C%20GraphQL-orange)

## Project Overview

Unified multi-cloud management platform for provisioning and managing resources across AWS and Azure with Terraform, a Python API layer, and GraphQL interface.

**Role**: IT Operations Specialist
**Organization**: ACORIA
**Duration**: July 2018 - November 2018
**Project**: #17 of 30 in IT Career Portfolio

## Business Impact

- **Single Pane of Glass**: Unified view across AWS and Azure
- **50% Faster Provisioning**: Terraform-automated multi-cloud deployments
- **Cost Visibility**: Cross-cloud cost tracking and optimization
- **Vendor Flexibility**: Avoid lock-in with abstracted provider layer

## Technology Stack

- **Terraform 0.11**: Multi-cloud Infrastructure as Code
- **Python 3.7**: Backend API and orchestration
- **Kubernetes 1.11**: Container orchestration
- **GraphQL**: Flexible API query layer

## Project Structure

```
multicloud/
├── README.md
├── requirements.txt
├── docker-compose.yml
├── src/
│   ├── cloud_manager.py
│   ├── graphql_schema.py
│   └── providers/
│       ├── aws_provider.py
│       └── azure_provider.py
├── terraform/
│   ├── main.tf
│   └── modules/compute/
│       └── main.tf
└── k8s/
    └── deployment.yaml
```

## Contributing

This is a historical project from July 2018 - November 2018, preserved for portfolio purposes.

## License

Professional portfolio project - ACORIA

---

**Developed during July 2018 - November 2018**
*Part of Alexander Efrem's IT Career Portfolio (2012-2024)*
