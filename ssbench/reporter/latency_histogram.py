import StringIO

import ssbench


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
        # mapping from crud type to a dict which mapping
        # from size string to histogram
        self._type2size2histogram = {}

    def process(self, result):
        """Result data will be feeded into this

        """
        crud_type = result['type']
        size_str = result['size_str']
        size_map = self._type2size2histogram.setdefault(crud_type, {})
        histogram = size_map.setdefault(size_str, [])
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

    def get_data_dict(self):
        """Output processing result to stats dict

        The output should be in follow format

            {
                range: [10, 20 50, 100], # the input histogram range
                types:
                    CREATE_OBJECT: { # keys are CRUD constants: CREATE_OBJECT,
                                     # READ_OBJECT, etc.
                        tiny: { # the size string e.g. tiny, small and large
                            histogram: [4, 3, 0, 0, 0], # the latency histogram
                            total: 7 # the total record number
                        },
                        # ...
                    },
                    # ...
                }
            }
        """
        output = dict(range=self.histogram_range[:])
        types = {}
        for crud_type, size2histogram in self._type2size2histogram.iteritems():
            size_map = {}
            for size_str, histogram in size2histogram.iteritems():
                size_map[size_str] = dict(
                    total=sum(histogram),
                    histogram=histogram[:],
                )
            types[crud_type] = size_map
        output['types'] = types
        return output

    def as_text(self, scenario):
        """Return as a text

        """
        data = self.get_data_dict()
        str_io = StringIO.StringIO()
        report = TextLatencyHistogramReport(scenario, str_io)
        report(data)
        return str_io.getvalue()


class TextLatencyHistogramReport:

    def __init__(self, scenario, output):
        self.scenario = scenario
        self.output = output

    def _report_one(self, header, crud_type, data):
        type_name_map = {
            ssbench.CREATE_OBJECT: 'CREATE',
            ssbench.READ_OBJECT: 'READ',
            ssbench.UPDATE_OBJECT: 'UPDATE',
            ssbench.DELETE_OBJECT: 'DELETE',
        }
        type_name = type_name_map[crud_type]
        print >> self.output, '%s; total latency' % type_name
        print >> self.output, ''.join(header)
        size_keys = self.scenario.sizes_by_name.keys()
        for size in size_keys:
            if size not in data:
                continue
            item = data[size]
            column = ['%12s' % t for t in [size, item['total']] + item['histogram']]
            print >> self.output, ''.join(column)

    def __call__(self, data):
        # TODO: may be we should use mako template here
        print >>self.output, 'Latency Histogram\n'

        types = data['types']

        terms = ['< %sms' % n for n in data['range']]
        terms.append('>= %sms' % data['range'][-1])
        header = ['%12s' % t for t in ['Size', 'Count'] + terms]

        for crud_type in [ssbench.CREATE_OBJECT, ssbench.READ_OBJECT,
                          ssbench.UPDATE_OBJECT, ssbench.DELETE_OBJECT]:
            if crud_type not in types:
                continue
            self._report_one(header, crud_type, types[crud_type])
