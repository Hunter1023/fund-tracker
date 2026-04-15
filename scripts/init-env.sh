#!/bin/bash

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "首次部署，正在生成 .env 配置文件..."

    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 | tr -d '/+=' | head -c 43)

    cat > .env << EOF
# 基金追踪器 环境配置（自动生成于 $(date '+%Y-%m-%d %H:%M:%S')）

# JWT 密钥（已自动生成，请勿随意修改，否则已登录用户Token会失效）
JWT_SECRET_KEY=${JWT_SECRET}

# GitHub OAuth 配置
GITHUB_CLIENT_ID=Ov23liKrV4KZxgYCqm3F
GITHUB_CLIENT_SECRET=00ed0318fe29e5975efa227047c5a0ada7af2dee

# SMTP 邮件配置（用于发送邮箱验证码，不配置则隐藏邮箱登录）
SMTP_HOST=
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# 默认公开自选基金代码（未登录用户可见）
DEFAULT_PUBLIC_FUNDS=000001,000011,000051,110011,161725
EOF

    echo "✅ .env 文件已生成，JWT_SECRET_KEY 已自动设置"
else
    echo "✅ .env 配置文件已存在"
fi
