import random
import time
import logging

import requests
from flask import request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, get_db
from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET

logger = logging.getLogger(__name__)

_verification_codes = {}

CODE_EXPIRE_SECONDS = 300
CODE_RATE_LIMIT_SECONDS = 60


def register_auth_routes(app):
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username:
            return jsonify({'error': '用户名不能为空'}), 400
        if not password:
            return jsonify({'error': '密码不能为空'}), 400
        if len(password) < 6:
            return jsonify({'error': '密码长度不能少于6位'}), 400

        db = next(get_db())
        try:
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                return jsonify({'error': '该用户名已被注册'}), 400

            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                nickname=username,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # 为新用户创建默认平台
            default_platform = Platform(
                name='默认',
                user_id=user.id,
                order_num=0
            )
            db.add(default_platform)
            db.commit()

            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            return jsonify({
                'token': access_token,
                'refresh_token': refresh_token,
                'user': _user_to_dict(user),
            }), 201
        except Exception as e:
            db.rollback()
            logger.error(f"注册失败: {e}")
            return jsonify({'error': '注册失败，请稍后重试'}), 500
        finally:
            db.close()

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'error': '请输入用户名和密码'}), 400

        db = next(get_db())
        try:
            user = db.query(User).filter(User.username == username).first()

            if not user or not user.password_hash:
                return jsonify({'error': '用户名或密码错误'}), 401

            if not check_password_hash(user.password_hash, password):
                return jsonify({'error': '用户名或密码错误'}), 401

            if not user.is_active:
                return jsonify({'error': '账号已被禁用'}), 403

            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            return jsonify({
                'token': access_token,
                'refresh_token': refresh_token,
                'user': _user_to_dict(user),
            })
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return jsonify({'error': '登录失败，请稍后重试'}), 500
        finally:
            db.close()

    @app.route('/api/auth/email/send-code', methods=['POST'])
    def send_email_code():
        data = request.get_json()
        email = data.get('email', '').strip()

        if not email:
            return jsonify({'error': '邮箱不能为空'}), 400

        now = time.time()
        cached = _verification_codes.get(email)
        if cached and now - cached['sent_at'] < CODE_RATE_LIMIT_SECONDS:
            remaining = int(CODE_RATE_LIMIT_SECONDS - (now - cached['sent_at']))
            return jsonify({'error': f'请{remaining}秒后再试'}), 429

        code = f"{random.randint(0, 999999):06d}"

        _verification_codes[email] = {
            'code': code,
            'sent_at': now,
            'verified': False,
        }

        try:
            _send_email(email, code)
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return jsonify({'error': '验证码发送失败，请稍后重试'}), 500

        return jsonify({'message': '验证码已发送'})

    @app.route('/api/auth/email/login', methods=['POST'])
    def email_login():
        data = request.get_json()
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()

        if not email or not code:
            return jsonify({'error': '邮箱和验证码不能为空'}), 400

        cached = _verification_codes.get(email)
        if not cached:
            return jsonify({'error': '请先发送验证码'}), 400

        now = time.time()
        if now - cached['sent_at'] > CODE_EXPIRE_SECONDS:
            del _verification_codes[email]
            return jsonify({'error': '验证码已过期，请重新发送'}), 400

        if cached['code'] != code:
            return jsonify({'error': '验证码错误'}), 401

        del _verification_codes[email]

        db = next(get_db())
        try:
            user = db.query(User).filter(User.email == email).first()

            if not user:
                username = email.split('@')[0]
                existing = db.query(User).filter(User.username == username).first()
                if existing:
                    username = f"{username}_{int(now)}"

                user = User(
                    email=email,
                    username=username,
                    nickname=username,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                # 为新用户创建默认平台
                default_platform = Platform(
                    name='默认',
                    user_id=user.id,
                    order_num=0
                )
                db.add(default_platform)
                db.commit()

            if not user.is_active:
                return jsonify({'error': '账号已被禁用'}), 403

            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            return jsonify({
                'token': access_token,
                'refresh_token': refresh_token,
                'user': _user_to_dict(user),
            })
        except Exception as e:
            db.rollback()
            logger.error(f"邮箱登录失败: {e}")
            return jsonify({'error': '登录失败，请稍后重试'}), 500
        finally:
            db.close()

    @app.route('/api/auth/github', methods=['POST'])
    def github_auth():
        data = request.get_json()
        code = data.get('code', '')

        if not code:
            return jsonify({'error': '缺少授权码'}), 400

        if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
            return jsonify({'error': 'GitHub登录未配置'}), 500

        try:
            token_response = requests.post(
                'https://github.com/login/oauth/access_token',
                json={
                    'client_id': OAUTH_CLIENT_ID,
                    'client_secret': OAUTH_CLIENT_SECRET,
                    'code': code,
                },
                headers={'Accept': 'application/json'},
                timeout=10,
            )
            token_data = token_response.json()

            if 'access_token' not in token_data:
                return jsonify({'error': 'GitHub授权失败'}), 400

            github_token = token_data['access_token']

            user_response = requests.get(
                'https://api.github.com/user',
                headers={
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/json',
                },
                timeout=10,
            )
            github_user = user_response.json()

            github_id = str(github_user.get('id', ''))
            if not github_id:
                return jsonify({'error': '获取GitHub用户信息失败'}), 400

            db = next(get_db())
            try:
                user = db.query(User).filter(User.github_id == github_id).first()

                if not user:
                    github_username = github_user.get('login', '')
                    github_email = github_user.get('email', '')

                    if github_email:
                        existing_by_email = db.query(User).filter(User.email == github_email).first()
                        if existing_by_email:
                            github_email = None

                    username = github_username or f"github_{github_id}"
                    existing = db.query(User).filter(User.username == username).first()
                    if existing:
                        username = f"{username}_{github_id}"

                    user = User(
                        github_id=github_id,
                        github_username=github_username,
                        github_avatar=github_user.get('avatar_url', ''),
                        email=github_email or None,
                        username=username,
                        nickname=github_user.get('name') or github_username,
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)

                    default_platform = Platform(
                        name='默认',
                        user_id=user.id,
                        order_num=0
                    )
                    db.add(default_platform)
                    db.commit()
                    db.refresh(user)

                if not user.is_active:
                    return jsonify({'error': '账号已被禁用'}), 403

                access_token = create_access_token(identity=str(user.id))
                refresh_token = create_refresh_token(identity=str(user.id))
                return jsonify({
                    'token': access_token,
                    'refresh_token': refresh_token,
                    'user': _user_to_dict(user),
                })
            except Exception as e:
                db.rollback()
                logger.error(f"GitHub登录处理失败: {e}")
                return jsonify({'error': 'GitHub登录失败，请稍后重试'}), 500
            finally:
                db.close()

        except requests.RequestException as e:
            logger.error(f"GitHub OAuth请求失败: {e}")
            return jsonify({'error': 'GitHub授权服务不可用'}), 503

    @app.route('/api/auth/refresh', methods=['POST'])
    @jwt_required(refresh=True)
    def refresh_token():
        user_id = get_jwt_identity()
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if not user or not user.is_active:
                return jsonify({'error': '用户不存在或已被禁用'}), 401

            access_token = create_access_token(identity=str(user.id))
            refresh_token_new = create_refresh_token(identity=str(user.id))
            return jsonify({
                'token': access_token,
                'refresh_token': refresh_token_new,
                'user': _user_to_dict(user),
            })
        finally:
            db.close()

    @app.route('/api/auth/me', methods=['GET'])
    @jwt_required(optional=True)
    def get_current_user():
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'user': None})

        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if not user:
                return jsonify({'user': None})

            return jsonify({'user': _user_to_dict(user)})
        finally:
            db.close()

    @app.route('/api/auth/github/config', methods=['GET'])
    def github_config():
        return jsonify({
            'client_id': OAUTH_CLIENT_ID,
            'enabled': bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET),
        })

    @app.route('/api/auth/email/config', methods=['GET'])
    def email_config():
        from config import SMTP_HOST, SMTP_USER, SMTP_PASSWORD
        return jsonify({
            'enabled': bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD),
        })


def get_current_user_id():
    from flask_jwt_extended import get_jwt_identity
    identity = get_jwt_identity()
    if identity:
        return int(identity)
    return None


def _send_email(to_email, code):
    import smtplib
    from email.mime.text import MIMEText
    from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

    subject = "叽咕宝 - 邮箱验证码"
    body = f"您的验证码是：{code}\n\n验证码5分钟内有效，请勿泄露给他人。"

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM or SMTP_USER
    msg['To'] = to_email

    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM or SMTP_USER, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM or SMTP_USER, [to_email], msg.as_string())


def _user_to_dict(user):
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'nickname': user.nickname,
        'github_id': user.github_id,
        'github_username': user.github_username,
        'github_avatar': user.github_avatar,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat() if user.created_at else None,
    }
