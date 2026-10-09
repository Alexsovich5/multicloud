variable "provider_type" {
  description = "Which cloud to create instances in: aws or azure"
}

variable "name_prefix" {
  default = "multicloud"
}

variable "instance_count" {
  default = 1
}

variable "instance_type" {
  description = "EC2 instance type or Azure VM size"
}

variable "aws_ami" {
  default = "ami-12c6146b"
}

variable "azure_location" {
  default = "East US"
}

variable "azure_resource_group" {
  default = ""
}

variable "azure_subnet_id" {
  default = ""
}

variable "ssh_public_key" {
  default = ""
}
