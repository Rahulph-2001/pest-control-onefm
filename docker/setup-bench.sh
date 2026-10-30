#!/usr/bin/env bash
# Builds the bench inside the `frappe` container and installs every app on a dev site.
# Run:  docker compose -f docker/docker-compose.yml exec frappe bash /workspace/pest_control/docker/setup-bench.sh
set -euo pipefail

SITE=${SITE:-pest.localhost}
BENCH_DIR=/home/frappe/bench/frappe-bench
APPS_FILE=/workspace/pest_control/docker/apps.txt

PYTHON="$HOME/.pyenv/versions/3.12.16/bin/python3"
CLI_DIR=/home/frappe/bench/cli

# Frappe v15 needs Python < 3.13; the image's default bench CLI runs on 3.14,
# so install bench into its own 3.12 virtualenv.
if [ ! -x "$CLI_DIR/bin/bench" ]; then
	"$PYTHON" -m venv "$CLI_DIR"
	"$CLI_DIR/bin/pip" install -q frappe-bench
fi
export PATH="$CLI_DIR/bin:$PATH"
source "$HOME/.nvm/nvm.sh"
nvm use 22 >/dev/null

if [ ! -d "$BENCH_DIR" ]; then
	cd /home/frappe/bench
	bench init --skip-redis-config-generation --frappe-branch version-15 --python "$PYTHON" frappe-bench
fi
cd "$BENCH_DIR"

bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
bench set-config -gp developer_mode 1

# apps.txt lines: <app_name> <git_url> <branch>
while read -r app url branch; do
	[[ -z "$app" || "$app" == \#* ]] && continue
	if [ ! -d "apps/$app" ]; then
		bench get-app --branch "$branch" "$url" --skip-assets
	fi
done < "$APPS_FILE"

# The extension app is mounted from the host so edits are live.
if [ ! -e apps/pest_control ]; then
	ln -s /workspace/pest_control apps/pest_control
	./env/bin/pip install -e apps/pest_control
	grep -qx pest_control sites/apps.txt || echo pest_control >> sites/apps.txt
fi

if [ ! -d "sites/$SITE" ]; then
	bench new-site "$SITE" --db-root-password 123 --admin-password admin --mariadb-user-host-login-scope='%'
fi

while read -r app url branch; do
	[[ -z "$app" || "$app" == \#* ]] && continue
	bench --site "$SITE" list-apps | grep -q "^$app" || bench --site "$SITE" install-app "$app"
done < "$APPS_FILE"
bench --site "$SITE" list-apps | grep -q "^pest_control" || bench --site "$SITE" install-app pest_control

bench --site "$SITE" set-config allow_tests true
bench --site "$SITE" migrate
bench use "$SITE"

# Record the exact commits used.
for d in apps/*; do
	[ -d "$d/.git" ] || [ -L "$d" ] || continue
	echo "$(basename "$d") $(git -C "$d" rev-parse HEAD) $(git -C "$d" rev-parse --abbrev-ref HEAD)"
done > /workspace/pest_control/docs/stack-lock.txt
echo "Done. Start with: bench start  (then open http://localhost:8000, Administrator / admin)"
