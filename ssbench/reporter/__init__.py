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
import math
import logging
import statlib.stats
from pprint import pformat
from datetime import datetime
from cStringIO import StringIO
from mako.template import Template

import ssbench
from ssbench.ordered_dict import OrderedDict


REPORT_TIME_FORMAT = '%F %T UTC'


class LatencyHistogramProcessor:
    REPORT_NAME = 'latency_histogram'

    def __init__(self, histogram_range):
        """Initialize processor

        :param histogram_range: The range of histogram interval
            It should be a list of interger, the unit is in ms.
            For example, [20, 50, 100, 500, 1000] stands for the ranges as

                <20ms, <50ms, <100ms, <500ms, <1000ms, >=1000ms
        """
        self.histogram_range = histogram_range

    def initialize(self):
        """Called to initialize report processing

        """
        # mapping from type to histogram
        self._type2histogram = {}

    def process(self, result):
        """Result data will be feeded into this

        """
        crud_type = result['type']
        histogram = self._type2histogram.setdefault(crud_type, [])
        if not histogram:
            histogram.extend([0] * (len(self.histogram_range) + 1))
        # TODO: should exception to be added to total?
        if 'exception' in result:
            return

        # TODO: what about first byte latency?
        found = False
        last_byte_latency = result['last_byte_latency']
        for i, edge in enumerate(self.histogram_range):
            if last_byte_latency < edge:
                histogram[i] += 1
                found = True
                break
        if not found:
            histogram[-1] += 1

    def output(self, stats, key=None):
        """Output processing result to stats dict

        The output should be in follow format

            {
                CREATE_OBJECT: { # keys are CRUD constants: CREATE_OBJECT, READ_OBJECT, etc.
                    'range': [10, 20 50, 100] # the input histogram range
                    'histogram': [4, 3, 0, 0, 0], # the latency histogram
                    'total': 7 # the total record number
                },
                # ...
            }
        """
        key = key or self.REPORT_NAME
        output = {}
        for crud_type, histogram in self._type2histogram.iteritems():
            output[crud_type] = dict(
                total=sum(histogram),
                range=self.histogram_range[:],
                histogram=histogram[:],
            )
        stats[key] = output


class LatencyHistogramReport:

    def __init__(self, output):
        self.output = output

    def _report_one(self, crud_type, data):
        type_name_map = {
            ssbench.CREATE_OBJECT: 'CREATE',
            ssbench.READ_OBJECT: 'READ',
            ssbench.UPDATE_OBJECT: 'UPDATE',
            ssbench.DELETE_OBJECT: 'DELETE',
        }
        type_name = type_name_map[crud_type]
        print >> self.output, '%s; total latency' % type_name
        terms = ['< %sms' % n for n in data['range']]
        terms.append('>= %sms' % data['range'][-1])
        column = ['%12s' % t for t in ['Count'] + terms]
        print >> self.output, ''.join(column)
        column = ['%12s' % t for t in [data['total']] + data['histogram']]
        print >> self.output, ''.join(column)

    def __call__(self, record):
        # TODO: may be we should use mako template here
        print >>self.output, 'Latency Histogram\n'
        for crud_type in [ssbench.CREATE_OBJECT, ssbench.READ_OBJECT,
                          ssbench.UPDATE_OBJECT, ssbench.DELETE_OBJECT]:
            if crud_type not in record:
                continue
            self._report_one(crud_type, record[crud_type])


