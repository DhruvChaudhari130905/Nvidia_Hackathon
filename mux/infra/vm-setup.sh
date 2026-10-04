#!/usr/bin/env bash
# VM Setup Script for MUX Server
# Run as root: sudo bash vm-setup.sh

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
APP_NAME="mux"
APP_USER="mux"
APP_DIR="/opt/${APP_NAME}"
SERVER_DIR="${APP_DIR}/mux/server"   # the Python backend inside the repo
REPO_URL="${REPO_URL:-https://github.com/your-org/mux.git}"  # Set via env or change default
BRANCH="${BRANCH:-main}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
DOMAIN="${DOMAIN:-api.example.com}"  # Set via env or change default
EMAIL="${EMAIL:-admin@example.com}"  # Set via env or change default

# Database
POSTGRES_VERSION="16"
DB_NAME="mux"
DB_USER="mux"
# Hex only: base64 can contain '/' and '+', which break the DATABASE_URL
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 24)}"

# GitHub OAuth (optional)
GITHUB_CLIENT_ID="${GITHUB_CLIENT_ID:-}"
GITHUB_CLIENT_SECRET="${GITHUB_CLIENT_SECRET:-}"
GITHUB_REDIRECT_URI="https://${DOMAIN}/api/export/github/callback"

# Encryption key for GitHub tokens (Fernet needs 32 bytes, URL-safe base64)
GITHUB_TOKEN_ENCRYPTION_KEY="${GITHUB_TOKEN_ENCRYPTION_KEY:-$(openssl rand -base64 32 | tr '+/' '-_')}"

# Supabase
SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET:-}"
SUPABASE_URL="${SUPABASE_URL:-}"
SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}"

# Token Factory (Nebius)
TOKEN_FACTORY_API_KEY="${TOKEN_FACTORY_API_KEY:-}"
TOKEN_FACTORY_BASE_URL="${TOKEN_FACTORY_BASE_URL:-}"
MODEL_LIGHTNING="${MODEL_LIGHTNING:-}"
MODEL_SUPER="${MODEL_SUPER:-}"
MODEL_ULTRA="${MODEL_ULTRA:-}"

# Tavily
TAVILY_API_KEY="${TAVILY_API_KEY:-}"

# =============================================================================
# Helper functions
# =============================================================================
log() {
    echo -e "\033[1;32m[$(date '+%H:%M:%S')]\033[0m $*"
}

warn() {
    echo -e "\033[1;33m[WARN]\033[0m $*" >&2
}

error() {
    echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
    exit 1
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
    fi
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        error "Cannot detect OS"
    fi
    log "Detected OS: $OS $VERSION"
}

# =============================================================================
# Main setup
# =============================================================================
main() {
    check_root
    detect_os

    log "Starting MUX server setup..."

    # 1. System packages
    install_system_packages

    # 2. Create app user
    create_app_user

    # 3. Install Python
    install_python

    # 4. Install and configure PostgreSQL
    setup_postgresql

    # 5. Deploy application (must come before Caddy: the Caddyfile is in the repo)
    deploy_application

    # 6. Install and configure Caddy
    setup_caddy

    # 7. Configure systemd service
    setup_systemd

    # 8. Configure firewall
    setup_firewall

    # 9. Final steps
    final_steps

    log "Setup complete!"
    print_summary
}

# =============================================================================
# Installation functions
# =============================================================================
install_system_packages() {
    log "Installing system packages..."

    case $OS in
        ubuntu|debian)
            apt-get update
            apt-get install -y \
                curl wget git unzip \
                build-essential libssl-dev libffi-dev \
                python3-venv python3-dev \
                ca-certificates gnupg lsb-release \
                ufw fail2ban \
                htop vim tmux
            ;;
        centos|rhel|fedora|rocky|almalinux)
            dnf update -y
            dnf install -y \
                curl wget git unzip \
                gcc openssl-devel libffi-devel \
                python3-devel \
                postgresql${POSTGRES_VERSION} \
                firewalld fail2ban \
                htop vim tmux
            ;;
        *)
            warn "Unsupported OS: $OS - skipping package install"
            ;;
    esac
}

create_app_user() {
    log "Creating app user: $APP_USER"
    if ! id "$APP_USER" &>/dev/null; then
        # -M: don't populate the home dir; git clone needs $APP_DIR to be empty
        useradd -r -M -d "$APP_DIR" -s /bin/bash "$APP_USER"
        usermod -aG docker "$APP_USER" 2>/dev/null || true
    fi
    mkdir -p "$APP_DIR"
    chown "$APP_USER:$APP_USER" "$APP_DIR"
}

