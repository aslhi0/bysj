import requests
import json
from django.core.mail import send_mail
from django.conf import settings

class Notifier:
    @staticmethod
    def send_webhook(webhook_url, title, message, status='info'):
        if not webhook_url:
            return False
        content = f"{title}\n\n{message}\n\n状态: {status}"
        payload = None
        url = str(webhook_url)
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
        except Exception as e:
            print(f"发送 webhook 失败: {str(e)}")
            return False

    @staticmethod
    def send_email(subject, message, recipient_list):
        if not settings.EMAIL_HOST_USER or 'your-email' in settings.EMAIL_HOST_USER:
            print("邮件配置未完成，跳过发送")
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
        except Exception as e:
            print(f"发送邮件失败: {str(e)}")
            return False
