terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    openstack = {
      source = "terraform-provider-openstack/openstack"
      version = "~> 3.4.0"
    }
  }
}
provider "openstack" {}
variable "admin_cidr" {
  type = string
}
variable "dns_servers" {
  type = list(string)
}
variable "workload_cidr" {
  type = string
}
variable "external_network_name" {
  type = string
  default = "public"
}
variable "image_name" {
  type = string
  default = "ubuntu-24.04"
}
variable "flavor_name" {
  type = string
  default = "lab.small"
}
variable "key_pair" {
  type = string
  default = "lab-key"
}
module "network" {
  source = "../modules/network"
  name = "first"
  external_network_name = var.external_network_name
  cidr = var.workload_cidr
  admin_cidr = var.admin_cidr
  dns_servers = var.dns_servers
}
module "compute" {
  source = "../modules/compute"
  name = "first-vm"
  network_id = module.network.network_id
  subnet_id = module.network.subnet_id
  security_group_id = module.network.security_group_id
  image_name = var.image_name
  flavor_name = var.flavor_name
  key_pair = var.key_pair
  external_network_name = var.external_network_name
}
output "floating_ip" {
  value = module.compute.floating_ip
}
