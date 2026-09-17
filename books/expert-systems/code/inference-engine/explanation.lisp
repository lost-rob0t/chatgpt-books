(in-package #:expert-systems.matcher)

(defstruct explanation-node
  "One typed vertex in a read-only explanation graph.

ID is deterministic and occurrence-sensitive. KIND names the role of the node.
DATA is an inspectable property list. The graph is a derived view; it never
owns or mutates inference-engine state."
  id
  kind
  data)

(defstruct explanation-edge
  "One typed directed relationship between two explanation-node IDs."
  from
  to
  kind)

(defstruct explanation-graph
  "A deterministic read-only explanation result.

STATUS is :GROUNDED, :ABSENT, :UNSUPPORTED, :CONTRADICTION, or :STALE.
ROOTS contains node IDs. NODES and EDGES preserve first-discovery order."
  status
  roots
  nodes
  edges)

(defun explanation-fact-node-id (stamp)
  (list :fact-occurrence (copy-tree stamp)))

(defun explanation-source-node-id (stamp support-kind)
  (list :support-source (copy-tree stamp) support-kind))

(defun explanation-justification-node-id (justification)
  (list :justification (copy-tree (justification-id justification))))

(defun explanation-contradiction-node-id (report)
  (list :contradiction
        (contradiction-report-spec-id report)
        (copy-tree (contradiction-report-left-stamp report))
        (copy-tree (contradiction-report-right-stamp report))))

(defun explanation-graph-signature (graph)
  "Return a stable, data-only signature useful for tests and debugging."
  (list
   :status (explanation-graph-status graph)
   :roots (copy-tree (explanation-graph-roots graph))
   :nodes
   (mapcar (lambda (node)
             (list (copy-tree (explanation-node-id node))
                   (explanation-node-kind node)
                   (copy-tree (explanation-node-data node))))
           (explanation-graph-nodes graph))
   :edges
   (mapcar (lambda (edge)
             (list (copy-tree (explanation-edge-from edge))
                   (copy-tree (explanation-edge-to edge))
                   (explanation-edge-kind edge)))
           (explanation-graph-edges graph))))

(defun explanation-find-production (truth-network production-id)
  (find production-id
        (engine-productions (truth-maintained-engine truth-network))
        :key #'production-id
        :test #'equal))

(defun explanation-current-entry-for-stamp (truth-network stamp)
  (let ((entry (find-wm-entry
                (truth-maintained-working-memory truth-network)
                (car stamp))))
    (and entry
         (= (wm-entry-sequence entry) (cdr stamp))
         entry)))

(defun explanation-current-grounded-justifications (truth-network fact-id)
  "Return current reasons that themselves have current, grounded supports."
  (remove-if-not
   (lambda (justification)
     (and
      (justification-supports-current-p truth-network justification)
      (every
       (lambda (support-stamp)
         (truth-maintained-fact-grounded-p truth-network (car support-stamp)))
       (justification-support-stamps justification))))
   (current-justifications-for truth-network fact-id)))

(defun explanation-add-node (node nodes)
  "Append NODE unless its deterministic ID is already present."
  (if (find (explanation-node-id node)
            nodes
            :key #'explanation-node-id
            :test #'equal)
      nodes
      (append nodes (list node))))

(defun explanation-add-edge (edge edges)
  "Append EDGE unless an equal typed relationship already exists."
  (if (find-if
       (lambda (current)
         (and (equal (explanation-edge-from current)
                     (explanation-edge-from edge))
              (equal (explanation-edge-to current)
                     (explanation-edge-to edge))
              (eq (explanation-edge-kind current)
                  (explanation-edge-kind edge))))
       edges)
      edges
      (append edges (list edge))))

(defun build-current-fact-explanation (network fact-id)
  "Build a current support/provenance graph for FACT-ID.

The graph is built from exact current occurrences and current grounded
justifications, not from the firing log. Historical reasons remain in the TMS
ledger but cannot appear as current support unless their exact conclusion and
support occurrence stamps are current and recursively grounded."
  (let* ((truth (assumption-network-truth-network network))
         (entry (find-wm-entry
                 (truth-maintained-working-memory truth)
                 fact-id)))
    (unless entry
      (return-from build-current-fact-explanation
        (make-explanation-graph
         :status :absent :roots '() :nodes '() :edges '())))
    (let* ((root-stamp (entry-stamp entry))
           (root-id (explanation-fact-node-id root-stamp))
           (nodes '())
           (edges '()))
      (labels
          ((add-node (node)
             (setf nodes (explanation-add-node node nodes)))
           (add-edge (from to kind)
             (setf edges
                   (explanation-add-edge
                    (make-explanation-edge :from from :to to :kind kind)
                    edges)))
           (walk-stamp (stamp visiting)
             (let ((current-entry
                     (explanation-current-entry-for-stamp truth stamp)))
               (when current-entry
                 (let* ((current-fact (wm-entry-fact current-entry))
                        (current-id (fact-id current-fact))
                        (node-id (explanation-fact-node-id stamp))
                        (support-kind
                          (assumption-network-support-kind network current-id))
                        (base-p
                          (truth-maintained-base-supported-p truth current-id)))
                   (add-node
                    (make-explanation-node
                     :id node-id
                     :kind :fact
                     :data
                     (list :fact-id current-id
                           :stamp (copy-tree stamp)
                           :relation (fact-relation current-fact)
                           :arguments (copy-tree (fact-arguments current-fact))
                           :provenance (copy-tree (fact-provenance current-fact))
                           :support-kind support-kind)))
                   (when base-p
                     (let ((source-id
                             (explanation-source-node-id stamp support-kind)))
                       (add-node
                        (make-explanation-node
                         :id source-id
                         :kind :source
                         :data (list :fact-id current-id
                                     :stamp (copy-tree stamp)
                                     :support-kind support-kind
                                     :provenance
                                     (copy-tree
                                      (fact-provenance current-fact)))))
                       (add-edge node-id source-id :grounded-by)))
                   (unless (member stamp visiting :test #'equal)
                     (dolist
                         (justification
                          (explanation-current-grounded-justifications
                           truth current-id))
                       (let* ((just-id
                                (explanation-justification-node-id
                                 justification))
                              (production
                                (explanation-find-production
                                 truth
                                 (justification-production-id
                                  justification))))
                         (add-node
                          (make-explanation-node
                           :id just-id
                           :kind :justification
                           :data
                           (list
                            :justification-id
                            (copy-tree (justification-id justification))
                            :production-id
                            (justification-production-id justification)
                            :production-provenance
                            (and production
                                 (copy-tree
                                  (production-provenance production)))
                            :bindings
                            (copy-tree
                             (justification-bindings justification))
                            :activation-key
                            (copy-tree
                             (justification-activation-key justification))
                            :conclusion-stamp
                            (copy-tree
                             (justification-conclusion-stamp
                              justification)))))
                         (add-edge node-id just-id :supported-by)
                         (dolist
                             (support-stamp
                              (justification-support-stamps justification))
                           (let ((support-id
                                   (explanation-fact-node-id support-stamp)))
                             (add-edge just-id support-id :uses)
                             (walk-stamp
                              support-stamp
                              (cons stamp visiting))))))))))))
        (walk-stamp root-stamp '()))
      (make-explanation-graph
       :status
       (if (truth-maintained-fact-grounded-p truth fact-id)
           :grounded
           :unsupported)
       :roots (list root-id)
       :nodes nodes
       :edges edges))))

(defun explain-current-fact (network fact-id)
  "Return a read-only explanation graph for FACT-ID in NETWORK.

An absent fact is reported as :ABSENT. A current but ungrounded fact is
:UNSUPPORTED. Neither case invents a failed-rule or opposite-fact narrative."
  (unless (typep network 'assumption-network)
    (error "Expected an ASSUMPTION-NETWORK, got ~S." network))
  (build-current-fact-explanation network fact-id))

(defun contradiction-report-current-p (network report)
  "Return true when REPORT's exact contradiction pair is still current."
  (let ((key (contradiction-report-key report)))
    (find key
          (assumption-network-contradictions network)
          :key #'contradiction-report-key
          :test #'equal)))

(defun explanation-merge-graph (graph nodes edges)
  "Merge GRAPH into NODES/EDGES, preserving first-discovery order."
  (dolist (node (explanation-graph-nodes graph))
    (setf nodes (explanation-add-node node nodes)))
  (dolist (edge (explanation-graph-edges graph))
    (setf edges (explanation-add-edge edge edges)))
  (values nodes edges))

(defun explain-contradiction-report (network report)
  "Explain one exact current contradiction without selecting a winner.

A stale report returns :STALE and no graph. A current report becomes a
contradiction root connected to both counterevidence fact occurrences, and each
side is expanded through the same exact-support explanation machinery."
  (unless (typep network 'assumption-network)
    (error "Expected an ASSUMPTION-NETWORK, got ~S." network))
  (unless (typep report 'contradiction-report)
    (error "Expected a CONTRADICTION-REPORT, got ~S." report))
  (unless (contradiction-report-current-p network report)
    (return-from explain-contradiction-report
      (make-explanation-graph
       :status :stale :roots '() :nodes '() :edges '())))
  (let* ((root-id (explanation-contradiction-node-id report))
         (left-graph
           (build-current-fact-explanation
            network (contradiction-report-left-fact-id report)))
         (right-graph
           (build-current-fact-explanation
            network (contradiction-report-right-fact-id report)))
         (nodes
           (list
            (make-explanation-node
             :id root-id
             :kind :contradiction
             :data
             (list
              :spec-id (contradiction-report-spec-id report)
              :spec-provenance
              (copy-tree (contradiction-report-spec-provenance report))
              :bindings
              (copy-tree (contradiction-report-bindings report))
              :left-stamp
              (copy-tree (contradiction-report-left-stamp report))
              :left-support-kind
              (contradiction-report-left-support-kind report)
              :right-stamp
              (copy-tree (contradiction-report-right-stamp report))
              :right-support-kind
              (contradiction-report-right-support-kind report)))))
         (edges '()))
    (multiple-value-setq (nodes edges)
      (explanation-merge-graph left-graph nodes edges))
    (multiple-value-setq (nodes edges)
      (explanation-merge-graph right-graph nodes edges))
    (let ((left-id
            (explanation-fact-node-id
             (contradiction-report-left-stamp report)))
          (right-id
            (explanation-fact-node-id
             (contradiction-report-right-stamp report))))
      (setf edges
            (explanation-add-edge
             (make-explanation-edge
              :from root-id :to left-id :kind :counterevidence)
             edges))
      (setf edges
            (explanation-add-edge
             (make-explanation-edge
              :from root-id :to right-id :kind :counterevidence)
             edges)))
    (make-explanation-graph
     :status :contradiction
     :roots (list root-id)
     :nodes nodes
     :edges edges)))
