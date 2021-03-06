import os
import numpy as np
import logging
import hytra.core.mergerresolver
from hytra.core.probabilitygenerator import Traxel

def getLogger():
    ''' logger to be used in this module '''
    return logging.getLogger(__name__)

class IlastikMergerResolver(hytra.core.mergerresolver.MergerResolver):
    '''
    Specialization of merger resolving to work with the hypotheses graph given by ilastik,
    and to read/write images from/to the input/output slots of the respective operators. 
    '''
    def __init__(self, hypothesesGraph, pluginPaths=[os.path.abspath('../hytra/plugins')], verbose=False):
        super(IlastikMergerResolver, self).__init__(pluginPaths, verbose)
        trackingGraph = hypothesesGraph.toTrackingGraph(noFeatures=True)
        self.model = trackingGraph.model
        self.result = hypothesesGraph.getSolutionDictionary()
        self.hypothesesGraph = hypothesesGraph
        
        # Find mergers in the given model and result
        traxelIdPerTimestepToUniqueIdMap, uuidToTraxelMap = hytra.core.jsongraph.getMappingsBetweenUUIDsAndTraxels(self.model)
        timesteps = [t for t in traxelIdPerTimestepToUniqueIdMap.keys()]

        mergers, detections, links, divisions = hytra.core.jsongraph.getMergersDetectionsLinksDivisions(self.result, uuidToTraxelMap)

        self.mergersPerTimestep = hytra.core.jsongraph.getMergersPerTimestep(mergers, timesteps)
        self.detectionsPerTimestep = hytra.core.jsongraph.getDetectionsPerTimestep(detections, timesteps)
        
        linksPerTimestep = hytra.core.jsongraph.getLinksPerTimestep(links, timesteps)
        divisionsPerTimestep = hytra.core.jsongraph.getDivisionsPerTimestep(divisions, linksPerTimestep, timesteps)
        mergerLinks = hytra.core.jsongraph.getMergerLinks(linksPerTimestep, self.mergersPerTimestep, timesteps)

        # Build graph of the unresolved (merger) nodes and their direct neighbors
        self._createUnresolvedGraph(divisionsPerTimestep, self.mergersPerTimestep, mergerLinks)
        self._prepareResolvedGraph()

    def run(self, transition_classifier_filename=None, transition_classifier_path=None):
        """
        Run merger resolving from within Ilastik 
        We can't use run() from parent because it has to be done on a per frame basis.

        1. Compute object features
        2. Run min-cost max-flow tracking to find the fate of all the de-merged objects
        3. Export refined segmentation, update member variables `model` and `result`
        4. Compute merger dictionary

        **Returns** a nested dictionary, indexed first by time, then object Id, containing a list of new segmentIDs per merger
        """
        traxelIdPerTimestepToUniqueIdMap, uuidToTraxelMap = hytra.core.jsongraph.getMappingsBetweenUUIDsAndTraxels(self.model)
        timesteps = [t for t in traxelIdPerTimestepToUniqueIdMap.keys()]

        mergers, detections, links, divisions = hytra.core.jsongraph.getMergersDetectionsLinksDivisions(self.result, uuidToTraxelMap)
        
        # compute new object features
        objectFeatures = self._computeObjectFeatures(timesteps)

        # load transition classifier if any
        if transition_classifier_filename is not None:
            getLogger().info("\tLoading transition classifier")
            transitionClassifier = probabilitygenerator.RandomForestClassifier(
                transition_classifier_path, transition_classifier_filename)
        else:
            getLogger().info("\tUsing distance based transition energies")
            transitionClassifier = None

        # run min-cost max-flow to find merger assignments
        getLogger().info("Running min-cost max-flow to find resolved merger assignments")

        nodeFlowMap, arcFlowMap = self._minCostMaxFlowMergerResolving(objectFeatures, transitionClassifier)

        # fuse results into a new solution
        # 1.) replace merger nodes in JSON graph by their replacements -> new JSON graph
        #     update UUID to traxel map.
        #     a) how do we deal with the smaller number of states?
        #        Does it matter as we're done with tracking anyway..?

        def mergerNodeFilter(jsonNode):
            uuid = int(jsonNode['id'])
            traxels = uuidToTraxelMap[uuid]
            return not any(t[1] in self.mergersPerTimestep[str(t[0])] for t in traxels)

        def mergerLinkFilter(jsonLink):
            srcUuid = int(jsonLink['src'])
            destUuid = int(jsonLink['dest'])
            srcTraxels = uuidToTraxelMap[srcUuid]
            destTraxels = uuidToTraxelMap[destUuid]
            # return True if there was no traxel in either source or target node that was a merger.
            return not (any(t[1] in self.mergersPerTimestep[str(t[0])] for t in srcTraxels) or any(t[1] in self.mergersPerTimestep[str(t[0])] for t in destTraxels))

        self.model = self._refineModel(uuidToTraxelMap,
                                       traxelIdPerTimestepToUniqueIdMap,
                                       mergerNodeFilter,
                                       mergerLinkFilter)

        # 2.) new result = union(old result, resolved mergers) - old mergers
        self.result = self._refineResult(nodeFlowMap,
                                         arcFlowMap,
                                         traxelIdPerTimestepToUniqueIdMap,
                                         mergerNodeFilter,
                                         mergerLinkFilter)

        # return a dictionary telling about which mergers were resolved into what
        mergerDict = {}
        for n in self.unresolvedGraph.nodes_iter():
            # skip non-mergers
            if not 'newIds' in self.unresolvedGraph.node[n] or len(self.unresolvedGraph.node[n]['newIds']) < 2:
                continue
            mergerDict.setdefault(n[0], {})[n[1]] = self.unresolvedGraph.node[n]['newIds']

        return mergerDict
 
    def getCoordinatesForObjectId(self, coordinatesForObjectIds, labelImage, objectId):
        '''
        Get coordinate for object IDs in labelImage.
        '''
        coordinatesForObjectIds[objectId] = np.transpose(np.vstack(np.where(labelImage == objectId)))
 
    def fitAndRefineNodesForTimestep(self, coordinatesForObjectIds, timestep):
        '''
        Update segmentation of mergers (nodes in unresolvedGraph) for each frame
        and create new nodes in `resolvedGraph`. Links to merger nodes are duplicated to all new nodes.
 
        Uses the mergerResolver plugin to update the segmentations in the labelImages.
         
        This function is used by Ilastik to fit and refine nodes per frame instead of
        loading the full volume in _fitAndRefineNodes()
        '''
 
        # use image provider plugin to load labelimage
        nextObjectId = max(coordinatesForObjectIds.keys()) + 1
 
        t = str(timestep)
        detections = self.detectionsPerTimestep[t]
 
        for idx, coordinates in coordinatesForObjectIds.items():
            if idx not in detections:
                continue
            
            node = (timestep, idx)
            if node not in self.resolvedGraph:
                continue
 
            count = 1
            if idx in self.mergersPerTimestep[t]:
                count = self.mergersPerTimestep[t][idx]
            getLogger().debug("Looking at node {} in timestep {} with count {}".format(idx, t, count))
             
            # collect initializations from incoming
            initializations = []
            for predecessor, _ in self.unresolvedGraph.in_edges(node):
                initializations.extend(self.unresolvedGraph.node[predecessor]['fits'])
            # TODO: what shall we do if e.g. a 2-merger and a single object merge to 2 + 1,
            # so there are 3 initializations for the 2-merger, and two initializations for the 1 merger?
            # What does pgmlink do in that case?
 
            # use merger resolving plugin to fit `count` objects
            fittedObjects = self.mergerResolverPlugin.resolveMergerForCoords(coordinates, count, initializations)
            
            assert(len(fittedObjects) == count)
 
            # split up node if count > 1, duplicate incoming and outgoing arcs
            if count > 1:
                for idx in range(nextObjectId, nextObjectId + count):
                    newNode = (timestep, idx)
                    self.resolvedGraph.add_node(newNode, division=False, count=1, origin=node)
 
                    for e in self.unresolvedGraph.out_edges(node):
                        self.resolvedGraph.add_edge(newNode, e[1])
                    for e in self.unresolvedGraph.in_edges(node):
                        if 'newIds' in self.unresolvedGraph.node[e[0]]:
                            for newId in self.unresolvedGraph.node[e[0]]['newIds']:
                                self.resolvedGraph.add_edge((e[0][0], newId), newNode)
                        else:
                            self.resolvedGraph.add_edge(e[0], newNode)
 
                self.resolvedGraph.remove_node(node)
                self.unresolvedGraph.node[node]['newIds'] = range(nextObjectId, nextObjectId + count)
                nextObjectId += count
 
            # each unresolved node stores its fitted shape(s) to be used
            # as initialization in the next frame, this way division duplicates
            # and de-merged nodes in the resolved graph do not need to store a fit as well
            self.unresolvedGraph.node[node]['fits'] = fittedObjects

    def _computeObjectFeatures(self, timesteps):
        '''
        Return the features per object as nested dictionaries:
        { (int(Timestep), int(Id)):{ "FeatureName" : np.array(value), "NextFeature": ...} }
        '''
        objectFeatures = {}

        # populate the dictionaries only with the Region Centers of the fit for the distance based
        # transitions in ilastik
        # TODO: in the future, this should recompute the object features from the relabeled image!
        for n in self.unresolvedGraph.nodes_iter():
            fits = self.unresolvedGraph.node[n]['fits']
            timestepIdTuples = [n]
            if 'newIds' in self.unresolvedGraph.node[n]:
                timestepIdTuples = [(n[0], i) for i in self.unresolvedGraph.node[n]['newIds']]
                assert(len(self.unresolvedGraph.node[n]['newIds']) == len(fits))

            for tidt, fit in zip(timestepIdTuples, fits):
                objectFeatures[tidt] = {'RegionCenter' : self._fitToRegionCenter(fit)}

        return objectFeatures
    
    def _fitToRegionCenter(self, fit):
        """
        Extract the region center from a GMM fit
        """
        return fit[2]
    
    def _refineResult(self,
                      nodeFlowMap,
                      arcFlowMap,
                      traxelIdPerTimestepToUniqueIdMap,
                      mergerNodeFilter,
                      mergerLinkFilter):
        """
        Overwrite parent method and simply call it, but then call _updateHypothesesGraph to
        also refine our Hypotheses Graph
        """
        refinedResult = super(IlastikMergerResolver, self)._refineResult(
            nodeFlowMap, arcFlowMap, traxelIdPerTimestepToUniqueIdMap, mergerNodeFilter, mergerLinkFilter)
        
        self._updateHypothesesGraph(arcFlowMap)

        return refinedResult

    def _updateHypothesesGraph(self, arcFlowMap):
        """
        After running merger resolving, insert new nodes, remove de-merged nodes
        and also update the links in the hypotheses graph.

        This also stores the new solution (`value` property) in the new nodes and links
        """
        # update nodes
        for n in self.unresolvedGraph.nodes_iter():
            # skip non-mergers
            if not 'newIds' in self.unresolvedGraph.node[n] or len(self.unresolvedGraph.node[n]['newIds']) < 2:
                continue
            
            # for this merger, insert all new nodes into the HG
            assert(len(self.unresolvedGraph.node[n]['newIds']) == self.unresolvedGraph.node[n]['count'])
            for newId, fit in zip(self.unresolvedGraph.node[n]['newIds'], self.unresolvedGraph.node[n]['fits']):
                traxel = Traxel()
                traxel.Id = newId
                traxel.Timestep = n[0]
                traxel.Features = self._fitToRegionCenter(fit)
                self.hypothesesGraph.addNodeFromTraxel(traxel, value=1)
            
            # remove merger from HG, which also removes all edges that would otherwise be dangling
            self.hypothesesGraph._graph.remove_node(n)

        # add new links
        for edge in self.resolvedGraph.edges_iter():
            srcId = self.resolvedGraph.node[edge[0]]['id']
            destId = self.resolvedGraph.node[edge[1]]['id']
            value = arcFlowMap[(srcId, destId)]
            self.hypothesesGraph._graph.add_edge(edge[0], edge[1], value=value)
