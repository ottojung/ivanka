"""Bounded ten-way concurrency and checkpoint integrity under low disk."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from expanded.micall_synthetic_scheduler import MIN_AVAILABLE_BYTES, execute


class SchedulerTests(unittest.TestCase):
    def test_schedules_all_cases_exactly_once(self):
        active = [0]
        maximum = [0]
        lock = threading.Lock()
        results = []
        def work(case):
            with lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
            time.sleep(.002)
            with lock:
                active[0] -= 1
            return case
        with ThreadPoolExecutor(max_workers=3) as pool:
            execute(pool, range(25), 3, work, results.append,
                    lambda: MIN_AVAILABLE_BYTES)
        self.assertCountEqual(results, range(25))
        self.assertLessEqual(maximum[0], 3)

    def test_no_case_starts_when_disk_below_guard(self):
        observed=[]
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.assertRaisesRegex(OSError,"workspace"):
                execute(pool,[1,2],2,observed.append,
                        observed.append,lambda: MIN_AVAILABLE_BYTES-1)
        self.assertEqual(observed,[])

    def test_inflight_results_are_checkpointed_before_pause(self):
        scheduled=[]
        committed=[]
        checks=[MIN_AVAILABLE_BYTES,MIN_AVAILABLE_BYTES,
                MIN_AVAILABLE_BYTES-1]
        def available():
            return checks.pop(0) if checks else MIN_AVAILABLE_BYTES-1
        def work(x):
            scheduled.append(x)
            return x
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.assertRaisesRegex(OSError,"checkpointed"):
                execute(pool,range(5),2,work,committed.append,available)
        self.assertCountEqual(committed,[0,1])
        self.assertCountEqual(scheduled,[0,1])


if __name__=="__main__":
    unittest.main()
