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
  name = "app"
  external_network_name = var.external_network_name
  cidr = var.workload_cidr
  admin_cidr = var.admin_cidr
  dns_servers = var.dns_servers
}
module "app" {
  source = "../modules/compute"
  name = "app-vm"
  network_id = module.network.network_id
  subnet_id = module.network.subnet_id
  security_group_id = module.network.security_group_id
  image_name = var.image_name
  flavor_name = var.flavor_name
  key_pair = var.key_pair
  external_network_name = var.external_network_name
}
module "database" {
  source = "../modules/compute"
  name = "db-vm"
  network_id = module.network.network_id
  subnet_id = module.network.subnet_id
  security_group_id = module.network.security_group_id
  image_name = var.image_name
  flavor_name = var.flavor_name
  key_pair = var.key_pair
  external_network_name = var.external_network_name
  allocate_floating_ip = false
}
resource "openstack_networking_secgroup_rule_v2" "database" {
  security_group_id = module.network.security_group_id
  remote_group_id = module.network.security_group_id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = 5432
  port_range_max = 5432
}
resource "openstack_networking_secgroup_rule_v2" "internal_ssh" {
  security_group_id = module.network.security_group_id
  remote_group_id = module.network.security_group_id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = 22
  port_range_max = 22
}
resource "openstack_blockstorage_volume_v3" "database" {
  name = "app-db-data"
  size = 5
  lifecycle {
    prevent_destroy = true
  }
}
resource "openstack_compute_volume_attach_v2" "database" {
  instance_id = module.database.instance_id
  volume_id = openstack_blockstorage_volume_v3.database.id
}
output "app_floating_ip" {
  value = module.app.floating_ip
}
output "app_private_ip" {
  value = module.app.private_ip
}
output "database_volume_id" {
  value = openstack_blockstorage_volume_v3.database.id
}
output "ansible_inventory" {
  value = {
    all = {
      children = {
        app = {
          hosts = {
            app1 = {
              ansible_host = module.app.floating_ip
              ansible_user = "ubuntu"
              private_ip = module.app.private_ip
              database_host = module.database.private_ip
            }
          }
        }
        database = {
          hosts = {
            db1 = {
              ansible_host = module.database.private_ip
              ansible_user = "ubuntu"
              private_ip = module.database.private_ip
              ansible_ssh_common_args = "-o ProxyJump=ubuntu@${module.app.floating_ip}"
            }
          }
        }
      }
    }
  }
}
