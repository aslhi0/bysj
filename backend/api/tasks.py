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
    """将执行结果写入 TestRecord 并保存（单次尝试；供 suite 路径使用）。"""
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
    record.attempts = 1
    record.attempt_logs = [{
        'attempt': 1,
        'status': record.status,
        'elapsed': round(elapsed, 4),
        'error_message': error_message or None,
    }]
    record.save()
    return record.status == 'success'


def _invoke_engine_once(case, *, variables, db_config):
    """仅驱动引擎执行一次，不创建/持久化 TestRecord。

    返回 dict：{'engine', 'success', 'error_message', 'elapsed'}。
    `engine.close()` 由调用方负责，便于复用日志/截图。
    """
    engine = None
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
    return {
        'engine': engine,
        'success': success,
        'error_message': error_message,
        'elapsed': time.time() - start_time,
    }


def _execute_case_once(case, *, variables, db_config):
    """执行单个用例，创建并写入一条 TestRecord。供套件任务使用。"""
    record = TestRecord.objects.create(case=case, status='running')
    start_time = time.time()
    result = _invoke_engine_once(case, variables=variables, db_config=db_config)
    engine = result['engine']
    error_message = result['error_message']
    try:
        _finalize_record(record, engine, start_time, error_message, success_override=result['success'])
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
    return record, engine, error_message


# ---------------------------------------------------------------------------
# Celery 任务
# ---------------------------------------------------------------------------

@shared_task
def run_test_case_task(case_id, env_id=None, extra_vars=None, retry_times=0):
    """执行单个用例，内部重试聚合为单条 TestRecord。

    语义：一次 API 调用 = 一个 Flaky 样本。重试是对该样本的补救策略，明细记录在
    ``TestRecord.attempt_logs`` 中；record.status 取"最终"结果（最后一次尝试或第一次
    成功后立即终止），record.elapsed_time 累计所有尝试耗时。
    """
    case = None
    record = None
    error_message = None
    max_attempts = 1
    attempts_made = 0
    retries_used = 0

    try:
        try:
            retry_times = int(retry_times or 0)
        except Exception:
            retry_times = 0
        retry_times = max(0, min(retry_times, 3))
        max_attempts = retry_times + 1

        case = TestCase.objects.get(id=case_id)
        env_vars, db_config = _resolve_env(case.project, env_id)
        case_vars_raw = case.variables or {}
        case_vars = decrypt_json(case_vars_raw) if isinstance(case_vars_raw, dict) else case_vars_raw
        merged_vars = {**env_vars, **(case_vars or {}), **(extra_vars or {})}

        record = TestRecord.objects.create(case=case, status='running', attempts=0, attempt_logs=[])
        attempt_logs = []
        final_engine = None
        total_elapsed = 0.0
        final_success = False

        for idx in range(max_attempts):
            attempts_made = idx + 1
            result = _invoke_engine_once(case, variables=merged_vars, db_config=db_config)
            engine = result['engine']
            attempt_error = result['error_message']
            if attempt_error:
                attempt_status = 'error'
            else:
                attempt_status = 'success' if result['success'] else 'failed'
            attempt_logs.append({
                'attempt': attempts_made,
                'status': attempt_status,
                'elapsed': round(result['elapsed'], 4),
                'error_message': attempt_error or None,
            })
            total_elapsed += result['elapsed']
            error_message = attempt_error

            # 仅保留最近一次 engine 的日志/截图作为主记录快照；更早的 engine 先释放
            if final_engine is not None:
                try:
                    final_engine.close()
                except Exception:
                    pass
            final_engine = engine

            if attempt_status == 'success':
                final_success = True
                break

        retries_used = max(0, attempts_made - 1)

        if error_message and not final_success:
            record.status = 'error'
        elif final_success:
            record.status = 'success'
        else:
            record.status = 'failed'
        record.result_log = final_engine.get_full_log() if final_engine is not None else (error_message or '')
        record.step_results = final_engine.step_results if final_engine is not None else []
        if final_engine is not None and final_engine.last_screenshot:
            filename = f'screenshot_{record.id}_{int(time.time())}.png'
            record.screenshot.save(filename, ContentFile(final_engine.last_screenshot), save=False)
        record.elapsed_time = total_elapsed
        record.attempts = attempts_made
        record.attempt_logs = attempt_logs
        record.save()

        if final_engine is not None:
            try:
                final_engine.close()
            except Exception:
                pass
    except Exception as e:
        error_message = str(e)
        logger.exception('run_test_case_task failed case_id=%s', case_id)
        if record is not None:
            try:
                record.status = 'error'
                record.result_log = (record.result_log or '') + f'\n任务异常: {error_message}'
                record.attempts = max(record.attempts, attempts_made or 1)
                record.save()
            except Exception:
                logger.exception('failed to mark TestRecord error')

    if record is not None and case is not None and case.project.webhook_url:
        Notifier.send_webhook(
            case.project.webhook_url,
            f'测试用例执行完成: {case.title}',
            f'结果: {record.status}\n耗时: {record.elapsed_time}s\n尝试次数: {attempts_made}/{max_attempts}',
            status=record.status,
        )

    if record is None:
        return {'status': 'error', 'message': error_message or '无法创建执行记录'}

    logger.info(
        'run_test_case_task finished case_id=%s record_id=%s status=%s attempts=%s/%s',
        case_id, record.id, record.status, attempts_made, max_attempts,
    )
    return {
        'status': record.status,
        'record_id': record.id,
        'elapsed_time': f'{record.elapsed_time:.2f}',
        'message': error_message,
        'attempts': max_attempts,
        'attempts_made': attempts_made,
        'retries_used': retries_used,
    }


