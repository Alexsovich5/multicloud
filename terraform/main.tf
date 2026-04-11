# Multi-Cloud Terraform Configuration
# IT Operations Specialist - ACORIA (2018)

provider "aws" {
  region = "us-east-1"
}

provider "azurerm" {
  version = "~> 1.0"
}

module "aws_compute" {
  source        = "./modules/compute"
  provider_type = "aws"
  instance_count = 2
  instance_type  = "t3.medium"
}

resource "azurerm_resource_group" "main" {
  name     = "acoria-multicloud-rg"
  location = "East US"
}

resource "azurerm_virtual_machine" "app" {
  name                  = "acoria-app-vm"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  vm_size               = "Standard_B2s"
  network_interface_ids = []

  storage_os_disk {
    name              = "osdisk"
    caching           = "ReadWrite"
    create_option     = "FromImage"
    managed_disk_type = "Standard_LRS"
  }

  os_profile {
    computer_name  = "acoria-app"
    admin_username = "adminuser"
  }

  os_profile_linux_config {
    disable_password_authentication = true
  }
}
