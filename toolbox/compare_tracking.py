#!/usr/bin/env python
import sys
sys.path.append('../.')
sys.path.append('.')

import numpy as np
import cPickle
import collections
import multiprocessing
import os
import os.path as path
import optparse
import sys
from empryonic import io
from empryonic.learning import match as m
from empryonic.learning import quantification as quant
import h5py

def match(fn_pair):    
    assoc = m.match_files(fn_pair[0], fn_pair[1], options.threshold, options.ignore_z, options.swap_xy, verbose=False)
    print "-> matched: " + path.basename(fn_pair[0]) + " <-> " + path.basename(fn_pair[1])
    return assoc


def construct_associations(base_fns, cont_fns, timesteps, verbose=False):
    assocs = []
    for t in range(timesteps):
        base_fn = base_fns[t]
        cont_fn = cont_fns[t]
        with h5py.File(base_fn, 'r') as f:
            base_ids = np.sort(f['objects/meta/id'].value)            
            base_valid = f['objects/meta/valid'].value
            # base_detection = f['objects/meta/detection'].value

        with h5py.File(cont_fn, 'r') as f:
            cont_ids = np.sort(f['objects/meta/id'].value)
            cont_valid = f['objects/meta/valid'].value
            # cont_detection = f['objects/meta/detection'].value

        if verbose:
            print "sanity checking %d" % t
        assert(np.all(base_ids == cont_ids))
        assert(np.all(base_valid == 1))
        assert(np.all(cont_valid == 1))
        base_ids = map(int, base_ids)
        cont_ids = map(int, cont_ids)
        assoc = {'lhs':dict(zip(base_ids, cont_ids)), 'rhs':dict(zip(cont_ids, base_ids))}
        assocs.append(assoc)
    return assocs


if __name__=="__main__":

    usage = """%prog [options] BASE_DIR CONTESTANT_DIR
Compare two tracking results, based only on the association information in the tracking group.
"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--quietly', action='store_true', dest='quiet', help='non-verbose')
    parser.add_option('--max-ts', dest='max_ts', type=int, default=-1, help='max. timestep (exclusive) [default=%default]')
    #parser.add_option('--no-detailed-stats', action='store_true', dest='no_detailed_stats', help="don't write detailed statistics into an output file")
    #parser.add_option('-o', type='str', dest='output_fn', default='batch_performance.txt', help='output file for detailed stats; no effect if "--no-detailed-stats" is set [default: %default]')
    #parser.add_option('-t', '--threshold', type='float', dest='threshold', default=25, help='distance threshold for the matching (matching only below the threshold) [default: %default]')
    #parser.add_option('--swap-xy', action='store_true', dest='swap_xy', help='switches x and y coordinates of the traxels in FILE1')
    #parser.add_option('--ignore-z', action='store_true', dest='ignore_z', help='only match in the x-y subspace')
    #parser.add_option('--precomputed-match', action='store_true', dest='precomputed_match', help='match files will be loaded from ./matched/ [invalidates all match related options]')

    options, args = parser.parse_args()

    verbose = not bool(options.quiet)

    numArgs = len(args)
    if numArgs == 2:
        base_dir = args[0]
        cont_dir = args[1]

        base_fns = [path.abspath(path.join(base_dir, fn)) for fn in os.listdir(base_dir)]
        base_fns.sort()
        cont_fns = [path.abspath(path.join(cont_dir, fn)) for fn in os.listdir(cont_dir)]
        cont_fns.sort()
    else:
        parser.print_help()
        sys.exit(1)
    
    if options.max_ts != -1:
        base_fns = base_fns[:options.max_ts]

    if len(base_fns) < 2:
        print "Abort: at least two base files needed."
        sys.exit(1)
    if len(cont_fns) < 2:
        print "Abort: at least two contestant files needed."
        sys.exit(1)
    # if len(base_fns) != len(cont_fns):
    #     print "Warning: number of base files has to match number of contestant files."

    timesteps = min((len(base_fns), len(cont_fns)))

    ##
    ## construct id assocs; assumed to be identically mapped in this script 
    ## (i.e. the ids don't differ for the same object in base and contestant) 
    ##
    assocs = construct_associations(base_fns, cont_fns, timesteps, verbose)

    ## 
    ## generate taxonomy
    ##
    fn_pairs = zip(base_fns[0:timesteps], cont_fns[0:timesteps])
    assert(timesteps == len(assocs))


    ts = []
    for i,v in enumerate(fn_pairs[1:]):
        if verbose:
            print path.basename(v[0]), path.basename(v[1])
        t = quant.compute_taxonomy(assocs[i], assocs[i+1], v[0], v[1], i+1)
        ts.append(t)
        #sys.stdout.write('%d ' % i)
        sys.stdout.flush()
    overall = reduce( quant.Taxonomy.union, ts )

    def total_elements( taxonomy ):
        return len(taxonomy.base_basic) + len(taxonomy.cont_basic)
    assert(sum((total_elements(t) for t in ts)) == total_elements(overall))

    ##
    ## report results
    ##
    if verbose:
        print "Measuring performance..."
        print "-> Precision: %.3f" % overall.precision()
        print "-> Recall: %.3f" % overall.recall()
        print "-> F-measure %.3f: " % overall.f_measure()
        print "Check", 2.*overall.precision() * overall.recall() / (overall.precision() + overall.recall())
        print
        print overall
    else:
        print overall.to_line()