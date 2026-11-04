from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor


class BackgroundJobs:
    """Network work in a worker; SQLite and match state stay on the server thread."""
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.jobs = {}

    def start(self, work, finish=lambda result: result) -> dict:
        self.poll()
        if any(j['status'] == 'running' for j in self.jobs.values()):
            raise ValueError('An import or Google operation is already running. Wait for it to finish.')
        key = uuid.uuid4().hex
        self.jobs[key] = dict(status='running', future=self.executor.submit(work), finish=finish, created=time.monotonic())
        return {'job_id': key}

    def poll(self):
        for key, job in list(self.jobs.items()):
            if job['status'] == 'running' and job['future'].done():
                try:
                    job['result'] = job['finish'](job['future'].result())
                    job['status'] = 'done'
                except Exception as exc:
                    job.update(status='error', error=str(exc))
                del job['future'], job['finish']
            if job['status'] != 'running' and time.monotonic() - job['created'] > 3600:
                del self.jobs[key]

    def get(self, key):
        self.poll()
        if key not in self.jobs:
            raise ValueError('Operation not found; check game status before retrying')
        return {k: v for k, v in self.jobs[key].items() if k in ('status', 'result', 'error')}

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
