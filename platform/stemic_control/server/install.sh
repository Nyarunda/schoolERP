#!/usr/bin/env bash
# One-time setup on the production server, so schools' custom domains go live without anyone editing nginx:
#
#   sudo bash /home/frappe/frappe-bench/apps/stemic_control/server/install.sh /home/frappe/frappe-bench
#
# Installs stemic-domains-sync and its systemd units, the shared nginx site settings (snippets/stemic-site.conf) and
# the main nginx config (conf.d/stemic.conf). The current nginx files are backed up first and put back if nginx -t
# fails. Safe to run again after an update.
set -euo pipefail
BENCH=${1:?usage: install.sh <bench path>}
BENCH=$(realpath "$BENCH")
HERE=$(dirname "$(realpath "$0")")
[ -d "$BENCH/sites" ] || { echo "$BENCH is not a bench"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
OWNER=$(stat -c %U "$BENCH/sites")

stamp=$(date +%Y%m%d%H%M%S)
backup=/var/backups/stemic-nginx-$stamp
mkdir -p "$backup"
for f in /etc/nginx/conf.d/stemic.conf /etc/nginx/conf.d/stemic-domains.conf /etc/nginx/snippets/stemic-site.conf; do
    [ -e "$f" ] && cp -p "$f" "$backup/"
done
restore() {
    echo "nginx -t failed: putting the previous configuration back ($backup)"
    rm -f /etc/nginx/conf.d/stemic-domains.conf /etc/nginx/snippets/stemic-site.conf
    for f in "$backup"/*; do
        [ -e "$f" ] || continue
        case $(basename "$f") in
            stemic-site.conf) cp -p "$f" /etc/nginx/snippets/ ;;
            *) cp -p "$f" /etc/nginx/conf.d/ ;;
        esac
    done
    exit 1
}

install -m 755 "$HERE/stemic-domains-sync" /usr/local/sbin/stemic-domains-sync
install -d -m 755 /var/lib/stemic
install -d -m 755 -o "$OWNER" "$BENCH/config"
for unit in stemic-domains.path stemic-domains.service; do
    sed "s|@BENCH@|$BENCH|g" "$HERE/systemd/$unit" > "/etc/systemd/system/$unit"
done
install -m 644 "$HERE/nginx/stemic-site.conf" /etc/nginx/snippets/stemic-site.conf
STEMIC_NO_RELOAD=1 /usr/local/sbin/stemic-domains-sync "$BENCH" || restore   # writes the $stemic_site map first
install -m 644 "$HERE/nginx/stemic.conf" /etc/nginx/conf.d/stemic.conf
nginx -t || restore
systemctl reload nginx
systemctl daemon-reload
systemctl enable --now stemic-domains.path
echo "Done. Previous nginx files: $backup. Status: /var/lib/stemic/domains-status.json"
