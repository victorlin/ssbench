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
