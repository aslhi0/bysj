import time
import subprocess
import os
import sys
import logging
from datetime import timedelta
from celery import shared_task
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
from .models import TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord
from .engine import TestEngine
from .utils import Notifier
from .crypto_utils import decrypt_json

logger = logging.getLogger(__name__)


def _duration_to_seconds(duration, default=60):
    import re as _re

    text = str(duration or f'{default}s').strip().lower()
    m = _re.fullmatch(r'(\d+)\s*([smh]?)', text)
    if not m:
        return default
    n = int(m.group(1))
    unit = m.group(2) or 's'
    seconds = n * (3600 if unit == 'h' else 60 if unit == 'm' else 1)
    return max(1, min(seconds, 600))


def reconcile_stale_perf_records(grace_seconds=120):
    """将历史脏状态自动收敛，避免页面长期显示错误状态。"""
    now = timezone.now()
    changed = []
    qs = PerfRecord.objects.filter(status__in=['running', 'queued', 'finished']).order_by('id')
    for record in qs:
        perf_dir = os.path.join(str(getattr(settings, 'MEDIA_ROOT', os.getcwd())), 'perf', str(record.id))
        prefix = record.csv_prefix or ''
        stats_path = os.path.join(perf_dir, f'{prefix}_stats.csv') if prefix else ''
        history_path = os.path.join(perf_dir, f'{prefix}_stats_history.csv') if prefix else ''
        has_report = bool(prefix) and (os.path.exists(stats_path) or os.path.exists(history_path))

        if record.status in {'running', 'queued'}:
            seconds = _duration_to_seconds(record.duration, default=60)
            deadline = record.created_at + timedelta(seconds=seconds + grace_seconds)
            if now <= deadline:
                continue
            record.status = 'finished' if has_report else 'timeout'
            record.save(update_fields=['status'])
            changed.append(record.id)
            continue

        # finished 但无 CSV，说明历史记录状态不一致，统一收敛为 error。
        if record.status == 'finished' and not has_report:
            record.status = 'error'
            record.save(update_fields=['status'])
            changed.append(record.id)
    return changed


# ---------------------------------------------------------------------------
# 共享辅助函数
# ---------------------------------------------------------------------------

def _resolve_env(project, env_id=None):
    """解析环境配置，返回 (env_vars, db_config)。

    优先使用 env_id 指定的环境；若无则取项目默认环境；均无则返回空字典。
    """
    env = None
    if env_id:
        try:
            env = EnvConfig.objects.get(id=env_id)
        except EnvConfig.DoesNotExist:
            pass
    if env is None:
        env = (
            EnvConfig.objects.filter(project=project, is_default=True)
            .order_by('-created_at')
            .first()
        )
    if env is None:
        return {}, {}

    env_vars = decrypt_json(env.variables or {}) if isinstance(env.variables, dict) else (env.variables or {})
    db_config = decrypt_json(env.db_config or {}) if isinstance(env.db_config, dict) else (env.db_config or {})
    if env.base_url:
        env_vars['base_url'] = env.base_url
    return env_vars, db_config


def _finalize_record(record, engine, start_time, error_message, *, success_override=None):
    """将执行结果写入 TestRecord 并保存。"""
    elapsed = time.time() - start_time
    if error_message:
        record.status = 'error'
    else:
        if success_override is None:
            success = all(
                sr.get('status') == 'success'
                for sr in (engine.step_results if engine is not None else [])
            )
        else:
            success = bool(success_override)
        # step_results 为空时视为成功（无步骤的用例）
        record.status = 'success' if success else 'failed'

    record.result_log = engine.get_full_log() if engine is not None else (error_message or '')
    record.step_results = engine.step_results if engine is not None else []
    if engine is not None and engine.last_screenshot:
        filename = f'screenshot_{record.id}_{int(time.time())}.png'
        record.screenshot.save(filename, ContentFile(engine.last_screenshot), save=False)
    record.elapsed_time = elapsed
    record.save()
    return record.status == 'success'