def _execute_case_with_retry(case, *, variables, db_config, max_attempts):
    """套件路径上的单用例执行：沿用与 run_test_case_task 一致的"单记录 + attempt_logs"语义。

    返回 (record, last_engine, error_message, attempts_made)；last_engine 由调用方决定是否
    复用其 variables 做跨 case 传递，最终由调用方 close。
    """
    record = TestRecord.objects.create(case=case, status='running', attempts=0, attempt_logs=[])
    attempt_logs = []
    final_engine = None
    total_elapsed = 0.0
    final_success = False
    attempts_made = 0
    last_error = None
    max_attempts = max(1, int(max_attempts or 1))

    for idx in range(max_attempts):
        attempts_made = idx + 1
        result = _invoke_engine_once(case, variables=variables, db_config=db_config)
        engine = result['engine']
        err = result['error_message']
        if err:
            status_s = 'error'
        else:
            status_s = 'success' if result['success'] else 'failed'
        attempt_logs.append({
            'attempt': attempts_made,
            'status': status_s,
            'elapsed': round(result['elapsed'], 4),
            'error_message': err or None,
        })
        total_elapsed += result['elapsed']
        last_error = err
        if final_engine is not None:
            try:
                final_engine.close()
            except Exception:
                pass
        final_engine = engine
        if status_s == 'success':
            final_success = True
            break

    if last_error and not final_success:
        record.status = 'error'
    elif final_success:
        record.status = 'success'
    else:
        record.status = 'failed'
    record.result_log = final_engine.get_full_log() if final_engine is not None else (last_error or '')
    record.step_results = final_engine.step_results if final_engine is not None else []
    if final_engine is not None and final_engine.last_screenshot:
        filename = f'screenshot_{record.id}_{int(time.time())}.png'
        record.screenshot.save(filename, ContentFile(final_engine.last_screenshot), save=False)
    record.elapsed_time = total_elapsed
    record.attempts = attempts_made
    record.attempt_logs = attempt_logs
    record.save()
    return record, final_engine, last_error, attempts_made


@shared_task
def run_test_suite_task(suite_id, env_id=None, extra_vars=None, stop_on_failure=False, retry_times=0):
    """顺序执行套件内所有用例；每个用例最多 `retry_times+1` 次尝试（与单用例执行一致）。"""
    suite = None
    suite_run = None
    try:
        try:
            retry_times = int(retry_times or 0)
        except Exception:
            retry_times = 0
        retry_times = max(0, min(retry_times, 3))
        max_attempts = retry_times + 1

        suite = TestSuite.objects.get(id=suite_id)
        env_vars, db_config = _resolve_env(suite.project, env_id)
        suite_vars_raw = suite.variables or {}
        suite_vars = decrypt_json(suite_vars_raw) if isinstance(suite_vars_raw, dict) else suite_vars_raw
        merged_vars = {**env_vars, **(suite_vars or {}), **(extra_vars or {})}
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
            case_vars_raw = case.variables or {}
            case_vars = decrypt_json(case_vars_raw) if isinstance(case_vars_raw, dict) else case_vars_raw
            engine_vars = {**shared_vars, **(case_vars or {})}
            record, engine, _error_message, attempts_made = _execute_case_with_retry(
                case,
                variables=engine_vars,
                db_config=db_config,
                max_attempts=max_attempts,
            )

            if engine is not None and isinstance(engine.variables, dict):
                shared_vars.update(engine.variables)
                try:
                    engine.close()
                except Exception:
                    pass

            results.append({
                'case_id': case.id,
                'case_title': case.title,
                'record_id': record.id,
                'status': record.status,
                'elapsed_time': f'{record.elapsed_time:.2f}',
                'attempts': attempts_made,
            })

            if record.status == 'success':
                passed += 1
            else:
                failed += 1
                stop_now = bool(stop_on_failure)

            if stop_now:
                break

        suite_run.summary = {
            'total': passed + failed,
            'passed': passed,
            'failed': failed,
            'max_attempts_per_case': max_attempts,
        }
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


@shared_task
def reconcile_perf_records_task():
    """Celery beat 周期任务：收敛脏状态的 PerfRecord。

    从请求级 `PerfRecordViewSet.get_queryset` 迁移而来，避免每次列表请求触发一次
    全表扫描 + 磁盘 stat，降低列表接口的 P95 延迟；beat 每 2 分钟执行一次足够业务需求。
    """
    try:
        changed = reconcile_stale_perf_records()
        if changed:
            logger.info('reconcile_perf_records_task changed ids=%s', changed)
        return {'changed': changed}
    except Exception as e:
        logger.exception('reconcile_perf_records_task failed')
        return {'changed': [], 'error': str(e)}
