class ProgressBar:
    def __init__(self, start=0, stop=100):
        self._state = 0
        self._start = start
        self._stop = stop

    def reset(self, val=0):
        self._state = val

    def show(self, increase=1):
        import sys
        self._state += increase
        if self._state > self._stop:
            self._state = self._stop

        # show
        pos = float(self._state - self._start)/(self._stop - self._start)
        sys.stdout.write("\r[%-20s] %d%%" % ('='*int(20*pos), (100*pos)))

        if self._state == self._stop:
            sys.stdout.write('\n')
        sys.stdout.flush()