def _execute_case_once(case, *, variables, db_config):
    """执行单个用例并返回 (record, engine, error_message)。"""
    engine = None
    record = TestRecord.objects.create(case=case, status='running')
    start_time = time.time()
    success = False
    error_message = None
    try:
        engine = TestEngine(variables=variables, db_config=db_config)
        engine.run_setup(case.setup_sql)
        success = True
        for step in case.steps or []:
            if not engine.run_step(step):
                success = False
                break
    except Exception as e:
        error_message = str(e)
        if engine is not None:
            try:
                engine.add_log(f'任务异常: {error_message}')
            except Exception:
                pass
    finally:
        if engine is not None:
            try:
                engine.run_teardown(case.teardown_sql)
            except Exception as e:
                try:
                    engine.add_log(f'Teardown 异常: {str(e)}')
                except Exception:
                    pass
            try:
                engine.close()
            except Exception:
                pass
        _finalize_record(record, engine, start_time, error_message, success_override=success)
    return record, engine, error_message


# ---------------------------------------------------------------------------
# Celery 任务
# ---------------------------------------------------------------------------

@shared_task
def run_test_case_task(case_id, env_id=None, extra_vars=None, retry_times=0):
    case = None
    record = None
    error_message = None
    attempts = 1
    retries_used = 0

    try:
        try:
            retry_times = int(retry_times or 0)
        except Exception:
            retry_times = 0
        retry_times = max(0, min(retry_times, 3))
        attempts = retry_times + 1

        case = TestCase.objects.get(id=case_id)
        env_vars, db_config = _resolve_env(case.project, env_id)
        merged_vars = {**env_vars, **(case.variables or {}), **(extra_vars or {})}
        for idx in range(attempts):
            record, _engine, error_message = _execute_case_once(
                case,
                variables=merged_vars,
                db_config=db_config,
            )
            retries_used = idx
            if record is not None and record.status == 'success':
                break
    except Exception as e:
        error_message = str(e)
        logger.exception('run_test_case_task failed case_id=%s', case_id)

    if record is not None and case is not None and case.project.webhook_url:
        Notifier.send_webhook(
            case.project.webhook_url,
            f'测试用例执行完成: {case.title}',
            f'结果: {record.status}\n耗时: {record.elapsed_time}s',
            status=record.status,
        )

    if record is None:
        return {'status': 'error', 'message': error_message or '无法创建执行记录'}

    logger.info(
        'run_test_case_task finished case_id=%s record_id=%s status=%s',
        case_id, record.id, record.status,
    )
    return {
        'status': record.status,
        'record_id': record.id,
        'elapsed_time': f'{record.elapsed_time:.2f}',
        'message': error_message,
        'attempts': attempts,
        'retries_used': retries_used,
    }


@shared_task
def run_test_suite_task(suite_id, env_id=None, extra_vars=None, stop_on_failure=False):
    suite = None
    suite_run = None
    try:
        suite = TestSuite.objects.get(id=suite_id)
        env_vars, db_config = _resolve_env(suite.project, env_id)
        merged_vars = {**env_vars, **(suite.variables or {}), **(extra_vars or {})}
        shared_vars = dict(merged_vars)
        suite_run = SuiteRun.objects.create(suite=suite, stop_on_failure=stop_on_failure)

        results = []
        passed, failed = 0, 0

        for case_id in suite.ordered_case_ids or []:
            try:
                case = TestCase.objects.get(id=case_id)
            except TestCase.DoesNotExist:
                continue

            stop_now = False
            engine_vars = {**shared_vars, **(case.variables or {})}
            record, engine, _error_message = _execute_case_once(
                case,
                variables=engine_vars,
                db_config=db_config,
            )
            elapsed = record.elapsed_time

            if engine is not None and isinstance(engine.variables, dict):
                shared_vars.update(engine.variables)

            results.append({
                'case_id': case.id,
                'case_title': case.title,
                'record_id': record.id,
                'status': record.status,
                'elapsed_time': f'{elapsed:.2f}',
            })

            if record.status == 'success':
                passed += 1
            else:
                failed += 1
                stop_now = bool(stop_on_failure)

            if stop_now:
                break

        suite_run.summary = {'total': passed + failed, 'passed': passed, 'failed': failed}
        suite_run.results = results
        suite_run.save()

        logger.info(
            'run_test_suite_task finished suite_id=%s suite_run_id=%s summary=%s',
            suite_id, suite_run.id, suite_run.summary,
        )
        return {'suite_run_id': suite_run.id, 'summary': suite_run.summary}
    except Exception as e:
        msg = str(e)
        if suite_run is not None:
            try:
                suite_run.summary = {'total': 0, 'passed': 0, 'failed': 0}
                suite_run.results = [{'status': 'error', 'message': msg}]
                suite_run.save()
            except Exception:
                pass
        return {'status': 'error', 'message': msg}


