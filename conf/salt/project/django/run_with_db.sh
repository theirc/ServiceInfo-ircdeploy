# Shell script to set up necessary environment variables and run a PostgreSQL command
export PGHOST="{{ pillar['env']['DB_HOST'] }}"
export PGUSER="{{ pillar['project_name'] }}_{{ pillar['environment'] }}"
export PGPASSWORD="{{ pillar['secrets']['DB_PASSWORD'] }}"
exec "$@"