install_python() {
    log "Installing Python $PYTHON_VERSION..."

    case $OS in
        ubuntu|debian)
            # Use deadsnakes PPA for newer Python
            apt-get install -y software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update
            apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev
            update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1
            ;;
        centos|rhel|fedora|rocky|almalinux)
            dnf install -y python${PYTHON_VERSION//./} python${PYTHON_VERSION//./}-devel
            alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1
            ;;
    esac

    # Verify
    python3 --version
    python3 -m pip install --upgrade pip setuptools wheel
}

setup_postgresql() {
    log "Setting up PostgreSQL $POSTGRES_VERSION..."

    case $OS in
        ubuntu|debian)
            # Add PostgreSQL APT repository
            apt-get install -y postgresql-common
            /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
            apt-get update
            apt-get install -y postgresql-${POSTGRES_VERSION} postgresql-contrib-${POSTGRES_VERSION}
            ;;
        centos|rhel|fedora|rocky|almalinux)
            dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm
            dnf -qy module disable postgresql
            dnf install -y postgresql${POSTGRES_VERSION}-server postgresql${POSTGRES_VERSION}-contrib
            /usr/pgsql-${POSTGRES_VERSION}/bin/postgresql-${POSTGRES_VERSION}-setup initdb
            systemctl enable --now postgresql-${POSTGRES_VERSION}
            ;;
    esac

    # Configure PostgreSQL
    PG_CONF="/etc/postgresql/${POSTGRES_VERSION}/main/postgresql.conf"
    PG_HBA="/etc/postgresql/${POSTGRES_VERSION}/main/pg_hba.conf"

    if [[ -f "$PG_CONF" ]]; then
        # Tune for production
        sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
        sed -i "s/^#max_connections = 100/max_connections = 200/" "$PG_CONF"
        sed -i "s/^#shared_buffers = 128MB/shared_buffers = 256MB/" "$PG_CONF"
        sed -i "s/^#effective_cache_size = 4GB/effective_cache_size = 1GB/" "$PG_CONF"
        sed -i "s/^#work_mem = 4MB/work_mem = 16MB/" "$PG_CONF"
        sed -i "s/^#maintenance_work_mem = 64MB/maintenance_work_mem = 128MB/" "$PG_CONF"

        systemctl restart postgresql
    fi

    # Create database and user (idempotent so the script can be re-run)
    log "Creating database and user..."
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD' CREATEDB;"
    else
        sudo -u postgres psql -c "ALTER USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';"
    fi
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    fi

    log "Database created: $DB_NAME"
}

setup_caddy() {
    log "Installing and configuring Caddy..."

    case $OS in
        ubuntu|debian)
            apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
            apt-get update
            apt-get install -y caddy
            ;;
        centos|rhel|fedora|rocky|almalinux)
            dnf install -y 'dnf-command(copr)'
            dnf copr enable -y @caddy/caddy
            dnf install -y caddy
            ;;
    esac

    # Copy Caddyfile
    mkdir -p /etc/caddy
    cp "${APP_DIR}/mux/infra/Caddyfile" /etc/caddy/Caddyfile

    # Replace domain placeholder
    sed -i "s/api.example.com/${DOMAIN}/g" /etc/caddy/Caddyfile
    sed -i "s/admin@example.com/${EMAIL}/g" /etc/caddy/Caddyfile

    # Create log directory
    mkdir -p /var/log/caddy
    chown caddy:caddy /var/log/caddy

    # Enable and start
    systemctl enable --now caddy

    log "Caddy configured for ${DOMAIN}"
}

deploy_application() {
    log "Deploying application..."

    # Clone or update repository
    git config --global --add safe.directory "$APP_DIR"
    if [[ -d "$APP_DIR/.git" ]]; then
        log "Updating existing repository..."
        cd "$APP_DIR"
        sudo -u "$APP_USER" git fetch origin
        sudo -u "$APP_USER" git checkout "$BRANCH"
        sudo -u "$APP_USER" git pull origin "$BRANCH"
    else
        log "Cloning repository..."
        sudo -u "$APP_USER" git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
    fi

    # Create virtual environment
    log "Creating Python virtual environment..."
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel

    # Install dependencies
    log "Installing Python dependencies..."
    if [[ -f "$SERVER_DIR/pyproject.toml" ]]; then
        sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -e "$SERVER_DIR"
    else
        error "No pyproject.toml found in $SERVER_DIR"
    fi

    # Create .env file
    log "Creating environment file..."
    cat > "$SERVER_DIR/.env" <<EOF
# Database
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}

# Server
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Supabase
SUPABASE_JWT_SECRET=${SUPABASE_JWT_SECRET}
SUPABASE_URL=${SUPABASE_URL}
SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}

# GitHub OAuth
GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
GITHUB_REDIRECT_URI=${GITHUB_REDIRECT_URI}
GITHUB_TOKEN_ENCRYPTION_KEY=${GITHUB_TOKEN_ENCRYPTION_KEY}

