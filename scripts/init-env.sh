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
# 请在部署环境中设置以下环境变量，或直接在此文件中填写
OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID:-}
OAUTH_CLIENT_SECRET=${OAUTH_CLIENT_SECRET:-}

# SMTP 邮件配置（用于发送邮箱验证码，不配置则隐藏邮箱登录）
# 请在部署环境中设置以下环境变量，或直接在此文件中填写
SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-587}
SMTP_USER=${SMTP_USER:-}
SMTP_PASSWORD=${SMTP_PASSWORD:-}
SMTP_FROM=${SMTP_FROM:-}

# 默认公开自选基金代码（未登录用户可见）
DEFAULT_PUBLIC_FUNDS=${DEFAULT_PUBLIC_FUNDS:-020111,020112,020501,016531}
EOF

    echo "✅ .env 文件已生成，JWT_SECRET_KEY 已自动设置"
else
    echo "✅ .env 配置文件已存在"
fi
