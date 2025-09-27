# CaseGuard Staging Deployment Guide

This guide walks you through setting up automated deployment to your DigitalOcean droplet for the CaseGuard data pipeline.

## 📋 Overview

- **Droplet IP**: 178.62.78.12
- **Staging URL**: <https://caseguard-staging.vynta.ai>
- **Branch**: `develop` (auto-deploy)
- **Container Registry**: GitHub Container Registry (ghcr.io)

## 🚀 Quick Setup

### Step 1: Configure DNS

Set up the subdomain to point to your droplet:

```
Type: A
Name: caseguard-staging
Value: 178.62.78.12
Domain: vynta.ai
TTL: 300 (5 minutes)
```

### Step 2: Run Droplet Setup

SSH into your droplet and run the setup script:

```bash
# SSH as root
ssh root@178.62.78.12

# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/hamzavynta/caseguard-datapipelines/main/deployment/scripts/setup-droplet.sh | bash

# This will:
# - Install Docker and Docker Compose
# - Create deploy user with proper permissions
# - Configure firewall and security
# - Set up deployment directories
# - Install SSL certificate tools
```

### Step 3: Generate SSH Keys

Run this locally to generate deployment keys:

```bash
# Make the script executable and run it
chmod +x deployment/scripts/setup-ssh-keys.sh
./deployment/scripts/setup-ssh-keys.sh
```

This script will:

- Generate SSH key pair for GitHub Actions
- Display the public key to add to the droplet
- Display the private key for GitHub Secrets
- Configure your local SSH config

### Step 4: Add SSH Key to Droplet

Copy the public key from the script output and add it to the droplet:

```bash
# SSH to droplet
ssh root@178.62.78.12

# Add the public key to deploy user
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDQkA/OhlB+F3RB4Ky1gdL2UkQeAQZo0dDLVytZX+RlsSKxpS6+S72cNimSPVquGTwEbsvByF463Bd4XSyz6P3kHQmZFCYYeiXE5anCELCGAd9HiR1Nt6os7rSyppLAfucIUMUJsiSiWtlcsG586uUw+FxenAOb5HQmMiZ6OHz+wB8OTwgiUOR+7J3byFOg9YrY981xQ2J3nbY96f4IOSsmriQSJRAKBS9Xeyu8k+zty6QX6TsFxj1tNsysm65RT6tuNiXbjsaw664rk+otJlslMcCls2SObyOWt5oD6r/PW4GQ2tchNP368Gj5wxOz57Q1aCDLCGVe41GaQAkShfpmNJ3DTMylr7NsUghKDEtKxFraUsFmy/mk+AT0a5ZehvBcyLomu+HZEpKpkN15Bw+9bcKVgrEzmWf2cQ3DHheSMf16ItLiReW/znnTaeCalGe6BZBRLWXUNUbDyBG+ROgT/wIWskgVXZN1p7ppygAnlFOESjPA4Unhy/Qce5u2NTeqtq4q9Me7sy2BcFZgdCtEqXhl+XGTFfQU1TDyAHXgZSQAvrwK7qIVDy4A4l9rzocSkNOsD9+oPfnjnWvfS/Jq9E0fB5GtoGtp9/8RlD1Twy6Rzf8wUvBhEx7JG9mN4tzDW+2rE27W/X/YXLyCSdu2pkig72X/dRodsEbdp3J/1w== github-actions@caseguard-staging
" >> /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
```

Test SSH access:

```bash
ssh deploy@178.62.78.12
```

## 🔧 GitHub Configuration

### GitHub Environments

1. Go to your repository → Settings → Environments
2. Create environment named `staging`
3. Add environment protection rules:
   - **Deployment branches**: Restrict to `develop` branch only
   - **Required reviewers**: Optional for staging

### GitHub Secrets

Add these secrets to your repository (Settings → Secrets and variables → Actions):

**Repository Secrets:**

```
STAGING_HOST=178.62.78.12
STAGING_SSH_USER=deploy
STAGING_SSH_KEY=[Private SSH key from setup-ssh-keys.sh output]
```

**Environment Secrets (staging environment):**

```
STAGING_ENV_FILE=[Complete .env file content - see example below]
```

### Example STAGING_ENV_FILE Content

Use `deployment/.env.staging.example` as a template and fill in real values:

```bash
# Copy the example and modify
cp deployment/.env.staging.example staging.env
# Edit staging.env with your actual credentials
# Then copy the entire content to GitHub Secrets as STAGING_ENV_FILE
```

**Key variables to update:**

- `OPENAI_API_KEY`: Your OpenAI API key
- `PINECONE_API_KEY`: Your Pinecone API key
- `PROCLAIM_USERNAME/PASSWORD`: Staging Proclaim credentials
- `SPACES_ACCESS_KEY/SECRET_KEY`: DigitalOcean Spaces credentials
- `SECRET_KEY/JWT_SECRET`: Generate secure random keys