# Token Factory (Nebius)
TOKEN_FACTORY_API_KEY=${TOKEN_FACTORY_API_KEY}
TOKEN_FACTORY_BASE_URL=${TOKEN_FACTORY_BASE_URL}
MODEL_LIGHTNING=${MODEL_LIGHTNING}
MODEL_SUPER=${MODEL_SUPER}
MODEL_ULTRA=${MODEL_ULTRA}

# Tavily
TAVILY_API_KEY=${TAVILY_API_KEY}
EOF

    chown "$APP_USER:$APP_USER" "$SERVER_DIR/.env"
    chmod 600 "$SERVER_DIR/.env"

    # No migrations yet: the server does not create or use database tables
    # (event logs are in memory). Add an Alembic step here once persistence lands.

    log "Application deployed"
}

setup_systemd() {
    log "Configuring systemd service..."

    cat > /etc/systemd/system/${APP_NAME}.service <<EOF
[Unit]
Description=MUX API Server
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${SERVER_DIR}
EnvironmentFile=${SERVER_DIR}/.env
# Single worker: rooms, event logs and WebSocket connections live in process
# memory, so multiple workers would each see a different set of rooms.
ExecStart=${APP_DIR}/venv/bin/uvicorn mux.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=5
TimeoutStartSec=30
TimeoutStopSec=30

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${APP_DIR}
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

# Resource limits
LimitNOFILE=65536
LimitNPROC=32768

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now "${APP_NAME}"

    log "Systemd service created and started"
}

setup_firewall() {
    log "Configuring firewall..."

    case $OS in
        ubuntu|debian)
            ufw --force enable
            ufw default deny incoming
            ufw default allow outgoing
            ufw allow ssh
            ufw allow 80/tcp
            ufw allow 443/tcp
            ufw reload
            ;;
        centos|rhel|fedora|rocky|almalinux)
            systemctl enable --now firewalld
            firewall-cmd --permanent --add-service=ssh
            firewall-cmd --permanent --add-service=http
            firewall-cmd --permanent --add-service=https
            firewall-cmd --reload
            ;;
    esac

    log "Firewall configured"
}

final_steps() {
    log "Running final steps..."

    # Wait for services to be ready
    sleep 5

    # Check service status
    systemctl is-active --quiet "${APP_NAME}" && log "✓ ${APP_NAME} service is running" || warn "✗ ${APP_NAME} service failed"
    systemctl is-active --quiet caddy && log "✓ Caddy is running" || warn "✗ Caddy failed"
    systemctl is-active --quiet postgresql && log "✓ PostgreSQL is running" || warn "✗ PostgreSQL failed"

    # Test health endpoint
    if curl -sf "http://localhost:8000/health" >/dev/null; then
        log "✓ Application health check passed"
    else
        warn "✗ Application health check failed"
    fi

    # Test Caddy
    if curl -sf "https://${DOMAIN}/health" >/dev/null 2>&1; then
        log "✓ HTTPS endpoint accessible"
    else
        warn "✗ HTTPS endpoint not yet accessible (DNS may need time to propagate)"
    fi
}

print_summary() {
    cat <<EOF

================================================================================
MUX Server Setup Complete
================================================================================

Application:     ${APP_NAME}
Directory:       ${APP_DIR}
User:            ${APP_USER}
Domain:          ${DOMAIN}
Database:        postgresql://${DB_USER}:****@localhost:5432/${DB_NAME}

Services:
  - ${APP_NAME}.service  (FastAPI on port 8000)
  - caddy.service        (Reverse proxy + HTTPS on 80/443)
  - postgresql           (Database)

Environment file: ${SERVER_DIR}/.env
  (Contains all secrets - keep secure!)

Logs:
  - Application: journalctl -u ${APP_NAME} -f
  - Caddy:       journalctl -u caddy -f
  - Caddy access: /var/log/caddy/api-access.log
  - PostgreSQL:  /var/log/postgresql/postgresql-${POSTGRES_VERSION}-main.log

Useful commands:
  - Restart app:     systemctl restart ${APP_NAME}
  - View app logs:   journalctl -u ${APP_NAME} -f
  - Update app:      cd ${APP_DIR} && sudo -u ${APP_USER} git pull && systemctl restart ${APP_NAME}
  - Backup DB:       pg_dump -U ${DB_USER} ${DB_NAME} > backup_\$(date +%F).sql

Next steps:
  1. Point DNS A record for ${DOMAIN} to this server's IP
  2. Wait for Let's Encrypt certificate issuance (automatic via Caddy)
  3. Test API at https://${DOMAIN}/docs
  4. Configure GitHub OAuth in GitHub Developer Settings with redirect URI:
     ${GITHUB_REDIRECT_URI}

================================================================================
EOF
}

# Run main
main "$@"