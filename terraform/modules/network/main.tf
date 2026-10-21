terraform {
  required_providers {
    openstack = {
      source = "terraform-provider-openstack/openstack"
      version = "~> 3.4.0"
    }
  }
}

variable "name" {
  type = string
}
variable "external_network_name" {
  type = string
}
variable "cidr" {
  type = string
  validation {
    condition = can(cidrnetmask(var.cidr))
    error_message = "Supply a valid IPv4 CIDR after checking for overlap."
  }
}
variable "admin_cidr" {
  type = string
}
variable "dns_servers" {
  type = list(string)
}
variable "tcp_ports" {
  type = set(number)
  default = [22, 80]
}

data "openstack_networking_network_v2" "external" {
  name = var.external_network_name
  external = true
}
resource "openstack_networking_network_v2" "private" {
  name = "${var.name}-net"
}
resource "openstack_networking_subnet_v2" "private" {
  name = "${var.name}-subnet"
  network_id = openstack_networking_network_v2.private.id
  cidr = var.cidr
  ip_version = 4
  dns_nameservers = var.dns_servers
}
resource "openstack_networking_router_v2" "router" {
  name = "${var.name}-router"
  external_network_id = data.openstack_networking_network_v2.external.id
}
resource "openstack_networking_router_interface_v2" "private" {
  router_id = openstack_networking_router_v2.router.id
  subnet_id = openstack_networking_subnet_v2.private.id
}
resource "openstack_networking_secgroup_v2" "access" {
  name = "${var.name}-access"
  description = "Lab access from the reviewed management CIDR"
}
resource "openstack_networking_secgroup_rule_v2" "tcp" {
  for_each = toset([for port in var.tcp_ports : tostring(port)])
  security_group_id = openstack_networking_secgroup_v2.access.id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "tcp"
  port_range_min = tonumber(each.value)
  port_range_max = tonumber(each.value)
  remote_ip_prefix = var.admin_cidr
}
resource "openstack_networking_secgroup_rule_v2" "icmp" {
  security_group_id = openstack_networking_secgroup_v2.access.id
  direction = "ingress"
  ethertype = "IPv4"
  protocol = "icmp"
  remote_ip_prefix = var.admin_cidr
}
output "network_id" {
  value = openstack_networking_network_v2.private.id
  depends_on = [openstack_networking_router_interface_v2.private]
}
output "subnet_id" {
  value = openstack_networking_subnet_v2.private.id
}
output "security_group_id" {
  value = openstack_networking_secgroup_v2.access.id
}
