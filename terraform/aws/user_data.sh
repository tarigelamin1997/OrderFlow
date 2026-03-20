#!/bin/bash
set -euo pipefail

apt-get update -y
apt-get install -y docker.io git curl wget unzip python3-pip

# Docker post-install
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# kind
curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x /usr/local/bin/kind

# helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# terraform 1.7.5 (matches versions.yaml)
wget https://releases.hashicorp.com/terraform/1.7.5/terraform_1.7.5_linux_amd64.zip
unzip terraform_1.7.5_linux_amd64.zip
mv terraform /usr/local/bin/
rm terraform_1.7.5_linux_amd64.zip

# ggshield — pre-commit secret scanning (second line of defence after GitGuardian)
pip3 install ggshield
ggshield install -m global

echo "Bootstrap complete" > /tmp/bootstrap.done
