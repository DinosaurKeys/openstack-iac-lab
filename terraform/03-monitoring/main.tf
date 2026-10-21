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
variable "app_private_ip" {
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
data "openstack_networking_network_v2" "app" {
  name = "app-net"
}
data "openstack_networking_subnet_v2" "app" {
  name = "app-subnet"
}
data "openstack_networking_secgroup_v2" "app" {
  name = "app-access"
}
resource "openstack_networking_secgroup_v2" "monitor" {
  name = "monitor-access"
}
resource "openstack_networking_secgroup_rule_v2" "admin" {
  for_each = toset(["22", "3000"])
  security_group_id = openstack_networking_secgroup_v2.monitor.id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = tonumber(each.value)
  port_range_max = tonumber(each.value)
  remote_ip_prefix = var.admin_cidr
}
resource "openstack_networking_secgroup_rule_v2" "app_metrics" {
  security_group_id = data.openstack_networking_secgroup_v2.app.id
  remote_group_id = openstack_networking_secgroup_v2.monitor.id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = 9100
  port_range_max = 9100
}
resource "openstack_networking_secgroup_rule_v2" "app_probe" {
  security_group_id = data.openstack_networking_secgroup_v2.app.id
  remote_group_id = openstack_networking_secgroup_v2.monitor.id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = 80
  port_range_max = 80
}
module "monitor" {
  source = "../modules/compute"
  name = "monitor-vm"
  network_id = data.openstack_networking_network_v2.app.id
  subnet_id = data.openstack_networking_subnet_v2.app.id
  security_group_id = openstack_networking_secgroup_v2.monitor.id
  image_name = var.image_name
  flavor_name = var.flavor_name
  key_pair = var.key_pair
  external_network_name = var.external_network_name
}
output "floating_ip" {
  value = module.monitor.floating_ip
}
output "ansible_inventory" {
  value = {
    all = {
      children = {
        monitoring = {
          hosts = {
            monitor1 = {
              ansible_host = module.monitor.floating_ip
              ansible_user = "ubuntu"
              private_ip = module.monitor.private_ip
              app_probe_url = "http://${var.app_private_ip}/health"
            }
          }
        }
      }
    }
  }
}
