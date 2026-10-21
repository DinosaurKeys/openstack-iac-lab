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
variable "network_id" {
  type = string
}
variable "subnet_id" {
  type = string
}
variable "security_group_id" {
  type = string
}
variable "image_name" {
  type = string
}
variable "flavor_name" {
  type = string
}
variable "key_pair" {
  type = string
}
variable "external_network_name" {
  type = string
}
variable "allocate_floating_ip" {
  type = bool
  default = true
}
data "openstack_images_image_v2" "image" {
  name = var.image_name
}
data "openstack_compute_flavor_v2" "flavor" {
  name = var.flavor_name
}
resource "openstack_networking_port_v2" "vm" {
  name = "${var.name}-port"
  network_id = var.network_id
  security_group_ids = [var.security_group_id]
  fixed_ip {
    subnet_id = var.subnet_id
  }
}
resource "openstack_compute_instance_v2" "vm" {
  name = var.name
  image_id = data.openstack_images_image_v2.image.id
  flavor_id = data.openstack_compute_flavor_v2.flavor.id
  key_pair = var.key_pair
  network {
    port = openstack_networking_port_v2.vm.id
  }
  user_data = "#cloud-config\npackage_update: false\n"
}
resource "openstack_networking_floatingip_v2" "vm" {
  count = var.allocate_floating_ip ? 1 : 0
  pool = var.external_network_name
  port_id = openstack_networking_port_v2.vm.id
}
output "instance_id" {
  value = openstack_compute_instance_v2.vm.id
}
output "private_ip" {
  value = openstack_networking_port_v2.vm.all_fixed_ips[0]
}
output "floating_ip" {
  value = var.allocate_floating_ip ? openstack_networking_floatingip_v2.vm[0].address : null
}