class Reporter:
    def __init__(self, run_results, processors=None):
        self.processors = processors
        if self.processors is None:
            self.processors = []
        self.run_results = run_results

    def read_results(self, nth_pctile=95, format_numbers=True):
        self.scenario, self.unpacker = self.run_results.read_results()
        self.stats = self.calculate_scenario_stats(nth_pctile, format_numbers)

    def write_rps_histogram(self, target_file):
        target_file.write('"Seconds Since Start","Requests Completed"\n')
        for i, req_count in enumerate(self.stats['time_series']['data'], 1):
            target_file.write('%d,%d\n' % (i, req_count))

    def scenario_template(self):
        return """
${scenario.name}  (generated with ssbench version ${scenario.version})
Worker count: ${'%3d' % agg_stats['worker_count']}   Concurrency: ${'%3d' % scenario.user_count}  Ran ${start_time} to ${stop_time} (${'%.0f' % round(duration)}s)

%% Ops    C   R   U   D       Size Range       Size Name
% for size_datum in size_data:
${size_datum['pct_total_ops']}   % ${size_datum['crud_pcts']}      ${size_datum['size_range']}  ${size_datum['size_name']}
% endfor
---------------------------------------------------------------------
        ${'%3.0f' % weighted_c} ${'%3.0f' % weighted_r} ${'%3.0f' % weighted_u} ${'%3.0f' % weighted_d}      CRUD weighted average

% for label, stats, sstats in stat_list:
% if stats['req_count']:
${label}
       Count: ${'%5d' % stats['req_count']} (${'%5d' % stats['errors']} error; ${'%5d' % stats['retries']} retries: ${'%5.2f' % stats['retry_rate']}%)  Average requests per second: ${'%5.1f' % stats['avg_req_per_sec']}
                            min       max      avg      std_dev  ${'%02d' % nth_pctile}%-ile  ${'%15s' % ''}  Worst latency TX ID
       First-byte latency: ${stats['first_byte_latency']['min']} - ${stats['first_byte_latency']['max']}  ${stats['first_byte_latency']['avg']}  (${stats['first_byte_latency']['std_dev']})  ${stats['first_byte_latency']['pctile']}  (all obj sizes)  ${stats['worst_first_byte_latency'][1] if 'worst_first_byte_latency' in stats else ''}
       Last-byte  latency: ${stats['last_byte_latency']['min']} - ${stats['last_byte_latency']['max']}  ${stats['last_byte_latency']['avg']}  (${stats['last_byte_latency']['std_dev']})  ${stats['last_byte_latency']['pctile']}  (all obj sizes)  ${stats['worst_last_byte_latency'][1] if 'worst_last_byte_latency' in stats else ''}
% for size_str, per_size_stats in sstats.iteritems():
% if per_size_stats:
       First-byte latency: ${per_size_stats['first_byte_latency']['min']} - ${per_size_stats['first_byte_latency']['max']}  ${per_size_stats['first_byte_latency']['avg']}  (${per_size_stats['first_byte_latency']['std_dev']})  ${per_size_stats['first_byte_latency']['pctile']}  ${'(%8s objs)' % size_str}  ${per_size_stats['worst_first_byte_latency'][1] if 'worst_first_byte_latency' in per_size_stats else ''}
       Last-byte  latency: ${per_size_stats['last_byte_latency']['min']} - ${per_size_stats['last_byte_latency']['max']}  ${per_size_stats['last_byte_latency']['avg']}  (${per_size_stats['last_byte_latency']['std_dev']})  ${per_size_stats['last_byte_latency']['pctile']}  ${'(%8s objs)' % size_str}  ${per_size_stats['worst_last_byte_latency'][1] if 'worst_last_byte_latency' in per_size_stats else ''}
% endif
% endfor

% endif
% endfor
Distribution of requests per worker-ID: ${jobs_per_worker_stats['min']} - ${jobs_per_worker_stats['max']} (avg: ${jobs_per_worker_stats['avg']}; stddev: ${jobs_per_worker_stats['std_dev']})
"""

    def generate_default_report(self, output_csv=False):
        """Format a default summary report based on calculated statistics for
        an executed scenario.

        :returns: A report (string) suitable for printing, emailing, etc.
        """

        stats = self.stats
        template = Template(self.scenario_template())
        tmpl_vars = {
            'size_data': [],
            'stat_list': [
                ('TOTAL', stats['agg_stats'], stats['size_stats']),
                ('CREATE', stats['op_stats'][ssbench.CREATE_OBJECT],
                 stats['op_stats'][ssbench.CREATE_OBJECT]['size_stats']),
                ('READ', stats['op_stats'][ssbench.READ_OBJECT],
                 stats['op_stats'][ssbench.READ_OBJECT]['size_stats']),
                ('UPDATE', stats['op_stats'][ssbench.UPDATE_OBJECT],
                 stats['op_stats'][ssbench.UPDATE_OBJECT]['size_stats']),
                ('DELETE', stats['op_stats'][ssbench.DELETE_OBJECT],
                 stats['op_stats'][ssbench.DELETE_OBJECT]['size_stats']),
            ],
            'agg_stats': stats['agg_stats'],
            'nth_pctile': stats['nth_pctile'],
            'start_time': datetime.utcfromtimestamp(
                stats['time_series']['start_time']
            ).strftime(REPORT_TIME_FORMAT),
            'stop_time': datetime.utcfromtimestamp(
                stats['time_series']['stop']).strftime(REPORT_TIME_FORMAT),
            'duration': stats['time_series']['stop']
            - stats['time_series']['start_time'],
            'jobs_per_worker_stats': stats['jobs_per_worker_stats'],
            'weighted_c': 0.0,
            'weighted_r': 0.0,
            'weighted_u': 0.0,
            'weighted_d': 0.0,
        }
        for size_data in self.scenario.sizes_by_name.values():
            if size_data['size_min'] == size_data['size_max']:
                size_range = '%-15s' % (
                    self._format_bytes(size_data['size_min']),)
            else:
                size_range = '%s - %s' % (
                    self._format_bytes(size_data['size_min']),
                    self._format_bytes(size_data['size_max']))
            initial_files = self.scenario._scenario_data['initial_files']
            initial_total = sum(initial_files.values())
            pct_total = (initial_files.get(size_data['name'], 0)
                         / float(initial_total) * 100.0)
            tmpl_vars['size_data'].append({
                'crud_pcts': '  '.join(map(lambda p: '%2.0f' % p,
                                           size_data['crud_pcts'])),
                'size_range': size_range,
                'size_name': size_data['name'],
                'pct_total_ops': '%3.0f%%' % pct_total,
            })
            tmpl_vars['weighted_c'] += \
                pct_total * size_data['crud_pcts'][0] / 100.0
            tmpl_vars['weighted_r'] += \
                pct_total * size_data['crud_pcts'][1] / 100.0
            tmpl_vars['weighted_u'] += \
                pct_total * size_data['crud_pcts'][2] / 100.0
            tmpl_vars['weighted_d'] += \
                pct_total * size_data['crud_pcts'][3] / 100.0
        if output_csv:
            csv_fields = [
                'scenario_name', 'ssbench_version', 'worker_count',
                'concurrency', 'start_time', 'stop_time', 'duration']
            csv_data = {
                'scenario_name': self.scenario.name,
                'ssbench_version': self.scenario.version,
                'worker_count': tmpl_vars['agg_stats']['worker_count'],
                'concurrency': self.scenario.user_count,
                'start_time': tmpl_vars['start_time'],
                'stop_time': tmpl_vars['stop_time'],
                'duration': tmpl_vars['duration'],
            }
            for label, stats, sstats in tmpl_vars['stat_list']:
                label_lc = label.lower()
                if stats.get('req_count', 0):
                    self._add_csv_kv(csv_fields, csv_data,
                                     '%s_count' % label_lc, stats['req_count'])
                    self._add_csv_kv(csv_fields, csv_data,
                                     '%s_avg_req_per_s' % label_lc,
                                     stats['avg_req_per_sec'])
                    self._add_stats_for(csv_fields, csv_data, label, 'all',
                                        stats, tmpl_vars['nth_pctile'])
                    for size_str, per_size_stats in sstats.iteritems():
                        if per_size_stats:
                            self._add_stats_for(csv_fields, csv_data, label,
                                                size_str, per_size_stats,
                                                tmpl_vars['nth_pctile'])
            csv_file = StringIO()
            csv_writer = csv.DictWriter(csv_file, csv_fields,
                                        lineterminator='\n',
                                        quoting=csv.QUOTE_NONNUMERIC)
            csv_writer.writeheader()
            csv_writer.writerow(csv_data)
            return csv_file.getvalue()
        else:
            return template.render(scenario=self.scenario, **tmpl_vars)

    def _add_csv_kv(self, csv_fields, csv_data, key, value):
        csv_fields.append(key)
        csv_data[key] = value

    def _add_stats_for(self, csv_fields, csv_data, label, size_str, stats,
                       nth_pctile):
        for latency_type in ('first', 'last'):
            latency_stats = stats['%s_byte_latency' % latency_type]
            key_base = '%s_%s_%s_' % (label.lower(), latency_type, size_str)
            self._add_csv_kv(csv_fields, csv_data, key_base + 'min',
                             latency_stats['min'])
            self._add_csv_kv(csv_fields, csv_data, key_base + 'max',
                             latency_stats['max'])
            self._add_csv_kv(csv_fields, csv_data, key_base + 'avg',
                             latency_stats['avg'])
            self._add_csv_kv(csv_fields, csv_data, key_base + 'std_dev',
                             latency_stats['std_dev'])
            self._add_csv_kv(csv_fields, csv_data,
                             key_base + '%d_pctile' % nth_pctile,
                             latency_stats['pctile'])
            worst_key = 'worst_%s_byte_latency' % latency_type
            self._add_csv_kv(
                csv_fields, csv_data, key_base + 'worst_txid',
                stats[worst_key][1] if worst_key in stats else '')

    def _format_bytes(self, byte_count):
        units = [' B', 'kB', 'MB', 'GB']
        i = 0
        while round(byte_count / 1000.0, 3) >= 1.0:
            byte_count = byte_count / 1000.0
            i += 1
        return '%3.0f %s' % (round(byte_count), units[i])

    def calculate_scenario_stats(self, nth_pctile=95, format_numbers=True):
        """Compute various statistics from worker job result dicts.

        :param nth_pctile: Use this percentile when calculating the stats
        :param format_numbers: Should various floating-point numbers be
        formatted as strings or left full-precision floats
        :returns: A stats python dict which looks something like:
            SERIES_STATS = {
                'min': 1.1,
                'max': 1.1,
                'avg': 1.1,
                'std_dev': 1.1,
                'median': 1.1,
            }
            {
                'agg_stats': {
                    'worker_count': 1,
                    'start': 1.1,
                    'stop': 1.1,
                    'req_count': 1,
                    'retries': 0,
                    'errors' : 0,
                    'avg_req_per_sec': 1.1, # req_count / (stop - start)?
                    'retry_rate': 0.0,
                    'first_byte_latency': SERIES_STATS,
                    'last_byte_latency': SERIES_STATS,
                },
                'worker_stats': {
                    1: {  # keys are worker_ids
                        'start': 1.1,
                        'stop': 1.1,
                        'req_count': 1,
                        'retries': 0,
                        'retry_rate': 0.0,
                        'errors': 0,
                        'avg_req_per_sec': 1.1, # req_count / (stop - start)?
                        'first_byte_latency': SERIES_STATS,
                        'last_byte_latency': SERIES_STATS,
                    },
                    # ...
                },
                'op_stats': {
                    CREATE_OBJECT: { # keys are CRUD constants: CREATE_OBJECT, READ_OBJECT, etc.
                        'req_count': 1, # num requests of this CRUD type
                        'avg_req_per_sec': 1.1, # total_requests / sum(last_byte_latencies)
                        'first_byte_latency': SERIES_STATS,
                        'last_byte_latency': SERIES_STATS,
                        'size_stats': {
                            'small': { # keys are size_str values
                                'req_count': 1, # num requests of this type and size
                                'retries': 0, # num of retries
                                'avg_req_per_sec': 1.1, # total_requests / sum(last_byte_latencies)
                                'errors': 0,
                                'retry_rate': 0.0,
                                'first_byte_latency': SERIES_STATS,
                                'last_byte_latency': SERIES_STATS,
                            },
                            # ...
                        },
                    },
                    # ...
                },
                'size_stats': {
                    'small': { # keys are size_str values
                        'req_count': 1, # num requests of this size (for all CRUD types)
                        'retries': 0, # num of retries
                        'acutual_request_count': 1, # num requests includes retries
                        'avg_req_per_sec': 1.1, # total_requests / sum(last_byte_latencies)
                        'errors': 0,
                        'retry_rate': 0.0,
                        'first_byte_latency': SERIES_STATS,
                        'last_byte_latency': SERIES_STATS,
                    },
                    # ...
                },
                'time_series': {
                    'start': 1, # epoch time of first data point
                    'data': [
                        1, # number of requests finishing during this second
                        # ...
                    ],
                },
            }
        """
        # Each result looks like:
        # {
        #   'worker_id': 1,
        #   'type': 'get_object',
        #   'size': 4900000,
        #   'size_str': 'large',
        #   'first_byte_latency': 0.9137639999389648,
        #   'last_byte_latency': 0.913769006729126,
        #   'retries': 1
        #   'completed_at': 1324372892.360802,
        #}
        # OR
        # {
        #   'worker_id': 1,
        #   'type': 'get_object',
        #   'size_str': 'large'
        #   'completed_at': 1324372892.360802,
        #   'retries': 1
        #   'exception': '...',
        # }
        logging.info('Calculating statistics...')
        agg_stats = dict(start=2 ** 32, stop=0, req_count=0)
        op_stats = {}
        for crud_type in [ssbench.CREATE_OBJECT, ssbench.READ_OBJECT,
                          ssbench.UPDATE_OBJECT, ssbench.DELETE_OBJECT]:
            op_stats[crud_type] = dict(
                req_count=0, avg_req_per_sec=0,
                size_stats=OrderedDict.fromkeys(
                    self.scenario.sizes_by_name.keys()))

        req_completion_seconds = {}
        start_time = 0
        completion_time_max = 0
        completion_time_min = 2 ** 32
        stats = dict(
            nth_pctile=nth_pctile,
            agg_stats=agg_stats,
            worker_stats={},
            op_stats=op_stats,
            size_stats=OrderedDict.fromkeys(
                self.scenario.sizes_by_name.keys()))

        # initialize all report processors
        for processor in self.processors:
            processor.initialize()

        for results in self.unpacker:
            for result in results:

                for processor in self.processors:
                    processor.process(result)

                completion_time = int(result['completed_at'])
                if 'exception' in result:
                    # report log exceptions
                    logging.warn('calculate_scenario_stats: exception from '
                                 'worker %d: %s',
                                 result['worker_id'], result['exception'])
                    logging.info(result['traceback'])
                else:
                    if completion_time < completion_time_min:
                        completion_time_min = completion_time
                        start_time = (
                            completion_time - result['last_byte_latency'])
                    if completion_time > completion_time_max:
                        completion_time_max = completion_time
                    req_completion_seconds[completion_time] = \
                        1 + req_completion_seconds.get(completion_time, 0)
                    result['start'] = (
                        result['completed_at'] - result['last_byte_latency'])

                # Stats per-worker
                if result['worker_id'] not in stats['worker_stats']:
                    stats['worker_stats'][result['worker_id']] = {}
                self._add_result_to(stats['worker_stats'][result['worker_id']],
                                    result)

                # Stats per-file-size
                if not stats['size_stats'][result['size_str']]:
                    stats['size_stats'][result['size_str']] = {}
                self._add_result_to(stats['size_stats'][result['size_str']],
                                    result)

                self._add_result_to(agg_stats, result)

                type_stats = op_stats[result['type']]
                self._add_result_to(type_stats, result)

                # Stats per-operation-per-file-size
                if not type_stats['size_stats'][result['size_str']]:
                    type_stats['size_stats'][result['size_str']] = {}
                self._add_result_to(
                    type_stats['size_stats'][result['size_str']], result)

        agg_stats['worker_count'] = len(stats['worker_stats'].keys())
        self._compute_req_per_sec(agg_stats)
        self._compute_retry_rate(agg_stats)
        self._compute_latency_stats(agg_stats, nth_pctile, format_numbers)

        jobs_per_worker = []
        for worker_stats in stats['worker_stats'].values():
            jobs_per_worker.append(worker_stats['req_count'])
            self._compute_req_per_sec(worker_stats)
            self._compute_retry_rate(worker_stats)
            self._compute_latency_stats(worker_stats, nth_pctile,
                                        format_numbers)
        stats['jobs_per_worker_stats'] = self._series_stats(jobs_per_worker,
                                                            nth_pctile,
                                                            format_numbers)
        logging.debug('Jobs per worker stats:\n' +
                      pformat(stats['jobs_per_worker_stats']))

        for op_stat, op_stats_dict in op_stats.iteritems():
            if op_stats_dict['req_count']:
                self._compute_req_per_sec(op_stats_dict)
                self._compute_retry_rate(op_stats_dict)
                self._compute_latency_stats(op_stats_dict, nth_pctile,
                                            format_numbers)
                for size_str, size_stats in \
                        op_stats_dict['size_stats'].iteritems():
                    if size_stats:
                        self._compute_req_per_sec(size_stats)
                        self._compute_retry_rate(size_stats)
                        self._compute_latency_stats(size_stats, nth_pctile,
                                                    format_numbers)
                    else:
                        op_stats_dict['size_stats'].pop(size_str)
        for size_str, size_stats in stats['size_stats'].iteritems():
            if size_stats:
                self._compute_req_per_sec(size_stats)
                self._compute_retry_rate(size_stats)
                self._compute_latency_stats(size_stats, nth_pctile,
                                            format_numbers)
            else:
                stats['size_stats'].pop(size_str)
        time_series_data = [req_completion_seconds.get(t, 0)
                            for t in range(completion_time_min,
                                           completion_time_max + 1)]
        stats['time_series'] = dict(start=completion_time_min,
                                    start_time=start_time,
                                    stop=completion_time_max,
                                    data=time_series_data)

        # output data from all processor
        for processor in self.processors:
            processor.output(stats)

        return stats

    def _compute_latency_stats(self, stat_dict, nth_pctile, format_numbers):
        try:
            for latency_type in ('first_byte_latency', 'last_byte_latency'):
                stat_dict[latency_type] = self._series_stats(
                    stat_dict.get(latency_type, []), nth_pctile,
                    format_numbers)
        except KeyError:
            logging.exception('stat_dict: %r', stat_dict)
            raise

    def _compute_req_per_sec(self, stat_dict):
        if 'start' in stat_dict:
            delta_t = stat_dict['stop'] - stat_dict['start']
            stat_dict['avg_req_per_sec'] = round(
                stat_dict['req_count'] / delta_t,
                6)
        else:
            stat_dict['avg_req_per_sec'] = 0.0

    def _compute_retry_rate(self, stat_dict):
        stat_dict['retry_rate'] = round((float(stat_dict['retries']) /
                                         stat_dict['req_count']) * 100, 6)

    def _add_result_to(self, stat_dict, result):
        if 'errors' not in stat_dict:
            stat_dict['errors'] = 0
        if 'start' in result and ('start' not in stat_dict or
                                  result['start'] < stat_dict['start']):
            stat_dict['start'] = result['start']
        if 'stop' not in stat_dict or \
                result['completed_at'] > stat_dict['stop']:
            stat_dict['stop'] = result['completed_at']
        stat_dict['req_count'] = stat_dict.get('req_count', 0) + 1
        stat_dict['retries'] = \
            stat_dict.get('retries', 0) + int(result['retries'])
        if 'exception' not in result:
            self._rec_latency(stat_dict, result)
        else:
            stat_dict['errors'] += 1

    def _series_stats(self, sequence, nth_pctile, format_numbers):
        sequence = filter(None, sequence)
        if not sequence:
            # No data available
            return dict(min=' N/A  ', max='  N/A  ', avg='  N/A  ',
                        pctile='  N/A  ', std_dev='  N/A  ', median='  N/A  ')
        sequence.sort()
        try:
            n, (minval, maxval), mean, std_dev, skew, kurtosis = \
                statlib.stats.ldescribe(sequence)
        except ZeroDivisionError:
            # Handle the case of a single-element sequence (population standard
            # deviation divides by N-1)
            minval = sequence[0]
            maxval = sequence[0]
            mean = sequence[0]
        if format_numbers:
            return dict(
                min='%6.3f' % minval,
                max='%7.3f' % maxval,
                avg='%7.3f' % mean,
                pctile='%7.3f' % self.pctile(sequence, nth_pctile),
                std_dev='%7.3f' % statlib.stats.lsamplestdev(sequence),
                median='%7.3f' % statlib.stats.lmedianscore(sequence))
        else:
            return dict(
                min=round(minval, 6),
                max=round(maxval, 6),
                avg=round(mean, 6),
                pctile=round(self.pctile(sequence, nth_pctile), 6),
                std_dev=round(statlib.stats.lsamplestdev(sequence), 6),
                median=round(statlib.stats.lmedianscore(sequence), 6))

    def pctile(self, sequence, nth_pctile):
        seq_len = len(sequence)
        rank = seq_len * nth_pctile / 100.0
        if float(int(rank)) == rank:
            # integer rank means we interpolate between two values
            rank = int(rank)
            return (sequence[rank - 1] + sequence[rank]) / 2.0
        else:
            return sequence[int(math.ceil(rank)) - 1]

    def _rec_latency(self, stats_dict, result):
        for latency_type in ('first_byte_latency', 'last_byte_latency'):
            if latency_type in stats_dict:
                stats_dict[latency_type].append(result[latency_type])
            else:
                stats_dict[latency_type] = [result[latency_type]]
            if result[latency_type] is not None:
                worst_key = 'worst_%s' % latency_type
                if worst_key not in stats_dict \
                        or result[latency_type] > stats_dict[worst_key][0]:
                    stats_dict[worst_key] = (round(result[latency_type], 6),
                                             result['trans_id'])
