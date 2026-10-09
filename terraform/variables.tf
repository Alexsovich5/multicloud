variable "aws_endpoint" {
  description = "EC2 API endpoint; point it at moto for local plans"
  default     = "https://ec2.us-east-1.amazonaws.com"
}

variable "aws_access_key" {
  default = "testing"
}

variable "aws_secret_key" {
  default = "testing"
}

variable "instance_count" {
  description = "Number of compute instances per cloud"
  default     = 2
}

variable "aws_instance_type" {
  default = "m4.large"
}

variable "azure_vm_size" {
  default = "Standard_B2s"
}

variable "azure_location" {
  default = "East US"
}

variable "ssh_public_key" {
  description = "Public key installed for the Azure admin user"
  default     = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ replace-with-a-real-key"
}
