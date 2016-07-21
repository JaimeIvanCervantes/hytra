import hytra.core.hypothesesgraph as hg
import hytra.core.probabilitygenerator as pg
import networkx as nx
import numpy as np
from hytra.core.probabilitygenerator import Traxel

def test_trackletgraph():
    h = hg.HypothesesGraph()
    h._graph.add_path([(0,1),(1,1),(2,1),(3,1)])
    for i in [(0,1),(1,1),(2,1),(3,1)]:
        t = Traxel()
        t.Timestep = i[0]
        t.Id = i[1]
        h._graph.node[i]['traxel'] = t
    
    t = h.generateTrackletGraph()
    assert(t.countArcs() == 0)
    assert(t.countNodes() == 1)
    assert('tracklet' in t._graph.node[(0,1)])

def test_computeLineages():
    h = hg.HypothesesGraph()
    h._graph.add_path([(0, 0),(1, 1),(2, 2)])
    h._graph.add_path([(1, 1),(2, 3),(3, 4)])

    for n in h._graph.node:
        h._graph.node[n]['id'] = n[1]
        h._graph.node[n]['traxel'] = pg.Traxel()
        h._graph.node[n]['traxel'].Id = n[1]
        h._graph.node[n]['traxel'].Timestep = n[0]

    solutionDict = {
    "detectionResults": [
        {
            "id": 0,
            "value": 1
        },
        {
            "id": 1,
            "value": 1
        },
        {
            "id": 2,
            "value": 1
        },
        {
            "id": 3,
            "value": 1
        },
        {
            "id": 4,
            "value": 0
        }
    ],
    "linkingResults": [
        {
            "dest": 1,
            "src": 0,
            "value": 1
        },
        {
            "dest": 2,
            "src": 1,
            "value": 1
        },
        {
            "dest": 3,
            "src": 1,
            "value": 1
        },
        {
            "dest": 4,
            "src": 3,
            "value": 0
        }
    ],
    "divisionResults": [
        {
            "id": 1,
            "value": True
        },
        {
            "id": 2,
            "value": False
        }
    ]
    }

    h.insertSolution(solutionDict)
    h.computeLineage()

def test_insertSolution():
    h = hg.HypothesesGraph()
    h._graph.add_path([(0, 0),(1, 1),(2, 2)])
    h._graph.add_path([(1, 1),(2, 3),(3, 4)])

    for n in h._graph.node:
        h._graph.node[n]['id'] = n[1]
        h._graph.node[n]['traxel'] = pg.Traxel()
        h._graph.node[n]['traxel'].Id = n[1]
        h._graph.node[n]['traxel'].Timestep = n[0]

    solutionDict = {
    "detectionResults": [
        {
            "id": 0,
            "value": 1
        },
        {
            "id": 1,
            "value": 1
        },
        {
            "id": 2,
            "value": 1
        },
        {
            "id": 3,
            "value": 1
        },
        {
            "id": 4,
            "value": 0
        }
    ],
    "linkingResults": [
        {
            "dest": 1,
            "src": 0,
            "value": 1
        },
        {
            "dest": 2,
            "src": 1,
            "value": 1
        },
        {
            "dest": 3,
            "src": 1,
            "value": 1
        },
        {
            "dest": 4,
            "src": 3,
            "value": 0
        }
    ],
    "divisionResults": [
        {
            "id": 1,
            "value": True
        },
        {
            "id": 2,
            "value": False
        }
    ]
    }

    h.insertSolution(solutionDict)
    assert(h._graph.node[(1, 1)]["divisionValue"] == 1)
    assert(h._graph.node[(2, 2)]["divisionValue"] == 0)
    assert(h._graph.node[(0, 0)]["value"] == 1)
    assert(h._graph.node[(1, 1)]["value"] == 1)
    assert(h._graph.node[(2, 2)]["value"] == 1)
    assert(h._graph.node[(2, 3)]["value"] == 1)
    assert(h._graph.node[(3, 4)]["value"] == 0)
    assert(h._graph.edge[(0, 0)][(1, 1)]["value"] == 1)
    assert(h._graph.edge[(1, 1)][(2, 2)]["value"] == 1)
    assert(h._graph.edge[(1, 1)][(2, 3)]["value"] == 1)
    assert(h._graph.edge[(2, 3)][(3, 4)]["value"] == 0)

def test_insertEnergies():
    h = hg.HypothesesGraph()
    h._graph.add_path([(0,1),(1,1),(2,1),(3,1)])
    for uuid, i in enumerate([(0,1),(1,1),(2,1),(3,1)]):
        t = Traxel()
        t.Timestep = i[0]
        t.Id = i[1]
        # fill in detProb, divProb, and center of mass
        t.Features['detProb'] = [0.2, 0.8]
        t.Features['divProb'] = [0.2, 0.8]
        t.Features['com'] = [float(i[0]), 0.0]

        h._graph.node[i]['traxel'] = t
        h._graph.node[i]['id'] = uuid
    
    # set up some dummy functions to compute probabilities from a traxel
    def detProbFunc(traxel):
        return traxel.Features['detProb']

    def divProbFunc(traxel):
        return traxel.Features['divProb']
    
    def boundaryCostFunc(traxel):
        return 1.0
    
    def transProbFunc(traxelA, traxelB):
        dist = np.linalg.norm(np.array(traxelA.Features['com']) - np.array(traxelB.Features['com']))
        return [1.0 - np.exp(-dist), np.exp(-dist)]

    h.insertEnergies(1, detProbFunc, transProbFunc, boundaryCostFunc, divProbFunc)
    
    for n in h.nodeIterator():
        assert('features' in h._graph.node[n])
        assert(h._graph.node[n]['features'] == [[1.6094379124341003], [0.22314355131420971]])
        assert('divisionFeatures' in h._graph.node[n])
        assert(h._graph.node[n]['divisionFeatures'] == [[1.6094379124341003], [0.22314355131420971]])
        assert('appearanceFeatures' in h._graph.node[n])
        assert(h._graph.node[n]['appearanceFeatures'] == [[0.0], [1.0]])
        assert('disappearanceFeatures' in h._graph.node[n])
        assert(h._graph.node[n]['disappearanceFeatures'] == [[0.0], [1.0]])
    
    for a in h.arcIterator():
        assert('features' in h._graph.edge[a[0]][a[1]])
        assert(h._graph.edge[a[0]][a[1]]['features'] == [[0.45867514538708193], [1.0]])

if __name__ == "__main__":
    test_trackletgraph()
    test_insertSolution()
    test_computeLineages()
    test_insertEnergies()