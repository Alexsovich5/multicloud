# Multi-cloud compute: the same module is called once per cloud.

provider "aws" {
  version    = "= 1.46.0"
  region     = "us-east-1"
  access_key = "${var.aws_access_key}"
  secret_key = "${var.aws_secret_key}"

  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_get_ec2_platforms      = true
  skip_region_validation      = true

  endpoints {
    ec2 = "${var.aws_endpoint}"
  }
}

provider "azurerm" {
  version                     = "= 1.19.0"
  skip_credentials_validation = true
}

resource "azurerm_resource_group" "main" {
  name     = "multicloud-demo-rg"
  location = "${var.azure_location}"
}

resource "azurerm_virtual_network" "main" {
  name                = "multicloud-vnet"
  address_space       = ["10.20.0.0/16"]
  location            = "${azurerm_resource_group.main.location}"
  resource_group_name = "${azurerm_resource_group.main.name}"
}

resource "azurerm_subnet" "main" {
  name                 = "compute"
  resource_group_name  = "${azurerm_resource_group.main.name}"
  virtual_network_name = "${azurerm_virtual_network.main.name}"
  address_prefix       = "10.20.1.0/24"
}

module "aws_compute" {
  source          = "./modules/compute"
  provider_type   = "aws"
  name_prefix     = "multicloud-aws"
  instance_count  = "${var.instance_count}"
  instance_type   = "${var.aws_instance_type}"
  azure_subnet_id = ""
}

module "azure_compute" {
  source               = "./modules/compute"
  provider_type        = "azure"
  name_prefix          = "multicloud-azure"
  instance_count       = "${var.instance_count}"
  instance_type        = "${var.azure_vm_size}"
  azure_location       = "${azurerm_resource_group.main.location}"
  azure_resource_group = "${azurerm_resource_group.main.name}"
  azure_subnet_id      = "${azurerm_subnet.main.id}"
  ssh_public_key       = "${var.ssh_public_key}"
}
