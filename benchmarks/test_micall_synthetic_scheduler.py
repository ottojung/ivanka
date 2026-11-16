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

    def test_disk_pressure_does_not_consume_unstarted_case(self):
        reserve = 512 * 1024**2
        scheduled, committed = [], []
        checks = [MIN_AVAILABLE_BYTES + reserve,
                  MIN_AVAILABLE_BYTES + 2 * reserve - 1]
        def free():
            return checks.pop(0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.assertRaisesRegex(OSError, "checkpointed"):
                execute(pool, [0, 1, 2], 2, scheduled.append,
                        committed.append, free, reserve_per_arm=reserve)
        self.assertEqual(committed, [None])
        self.assertEqual(scheduled, [0])

    def test_final_case_does_not_falsely_pause_when_disk_drops(self):
        reserve = 512 * 1024**2
        scheduled, committed = [], []
        checks = [MIN_AVAILABLE_BYTES + reserve, 0]
        def free():
            return checks.pop(0)
        with ThreadPoolExecutor(max_workers=1) as pool:
            execute(pool, [7], 1, scheduled.append,
                    committed.append, free, reserve_per_arm=reserve)
        self.assertEqual(scheduled, [7])

    def test_reservation_limits_parallel_running_arm_memory(self):
        reserve = 512 * 1024**2
        jobs = 10
        results = []
        available = MIN_AVAILABLE_BYTES + 3 * reserve
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            with self.assertRaisesRegex(OSError, "checkpointed"):
                execute(pool, range(12), jobs, lambda x: x, results.append,
                        lambda: available, reserve_per_arm=reserve)
        self.assertCountEqual(results, [0, 1, 2,])

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
