#!/bin/bash

# CaseGuard Staging Droplet Setup Script
# Run this script as root on the DigitalOcean droplet

set -e

echo "🚀 Setting up CaseGuard staging environment on DigitalOcean droplet..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install required packages
echo "📦 Installing required packages..."
apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    ufw \
    fail2ban \
    unzip \
    git

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

    # Add Docker repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker
    apt update
    apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose (standalone)
echo "🐳 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_VERSION="v2.24.5"
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "✅ Docker Compose already installed"
fi

# Install Certbot for SSL
echo "🔒 Installing Certbot..."
apt install -y certbot

# Create deploy user
echo "👤 Creating deploy user..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash deploy
    usermod -aG docker deploy
    usermod -aG sudo deploy

    # Set up sudo without password for deploy user (for deployment automation)
    echo "deploy ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/deploy
else
    echo "✅ Deploy user already exists"
fi

# Create deployment directory
echo "📁 Creating deployment directories..."
mkdir -p /opt/caseguard-staging
chown -R deploy:deploy /opt/caseguard-staging

# Create necessary directories for the application
mkdir -p /opt/caseguard-staging/{data,output,logs}
mkdir -p /var/log/caseguard-staging

# Set up SSH directory for deploy user
echo "🔑 Setting up SSH for deploy user..."
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Configure firewall
echo "🔥 Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# Allow SSH
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Allow application ports for staging
ufw allow 8001/tcp  # API staging port
ufw allow 4201/tcp  # Prefect staging port

# Enable firewall
ufw --force enable

# Configure fail2ban
echo "🛡️ Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/*error.log
maxretry = 5

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/*error.log
maxretry = 10
EOF

systemctl enable fail2ban
systemctl start fail2ban

# Set up log rotation
echo "📝 Setting up log rotation..."
cat > /etc/logrotate.d/caseguard-staging << EOF
/var/log/caseguard-staging/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 deploy deploy
    postrotate
        /bin/kill -USR1 \$(cat /var/run/nginx.pid 2>/dev/null) 2>/dev/null || true
    endscript
}
EOF

# Create deployment script
echo "📄 Creating deployment script..."
cat > /opt/caseguard-staging/deploy.sh << 'EOF'
#!/bin/bash

# CaseGuard Staging Deployment Script

set -e

DEPLOY_DIR="/opt/caseguard-staging"
BACKUP_DIR="/opt/caseguard-staging/backups"
COMPOSE_FILE="docker-compose.staging.yml"

cd $DEPLOY_DIR

echo "🚀 Starting CaseGuard staging deployment..."

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup current environment if it exists
if [ -f .env ]; then
    cp .env $BACKUP_DIR/.env.$(date +%Y%m%d_%H%M%S)
fi

# Pull latest images
echo "📥 Pulling latest Docker images..."
docker compose -f $COMPOSE_FILE pull

# Create database backup before deployment
echo "💾 Creating database backup..."
if docker ps | grep -q caseguard-postgres-staging; then
    docker exec caseguard-postgres-staging pg_dump -U caseguard_user caseguard_v2_staging | gzip > $BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sql.gz
fi

# Deploy with zero downtime
echo "🔄 Deploying services..."
docker compose -f $COMPOSE_FILE up -d --remove-orphans

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Health check
echo "🏥 Running health checks..."
for i in {1..10}; do
    if curl -f http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ Health check passed!"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ Health check failed after 10 attempts!"
        echo "📋 Recent logs:"
        docker compose -f $COMPOSE_FILE logs --tail=20
        exit 1
    fi
    echo "⏳ Health check attempt $i/10..."
    sleep 10
done

# Cleanup old images
echo "🧹 Cleaning up old Docker images..."
docker image prune -f

echo "✅ Deployment completed successfully!"
EOF

chmod +x /opt/caseguard-staging/deploy.sh
chown deploy:deploy /opt/caseguard-staging/deploy.sh

# Create SSL certificate script
echo "🔒 Creating SSL certificate setup script..."
cat > /opt/caseguard-staging/setup-ssl.sh << 'EOF'
#!/bin/bash

# SSL Certificate Setup for CaseGuard Staging

set -e

DOMAIN="caseguard-staging.vynta.ai"
EMAIL="admin@vynta.ai"  # Change this to your email

echo "🔒 Setting up SSL certificate for $DOMAIN..."

# Stop nginx if running
if docker ps | grep -q caseguard-nginx-staging; then
    echo "⏹️ Stopping nginx container..."
    docker stop caseguard-nginx-staging || true
fi

# Obtain SSL certificate
echo "📜 Obtaining SSL certificate..."
certbot certonly \
    --standalone \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --domains $DOMAIN

# Set up automatic renewal
echo "🔄 Setting up automatic SSL renewal..."
crontab -l 2>/dev/null | grep -v "certbot renew" | crontab -
(crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet --post-hook 'docker restart caseguard-nginx-staging'") | crontab -

echo "✅ SSL certificate setup completed!"
echo "🔗 Your staging site will be available at: https://$DOMAIN"
EOF

chmod +x /opt/caseguard-staging/setup-ssl.sh
chown deploy:deploy /opt/caseguard-staging/setup-ssl.sh

# Set ownership
chown -R deploy:deploy /opt/caseguard-staging

echo "✅ CaseGuard staging droplet setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Add the deploy user's SSH public key to GitHub Secrets"
echo "2. Configure DNS: Point caseguard-staging.vynta.ai to this droplet (178.62.78.12)"
echo "3. Run SSL setup: sudo /opt/caseguard-staging/setup-ssl.sh"
echo "4. Set up GitHub repository secrets"
echo "5. Push to develop branch to trigger deployment"
echo ""
echo "🔑 To add SSH key for GitHub Actions:"
echo "   - Generate SSH key: ssh-keygen -t rsa -b 4096 -C 'github-actions@caseguard'"
echo "   - Add public key to /home/deploy/.ssh/authorized_keys"
echo "   - Add private key to GitHub Secrets as STAGING_SSH_KEY"
echo ""
echo "🌐 Staging URL will be: https://caseguard-staging.vynta.ai"