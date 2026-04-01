#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Health Pose Assistant — Dev Environment Setup
# Works on macOS (Homebrew) and Ubuntu/Debian (apt)
# Usage: bash scripts/setup_dev.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$BACKEND_DIR/hpa_backend_env"
REQUIRED_NODE_MAJOR=22

DB_NAME="${HPA_DB_NAME:-health_pose_assistant}"
DB_USER="${HPA_DB_USER:-hva_user}"
DB_PASS="${HPA_DB_PASS:-hva_dev_pass123}"
ADMIN_EMAIL="${HPA_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASS="${HPA_ADMIN_PASS:-admin123}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ----------------------------------------------------------
# 1. Install PostgreSQL
# ----------------------------------------------------------
install_postgres() {
    if command -v psql &>/dev/null; then
        info "PostgreSQL already installed: $(psql --version)"
        return
    fi

    if [[ "$(uname)" == "Darwin" ]]; then
        info "Installing PostgreSQL 16 via Homebrew..."
        brew install postgresql@16
        brew services start postgresql@16
        # Ensure pg binaries are on PATH for this session
        export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
    else
        info "Installing PostgreSQL via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y postgresql postgresql-contrib
        sudo systemctl enable --now postgresql
    fi
    info "PostgreSQL installed."
}

# ----------------------------------------------------------
# 2. Create database & user
# ----------------------------------------------------------
setup_database() {
    # Make sure pg binaries are on PATH (macOS Homebrew)
    if [[ "$(uname)" == "Darwin" ]] && [[ -d "/opt/homebrew/opt/postgresql@16/bin" ]]; then
        export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
    fi

    if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        info "Database '$DB_NAME' already exists, skipping."
    else
        info "Creating database '$DB_NAME'..."
        if [[ "$(uname)" == "Darwin" ]]; then
            createdb "$DB_NAME"
        else
            sudo -u postgres createdb "$DB_NAME"
        fi
    fi

    info "Creating user '$DB_USER' (if not exists) and granting privileges..."
    if [[ "$(uname)" == "Darwin" ]]; then
        psql "$DB_NAME" -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$DB_USER') THEN CREATE USER $DB_USER WITH PASSWORD '$DB_PASS'; END IF; END \$\$;"
        psql "$DB_NAME" -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
        psql "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
    else
        sudo -u postgres psql "$DB_NAME" -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$DB_USER') THEN CREATE USER $DB_USER WITH PASSWORD '$DB_PASS'; END IF; END \$\$;"
        sudo -u postgres psql "$DB_NAME" -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
        sudo -u postgres psql "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
    fi
    info "Database setup done."
}

# ----------------------------------------------------------
# 3. Node.js environment
# ----------------------------------------------------------
setup_node() {
    if ! command -v node &>/dev/null; then
        warn "Node.js not found."
        if command -v nvm &>/dev/null || [[ -s "$HOME/.nvm/nvm.sh" ]]; then
            source "$HOME/.nvm/nvm.sh" 2>/dev/null || true
            info "Installing Node $REQUIRED_NODE_MAJOR via nvm..."
            nvm install "$REQUIRED_NODE_MAJOR"
            nvm use "$REQUIRED_NODE_MAJOR"
        else
            echo "Please install Node.js $REQUIRED_NODE_MAJOR+ or install nvm first:"
            echo "  https://github.com/nvm-sh/nvm#installing-and-updating"
            exit 1
        fi
    fi

    # Load nvm if available (ensures .nvmrc is respected)
    if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
        source "$HOME/.nvm/nvm.sh" 2>/dev/null || true
    fi

    local node_major
    node_major=$(node -v | sed 's/v\([0-9]*\).*/\1/')
    if (( node_major < REQUIRED_NODE_MAJOR )); then
        warn "Node.js v$node_major detected, need v$REQUIRED_NODE_MAJOR+."
        if command -v nvm &>/dev/null; then
            info "Switching to Node $REQUIRED_NODE_MAJOR via nvm..."
            nvm install "$REQUIRED_NODE_MAJOR"
            nvm use "$REQUIRED_NODE_MAJOR"
        else
            echo "Please upgrade Node.js to v$REQUIRED_NODE_MAJOR+ or install nvm."
            exit 1
        fi
    fi

    info "Node.js $(node -v) / npm $(npm -v) ready."
}

# ----------------------------------------------------------
# 4. Python venv & dependencies
# ----------------------------------------------------------
setup_venv() {
    if [[ ! -d "$VENV_DIR" ]]; then
        info "Creating Python venv at $VENV_DIR ..."
        python3.11 -m venv "$VENV_DIR"
    else
        info "Venv already exists at $VENV_DIR"
    fi

    info "Installing Python dependencies..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
    info "Dependencies installed."
}

# ----------------------------------------------------------
# 5. Create .env from example if missing
# ----------------------------------------------------------
setup_env() {
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        info "Creating .env from .env.example..."
        sed \
            -e "s|postgresql://hva_user:changeme@localhost/health_pose_assistant|postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME|" \
            -e "s|changeme-secret-key|$(openssl rand -hex 32)|" \
            "$BACKEND_DIR/.env.example" > "$BACKEND_DIR/.env"
        info ".env created."
    else
        warn ".env already exists, skipping."
    fi
}

# ----------------------------------------------------------
# 6. Run Alembic migrations
# ----------------------------------------------------------
run_migrations() {
    info "Running Alembic migrations..."
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/alembic" upgrade head
    info "Migrations complete."
}

# ----------------------------------------------------------
# 7. Seed admin user
# ----------------------------------------------------------
seed_admin() {
    info "Seeding admin user ($ADMIN_EMAIL)..."
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/seed_admin.py" \
        --email "$ADMIN_EMAIL" --password "$ADMIN_PASS"
    info "Admin user ready."
}

# ----------------------------------------------------------
# 8. Frontend dependencies
# ----------------------------------------------------------
setup_frontend() {
    info "Installing frontend dependencies..."
    cd "$FRONTEND_DIR"
    # Respect .nvmrc if nvm is available
    if command -v nvm &>/dev/null; then
        nvm use 2>/dev/null || true
    fi
    npm ci
    info "Frontend dependencies installed."
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
main() {
    info "===== Health Pose Assistant — Dev Setup ====="
    install_postgres
    setup_database
    setup_node
    setup_venv
    setup_env
    run_migrations
    seed_admin
    setup_frontend
    info "===== Setup complete! ====="
    echo ""
    echo "  Start the backend:"
    echo "    cd $BACKEND_DIR"
    echo "    source hpa_backend_env/bin/activate"
    echo "    uvicorn app.main:app --reload"
    echo ""
    echo "  Start the frontend:"
    echo "    cd $FRONTEND_DIR"
    echo "    nvm use   # auto-loads Node version from .nvmrc"
    echo "    npm run dev"
    echo ""
}

main "$@"
