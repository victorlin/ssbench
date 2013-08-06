# Copyright (c) 2012-2013 SwiftStack, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import csv
from mock import MagicMock
from statlib import stats
from unittest import TestCase
from cStringIO import StringIO

import ssbench
from ssbench.reporter import Reporter
from ssbench.ordered_dict import OrderedDict

from ssbench.tests.test_scenario import ScenarioFixture


class TestReporter(ScenarioFixture, TestCase):
    maxDiff = None

    def setUp(self):
        # Set our test scenario differently from the default; must be BEFORE
        # the super call.
        self.scenario_dict = dict(
            name='Reporter Test Scenario - ablkei',
            sizes=[
                dict(name='tiny', size_min=99, size_max=100),
                dict(name='small', size_min=1990, size_max=1990,
                     crud_profile=[71, 9, 12, 8]),
                dict(name='medium', size_min=2990, size_max=3000),
                dict(name='unused', size_min=9876543, size_max=9876543),
                dict(name='large', size_min=399000, size_max=400000,
                     crud_profile=[16, 61, 7, 16]),
                dict(name='huge', size_min=49900000, size_max=71499999)],
            initial_files=dict(
                tiny=300, small=400, medium=500, large=200, huge=70,
            ),
            operation_count=5000,
            #             C  R  U  D
            crud_profile=[5, 3, 1, 1],
            user_count=2,
        )
        super(TestReporter, self).setUp()

        self.result_index = 1  # for self.gen_result()

        self.stub_results = [
            # Results are actually a list of the lists returned by workers.
            # Thise lists will just have one element, unless the worker was
            # using a batch-size > 1, in which case they might have more.
            [self.gen_result(
                1, ssbench.CREATE_OBJECT, 'small', 100.0, 101.0, 103.0, 0),
             self.gen_result(
                 1, ssbench.READ_OBJECT, 'tiny', 103.0, 103.1, 103.8, 0)],
            [self.gen_result(
                1, ssbench.CREATE_OBJECT, 'huge', 103.8, 105.0, 106.0, 0),
             self.gen_result(
                 1, ssbench.UPDATE_OBJECT, 'large', 106.1, 106.3, 106.4, 0)],
            #
            # exceptions should be ignored
            [dict(worker_id=2, type=ssbench.UPDATE_OBJECT, size_str='large',
                  completed_at=152.2, retries=5, exception='wacky!',
                  traceback='ugh'),
             self.gen_result(
                 2, ssbench.UPDATE_OBJECT, 'medium', 100.1, 100.9, 102.9, 1)],
            [self.gen_result(
                2, ssbench.DELETE_OBJECT, 'large', 102.9, 103.0, 103.3, 0),
             self.gen_result(
                 2, ssbench.CREATE_OBJECT, 'tiny', 103.3, 103.4, 103.5, 1)],
            [self.gen_result(
                2, ssbench.READ_OBJECT, 'small', 103.5, 103.7, 104.0, 0),
             #
             self.gen_result(
                 3, ssbench.READ_OBJECT, 'tiny', 100.1, 101.1, 101.9, 0)],
            # worker 3 took a while (observer lower concurrency in second 102
            [self.gen_result(
                3, ssbench.DELETE_OBJECT, 'small', 103.1, 103.6, 103.9, 0),
             self.gen_result(
                 3, ssbench.READ_OBJECT, 'medium', 103.9, 104.2, 104.3, 0),
             self.gen_result(
                 3, ssbench.UPDATE_OBJECT, 'tiny', 104.3, 104.9, 104.999, 0)],
        ]
        self.run_results = MagicMock()
        self.run_results.read_results.return_value = (self.scenario,
                                                      self.stub_results)
        self.reporter = Reporter(self.run_results)
        self.reporter.read_results()

    def tearDown(self):
        super(TestReporter, self).tearDown()

    def gen_result(self, worker_id, op_type, size_str, start, first_byte,
                   last_byte, retries):
        self.result_index += 1

        return {
            # There are other keys in a "result", but these are the only ones
            # used for the reporting.
            'worker_id': worker_id,
            'type': op_type,
            'size_str': size_str,
            'size': 989,
            'retries': retries,
            'first_byte_latency': first_byte - start,
            'last_byte_latency': last_byte - start,
            'trans_id': 'txID%03d' % self.result_index,
            'completed_at': last_byte,
        }

    def test_format_bytes(self):
        input_expected = [
            (0, '  0  B'),
            (7, '  7  B'),
            (17, ' 17  B'),
            (117, '117  B'),
            (999, '999  B'),
            (1000, '  1 kB'),
            (1001, '  1 kB'),
            (1100, '  1 kB'),
            (1500, '  2 kB'),
            (1999, '  2 kB'),
            (2000, '  2 kB'),
            (7500, '  8 kB'),
            (7900, '  8 kB'),
            (9999, ' 10 kB'),
            (10000, ' 10 kB'),
            (19999, ' 20 kB'),
            (20000, ' 20 kB'),
            (84999, ' 85 kB'),
            (85000, ' 85 kB'),
            (99999, '100 kB'),
            (100000, '100 kB'),
            (100001, '100 kB'),
            (700500, '701 kB'),
            (999999, '  1 MB'),
            (1000000, '  1 MB'),
            (1000001, '  1 MB'),
            (4123456, '  4 MB'),
            (4543210, '  5 MB'),
            (99999999, '100 MB'),
            (100000000, '100 MB'),
            (9999999999, ' 10 GB'),
            (10000000000, ' 10 GB'),
            (99999999999, '100 GB'),
            (100000000000, '100 GB'),
            (234567890123, '235 GB'),
        ]
        for input_bytes, formatting in input_expected:
            self.assertEqual(
                formatting, self.reporter._format_bytes(input_bytes),
                '_format_bytes(%d) = %s instead of %s' % (
                    input_bytes, self.reporter._format_bytes(input_bytes),
                    formatting))

    def test__series_stats_empty_sequence(self):
        self.assertEqual({
            'min': ' N/A  ', 'max': '  N/A  ', 'avg': '  N/A  ',
            'pctile': '  N/A  ', 'std_dev': '  N/A  ',
            'median': '  N/A  '}, self.reporter._series_stats([], 88, True))

    def test__compute_latency_stats_bad_key(self):
        some_stats = {}
        self.reporter._compute_latency_stats(some_stats, 88, True)
        self.assertEqual({
            'first_byte_latency': {
                'min': ' N/A  ', 'max': '  N/A  ', 'avg': '  N/A  ',
                'pctile': '  N/A  ', 'std_dev': '  N/A  ',
                'median': '  N/A  '},
            'last_byte_latency': {
                'min': ' N/A  ', 'max': '  N/A  ', 'avg': '  N/A  ',
                'pctile': '  N/A  ', 'std_dev': '  N/A  ',
                'median': '  N/A  '}},
            some_stats)

    def test_calculate_scenario_stats_per_worker(self):
        req_counts = [4, 5, 4]
        self.assertDictEqual(dict(
            min='%6.3f' % 4,
            max='%7.3f' % 5,
            avg='%7.3f' % stats.lmean(req_counts),
            pctile='%7.3f' % 5,
            std_dev='%7.3f' % stats.lsamplestdev(req_counts),
            median='%7.3f' % stats.lmedianscore(req_counts),
        ), self.reporter.stats['jobs_per_worker_stats'])

    def test_calculate_scenario_stats_aggregate(self):
        first_byte_latency_all = [1, 0.1, 1.2, 0.2, 0.8, 0.1, 0.1,
                                  0.2, 1, 0.5, 0.3, 0.6]
        last_byte_latency_all = [3, 0.8, 2.2, 0.3, 2.8, 0.4, 0.2,
                                 0.5, 1.8, 0.8, 0.4, 0.699]
        self.assertDictEqual(dict(
            worker_count=3, start=100.0, stop=152.2, req_count=13,
            retries=7, retry_rate=53.846154, errors=1,
            avg_req_per_sec=round(13 / (152.2 - 100), 6),
            first_byte_latency=dict(
                min='%6.3f' % 0.1,
                max='%7.3f' % 1.2,
                avg='%7.3f' % stats.lmean(first_byte_latency_all),
                pctile='%7.3f' % 1.2,
                std_dev='%7.3f' % stats.lsamplestdev(first_byte_latency_all),
                median='%7.3f' % stats.lmedianscore(first_byte_latency_all),
            ),
            last_byte_latency=dict(
                min='%6.3f' % 0.2,
                max='%7.3f' % 3.0,
                avg='%7.3f' % stats.lmean(last_byte_latency_all),
                pctile='%7.3f' % 3.0,
                std_dev='%7.3f' % stats.lsamplestdev(last_byte_latency_all),
                median='  0.749',  # XXX why??
                # median='%7.3f' % stats.lmedianscore(last_byte_latency_all),
            ),
            worst_first_byte_latency=(1.2, 'txID004'),
            worst_last_byte_latency=(3.0, 'txID002'),
        ), self.reporter.stats['agg_stats'])

    def test_calculate_scenario_stats_aggregate_low_pctile(self):
        first_byte_latency_all = [1, 0.1, 1.2, 0.2, 0.8, 0.1, 0.1,
                                  0.2, 1, 0.5, 0.3, 0.6]
        last_byte_latency_all = [3, 0.8, 2.2, 0.3, 2.8, 0.4, 0.2,
                                 0.5, 1.8, 0.8, 0.4, 0.699]

        self.reporter.read_results(nth_pctile=20)

        self.assertDictEqual(dict(
            worker_count=3, start=100.0, stop=152.2, req_count=13,
            retries=7, retry_rate=53.846154, errors=1,
            avg_req_per_sec=round(13 / (152.2 - 100), 6),
            first_byte_latency=dict(
                min='%6.3f' % 0.1,
                max='%7.3f' % 1.2,
                avg='%7.3f' % stats.lmean(first_byte_latency_all),
                pctile='%7.3f' % sorted(first_byte_latency_all)[2],
                std_dev='%7.3f' % stats.lsamplestdev(first_byte_latency_all),
                median='%7.3f' % stats.lmedianscore(first_byte_latency_all),
            ),
            last_byte_latency=dict(
                min='%6.3f' % 0.2,
                max='%7.3f' % 3.0,
                avg='%7.3f' % stats.lmean(last_byte_latency_all),
                pctile='%7.3f' % sorted(last_byte_latency_all)[2],
                std_dev='%7.3f' % stats.lsamplestdev(last_byte_latency_all),
                median='  0.749',  # XXX why??
                # median='%7.3f' % stats.lmedianscore(last_byte_latency_all),
            ),
            worst_first_byte_latency=(1.2, 'txID004'),
            worst_last_byte_latency=(3.0, 'txID002'),
        ), self.reporter.stats['agg_stats'])

    def test_calculate_scenario_stats_worker1(self):
        w1_first_byte_latency = [1.0, 0.1, 1.2, 0.2]
        w1_last_byte_latency = [3.0, 0.8, 2.2, 0.3]
        self.assertDictEqual(dict(
            start=100.0, stop=106.4, req_count=4,
            retries=0, retry_rate=0.0, errors=0,
            avg_req_per_sec=round(4 / (106.4 - 100), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(w1_first_byte_latency),
                max='%7.3f' % max(w1_first_byte_latency),
                avg='%7.3f' % stats.lmean(w1_first_byte_latency),
                pctile='%7.3f' % 1.2,
                std_dev='%7.3f' % stats.lsamplestdev(w1_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(w1_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(w1_last_byte_latency),
                max='%7.3f' % max(w1_last_byte_latency),
                avg='%7.3f' % stats.lmean(w1_last_byte_latency),
                pctile='%7.3f' % 3.0,
                std_dev='%7.3f' % stats.lsamplestdev(w1_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(w1_last_byte_latency),
            ),
            worst_first_byte_latency=(float(max(w1_first_byte_latency)),
                                      'txID004'),
            worst_last_byte_latency=(
                float(max(w1_last_byte_latency)), 'txID002'),
        ), self.reporter.stats['worker_stats'][1])

    def test_calculate_scenario_stats_worker2(self):
        w2_first_byte_latency = [0.8, 0.1, 0.1, 0.2]
        w2_last_byte_latency = [2.8, 0.4, 0.2, 0.5]
        self.assertDictEqual(dict(
            start=100.1, stop=152.2, req_count=5,
            retries=7, retry_rate=140.0, errors=1,
            avg_req_per_sec=round(5 / (152.2 - 100.1), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(w2_first_byte_latency),
                max='%7.3f' % max(w2_first_byte_latency),
                avg='%7.3f' % stats.lmean(w2_first_byte_latency),
                pctile='%7.3f' % 0.8,
                std_dev='%7.3f' % stats.lsamplestdev(w2_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(w2_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(w2_last_byte_latency),
                max='%7.3f' % max(w2_last_byte_latency),
                avg='%7.3f' % stats.lmean(w2_last_byte_latency),
                pctile='%7.3f' % 2.8,
                std_dev='%7.3f' % stats.lsamplestdev(w2_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(w2_last_byte_latency),
            ),
            worst_first_byte_latency=(float(max(w2_first_byte_latency)),
                                      'txID006'),
            worst_last_byte_latency=(
                float(max(w2_last_byte_latency)), 'txID006'),
        ), self.reporter.stats['worker_stats'][2])

    def test_calculate_scenario_stats_worker3(self):
        w3_first_byte_latency = [1, 0.5, 0.3, 0.6]
        w3_last_byte_latency = [1.8, 0.8, 0.4, 0.699]
        self.assertDictEqual(dict(
            start=100.1, stop=104.999, req_count=4,
            retries=0, retry_rate=0.0, errors=0,
            avg_req_per_sec=round(4 / (104.999 - 100.1), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(w3_first_byte_latency),
                max='%7.3f' % max(w3_first_byte_latency),
                avg='%7.3f' % stats.lmean(w3_first_byte_latency),
                pctile='%7.3f' % 1.0,
                std_dev='%7.3f' % stats.lsamplestdev(w3_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(w3_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(w3_last_byte_latency),
                max='%7.3f' % max(w3_last_byte_latency),
                avg='%7.3f' % stats.lmean(w3_last_byte_latency),
                pctile='%7.3f' % 1.8,
                std_dev='%7.3f' % stats.lsamplestdev(w3_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(w3_last_byte_latency),
            ),
            worst_first_byte_latency=(
                float(max(w3_first_byte_latency)), 'txID010'),
            worst_last_byte_latency=(
                float(max(w3_last_byte_latency)), 'txID010'),
        ), self.reporter.stats['worker_stats'][3])

    def test_calculate_scenario_stats_create(self):
        # Stats for Create
        c_first_byte_latency = [1, 1.2, 0.1]
        c_last_byte_latency = [3.0, 2.2, 0.2]
        self.assertDictEqual(dict(
            start=100.0, stop=106.0, req_count=3,
            retries=1, retry_rate=33.333333, errors=0,
            avg_req_per_sec=round(3 / (106 - 100.0), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(c_first_byte_latency),
                max='%7.3f' % max(c_first_byte_latency),
                pctile='%7.3f' % max(c_first_byte_latency),
                avg='%7.3f' % stats.lmean(c_first_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(c_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(c_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(c_last_byte_latency),
                max='%7.3f' % max(c_last_byte_latency),
                pctile='%7.3f' % max(c_last_byte_latency),
                avg='%7.3f' % stats.lmean(c_last_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(c_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(c_last_byte_latency),
            ),
            worst_first_byte_latency=(max(c_first_byte_latency), 'txID004'),
            worst_last_byte_latency=(max(c_last_byte_latency), 'txID002'),
            size_stats=OrderedDict([
                ('tiny', {'avg_req_per_sec': 5.0,
                          'first_byte_latency': {'avg': '%7.3f' % 0.1,
                                                 'max': '%7.3f' % 0.1,
                                                 'pctile': '%7.3f' % 0.1,
                                                 'median': '%7.3f' % 0.1,
                                                 'min': '%6.3f' % 0.1,
                                                 'std_dev': '%7.3f' % 0.0},
                          'last_byte_latency': {'avg': '%7.3f' % 0.2,
                                                'max': '%7.3f' % 0.2,
                                                'pctile': '%7.3f' % 0.2,
                                                'median': '%7.3f' % 0.2,
                                                'min': '%6.3f' % 0.2,
                                                'std_dev': '%7.3f' % 0.0},
                          'worst_first_byte_latency': (0.1, 'txID008'),
                          'worst_last_byte_latency': (0.2, 'txID008'),
                          'req_count': 1,
                          'retries': 1,
                          'retry_rate': 100.0,
                          'errors': 0,
                          'start': 103.3,
                          'stop': 103.5}),
                ('small', {'avg_req_per_sec': 0.333333,
                           'first_byte_latency': {'avg': '%7.3f' % 1.0,
                                                  'max': '%7.3f' % 1.0,
                                                  'pctile': '%7.3f' % 1.0,
                                                  'median': '%7.3f' % 1.0,
                                                  'min': '%6.3f' % 1.0,
                                                  'std_dev': '%7.3f' % 0.0},
                           'last_byte_latency': {'avg': '%7.3f' % 3.0,
                                                 'max': '%7.3f' % 3.0,
                                                 'pctile': '%7.3f' % 3.0,
                                                 'median': '%7.3f' % 3.0,
                                                 'min': '%6.3f' % 3.0,
                                                 'std_dev': '%7.3f' % 0.0},
                           'worst_first_byte_latency': (1.0, 'txID002'),
                           'worst_last_byte_latency': (3.0, 'txID002'),
                           'req_count': 1,
                           'retries': 0,
                           'retry_rate': 0.0,
                           'errors': 0,
                           'start': 100.0,
                           'stop': 103.0}),
                ('huge', {'avg_req_per_sec': 0.454545,
                          'first_byte_latency': {'avg': '%7.3f' % 1.2,
                                                 'max': '%7.3f' % 1.2,
                                                 'pctile': '%7.3f' % 1.2,
                                                 'median': '%7.3f' % 1.2,
                                                 'min': '%6.3f' % 1.2,
                                                 'std_dev': '%7.3f' % 0.0},
                          'last_byte_latency': {'avg': '%7.3f' % 2.2,
                                                'max': '%7.3f' % 2.2,
                                                'pctile': '%7.3f' % 2.2,
                                                'median': '%7.3f' % 2.2,
                                                'min': '%6.3f' % 2.2,
                                                'std_dev': '%7.3f' % 0.0},
                          'worst_first_byte_latency': (1.2, 'txID004'),
                          'worst_last_byte_latency': (2.2, 'txID004'),
                          'req_count': 1,
                          'retries': 0,
                          'retry_rate': 0.0,
                          'errors': 0,
                          'start': 103.8,
                          'stop': 106.0})]),
        ), self.reporter.stats['op_stats'][ssbench.CREATE_OBJECT])

    def test_calculate_scenario_stats_read(self):
        # Stats for Read
        r_first_byte_latency = [0.1, 0.2, 1.0, 0.3]
        r_last_byte_latency = [0.8, 0.5, 1.8, 0.4]
        self.assertDictEqual(dict(
            start=100.1, stop=104.3, req_count=4,
            retries=0, retry_rate=0.0, errors=0,
            avg_req_per_sec=round(4 / (104.3 - 100.1), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(r_first_byte_latency),
                max='%7.3f' % max(r_first_byte_latency),
                pctile='%7.3f' % max(r_first_byte_latency),
                avg='%7.3f' % stats.lmean(r_first_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(r_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(r_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(r_last_byte_latency),
                max='%7.3f' % max(r_last_byte_latency),
                pctile='%7.3f' % max(r_last_byte_latency),
                avg='%7.3f' % stats.lmean(r_last_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(r_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(r_last_byte_latency),
            ),
            worst_first_byte_latency=(max(r_first_byte_latency), 'txID010'),
            worst_last_byte_latency=(max(r_last_byte_latency), 'txID010'),
            size_stats=OrderedDict([
                ('tiny', {'avg_req_per_sec': 0.540541,
                          'first_byte_latency': {'avg': '%7.3f' % 0.55,
                                                 'max': '%7.3f' % 1.0,
                                                 'pctile': '%7.3f' % 1.0,
                                                 'median': '%7.3f' % 0.55,
                                                 'min': '%6.3f' % 0.1,
                                                 'std_dev': '%7.3f' % 0.45},
                          'last_byte_latency': {'avg': '%7.3f' % 1.3,
                                                'max': '%7.3f' % 1.8,
                                                'pctile': '%7.3f' % 1.8,
                                                'median': '%7.3f' % 1.3,
                                                'min': '%6.3f' % 0.8,
                                                'std_dev': '%7.3f' % 0.5},
                          'worst_first_byte_latency': (1.0, 'txID010'),
                          'worst_last_byte_latency': (1.8, 'txID010'),
                          'req_count': 2,
                          'retries': 0,
                          'retry_rate': 0.0,
                          'errors': 0,
                          'start': 100.1,
                          'stop': 103.8}),
                ('small', {'avg_req_per_sec': 2.0,
                           'first_byte_latency': {'avg': '%7.3f' % 0.2,
                                                  'max': '%7.3f' % 0.2,
                                                  'pctile': '%7.3f' % 0.2,
                                                  'median': '%7.3f' % 0.2,
                                                  'min': '%6.3f' % 0.2,
                                                  'std_dev': '%7.3f' % 0.0},
                           'last_byte_latency': {'avg': '%7.3f' % 0.5,
                                                 'max': '%7.3f' % 0.5,
                                                 'pctile': '%7.3f' % 0.5,
                                                 'median': '%7.3f' % 0.5,
                                                 'min': '%6.3f' % 0.5,
                                                 'std_dev': '%7.3f' % 0.0},
                           'worst_first_byte_latency': (0.2, 'txID009'),
                           'worst_last_byte_latency': (0.5, 'txID009'),
                           'req_count': 1,
                           'retries': 0,
                           'retry_rate': 0.0,
                           'errors': 0,
                           'start': 103.5,
                           'stop': 104.0}),
                ('medium', {'avg_req_per_sec': 2.5,
                            'first_byte_latency': {'avg': '%7.3f' % 0.3,
                                                   'max': '%7.3f' % 0.3,
                                                   'pctile': '%7.3f' % 0.3,
                                                   'median': '%7.3f' % 0.3,
                                                   'min': '%6.3f' % 0.3,
                                                   'std_dev': '%7.3f' % 0.0},
                            'last_byte_latency': {'avg': '%7.3f' % 0.4,
                                                  'max': '%7.3f' % 0.4,
                                                  'pctile': '%7.3f' % 0.4,
                                                  'median': '%7.3f' % 0.4,
                                                  'min': '%6.3f' % 0.4,
                                                  'std_dev': '%7.3f' % 0.0},
                            'worst_first_byte_latency': (0.3, 'txID012'),
                            'worst_last_byte_latency': (0.4, 'txID012'),
                            'req_count': 1,
                            'retries': 0,
                            'retry_rate': 0.0,
                            'errors': 0,
                            'start': 103.9,
                            'stop': 104.3})]),
        ), self.reporter.stats['op_stats'][ssbench.READ_OBJECT])

    def test_calculate_scenario_stats_update(self):
        u_first_byte_latency = [0.2, 0.8, 0.6]
        u_last_byte_latency = [0.3, 2.8, 0.699]
        self.assertDictEqual(dict(
            start=100.1, stop=152.2, req_count=4,
            retries=6, retry_rate=150.0, errors=1,
            avg_req_per_sec=round(4 / (152.2 - 100.1), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(u_first_byte_latency),
                max='%7.3f' % max(u_first_byte_latency),
                avg='%7.3f' % stats.lmean(u_first_byte_latency),
                pctile='%7.3f' % 0.8,
                std_dev='%7.3f' % stats.lsamplestdev(u_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(u_first_byte_latency),
            ),
            worst_first_byte_latency=(max(u_first_byte_latency), 'txID006'),
            last_byte_latency=dict(
                min='%6.3f' % min(u_last_byte_latency),
                max='%7.3f' % max(u_last_byte_latency),
                avg='%7.3f' % stats.lmean(u_last_byte_latency),
                pctile='%7.3f' % 2.8,
                std_dev='%7.3f' % stats.lsamplestdev(u_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(u_last_byte_latency),
            ),
            worst_last_byte_latency=(max(u_last_byte_latency), 'txID006'),
            size_stats=OrderedDict([
                ('tiny', {'avg_req_per_sec': 1.430615,
                          'first_byte_latency': {'avg': '%7.3f' % 0.6,
                                                 'pctile': '%7.3f' % 0.6,
                                                 'max': '%7.3f' % 0.6,
                                                 'median': '%7.3f' % 0.6,
                                                 'min': '%6.3f' % 0.6,
                                                 'std_dev': '%7.3f' % 0.0},
                          'worst_first_byte_latency': (0.6, 'txID013'),
                          'last_byte_latency': {'avg': '%7.3f' % 0.699,
                                                'pctile': '%7.3f' % 0.699,
                                                'max': '%7.3f' % 0.699,
                                                'median': '%7.3f' % 0.699,
                                                'min': '%6.3f' % 0.699,
                                                'std_dev': '%7.3f' % 0.0},
                          'worst_last_byte_latency': (0.699, 'txID013'),
                          'req_count': 1,
                          'retries': 0,
                          'retry_rate': 0.0,
                          'errors': 0,
                          'start': 104.3,
                          'stop': 104.999}),
                ('medium', {'avg_req_per_sec': 0.357143,
                            'first_byte_latency': {'avg': '%7.3f' % 0.8,
                                                   'pctile': '%7.3f' % 0.8,
                                                   'max': '%7.3f' % 0.8,
                                                   'median': '%7.3f' % 0.8,
                                                   'min': '%6.3f' % 0.8,
                                                   'std_dev': '%7.3f' % 0.0},
                            'worst_first_byte_latency': (0.8, 'txID006'),
                            'last_byte_latency': {'avg': '%7.3f' % 2.8,
                                                  'pctile': '%7.3f' % 2.8,
                                                  'max': '%7.3f' % 2.8,
                                                  'median': '%7.3f' % 2.8,
                                                  'min': '%6.3f' % 2.8,
                                                  'std_dev': '%7.3f' % 0.0},
                            'worst_last_byte_latency': (2.8, 'txID006'),
                            'req_count': 1,
                            'retries': 1,
                            'retry_rate': 100.0,
                            'errors': 0,
                            'start': 100.1,
                            'stop': 102.9}),
                ('large', {'avg_req_per_sec': 0.043384,
                           'first_byte_latency': {'avg': '%7.3f' % 0.2,
                                                  'pctile': '%7.3f' % 0.2,
                                                  'max': '%7.3f' % 0.2,
                                                  'median': '%7.3f' % 0.2,
                                                  'min': '%6.3f' % 0.2,
                                                  'std_dev': '%7.3f' % 0.0},
                           'worst_first_byte_latency': (0.2, 'txID005'),
                           'last_byte_latency': {'avg': '%7.3f' % 0.3,
                                                 'pctile': '%7.3f' % 0.3,
                                                 'max': '%7.3f' % 0.3,
                                                 'median': '%7.3f' % 0.3,
                                                 'min': '%6.3f' % 0.3,
                                                 'std_dev': '%7.3f' % 0.0},
                           'worst_last_byte_latency': (0.3, 'txID005'),
                           'req_count': 2,
                           'retries': 5,
                           'retry_rate': 250.0,
                           'errors': 1,
                           'start': 106.1,
                           'stop': 152.2})]),
        ), self.reporter.stats['op_stats'][ssbench.UPDATE_OBJECT])

    def test_calculate_scenario_stats_delete(self):
        d_first_byte_latency = [0.1, 0.5]
        d_last_byte_latency = [0.4, 0.8]
        self.assertDictEqual(dict(
            start=102.9, stop=103.9, req_count=2,
            retries=0, retry_rate=0.0, errors=0,
            avg_req_per_sec=round(2 / (103.9 - 102.9), 6),
            first_byte_latency=dict(
                min='%6.3f' % min(d_first_byte_latency),
                max='%7.3f' % max(d_first_byte_latency),
                pctile='%7.3f' % max(d_first_byte_latency),
                avg='%7.3f' % stats.lmean(d_first_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(d_first_byte_latency),
                median='%7.3f' % stats.lmedianscore(d_first_byte_latency),
            ),
            last_byte_latency=dict(
                min='%6.3f' % min(d_last_byte_latency),
                max='%7.3f' % max(d_last_byte_latency),
                pctile='%7.3f' % max(d_last_byte_latency),
                avg='%7.3f' % stats.lmean(d_last_byte_latency),
                std_dev='%7.3f' % stats.lsamplestdev(d_last_byte_latency),
                median='%7.3f' % stats.lmedianscore(d_last_byte_latency),
            ),
            worst_first_byte_latency=(max(d_first_byte_latency), 'txID011'),
            worst_last_byte_latency=(max(d_last_byte_latency), 'txID011'),
            size_stats=OrderedDict([
                ('small', {'avg_req_per_sec': 1.25,
                           'first_byte_latency': {'avg': '%7.3f' % 0.5,
                                                  'max': '%7.3f' % 0.5,
                                                  'pctile': '%7.3f' % 0.5,
                                                  'median': '%7.3f' % 0.5,
                                                  'min': '%6.3f' % 0.5,
                                                  'std_dev': '%7.3f' % 0.0},
                           'last_byte_latency': {'avg': '%7.3f' % 0.8,
                                                 'max': '%7.3f' % 0.8,
                                                 'pctile': '%7.3f' % 0.8,
                                                 'median': '%7.3f' % 0.8,
                                                 'min': '%6.3f' % 0.8,
                                                 'std_dev': '%7.3f' % 0.0},
                           'worst_first_byte_latency': (0.5, 'txID011'),
                           'worst_last_byte_latency': (0.8, 'txID011'),
                           'req_count': 1,
                           'retries': 0,
                           'retry_rate': 0.0,
                           'errors': 0,
                           'start': 103.1,
                           'stop': 103.9}),
                ('large', {'avg_req_per_sec': 2.5,
                           'first_byte_latency': {'avg': '%7.3f' % 0.1,
                                                  'max': '%7.3f' % 0.1,
                                                  'pctile': '%7.3f' % 0.1,
                                                  'median': '%7.3f' % 0.1,
                                                  'min': '%6.3f' % 0.1,
                                                  'std_dev': '%7.3f' % 0.0},
                           'last_byte_latency': {'avg': '%7.3f' % 0.4,
                                                 'max': '%7.3f' % 0.4,
                                                 'pctile': '%7.3f' % 0.4,
                                                 'median': '%7.3f' % 0.4,
                                                 'min': '%6.3f' % 0.4,
                                                 'std_dev': '%7.3f' % 0.0},
                           'worst_first_byte_latency': (0.1, 'txID007'),
                           'worst_last_byte_latency': (0.4, 'txID007'),
                           'req_count': 1,
                           'retries': 0,
                           'retry_rate': 0.0,
                           'errors': 0,
                           'start': 102.9,
                           'stop': 103.3})]),
        ), self.reporter.stats['op_stats'][ssbench.DELETE_OBJECT])

    def test_calculate_scenario_size_stats(self):
        self.assertDictEqual(OrderedDict([
            ('tiny', {'avg_req_per_sec': 0.816493,
                      'first_byte_latency': {'avg': '%7.3f' % 0.45,
                                             'max': '%7.3f' % 1.0,
                                             'pctile': '%7.3f' % 1.0,
                                             'median': '%7.3f' % 0.35,
                                             'min': '%6.3f' % 0.1,
                                             'std_dev': '%7.3f' % 0.377492},
                      'last_byte_latency': {'avg': '%7.3f' % 0.87475,
                                            'max': '%7.3f' % 1.8,
                                            'pctile': '%7.3f' % 1.8,
                                            'median': '%7.3f' % 0.7494,
                                            'min': '%6.3f' % 0.2,
                                            'std_dev': '%7.3f' % 0.580485},
                      'worst_first_byte_latency': (1.0, 'txID010'),
                      'worst_last_byte_latency': (1.8, 'txID010'),
                      'req_count': 4,
                      'retries': 1,
                      'retry_rate': 25.0,
                      'errors': 0,
                      'start': 100.1,
                      'stop': 104.999}),
            ('small', {'avg_req_per_sec': 0.75,
                       'first_byte_latency': {'avg': '%7.3f' % 0.566667,
                                              'max': '%7.3f' % 1.0,
                                              'pctile': '%7.3f' % 1.0,
                                              'median': '%7.3f' % 0.5,
                                              'min': '%6.3f' % 0.2,
                                              'std_dev': '%7.3f' % 0.329983},
                       'last_byte_latency': {'avg': '%7.3f' % 1.433333,
                                             'max': '%7.3f' % 3.0,
                                             'pctile': '%7.3f' % 3.0,
                                             'median': '%7.3f' % 0.8,
                                             'min': '%6.3f' % 0.5,
                                             'std_dev': '%7.3f' % 1.11455},
                       'worst_first_byte_latency': (1.0, 'txID002'),
                       'worst_last_byte_latency': (3.0, 'txID002'),
                       'req_count': 3,
                       'retries': 0,
                       'retry_rate': 0.0,
                       'errors': 0,
                       'start': 100.0,
                       'stop': 104.0}),
            ('medium', {'avg_req_per_sec': 0.47619,
                        'first_byte_latency': {'avg': '%7.3f' % 0.55,
                                               'max': '%7.3f' % 0.8,
                                               'pctile': '%7.3f' % 0.8,
                                               'median': '%7.3f' % 0.55,
                                               'min': '%6.3f' % 0.3,
                                               'std_dev': '%7.3f' % 0.25},
                        'last_byte_latency': {'avg': '%7.3f' % 1.6,
                                              'max': '%7.3f' % 2.8,
                                              'pctile': '%7.3f' % 2.8,
                                              'median': '%7.3f' % 1.6,
                                              'min': '%6.3f' % 0.4,
                                              'std_dev': '%7.3f' % 1.2},
                        'worst_first_byte_latency': (0.8, 'txID006'),
                        'worst_last_byte_latency': (2.8, 'txID006'),
                        'req_count': 2,
                        'retries': 1,
                        'retry_rate': 50.0,
                        'errors': 0,
                        'start': 100.1,
                        'stop': 104.3}),
            ('large', {'avg_req_per_sec': 0.060852,
                       'first_byte_latency': {'avg': '%7.3f' % 0.15,
                                              'max': '%7.3f' % 0.2,
                                              'pctile': '%7.3f' % 0.2,
                                              'median': '%7.3f' % 0.15,
                                              'min': '%6.3f' % 0.1,
                                              'std_dev': '%7.3f' % 0.05},
                       'last_byte_latency': {'avg': '%7.3f' % 0.35,
                                             'max': '%7.3f' % 0.4,
                                             'pctile': '%7.3f' % 0.4,
                                             'median': '%7.3f' % 0.35,
                                             'min': '%6.3f' % 0.3,
                                             'std_dev': '%7.3f' % 0.05},
                       'worst_first_byte_latency': (0.2, 'txID005'),
                       'worst_last_byte_latency': (0.4, 'txID007'),
                       'req_count': 3,
                       'retries': 5,
                       'retry_rate': 166.666667,
                       'errors': 1,
                       'start': 102.9,
                       'stop': 152.2}),
            ('huge', {'avg_req_per_sec': 0.454545,
                      'first_byte_latency': {'avg': '%7.3f' % 1.2,
                                             'max': '%7.3f' % 1.2,
                                             'pctile': '%7.3f' % 1.2,
                                             'median': '%7.3f' % 1.2,
                                             'min': '%6.3f' % 1.2,
                                             'std_dev': '%7.3f' % 0.0},
                      'last_byte_latency': {'avg': '%7.3f' % 2.2,
                                            'max': '%7.3f' % 2.2,
                                            'pctile': '%7.3f' % 2.2,
                                            'median': '%7.3f' % 2.2,
                                            'min': '%6.3f' % 2.2,
                                            'std_dev': '%7.3f' % 0.0},
                      'worst_first_byte_latency': (1.2, 'txID004'),
                      'worst_last_byte_latency': (2.2, 'txID004'),
                      'req_count': 1,
                      'retries': 0,
                      'retry_rate': 0.0,
                      'errors': 0,
                      'start': 103.8,
                      'stop': 106.0})]),
            self.reporter.stats['size_stats'])

    def test_calculate_scenario_stats_time_series(self):
        # Time series (reqs completed each second
        self.assertDictEqual(dict(
            start=101,
            start_time=99.19999999999999,
            stop=106,
            data=[1, 1, 5, 3, 0, 2],
        ), self.reporter.stats['time_series'])

    def test_write_rps_histogram(self):
        # Write out time series data (requests-per-second histogram) to an
        # already open CSV file

        test_csv_file = StringIO()
        self.reporter.write_rps_histogram(test_csv_file)
        test_csv_file.seek(0)
        reader = csv.reader(test_csv_file)
        self.assertListEqual([
            ["Seconds Since Start", "Requests Completed"],
            ['1', '1'],
            ['2', '1'],
            ['3', '5'],
            ['4', '3'],
            ['5', '0'],
            ['6', '2'],
        ], list(reader))

    def test_generate_default_report(self):
        # Time series (reqs completed each second
        self.scenario.version = '0.2.14'
        self.reporter.read_results(nth_pctile=50)

        self.assertListEqual(u"""
Reporter Test Scenario - ablkei  (generated with ssbench version 0.2.14)
Worker count:   3   Concurrency:   2  Ran 1970-01-01 00:01:39 UTC to 1970-01-01 00:01:46 UTC (7s)

% Ops    C   R   U   D       Size Range       Size Name
 20%   % 50  30  10  10       99  B - 100  B  tiny
 27%   % 71   9  12   8        2 kB           small
 34%   % 50  30  10  10        3 kB -   3 kB  medium
  0%   % 50  30  10  10       10 MB           unused
 14%   % 16  61   7  16      399 kB - 400 kB  large
  5%   % 50  30  10  10       50 MB -  71 MB  huge
---------------------------------------------------------------------
         51  29  10  10      CRUD weighted average

TOTAL
       Count:    13 (    1 error;     7 retries: 53.85%)  Average requests per second:   0.2
                            min       max      avg      std_dev  50%-ile                   Worst latency TX ID
       First-byte latency:  0.100 -   1.200    0.508  (  0.386)    0.400  (all obj sizes)  txID004
       Last-byte  latency:  0.200 -   3.000    1.158  (  0.970)    0.749  (all obj sizes)  txID002
       First-byte latency:  0.100 -   1.000    0.450  (  0.377)    0.350  (    tiny objs)  txID010
       Last-byte  latency:  0.200 -   1.800    0.875  (  0.580)    0.749  (    tiny objs)  txID010
       First-byte latency:  0.200 -   1.000    0.567  (  0.330)    0.500  (   small objs)  txID002
       Last-byte  latency:  0.500 -   3.000    1.433  (  1.115)    0.800  (   small objs)  txID002
       First-byte latency:  0.300 -   0.800    0.550  (  0.250)    0.550  (  medium objs)  txID006
       Last-byte  latency:  0.400 -   2.800    1.600  (  1.200)    1.600  (  medium objs)  txID006
       First-byte latency:  0.100 -   0.200    0.150  (  0.050)    0.150  (   large objs)  txID005
       Last-byte  latency:  0.300 -   0.400    0.350  (  0.050)    0.350  (   large objs)  txID007
       First-byte latency:  1.200 -   1.200    1.200  (  0.000)    1.200  (    huge objs)  txID004
       Last-byte  latency:  2.200 -   2.200    2.200  (  0.000)    2.200  (    huge objs)  txID004

CREATE
       Count:     3 (    0 error;     1 retries: 33.33%)  Average requests per second:   0.5
                            min       max      avg      std_dev  50%-ile                   Worst latency TX ID
       First-byte latency:  0.100 -   1.200    0.767  (  0.478)    1.000  (all obj sizes)  txID004
       Last-byte  latency:  0.200 -   3.000    1.800  (  1.178)    2.200  (all obj sizes)  txID002
       First-byte latency:  0.100 -   0.100    0.100  (  0.000)    0.100  (    tiny objs)  txID008
       Last-byte  latency:  0.200 -   0.200    0.200  (  0.000)    0.200  (    tiny objs)  txID008
       First-byte latency:  1.000 -   1.000    1.000  (  0.000)    1.000  (   small objs)  txID002
       Last-byte  latency:  3.000 -   3.000    3.000  (  0.000)    3.000  (   small objs)  txID002
       First-byte latency:  1.200 -   1.200    1.200  (  0.000)    1.200  (    huge objs)  txID004
       Last-byte  latency:  2.200 -   2.200    2.200  (  0.000)    2.200  (    huge objs)  txID004

READ
       Count:     4 (    0 error;     0 retries:  0.00%)  Average requests per second:   1.0
                            min       max      avg      std_dev  50%-ile                   Worst latency TX ID
       First-byte latency:  0.100 -   1.000    0.400  (  0.354)    0.250  (all obj sizes)  txID010
       Last-byte  latency:  0.400 -   1.800    0.875  (  0.554)    0.650  (all obj sizes)  txID010
       First-byte latency:  0.100 -   1.000    0.550  (  0.450)    0.550  (    tiny objs)  txID010
       Last-byte  latency:  0.800 -   1.800    1.300  (  0.500)    1.300  (    tiny objs)  txID010
       First-byte latency:  0.200 -   0.200    0.200  (  0.000)    0.200  (   small objs)  txID009
       Last-byte  latency:  0.500 -   0.500    0.500  (  0.000)    0.500  (   small objs)  txID009
       First-byte latency:  0.300 -   0.300    0.300  (  0.000)    0.300  (  medium objs)  txID012
       Last-byte  latency:  0.400 -   0.400    0.400  (  0.000)    0.400  (  medium objs)  txID012

UPDATE
       Count:     4 (    1 error;     6 retries: 150.00%)  Average requests per second:   0.1
                            min       max      avg      std_dev  50%-ile                   Worst latency TX ID
       First-byte latency:  0.200 -   0.800    0.533  (  0.249)    0.600  (all obj sizes)  txID006
       Last-byte  latency:  0.300 -   2.800    1.266  (  1.097)    0.699  (all obj sizes)  txID006
       First-byte latency:  0.600 -   0.600    0.600  (  0.000)    0.600  (    tiny objs)  txID013
       Last-byte  latency:  0.699 -   0.699    0.699  (  0.000)    0.699  (    tiny objs)  txID013
       First-byte latency:  0.800 -   0.800    0.800  (  0.000)    0.800  (  medium objs)  txID006
       Last-byte  latency:  2.800 -   2.800    2.800  (  0.000)    2.800  (  medium objs)  txID006
       First-byte latency:  0.200 -   0.200    0.200  (  0.000)    0.200  (   large objs)  txID005
       Last-byte  latency:  0.300 -   0.300    0.300  (  0.000)    0.300  (   large objs)  txID005

DELETE
       Count:     2 (    0 error;     0 retries:  0.00%)  Average requests per second:   2.0
                            min       max      avg      std_dev  50%-ile                   Worst latency TX ID
       First-byte latency:  0.100 -   0.500    0.300  (  0.200)    0.300  (all obj sizes)  txID011
       Last-byte  latency:  0.400 -   0.800    0.600  (  0.200)    0.600  (all obj sizes)  txID011
       First-byte latency:  0.500 -   0.500    0.500  (  0.000)    0.500  (   small objs)  txID011
       Last-byte  latency:  0.800 -   0.800    0.800  (  0.000)    0.800  (   small objs)  txID011
       First-byte latency:  0.100 -   0.100    0.100  (  0.000)    0.100  (   large objs)  txID007
       Last-byte  latency:  0.400 -   0.400    0.400  (  0.000)    0.400  (   large objs)  txID007

Distribution of requests per worker-ID:  4.000 -   5.000 (avg:   4.333; stddev:   0.471)
""".split('\n'), self.reporter.generate_default_report().split('\n'))

    def test_generate_default_report_csv(self):
        # Time series (reqs completed each second
        self.scenario.version = '0.2.14'
        # (When generating CSV data, we'll also be passing in
        # format_numbers=False)
        self.reporter.read_results(nth_pctile=50, format_numbers=False)

        csv_text = self.reporter.generate_default_report(output_csv=True)
        csv_reader = csv.DictReader(csv_text.splitlines())
        csv_data = list(csv_reader)
        self.assertListEqual([{
            'scenario_name': 'Reporter Test Scenario - ablkei',
            'ssbench_version': '0.2.14',
            'worker_count': '3',
            'concurrency': '2',
            'start_time': '1970-01-01 00:01:39 UTC',
            'stop_time': '1970-01-01 00:01:46 UTC',
            'duration': '6.800000000000011',
            'total_count': '13',
            'total_avg_req_per_s': '0.249042',
            'total_first_all_min': '0.1',
            'total_first_all_max': '1.2',
            'total_first_all_avg': '0.508333',
            'total_first_all_std_dev': '0.386131',
            'total_first_all_50_pctile': '0.4',
            'total_first_all_worst_txid': 'txID004',
            'total_last_all_min': '0.2',
            'total_last_all_max': '3.0',
            'total_last_all_avg': '1.15825',
            'total_last_all_std_dev': '0.969969',
            'total_last_all_50_pctile': '0.7495',
            'total_last_all_worst_txid': 'txID002',
            'total_first_tiny_min': '0.1',
            'total_first_tiny_max': '1.0',
            'total_first_tiny_avg': '0.45',
            'total_first_tiny_std_dev': '0.377492',
            'total_first_tiny_50_pctile': '0.35',
            'total_first_tiny_worst_txid': 'txID010',
            'total_last_tiny_min': '0.2',
            'total_last_tiny_max': '1.8',
            'total_last_tiny_avg': '0.87475',
            'total_last_tiny_std_dev': '0.580485',
            'total_last_tiny_50_pctile': '0.7495',
            'total_last_tiny_worst_txid': 'txID010',
            'total_first_small_min': '0.2',
            'total_first_small_max': '1.0',
            'total_first_small_avg': '0.566667',
            'total_first_small_std_dev': '0.329983',
            'total_first_small_50_pctile': '0.5',
            'total_first_small_worst_txid': 'txID002',
            'total_last_small_min': '0.5',
            'total_last_small_max': '3.0',
            'total_last_small_avg': '1.433333',
            'total_last_small_std_dev': '1.11455',
            'total_last_small_50_pctile': '0.8',
            'total_last_small_worst_txid': 'txID002',
            'total_first_medium_min': '0.3',
            'total_first_medium_max': '0.8',
            'total_first_medium_avg': '0.55',
            'total_first_medium_std_dev': '0.25',
            'total_first_medium_50_pctile': '0.55',
            'total_first_medium_worst_txid': 'txID006',
            'total_last_medium_min': '0.4',
            'total_last_medium_max': '2.8',
            'total_last_medium_avg': '1.6',
            'total_last_medium_std_dev': '1.2',
            'total_last_medium_50_pctile': '1.6',
            'total_last_medium_worst_txid': 'txID006',
            'total_first_large_min': '0.1',
            'total_first_large_max': '0.2',
            'total_first_large_avg': '0.15',
            'total_first_large_std_dev': '0.05',
            'total_first_large_50_pctile': '0.15',
            'total_first_large_worst_txid': 'txID005',
            'total_last_large_min': '0.3',
            'total_last_large_max': '0.4',
            'total_last_large_avg': '0.35',
            'total_last_large_std_dev': '0.05',
            'total_last_large_50_pctile': '0.35',
            'total_last_large_worst_txid': 'txID007',
            'total_first_huge_min': '1.2',
            'total_first_huge_max': '1.2',
            'total_first_huge_avg': '1.2',
            'total_first_huge_std_dev': '0.0',
            'total_first_huge_50_pctile': '1.2',
            'total_first_huge_worst_txid': 'txID004',
            'total_last_huge_min': '2.2',
            'total_last_huge_max': '2.2',
            'total_last_huge_avg': '2.2',
            'total_last_huge_std_dev': '0.0',
            'total_last_huge_50_pctile': '2.2',
            'total_last_huge_worst_txid': 'txID004',
            'create_count': '3',
            'create_avg_req_per_s': '0.5',
            'create_first_all_min': '0.1',
            'create_first_all_max': '1.2',
            'create_first_all_avg': '0.766667',
            'create_first_all_std_dev': '0.478423',
            'create_first_all_50_pctile': '1.0',
            'create_first_all_worst_txid': 'txID004',
            'create_last_all_min': '0.2',
            'create_last_all_max': '3.0',
            'create_last_all_avg': '1.8',
            'create_last_all_std_dev': '1.177568',
            'create_last_all_50_pctile': '2.2',
            'create_last_all_worst_txid': 'txID002',
            'create_first_tiny_min': '0.1',
            'create_first_tiny_max': '0.1',
            'create_first_tiny_avg': '0.1',
            'create_first_tiny_std_dev': '0.0',
            'create_first_tiny_50_pctile': '0.1',
            'create_first_tiny_worst_txid': 'txID008',
            'create_last_tiny_min': '0.2',
            'create_last_tiny_max': '0.2',
            'create_last_tiny_avg': '0.2',
            'create_last_tiny_std_dev': '0.0',
            'create_last_tiny_50_pctile': '0.2',
            'create_last_tiny_worst_txid': 'txID008',
            'create_first_small_min': '1.0',
            'create_first_small_max': '1.0',
            'create_first_small_avg': '1.0',
            'create_first_small_std_dev': '0.0',
            'create_first_small_50_pctile': '1.0',
            'create_first_small_worst_txid': 'txID002',
            'create_last_small_min': '3.0',
            'create_last_small_max': '3.0',
            'create_last_small_avg': '3.0',
            'create_last_small_std_dev': '0.0',
            'create_last_small_50_pctile': '3.0',
            'create_last_small_worst_txid': 'txID002',
            'create_first_huge_min': '1.2',
            'create_first_huge_max': '1.2',
            'create_first_huge_avg': '1.2',
            'create_first_huge_std_dev': '0.0',
            'create_first_huge_50_pctile': '1.2',
            'create_first_huge_worst_txid': 'txID004',
            'create_last_huge_min': '2.2',
            'create_last_huge_max': '2.2',
            'create_last_huge_avg': '2.2',
            'create_last_huge_std_dev': '0.0',
            'create_last_huge_50_pctile': '2.2',
            'create_last_huge_worst_txid': 'txID004',
            'read_count': '4',
            'read_avg_req_per_s': '0.952381',
            'read_first_all_min': '0.1',
            'read_first_all_max': '1.0',
            'read_first_all_avg': '0.4',
            'read_first_all_std_dev': '0.353553',
            'read_first_all_50_pctile': '0.25',
            'read_first_all_worst_txid': 'txID010',
            'read_last_all_min': '0.4',
            'read_last_all_max': '1.8',
            'read_last_all_avg': '0.875',
            'read_last_all_std_dev': '0.553963',
            'read_last_all_50_pctile': '0.65',
            'read_last_all_worst_txid': 'txID010',
            'read_first_tiny_min': '0.1',
            'read_first_tiny_max': '1.0',
            'read_first_tiny_avg': '0.55',
            'read_first_tiny_std_dev': '0.45',
            'read_first_tiny_50_pctile': '0.55',
            'read_first_tiny_worst_txid': 'txID010',
            'read_last_tiny_min': '0.8',
            'read_last_tiny_max': '1.8',
            'read_last_tiny_avg': '1.3',
            'read_last_tiny_std_dev': '0.5',
            'read_last_tiny_50_pctile': '1.3',
            'read_last_tiny_worst_txid': 'txID010',
            'read_first_small_min': '0.2',
            'read_first_small_max': '0.2',
            'read_first_small_avg': '0.2',
            'read_first_small_std_dev': '0.0',
            'read_first_small_50_pctile': '0.2',
            'read_first_small_worst_txid': 'txID009',
            'read_last_small_min': '0.5',
            'read_last_small_max': '0.5',
            'read_last_small_avg': '0.5',
            'read_last_small_std_dev': '0.0',
            'read_last_small_50_pctile': '0.5',
            'read_last_small_worst_txid': 'txID009',
            'read_first_medium_min': '0.3',
            'read_first_medium_max': '0.3',
            'read_first_medium_avg': '0.3',
            'read_first_medium_std_dev': '0.0',
            'read_first_medium_50_pctile': '0.3',
            'read_first_medium_worst_txid': 'txID012',
            'read_last_medium_min': '0.4',
            'read_last_medium_max': '0.4',
            'read_last_medium_avg': '0.4',
            'read_last_medium_std_dev': '0.0',
            'read_last_medium_50_pctile': '0.4',
            'read_last_medium_worst_txid': 'txID012',
            'update_count': '4',
            'update_avg_req_per_s': '0.076775',
            'update_first_all_min': '0.2',
            'update_first_all_max': '0.8',
            'update_first_all_avg': '0.533333',
            'update_first_all_std_dev': '0.249444',
            'update_first_all_50_pctile': '0.6',
            'update_first_all_worst_txid': 'txID006',
            'update_last_all_min': '0.3',
            'update_last_all_max': '2.8',
            'update_last_all_avg': '1.266333',
            'update_last_all_std_dev': '1.096631',
            'update_last_all_50_pctile': '0.699',
            'update_last_all_worst_txid': 'txID006',
            'update_first_tiny_min': '0.6',
            'update_first_tiny_max': '0.6',
            'update_first_tiny_avg': '0.6',
            'update_first_tiny_std_dev': '0.0',
            'update_first_tiny_50_pctile': '0.6',
            'update_first_tiny_worst_txid': 'txID013',
            'update_last_tiny_min': '0.699',
            'update_last_tiny_max': '0.699',
            'update_last_tiny_avg': '0.699',
            'update_last_tiny_std_dev': '0.0',
            'update_last_tiny_50_pctile': '0.699',
            'update_last_tiny_worst_txid': 'txID013',
            'update_first_medium_min': '0.8',
            'update_first_medium_max': '0.8',
            'update_first_medium_avg': '0.8',
            'update_first_medium_std_dev': '0.0',
            'update_first_medium_50_pctile': '0.8',
            'update_first_medium_worst_txid': 'txID006',
            'update_last_medium_min': '2.8',
            'update_last_medium_max': '2.8',
            'update_last_medium_avg': '2.8',
            'update_last_medium_std_dev': '0.0',
            'update_last_medium_50_pctile': '2.8',
            'update_last_medium_worst_txid': 'txID006',
            'update_first_large_min': '0.2',
            'update_first_large_max': '0.2',
            'update_first_large_avg': '0.2',
            'update_first_large_std_dev': '0.0',
            'update_first_large_50_pctile': '0.2',
            'update_first_large_worst_txid': 'txID005',
            'update_last_large_min': '0.3',
            'update_last_large_max': '0.3',
            'update_last_large_avg': '0.3',
            'update_last_large_std_dev': '0.0',
            'update_last_large_50_pctile': '0.3',
            'update_last_large_worst_txid': 'txID005',
            'delete_count': '2',
            'delete_avg_req_per_s': '2.0',
            'delete_first_all_min': '0.1',
            'delete_first_all_max': '0.5',
            'delete_first_all_avg': '0.3',
            'delete_first_all_std_dev': '0.2',
            'delete_first_all_50_pctile': '0.3',
            'delete_first_all_worst_txid': 'txID011',
            'delete_last_all_min': '0.4',
            'delete_last_all_max': '0.8',
            'delete_last_all_avg': '0.6',
            'delete_last_all_std_dev': '0.2',
            'delete_last_all_50_pctile': '0.6',
            'delete_last_all_worst_txid': 'txID011',
            'delete_first_small_min': '0.5',
            'delete_first_small_max': '0.5',
            'delete_first_small_avg': '0.5',
            'delete_first_small_std_dev': '0.0',
            'delete_first_small_50_pctile': '0.5',
            'delete_first_small_worst_txid': 'txID011',
            'delete_last_small_min': '0.8',
            'delete_last_small_max': '0.8',
            'delete_last_small_avg': '0.8',
            'delete_last_small_std_dev': '0.0',
            'delete_last_small_50_pctile': '0.8',
            'delete_last_small_worst_txid': 'txID011',
            'delete_first_large_min': '0.1',
            'delete_first_large_max': '0.1',
            'delete_first_large_avg': '0.1',
            'delete_first_large_std_dev': '0.0',
            'delete_first_large_50_pctile': '0.1',
            'delete_first_large_worst_txid': 'txID007',
            'delete_last_large_min': '0.4',
            'delete_last_large_max': '0.4',
            'delete_last_large_avg': '0.4',
            'delete_last_large_std_dev': '0.0',
            'delete_last_large_50_pctile': '0.4',
            'delete_last_large_worst_txid': 'txID007',
        }], csv_data)


class TestLatencyHistogramProcessor(TestCase):

    def make_one(self, *args, **kwargs):
        from ssbench.reporter.latency_histogram import LatencyHistogramProcessor
        return LatencyHistogramProcessor(*args, **kwargs)

    def test_process_histogram(self):
        hrange = [20, 50, 100, 500, 1000]
        lhp = self.make_one(hrange)

        # feed 20 to <20ms
        for i in range(20):
            lhp.process(dict(type='test', last_byte_latency=i))
        # feed 30 to <50ms
        for i in range(20, 50):
            lhp.process(dict(type='test', last_byte_latency=i))
        # feed 50 to <100ms
        for i in range(50, 100):
            lhp.process(dict(type='test', last_byte_latency=i))
        # feed 400 to <500ms
        for i in range(100, 500):
            lhp.process(dict(type='test', last_byte_latency=i))
        # feed 500 to <1000ms
        for i in range(500, 1000):
            lhp.process(dict(type='test', last_byte_latency=i))
        # feed 1000 to >=1000ms
        for i in range(1000, 2000):
            lhp.process(dict(type='test', last_byte_latency=i))

        stats = {}
        lhp.output(stats, key='output')
        output = stats['output']['test']

        expected_histogram = [20, 30, 50, 400, 500, 1000]
        self.assertEqual(output['range'], hrange)
        self.assertEqual(output['total'], sum(expected_histogram))
        self.assertEqual(output['histogram'], expected_histogram)