## 🔒 SSL Certificate Setup

After DNS propagation (5-10 minutes), set up SSL:

```bash
# SSH to droplet as deploy user
ssh deploy@178.62.78.12

# Run SSL setup (will use Let's Encrypt)
sudo /opt/caseguard-staging/setup-ssl.sh
```

This will:

- Obtain SSL certificate for caseguard-staging.vynta.ai
- Set up automatic renewal
- Configure nginx for HTTPS

## 🎯 Deployment Process

### Automatic Deployment

1. Push changes to `develop` branch
2. GitHub Actions will automatically:
   - Build Docker images
   - Push to GitHub Container Registry
   - Deploy to staging droplet
   - Run health checks

### Manual Deployment

Trigger deployment manually:

1. Go to Actions tab in GitHub
2. Select "Deploy to Staging" workflow
3. Click "Run workflow" → Select `develop` branch

### Monitoring Deployment

- **GitHub Actions**: Monitor workflow progress
- **Application Logs**: `ssh deploy@178.62.78.12 && cd /opt/caseguard-staging && docker compose -f docker-compose.staging.yml logs -f`
- **Health Check**: <https://caseguard-staging.vynta.ai/health>
- **Prefect UI**: <https://caseguard-staging.vynta.ai/prefect/>

## 📊 Service Architecture

### Ports and Services

```
80/443    → Nginx (reverse proxy with SSL)
8001      → CaseGuard API (internal)
4201      → Prefect Server (internal, accessible via /prefect/)
5433      → PostgreSQL (internal)
6380      → Redis/Valkey (internal)
```

### Docker Services

- **caseguard-api-staging**: Main application
- **caseguard-prefect-worker-staging**: Background job processor
- **caseguard-postgres-staging**: Database
- **caseguard-valkey-staging**: Redis-compatible cache/queue
- **caseguard-prefect-server-staging**: Workflow orchestration
- **caseguard-nginx-staging**: Reverse proxy with SSL

## 🔍 Troubleshooting

### Common Issues

**1. DNS not propagating**

```bash
# Check DNS resolution
dig caseguard-staging.vynta.ai

# Should return: 178.62.78.12
```

**2. SSL certificate issues**

```bash
# Check certificate status
sudo certbot certificates

# Manually renew if needed
sudo certbot renew --dry-run
```

**3. Deployment failures**

```bash
# Check application logs
ssh deploy@178.62.78.12
cd /opt/caseguard-staging
docker compose -f docker-compose.staging.yml logs --tail=50

# Check service status
docker compose -f docker-compose.staging.yml ps
```

**4. Health check failures**

```bash
# Test health endpoint locally on droplet
curl http://localhost:8001/health

# Check nginx configuration
docker exec caseguard-nginx-staging nginx -t
```

### Log Locations

- **Application logs**: `/opt/caseguard-staging/logs/`
- **Nginx logs**: `/var/log/nginx/caseguard-staging-*.log`
- **System logs**: `/var/log/syslog`
- **Docker logs**: `docker compose -f docker-compose.staging.yml logs`

## 🔄 Maintenance

### Regular Tasks

1. **Monitor disk space**: `df -h`
2. **Check log sizes**: `du -sh /var/log/* /opt/caseguard-staging/logs/*`
3. **Update system**: `sudo apt update && sudo apt upgrade`
4. **Check SSL expiry**: `sudo certbot certificates`

### Backup Strategy

- **Database**: Automatic backup before each deployment
- **Configuration**: Environment files backed up
- **Logs**: Rotated daily, kept for 30 days

### Rolling Back

If deployment fails, the system automatically attempts rollback. Manual rollback:

```bash
ssh deploy@178.62.78.12
cd /opt/caseguard-staging

# View available backups
ls -la backups/

# Restore previous environment
cp backups/.env.YYYYMMDD_HHMMSS .env

# Restart services
docker compose -f docker-compose.staging.yml up -d
```

## 🎉 Success Criteria

After successful setup, you should have:

- ✅ <https://caseguard-staging.vynta.ai> responding with valid SSL
- ✅ Health check endpoint returning 200 OK
- ✅ Prefect UI accessible at /prefect/
- ✅ Automatic deployments on push to `develop`
- ✅ Proper SSL certificate with auto-renewal
- ✅ All services running and healthy

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review GitHub Actions logs for deployment failures
3. Check application logs on the droplet
4. Verify all secrets are correctly configured

**Next Steps**: Once staging is working, we can set up production deployment following a similar pattern but with `main` branch and production environment configuration.
