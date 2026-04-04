import time
import subprocess
import os
import sys
import re
import logging
from celery import shared_task
from django.core.files.base import ContentFile
from django.conf import settings
from .models import TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord
from .engine import TestEngine
from .utils import Notifier
from .crypto_utils import decrypt_json

logger = logging.getLogger(__name__)


@shared_task
def run_test_case_task(case_id, env_id=None, extra_vars=None):
    case = None
    record = None
    engine = None
    start_time = time.time()
    success = False
    error_message = None

    try:
        case = TestCase.objects.get(id=case_id)
        env_vars = {}
        db_config = {}
        env = None
        if env_id:
            try:
                env = EnvConfig.objects.get(id=env_id)
            except EnvConfig.DoesNotExist:
                env = None
        if env is None:
            env = (
                EnvConfig.objects.filter(project=case.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
        if env is not None:
            env_vars = decrypt_json(env.variables or {}) if isinstance(env.variables, dict) else (env.variables or {})
            db_config = decrypt_json(env.db_config or {}) if isinstance(env.db_config, dict) else (env.db_config or {})
            if env.base_url:
                env_vars['base_url'] = env.base_url

        merged_vars = {**env_vars, **(case.variables or {}), **(extra_vars or {})}

        record = TestRecord.objects.create(case=case, status='running')
        engine = TestEngine(variables=merged_vars, db_config=db_config)

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
                engine.add_log(f"任务异常: {error_message}")
            except Exception:
                pass
    finally:
        if engine is not None and case is not None:
            try:
                engine.run_teardown(case.teardown_sql)
            except Exception as e:
                try:
                    engine.add_log(f"Teardown 异常: {str(e)}")
                except Exception:
                    pass

        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

        if record is not None:
            elapsed = time.time() - start_time
            if error_message:
                record.status = 'error'
            else:
                record.status = 'success' if success else 'failed'

            record.result_log = engine.get_full_log() if engine is not None else (error_message or '')
            record.step_results = engine.step_results if engine is not None else []
            if engine is not None and engine.last_screenshot:
                filename = f"screenshot_{record.id}_{int(time.time())}.png"
                record.screenshot.save(filename, ContentFile(engine.last_screenshot), save=False)
            record.elapsed_time = elapsed
            record.save()

            if case is not None and case.project.webhook_url:
                Notifier.send_webhook(
                    case.project.webhook_url,
                    f"测试用例执行完成: {case.title}",
                    f"结果: {record.status}\n耗时: {record.elapsed_time}s",
                    status=record.status,
                )

    if record is None:
        return {'status': 'error', 'message': error_message or '无法创建执行记录'}

    logger.info(
        'run_test_case_task finished case_id=%s record_id=%s status=%s',
        case_id,
        record.id,
        record.status,
    )
    return {
        'status': record.status,
        'record_id': record.id,
        'elapsed_time': f"{record.elapsed_time:.2f}",
        'message': error_message,
    }

@shared_task
def run_test_suite_task(suite_id, env_id=None, extra_vars=None, stop_on_failure=False):
    suite = None
    suite_run = None
    try:
        suite = TestSuite.objects.get(id=suite_id)
        env_vars = {}
        db_config = {}
        env = None
        if env_id:
            try:
                env = EnvConfig.objects.get(id=env_id)
            except EnvConfig.DoesNotExist:
                env = None
        if env is None:
            env = (
                EnvConfig.objects.filter(project=suite.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
        if env is not None:
            env_vars = decrypt_json(env.variables or {}) if isinstance(env.variables, dict) else (env.variables or {})
            db_config = decrypt_json(env.db_config or {}) if isinstance(env.db_config, dict) else (env.db_config or {})
            if env.base_url:
                env_vars['base_url'] = env.base_url

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

            engine = None
            record = None
            start_time = time.time()
            success = False
            error_message = None
            stop_now = False

            try:
                engine_vars = {**shared_vars, **(case.variables or {})}
                record = TestRecord.objects.create(case=case, status='running')
                engine = TestEngine(variables=engine_vars, db_config=db_config)

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
                        engine.add_log(f"任务异常: {error_message}")
                    except Exception:
                        pass
            finally:
                if engine is not None:
                    try:
                        engine.run_teardown(case.teardown_sql)
                    except Exception as e:
                        try:
                            engine.add_log(f"Teardown 异常: {str(e)}")
                        except Exception:
                            pass
                    try:
                        engine.close()
                    except Exception:
                        pass

                if record is not None:
                    elapsed = time.time() - start_time
                    if error_message:
                        record.status = 'error'
                    else:
                        record.status = 'success' if success else 'failed'

                    record.result_log = engine.get_full_log() if engine is not None else (error_message or '')
                    record.step_results = engine.step_results if engine is not None else []
                    if engine is not None and engine.last_screenshot:
                        filename = f"screenshot_{record.id}_{int(time.time())}.png"
                        record.screenshot.save(filename, ContentFile(engine.last_screenshot), save=False)
                    record.elapsed_time = elapsed
                    record.save()

                    if engine is not None and isinstance(engine.variables, dict):
                        shared_vars.update(engine.variables)

                    results.append({
                        'case_id': case.id,
                        'case_title': case.title,
                        'record_id': record.id,
                        'status': record.status,
                        'elapsed_time': f"{elapsed:.2f}",
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
            suite_id,
            suite_run.id,
            suite_run.summary,
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
    try:
        record = PerfRecord.objects.get(id=perf_record_id)
        locust_file = f"perf_{perf_record_id}.py"
        csv_prefix = record.csv_prefix

        perf_dir = os.path.join(str(getattr(settings, 'MEDIA_ROOT', os.getcwd())), 'perf', str(perf_record_id))
        os.makedirs(perf_dir, exist_ok=True)
        locust_path = os.path.join(perf_dir, locust_file)

        duration_s = str(record.duration or '60s').strip().lower()
        m = re.fullmatch(r'(\d+)\s*([smh]?)', duration_s)
        if not m:
            seconds = 60
        else:
            n = int(m.group(1))
            unit = m.group(2) or 's'
            seconds = n * (3600 if unit == 'h' else 60 if unit == 'm' else 1)
        if seconds < 1:
            seconds = 1
        if seconds > 600:
            seconds = 600
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
            subprocess.run(cmd, cwd=perf_dir, timeout=seconds + 30, check=False)
        except subprocess.TimeoutExpired:
            record.status = 'timeout'
            record.save(update_fields=['status'])
            return {'status': 'timeout', 'perf_record_id': perf_record_id}
        
        record.status = 'finished'
        record.save()

        try:
            if os.path.exists(locust_path):
                os.remove(locust_path)
        except Exception:
            pass
        
        logger.info('run_perf_test_task finished perf_record_id=%s', perf_record_id)
        return {'status': 'finished', 'perf_record_id': perf_record_id}
    except Exception as e:
        logger.exception('run_perf_test_task failed perf_record_id=%s', perf_record_id)
        try:
            record = PerfRecord.objects.get(id=perf_record_id)
            record.status = 'error'
            record.save(update_fields=['status'])
        except PerfRecord.DoesNotExist:
            pass
        except Exception:
            logger.exception('failed to mark PerfRecord error state')
        return {'status': 'error', 'message': str(e)}
