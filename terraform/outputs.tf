output "aws_instance_ids" {
  value = ["${module.aws_compute.aws_instance_ids}"]
}

output "azure_vm_ids" {
  value = ["${module.azure_compute.azure_vm_ids}"]
}

output "azure_subnet_id" {
  value = "${azurerm_subnet.main.id}"
}
