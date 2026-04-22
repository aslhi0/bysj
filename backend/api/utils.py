import requests
import json
import logging
from urllib.parse import urlparse
from django.core.mail import send_mail
from django.conf import settings
from .engine import validate_outbound_http_url

logger = logging.getLogger(__name__)

# 代码内置的公网群机器人域名：这些 host 的解析可视为受信任（大厂 DNS 不会被
# 本地 ISP/企业 DNS 劫持到 198.18/192.168），所以跳过 DNS 内网审查。自定义
# webhook 域名一律走 allowed_hosts=None 的完整 SSRF 检查。
_WEBHOOK_ALLOWED_HOSTS = {
    'oapi.dingtalk.com',
    'qyapi.weixin.qq.com',
    'open.feishu.cn',
    'hooks.slack.com',
}


class Notifier:
    @staticmethod
    def send_webhook(webhook_url, title, message, status='info'):
        if not webhook_url:
            return False
        url = str(webhook_url)
        try:
            host = (urlparse(url).hostname or '').lower()
            allowed = [host] if host in _WEBHOOK_ALLOWED_HOSTS else None
            validate_outbound_http_url(url, allowed_hosts=allowed)
        except ValueError as e:
            logger.warning('webhook URL 被安全策略拒绝: %s', e)
            return False
        content = f"{title}\n\n{message}\n\n状态: {status}"
        payload = None
        if 'oapi.dingtalk.com' in url:
            payload = {
                'msgtype': 'markdown',
                'markdown': {
                    'title': title,
                    'text': content,
                },
            }
        elif 'qyapi.weixin.qq.com' in url:
            payload = {
                'msgtype': 'markdown',
                'markdown': {
                    'content': content,
                },
            }
        else:
            payload = {'title': title, 'message': message, 'status': status}

        try:
            resp = requests.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=10,
            )
            return 200 <= resp.status_code < 300
        except Exception:
            logger.exception("发送 webhook 失败")
            return False

    @staticmethod
    def send_email(subject, message, recipient_list):
        if not settings.EMAIL_HOST_USER or 'your-email' in settings.EMAIL_HOST_USER:
            logger.warning("邮件配置未完成，跳过发送")
            return False
        try:
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                recipient_list,
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception("发送邮件失败")
            return False
