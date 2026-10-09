output "aws_instance_ids" {
  value = ["${aws_instance.this.*.id}"]
}

output "azure_vm_ids" {
  value = ["${azurerm_virtual_machine.this.*.id}"]
}
