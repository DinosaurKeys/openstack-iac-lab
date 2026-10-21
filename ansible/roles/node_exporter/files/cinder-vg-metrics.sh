#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
metrics_dir=/var/lib/prometheus/node-exporter
sample=$(mktemp "$metrics_dir/.cinder-vg.XXXXXX")
trap 'rm -f "$sample"' EXIT
free_bytes=$(vgs --noheadings --units b --nosuffix -o vg_free cinder-volumes | tr -d ' ')
size_bytes=$(vgs --noheadings --units b --nosuffix -o vg_size cinder-volumes | tr -d ' ')
[[ "$free_bytes" =~ ^[0-9]+([.][0-9]+)?$ ]]
[[ "$size_bytes" =~ ^[0-9]+([.][0-9]+)?$ ]]
printf '# HELP lab_cinder_vg_free_bytes Free extents in the Cinder volume group.\n# TYPE lab_cinder_vg_free_bytes gauge\nlab_cinder_vg_free_bytes %s\n' "$free_bytes" > "$sample"
printf '# HELP lab_cinder_vg_size_bytes Total Cinder volume-group capacity.\n# TYPE lab_cinder_vg_size_bytes gauge\nlab_cinder_vg_size_bytes %s\n' "$size_bytes" >> "$sample"
chmod 0644 "$sample"
mv "$sample" "$metrics_dir/cinder-vg.prom"
