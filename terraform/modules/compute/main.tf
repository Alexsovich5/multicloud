data "aws_availability_zones" "available" {}

resource "aws_instance" "this" {
  count             = "${var.provider_type == "aws" ? var.instance_count : 0}"
  ami               = "${var.aws_ami}"
  instance_type     = "${var.instance_type}"
  availability_zone = "${element(data.aws_availability_zones.available.names, count.index)}"

  tags {
    Name = "${var.name_prefix}-${count.index}"
  }
}

resource "azurerm_network_interface" "this" {
  count               = "${var.provider_type == "azure" ? var.instance_count : 0}"
  name                = "${var.name_prefix}-nic-${count.index}"
  location            = "${var.azure_location}"
  resource_group_name = "${var.azure_resource_group}"

  ip_configuration {
    name                          = "internal"
    subnet_id                     = "${var.azure_subnet_id}"
    private_ip_address_allocation = "dynamic"
  }
}

resource "azurerm_virtual_machine" "this" {
  count                 = "${var.provider_type == "azure" ? var.instance_count : 0}"
  name                  = "${var.name_prefix}-vm-${count.index}"
  location              = "${var.azure_location}"
  resource_group_name   = "${var.azure_resource_group}"
  vm_size               = "${var.instance_type}"
  network_interface_ids = ["${element(azurerm_network_interface.this.*.id, count.index)}"]

  delete_os_disk_on_termination = true

  storage_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "18.04-LTS"
    version   = "latest"
  }

  storage_os_disk {
    name              = "${var.name_prefix}-osdisk-${count.index}"
    caching           = "ReadWrite"
    create_option     = "FromImage"
    managed_disk_type = "Standard_LRS"
  }

  os_profile {
    computer_name  = "${var.name_prefix}-${count.index}"
    admin_username = "azureuser"
  }

  os_profile_linux_config {
    disable_password_authentication = true

    ssh_keys {
      path     = "/home/azureuser/.ssh/authorized_keys"
      key_data = "${var.ssh_public_key}"
    }
  }
}