@shared_task
def run_perf_test_task(perf_record_id):
    locust_path = None
    timed_out = False
    process_rc = None
    try:
        record = PerfRecord.objects.get(id=perf_record_id)
        record.status = 'running'
        record.save(update_fields=['status'])
        locust_file = f'perf_{perf_record_id}.py'
        csv_prefix = record.csv_prefix

        perf_dir = os.path.join(str(getattr(settings, 'MEDIA_ROOT', os.getcwd())), 'perf', str(perf_record_id))
        os.makedirs(perf_dir, exist_ok=True)
        locust_path = os.path.join(perf_dir, locust_file)

        seconds = _duration_to_seconds(record.duration, default=60)
        run_time = f'{seconds}s'

        cmd = [
            sys.executable, '-m', 'locust',
            '-f', locust_path,
            '--headless',
            '-u', str(record.users),
            '-r', str(record.spawn_rate),
            '--run-time', run_time,
            '--csv', os.path.join(perf_dir, csv_prefix),
        ]

        try:
            completed = subprocess.run(cmd, cwd=perf_dir, timeout=seconds + 30, check=False)
            process_rc = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    except Exception as e:
        logger.exception('run_perf_test_task failed perf_record_id=%s', perf_record_id)
        try:
            record = PerfRecord.objects.get(id=perf_record_id)
            record.status = 'error'
            record.save(update_fields=['status'])
        except Exception:
            logger.exception('failed to mark PerfRecord error state')
        return {'status': 'error', 'message': str(e)}
    finally:
        # 无论成功、超时还是异常，都清理临时脚本文件
        if locust_path:
            try:
                if os.path.exists(locust_path):
                    os.remove(locust_path)
            except Exception:
                pass

    if timed_out:
        try:
            record = PerfRecord.objects.get(id=perf_record_id)
            record.status = 'timeout'
            record.save(update_fields=['status'])
        except Exception:
            pass
        return {'status': 'timeout', 'perf_record_id': perf_record_id}

    try:
        record = PerfRecord.objects.get(id=perf_record_id)
        perf_dir = os.path.join(str(getattr(settings, 'MEDIA_ROOT', os.getcwd())), 'perf', str(perf_record_id))
        stats_path = os.path.join(perf_dir, f'{record.csv_prefix}_stats.csv') if record.csv_prefix else ''
        history_path = os.path.join(perf_dir, f'{record.csv_prefix}_stats_history.csv') if record.csv_prefix else ''
        has_report = bool(record.csv_prefix) and (os.path.exists(stats_path) or os.path.exists(history_path))
        if process_rc not in (0, None) and not has_report:
            record.status = 'error'
        else:
            record.status = 'finished' if has_report else 'error'
        record.save(update_fields=['status'])
    except Exception:
        pass

    logger.info('run_perf_test_task finished perf_record_id=%s', perf_record_id)
    return {'status': record.status if 'record' in locals() else 'error', 'perf_record_id': perf_record_id}
