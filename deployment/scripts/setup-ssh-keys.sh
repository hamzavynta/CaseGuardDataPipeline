#!/bin/bash

# SSH Key Setup Script for GitHub Actions Deployment
# Run this locally to generate and configure SSH keys

set -e

echo "🔑 Setting up SSH keys for GitHub Actions deployment..."

# Configuration
DROPLET_IP="178.62.78.12"
KEY_NAME="caseguard-staging-deploy"
KEY_PATH="$HOME/.ssh/$KEY_NAME"

# Generate SSH key pair if it doesn't exist
if [ ! -f "$KEY_PATH" ]; then
    echo "🔐 Generating SSH key pair..."
    ssh-keygen -t rsa -b 4096 -C "github-actions@caseguard-staging" -f "$KEY_PATH" -N ""
    echo "✅ SSH key pair generated at $KEY_PATH"
else
    echo "✅ SSH key pair already exists at $KEY_PATH"
fi

# Display public key
echo ""
echo "📋 Public key to add to droplet:"
echo "================================="
cat "$KEY_PATH.pub"
echo "================================="

# Display private key for GitHub Secrets
echo ""
echo "🔒 Private key for GitHub Secrets (STAGING_SSH_KEY):"
echo "====================================================="
cat "$KEY_PATH"
echo "====================================================="

# Add to SSH config for easy access
SSH_CONFIG="$HOME/.ssh/config"
if ! grep -q "Host caseguard-staging" "$SSH_CONFIG" 2>/dev/null; then
    echo ""
    echo "📝 Adding to SSH config..."
    cat >> "$SSH_CONFIG" << EOF

# CaseGuard Staging Droplet
Host caseguard-staging
    HostName $DROPLET_IP
    User deploy
    IdentityFile $KEY_PATH
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
    echo "✅ Added to SSH config"
fi

echo ""
echo "📋 Next steps:"
echo "1. Copy the public key above and add it to the droplet:"
echo "   ssh root@$DROPLET_IP"
echo "   mkdir -p /home/deploy/.ssh"
echo "   echo 'PUBLIC_KEY_HERE' >> /home/deploy/.ssh/authorized_keys"
echo "   chmod 600 /home/deploy/.ssh/authorized_keys"
echo "   chown deploy:deploy /home/deploy/.ssh/authorized_keys"
echo ""
echo "2. Test SSH access:"
echo "   ssh caseguard-staging"
echo ""
echo "3. Add to GitHub Secrets:"
echo "   - STAGING_HOST: $DROPLET_IP"
echo "   - STAGING_SSH_USER: deploy"
echo "   - STAGING_SSH_KEY: (private key content above)"
echo ""
echo "4. Set up DNS record:"
echo "   - Type: A"
echo "   - Name: caseguard-staging"
echo "   - Value: $DROPLET_IP"
echo "   - Domain: vynta.ai"