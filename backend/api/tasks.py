import time
import subprocess
import os
import sys
from celery import shared_task
from django.core.files.base import ContentFile
from django.conf import settings
from .models import TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord
from .engine import TestEngine
from .utils import Notifier

@shared_task
def run_test_case_task(case_id, env_id=None, extra_vars=None):
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
            env_vars = env.variables or {}
            db_config = env.db_config or {}
            if env.base_url:
                env_vars['base_url'] = env.base_url
        
        merged_vars = {**env_vars, **case.variables, **(extra_vars or {})}
        
        engine = TestEngine(variables=merged_vars, db_config=db_config)
        record = TestRecord.objects.create(case=case, status='running')
        
        start_time = time.time()
        
        # --- Run Setup SQL ---
        engine.run_setup(case.setup_sql)
        
        success = True
        for step in case.steps:
            if not engine.run_step(step):
                success = False
                break
        
        # --- Run Teardown SQL ---
        engine.run_teardown(case.teardown_sql)
        
        elapsed = time.time() - start_time
        engine.close()
        
        record.status = 'success' if success else 'failed'
        record.result_log = engine.get_full_log()
        record.step_results = engine.step_results
        if engine.last_screenshot:
            filename = f"screenshot_{record.id}_{int(time.time())}.png"
            record.screenshot.save(filename, ContentFile(engine.last_screenshot), save=False)
        record.elapsed_time = elapsed
        record.save()
        
        # Send Notification
        if case.project.webhook_url:
            Notifier.send_webhook(
                case.project.webhook_url,
                f"测试用例执行完成: {case.title}",
                f"结果: {record.status}\n耗时: {record.elapsed_time}s",
                status=record.status
            )
        
        return {
            'status': record.status,
            'record_id': record.id,
            'elapsed_time': f"{elapsed:.2f}",
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@shared_task
def run_test_suite_task(suite_id, env_id=None, extra_vars=None, stop_on_failure=False):
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
            env_vars = env.variables or {}
            db_config = env.db_config or {}
            if env.base_url:
                env_vars['base_url'] = env.base_url

        merged_vars = {**env_vars, **(suite.variables or {}), **(extra_vars or {})}
        shared_vars = dict(merged_vars)
        suite_run = SuiteRun.objects.create(suite=suite, stop_on_failure=stop_on_failure)
        
        results = []
        passed, failed = 0, 0
        
        for case_id in suite.ordered_case_ids:
            try:
                case = TestCase.objects.get(id=case_id)
            except TestCase.DoesNotExist:
                continue
            
            engine_vars = {**shared_vars, **(case.variables or {})}
            engine = TestEngine(variables=engine_vars, db_config=db_config)
            record = TestRecord.objects.create(case=case, status='running')
            
            start_time = time.time()
            engine.run_setup(case.setup_sql)
            success = True
            for step in case.steps:
                if not engine.run_step(step):
                    success = False
                    break
            engine.run_teardown(case.teardown_sql)
            
            elapsed = time.time() - start_time
            engine.close()
            
            record.status = 'success' if success else 'failed'
            record.result_log = engine.get_full_log()
            record.step_results = engine.step_results
            if engine.last_screenshot:
                filename = f"screenshot_{record.id}_{int(time.time())}.png"
                record.screenshot.save(filename, ContentFile(engine.last_screenshot), save=False)
            record.elapsed_time = elapsed
            record.save()

            if isinstance(engine.variables, dict):
                shared_vars.update(engine.variables)
            
            results.append({
                'case_id': case.id,
                'case_title': case.title,
                'record_id': record.id,
                'status': record.status,
                'elapsed_time': f"{elapsed:.2f}"
            })
            
            if success:
                passed += 1
            else:
                failed += 1
                if stop_on_failure:
                    break
        
        suite_run.summary = {'total': passed + failed, 'passed': passed, 'failed': failed}
        suite_run.results = results
        suite_run.save()
        
        return {
            'suite_run_id': suite_run.id,
            'summary': suite_run.summary
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@shared_task
def run_perf_test_task(perf_record_id):
    try:
        record = PerfRecord.objects.get(id=perf_record_id)
        case = record.case
        
        locust_file = f"perf_{perf_record_id}.py"
        csv_prefix = record.csv_prefix
        
        cmd = [
            sys.executable, '-m', 'locust', '-f', locust_file, '--headless',
            '-u', str(record.users), '-r', str(record.spawn_rate),
            '--run-time', record.duration, '--csv', csv_prefix
        ]
        
        cwd = str(getattr(settings, 'BASE_DIR', os.getcwd()))
        process = subprocess.Popen(cmd, cwd=cwd)
        process.wait() # Wait for completion
        
        record.status = 'finished'
        record.save()

        try:
            fp = os.path.join(cwd, locust_file)
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
        
        return {'status': 'finished', 'perf_record_id': perf_record_id}
    except Exception as e:
        try:
            record = PerfRecord.objects.get(id=perf_record_id)
            record.status = 'error'
            record.save()
        except: pass
        return {'status': 'error', 'message': str(e)}
