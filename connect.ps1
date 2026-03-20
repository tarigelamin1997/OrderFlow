# connect.ps1 — Auto-update security group with current IP and connect via SSH
# Usage: .\connect.ps1

$SG_ID = "sg-0e6fb5424f8ba0c6d"
$REGION = "eu-north-1"
$PROFILE = "orderflow"

# Get instance IP from Terraform output (Elastic IP)
$INSTANCE_IP = (cd terraform/aws && terraform output -raw public_ip)
if (-not $INSTANCE_IP) {
    Write-Host "ERROR: Could not get public_ip from Terraform output" -ForegroundColor Red
    exit 1
}
Write-Host "Instance IP (EIP): $INSTANCE_IP" -ForegroundColor Cyan

# Get current public IP
$CURRENT_IP = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
$CIDR = "$CURRENT_IP/32"

Write-Host "Current IP: $CURRENT_IP" -ForegroundColor Cyan

# Add current IP to security group (ignore error if rule already exists)
Write-Host "Updating security group $SG_ID..." -ForegroundColor Yellow
aws ec2 authorize-security-group-ingress `
    --group-id $SG_ID `
    --protocol tcp `
    --port 22 `
    --cidr $CIDR `
    --profile $PROFILE `
    --region $REGION 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "Added $CIDR to security group" -ForegroundColor Green
} else {
    Write-Host "Rule for $CIDR already exists (or error) - continuing" -ForegroundColor Yellow
}

# Also set the TF_VAR for consistency
$env:TF_VAR_allowed_ssh_cidr = $CIDR

# Update SSH config HostName dynamically
$SSH_CONFIG = "$env:USERPROFILE\.ssh\config"
if (Test-Path $SSH_CONFIG) {
    $content = Get-Content $SSH_CONFIG -Raw
    $content = $content -replace '(?m)(Host orderflow\s*\n\s*HostName\s+)\S+', "`${1}$INSTANCE_IP"
    Set-Content $SSH_CONFIG $content -NoNewline
    Write-Host "Updated SSH config HostName to $INSTANCE_IP" -ForegroundColor Green
}

# Connect
Write-Host "Connecting to orderflow..." -ForegroundColor Cyan
ssh orderflow
