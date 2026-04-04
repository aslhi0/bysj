from pathlib import Path
import os
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

_DEFAULT_SECRET_KEY = 'django-insecure-dev-only'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', _DEFAULT_SECRET_KEY)
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() in {'1', 'true', 'yes', 'on'}
if not DEBUG and SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise RuntimeError('生产环境必须设置 DJANGO_SECRET_KEY')
ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'django_celery_beat',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
DB_ENGINE = (os.getenv('DJANGO_DB_ENGINE') or '').strip().lower()
if DB_ENGINE in {'postgres', 'postgresql', 'psql'} or os.getenv('POSTGRES_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
            'PORT': int(os.getenv('POSTGRES_PORT', '5432')),
            'NAME': os.getenv('POSTGRES_DB', 'autotest'),
            'USER': os.getenv('POSTGRES_USER', 'autotest'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'autotest'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

_cors_all = os.getenv('DJANGO_CORS_ALLOW_ALL')
if _cors_all is None:
    CORS_ALLOW_ALL_ORIGINS = bool(DEBUG)
else:
    CORS_ALLOW_ALL_ORIGINS = _cors_all.lower() in {'1', 'true', 'yes', 'on'}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
        'register': '5/min',
        'login': '10/min',
        'token_refresh': '30/min',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Celery：未设置 CELERY_ALWAYS_EAGER 时，DEBUG 下默认同步执行（本地不配 Redis 也可跑通 .delay 入口）；
# Docker / 生产请显式设置 CELERY_ALWAYS_EAGER=false 并使用 worker。
_celery_eager_raw = os.getenv('CELERY_ALWAYS_EAGER')
if _celery_eager_raw is not None:
    CELERY_ALWAYS_EAGER = _celery_eager_raw.lower() in {'1', 'true', 'yes', 'on'}
else:
    CELERY_ALWAYS_EAGER = bool(DEBUG)

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
if not DEBUG:
    missing = []
    if os.getenv('CELERY_BROKER_URL') is None:
        missing.append('CELERY_BROKER_URL')
    if os.getenv('CELERY_RESULT_BACKEND') is None:
        missing.append('CELERY_RESULT_BACKEND')
    if missing:
        raise RuntimeError('生产环境必须设置: ' + ', '.join(missing))
if CELERY_ALWAYS_EAGER:
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_STORE_EAGER_RESULT = True
    CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# 邮件通知配置 (演示使用，真实环境需填入有效账号)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST', 'smtp.qq.com')
EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '465'))
EMAIL_USE_SSL = os.getenv('DJANGO_EMAIL_USE_SSL', 'true').lower() in {'1', 'true', 'yes', 'on'}
EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', 'your-email@qq.com')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', 'your-smtp-password')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'api': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
        'celery': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
    },
}
