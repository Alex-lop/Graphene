# Full-matrix hang, reproduced in this tree — 2026-08-24

Captured during `scripts/morning_verify.sh` on the working tree at commit
02a75f7 plus the uncommitted `--plan-edit` change. The matrix wedged; the
`faulthandler_timeout = 180` guard produced the dump below, and
`timeout_method = "thread"` ended the run.

Two threads are the whole story, and they are the two ends of the same
connection lifecycle against one WAL database:

- one **closing** a connection — `contextlib.__exit__` on `store.py` `snapshot`;
- one **opening** a connection — `store.py` `_connect`, i.e.
  `sqlite3.connect(self.path, isolation_level=None, timeout=5)`.

`timeout=5` and `PRAGMA busy_timeout=5000` configure SQLite's busy handler,
which retries when the *database* is locked. Native stacks of the same shape
captured elsewhere show the threads parked in `__psynch_mutexwait` inside
libsqlite3's unix VFS (`unixOpen`/`findReusableFd` on open,
`sqlite3WalClose`/`unixLock` on close) — a layer below that handler, which
no SQLite timeout setting reaches.

NOT PROVEN: no fix is claimed. See the "Full-matrix hang under load" row in
`docs/KNOWN_LIMITATIONS.md`.

```
...............................................................Timeout (0:03:00)!
Thread 0x000000017396b000 (most recent call first):
  File "/opt/anaconda3/lib/python3.13/contextlib.py", line 364 in __exit__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 6703 in snapshot
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 59 in run
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 93 in _worker
  File "/opt/anaconda3/lib/python3.13/threading.py", line 994 in run
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1043 in _bootstrap_inner
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1014 in _bootstrap

Thread 0x000000017295f000 (most recent call first):
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 560 in _connect
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 6703 in snapshot
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/cli/mission.py", line 4367 in <lambda>
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/process_control.py", line 442 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/execution/adapter.py", line 467 in run_fixture_tests
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 59 in run
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 93 in _worker
  File "/opt/anaconda3/lib/python3.13/threading.py", line 994 in run
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1043 in _bootstrap_inner
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1014 in _bootstrap

Thread 0x0000000170947000 (most recent call first):
  File "/opt/anaconda3/lib/python3.13/threading.py", line 363 in wait
  File "/opt/anaconda3/lib/python3.13/threading.py", line 659 in wait
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1342 in run
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1043 in _bootstrap_inner
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1014 in _bootstrap

Thread 0x00000001f2565d80 (most recent call first):
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 560 in _connect
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 3055 in heartbeat
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/scheduler.py", line 249 in heartbeat
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/runtime.py", line 1074 in heartbeat
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/workers/gemini.py", line 285 in _heartbeat
  File "/opt/anaconda3/lib/python3.13/asyncio/events.py", line 89 in _run
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 2050 in _run_once
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 683 in run_forever
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 712 in run_until_complete
  File "/opt/anaconda3/lib/python3.13/asyncio/runners.py", line 118 in run
  File "/opt/anaconda3/lib/python3.13/asyncio/runners.py", line 195 in run
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/runner.py", line 394 in run
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/cli/mission.py", line 4489 in _execute_adk_mission
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/tests/unit/orchestration/test_failure_laboratory.py", line 333 in test_sigkilled_second_worker_retries_under_higher_fence_without_touching_sibling
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/python.py", line 167 in pytest_pyfunc_call
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/python.py", line 1707 in runtest
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 184 in pytest_runtest_call
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 250 in <lambda>
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 361 in from_call
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 249 in call_and_report
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 139 in runtestprotocol
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 118 in pytest_runtest_protocol
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 408 in pytest_runtestloop
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 384 in _main
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 330 in wrap_session
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 377 in pytest_cmdline_main
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py", line 229 in _main
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py", line 253 in _console_main
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/bin/pytest", line 10 in <module>
+++++++++++++++++++++++++++++++++++ Timeout ++++++++++++++++++++++++++++++++++++
~~~~~~~~~~~~~~~~~~~~~~~ Stack of asyncio_1 (6234222592) ~~~~~~~~~~~~~~~~~~~~~~~~
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1014, in _bootstrap
    self._bootstrap_inner()
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1043, in _bootstrap_inner
    self.run()
  File "/opt/anaconda3/lib/python3.13/threading.py", line 994, in run
    self._target(*self._args, **self._kwargs)
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 93, in _worker
    work_item.run()
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 59, in run
    result = self.fn(*self.args, **self.kwargs)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 6703, in snapshot
    with closing(self._connect()) as connection:
  File "/opt/anaconda3/lib/python3.13/contextlib.py", line 364, in __exit__
    self.thing.close()
~~~~~~~~~~~~~~~~~~~~~~~ Stack of asyncio_0 (6217396224) ~~~~~~~~~~~~~~~~~~~~~~~~
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1014, in _bootstrap
    self._bootstrap_inner()
  File "/opt/anaconda3/lib/python3.13/threading.py", line 1043, in _bootstrap_inner
    self.run()
  File "/opt/anaconda3/lib/python3.13/threading.py", line 994, in run
    self._target(*self._args, **self._kwargs)
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 93, in _worker
    work_item.run()
  File "/opt/anaconda3/lib/python3.13/concurrent/futures/thread.py", line 59, in run
    result = self.fn(*self.args, **self.kwargs)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/execution/adapter.py", line 467, in run_fixture_tests
    result = (process_runner or subprocess.run)(
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/process_control.py", line 442, in __call__
    state = self.status()
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/cli/mission.py", line 4367, in <lambda>
    status=lambda: store.snapshot(mission_id).mission.status,
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 6703, in snapshot
    with closing(self._connect()) as connection:
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 560, in _connect
    connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
~~~~~~~~~~~~~~~~~~~~~~~ Stack of MainThread (8360713600) ~~~~~~~~~~~~~~~~~~~~~~~
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/bin/pytest", line 10, in <module>
    sys.exit(_console_main())
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py", line 253, in _console_main
    code = _main(prog=_get_prog_name(sys.argv))
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py", line 229, in _main
    ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 377, in pytest_cmdline_main
    return wrap_session(config, _main)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 330, in wrap_session
    session.exitstatus = doit(config, session) or 0
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 384, in _main
    config.hook.pytest_runtestloop(session=session)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/main.py", line 408, in pytest_runtestloop
    item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 118, in pytest_runtest_protocol
    runtestprotocol(item, nextitem=nextitem)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 139, in runtestprotocol
    reports.append(call_and_report(item, "call", log))
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 249, in call_and_report
    call = CallInfo.from_call(
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 361, in from_call
    result: TResult | None = func()
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 250, in <lambda>
    lambda: runtest_hook(item=item, **kwds),
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/runner.py", line 184, in pytest_runtest_call
    item.runtest()
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/python.py", line 1707, in runtest
    self.ihook.pytest_pyfunc_call(pyfuncitem=self)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.venv/lib/python3.13/site-packages/_pytest/python.py", line 167, in pytest_pyfunc_call
    result = testfunction(**testargs)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/tests/unit/orchestration/test_failure_laboratory.py", line 333, in test_sigkilled_second_worker_retries_under_higher_fence_without_touching_sibling
    result = mission_cli._execute_adk_mission(
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/cli/mission.py", line 4489, in _execute_adk_mission
    ).run(mission_id)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/runner.py", line 394, in run
    return asyncio.run(self.run_async(mission_id))
  File "/opt/anaconda3/lib/python3.13/asyncio/runners.py", line 195, in run
    return runner.run(main)
  File "/opt/anaconda3/lib/python3.13/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 712, in run_until_complete
    self.run_forever()
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 683, in run_forever
    self._run_once()
  File "/opt/anaconda3/lib/python3.13/asyncio/base_events.py", line 2050, in _run_once
    handle._run()
  File "/opt/anaconda3/lib/python3.13/asyncio/events.py", line 89, in _run
    self._context.run(self._callback, *self._args)
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/workers/gemini.py", line 285, in _heartbeat
    await context.heartbeat()
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/runtime.py", line 1074, in heartbeat
    await _maybe_await(self.runtime.heartbeat(self.dispatch))
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/scheduler.py", line 249, in heartbeat
    return self.store.heartbeat(
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 3055, in heartbeat
    with closing(self._connect()) as connection:
  File "/Users/alexlopez/Desktop/AllThingsAgenticHackathon/backend/graphene/orchestration/store.py", line 560, in _connect
    connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
+++++++++++++++++++++++++++++++++++ Timeout ++++++++++++++++++++++++++++++++++++
--- end output
```
