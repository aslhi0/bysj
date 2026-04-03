"""单用例同步执行：创建 TestRecord 并运行 HttpExecutor（供单条 run 与套件批量 run 复用）。"""
from __future__ import annotations

import time
import traceback
from typing import Any

from apps.cases.models import TestCase
from apps.runs.executors import HttpExecutor
from apps.runs.models import TestRecord


def execute_case_record(
    test_case: TestCase,
    runtime_variables: dict[str, Any] | None = None,
) -> TestRecord:
    extra = runtime_variables if isinstance(runtime_variables, dict) else {}
    record = TestRecord.objects.create(
        testcase=test_case,
        status=TestRecord.Status.RUNNING,
        result_log='同步执行已开始…',
        elapsed_time=0.0,
    )
    t0 = time.perf_counter()
    try:
        executor = HttpExecutor(test_case, runtime_variables=extra)
        st, log, elapsed = executor.execute()
        record.status = st
        record.result_log = log
        record.elapsed_time = elapsed
        record.save(update_fields=['status', 'result_log', 'elapsed_time'])
    except Exception:
        record.status = TestRecord.Status.FAILED
        record.result_log = traceback.format_exc()
        record.elapsed_time = time.perf_counter() - t0
        record.save(update_fields=['status', 'result_log', 'elapsed_time'])
    return record
