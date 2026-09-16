(in-package #:expert-systems.matcher)

(defstruct alpha-item
  "One asserted working-memory occurrence accepted by one alpha condition."
  entry
  bindings)

(defstruct alpha-memory
  "Condition-local cache for the positive pattern subset used in milestone C."
  condition
  (items '()))

(defstruct beta-token
  "One partial left-to-right join result.

BINDINGS follows the same first-binding order as MATCH-CONDITIONS. FACT-IDS and
SUPPORT-STAMPS preserve condition order so a token is directly comparable with
the complete-rematch oracle's MATCH-RESULT."
  bindings
  fact-ids
  support-stamps)

(defstruct beta-memory
  "Tokens after DEPTH conditions have been joined."
  depth
  (tokens '()))

(defstruct join-node
  "One explicit join edge between a beta memory and an alpha memory."
  index
  alpha-memory
  left-memory
  right-memory)

(defstruct production-node
  "Terminal node that turns complete beta tokens into activations."
  production
  beta-memory)

(defstruct production-network
  production
  alpha-memories
  beta-memories
  join-nodes
  production-node)

(defstruct (incremental-network (:constructor %make-incremental-network))
  "Incremental positive-pattern network attached to one milestone-B ENGINE.

This is deliberately RETE-like rather than a claim to reproduce every RETE or
CLIPS implementation detail. Each production owns its alpha memories in this
teaching milestone; common-test/node sharing is deferred."
  engine
  production-networks)

(defun empty-beta-token ()
  (make-beta-token :bindings '() :fact-ids '() :support-stamps '()))

(defun make-production-network-for (production)
  (let* ((conditions (production-conditions production))
         (alpha-memories
           (mapcar (lambda (condition)
                     (make-alpha-memory :condition condition))
                   conditions))
         (beta-memories
           (loop for depth from 0 to (length conditions)
                 collect (make-beta-memory :depth depth)))
         (joins
           (loop for index from 0 below (length conditions)
                 collect
                 (make-join-node
                  :index index
                  :alpha-memory (nth index alpha-memories)
                  :left-memory (nth index beta-memories)
                  :right-memory (nth (1+ index) beta-memories)))))
    ;; The empty token is the identity for the first join. For a production
    ;; with no conditions it is also the single complete token.
    (setf (beta-memory-tokens (first beta-memories))
          (list (empty-beta-token)))
    (make-production-network
     :production production
     :alpha-memories alpha-memories
     :beta-memories beta-memories
     :join-nodes joins
     :production-node
     (make-production-node :production production
                           :beta-memory (car (last beta-memories))))))

(defun merge-binding-environments (base additions)
  "Merge ADDITIONS into BASE using the milestone-A binding consistency rule."
  (let ((current base))
    (dolist (pair additions (values current t))
      (multiple-value-bind (next consistent-p)
          (extend-binding (car pair) (cdr pair) current)
        (unless consistent-p
          (return (values nil nil)))
        (setf current next)))))

(defun alpha-item-for-entry (memory entry)
  "Return an ALPHA-ITEM when ENTRY satisfies MEMORY's local condition."
  (multiple-value-bind (bindings matched-p)
      (match-condition (alpha-memory-condition memory)
                       (wm-entry-fact entry))
    (when matched-p
      (make-alpha-item :entry entry :bindings bindings))))

(defun beta-token-key (token)
  (list (beta-token-support-stamps token)
        (beta-token-bindings token)))

(defun beta-memory-add-token (memory token)
  "Append TOKEN unless an equal support/binding token is already present.

Returns true only when TOKEN was newly inserted."
  (unless (find (beta-token-key token)
                (beta-memory-tokens memory)
                :key #'beta-token-key
                :test #'equal)
    (setf (beta-memory-tokens memory)
          (append (beta-memory-tokens memory) (list token)))
    t))

(defun join-token-and-alpha-item (token item)
  (multiple-value-bind (bindings consistent-p)
      (merge-binding-environments (beta-token-bindings token)
                                  (alpha-item-bindings item))
    (when consistent-p
      (let* ((entry (alpha-item-entry item))
             (fact (wm-entry-fact entry))
             (stamp (cons (fact-id fact) (wm-entry-sequence entry))))
        (make-beta-token
         :bindings bindings
         :fact-ids (append (beta-token-fact-ids token)
                           (list (fact-id fact)))
         :support-stamps (append (beta-token-support-stamps token)
                                 (list stamp)))))))

(defun propagate-beta-token (production-network depth token)
  "Propagate one newly inserted TOKEN rightward from beta DEPTH."
  (let ((condition-count
          (length (production-conditions
                   (production-network-production production-network)))))
    (when (< depth condition-count)
      (let* ((join (nth depth (production-network-join-nodes
                               production-network)))
             (right (join-node-right-memory join)))
        (dolist (item (alpha-memory-items (join-node-alpha-memory join)))
          (let ((next (join-token-and-alpha-item token item)))
            (when (and next (beta-memory-add-token right next))
              (propagate-beta-token production-network (1+ depth) next))))))))

(defun propagate-alpha-item (production-network index item)
  "Join one newly cached alpha ITEM against existing left beta tokens."
  (let* ((join (nth index (production-network-join-nodes production-network)))
         (right (join-node-right-memory join)))
    (dolist (token (beta-memory-tokens (join-node-left-memory join)))
      (let ((next (join-token-and-alpha-item token item)))
        (when (and next (beta-memory-add-token right next))
          (propagate-beta-token production-network (1+ index) next))))))

(defun production-network-assert-entry (production-network entry)
  "Incrementally propagate one asserted working-memory ENTRY."
  (loop for memory in (production-network-alpha-memories production-network)
        for index from 0
        for item = (alpha-item-for-entry memory entry)
        when item
          do (setf (alpha-memory-items memory)
                   (append (alpha-memory-items memory) (list item)))
             (propagate-alpha-item production-network index item))
  production-network)

(defun support-stamp-present-p (stamp token)
  (member stamp (beta-token-support-stamps token) :test #'equal))

(defun production-network-retract-entry (production-network entry)
  "Remove every cached alpha item and beta token depending on ENTRY."
  (let* ((fact (wm-entry-fact entry))
         (stamp (cons (fact-id fact) (wm-entry-sequence entry))))
    (dolist (memory (production-network-alpha-memories production-network))
      (setf (alpha-memory-items memory)
            (remove entry
                    (alpha-memory-items memory)
                    :key #'alpha-item-entry
                    :test #'eq)))
    ;; beta depth 0 contains the permanent empty token and cannot depend on a WME.
    (dolist (memory (rest (production-network-beta-memories production-network)))
      (setf (beta-memory-tokens memory)
            (remove-if (lambda (token)
                         (support-stamp-present-p stamp token))
                       (beta-memory-tokens memory)))))
  production-network)

(defun incremental-network-propagate-entry (network entry)
  (dolist (production-network (incremental-network-production-networks network))
    (production-network-assert-entry production-network entry))
  network)

(defun make-incremental-network (engine)
  "Compile ENGINE's current positive-condition productions and seed its memories.

The ENGINE remains the authority for working memory, refraction, firing records,
and agenda policy. This network caches only matching state. Production sets are
fixed for the lifetime of this milestone-C network."
  (let* ((production-networks
           (mapcar #'make-production-network-for (engine-productions engine)))
         (network (%make-incremental-network
                   :engine engine
                   :production-networks production-networks)))
    (dolist (entry (working-memory-entries (engine-working-memory engine)))
      (incremental-network-propagate-entry network entry))
    network))

(defun incremental-production-network (network production-id)
  "Return the compiled network for PRODUCTION-ID, or NIL."
  (find production-id
        (incremental-network-production-networks network)
        :key (lambda (production-network)
               (production-id
                (production-network-production production-network)))
        :test #'equal))

(defun activation-from-beta-token (production token)
  (let* ((stamps (beta-token-support-stamps token))
         (bindings (beta-token-bindings token)))
    (make-activation
     :production production
     :bindings (copy-tree bindings)
     :fact-ids (copy-list (beta-token-fact-ids token))
     :support-stamps (copy-tree stamps)
     :recency (reduce #'max stamps :key #'cdr :initial-value 0)
     :specificity (production-specificity production)
     :key (activation-key-for production bindings stamps))))

(defun incremental-agenda (network)
  "Return the same ordered activation contract as BUILD-AGENDA from cached tokens."
  (let ((engine (incremental-network-engine network))
        (activations '()))
    (dolist (production-network (incremental-network-production-networks network))
      (let* ((node (production-network-production-node production-network))
             (production (production-node-production node)))
        (dolist (token (beta-memory-tokens (production-node-beta-memory node)))
          (push (activation-from-beta-token production token) activations))))
    (stable-sort
     (remove-if (lambda (activation)
                  (activation-refracted-p engine activation))
                (nreverse activations))
     #'activation-precedes-p)))

(defun incremental-assert-facts (network facts)
  "Assert FACTS through ENGINE semantics, then propagate only their new occurrences."
  (let ((entries (assert-facts
                  (engine-working-memory (incremental-network-engine network))
                  facts)))
    (dolist (entry entries)
      (incremental-network-propagate-entry network entry))
    entries))

(defun incremental-assert-fact (network fact)
  (first (incremental-assert-facts network (list fact))))

(defun incremental-retract-fact (network fact-id)
  "Retract FACT-ID and remove cached tokens that depended on its exact occurrence."
  (let* ((engine (incremental-network-engine network))
         (memory (engine-working-memory engine))
         (entry (find-wm-entry memory fact-id)))
    (if (null entry)
        (values nil nil)
        (multiple-value-bind (fact present-p)
            (retract-fact memory fact-id)
          (when present-p
            (dolist (production-network
                     (incremental-network-production-networks network))
              (production-network-retract-entry production-network entry)))
          (values fact present-p)))))

(defun incremental-fire-activation (network activation)
  "Fire ACTIVATION through ENGINE, then propagate only its newly asserted entries."
  (multiple-value-bind (record new-entries)
      (fire-activation (incremental-network-engine network) activation)
    (dolist (entry new-entries)
      (incremental-network-propagate-entry network entry))
    record))

(defun run-incremental-engine (network &key (firing-limit 100))
  "Forward-chain from cached matches until quiescence or FIRING-LIMIT."
  (unless (and (integerp firing-limit) (not (minusp firing-limit)))
    (error "FIRING-LIMIT must be a non-negative integer, got ~S." firing-limit))
  (let ((engine (incremental-network-engine network)))
    (loop repeat firing-limit
          for agenda = (incremental-agenda network)
          do (when (endp agenda)
               (return-from run-incremental-engine
                 (make-run-result-from-engine engine :quiescent agenda)))
             (incremental-fire-activation network (first agenda)))
    (let ((agenda (incremental-agenda network)))
      (make-run-result-from-engine
       engine
       (if (endp agenda) :quiescent :limit)
       agenda))))

(defun incremental-network-snapshot (network)
  "Return deterministic inspectable cache sizes and terminal activation keys."
  (mapcar
   (lambda (production-network)
     (let* ((production (production-network-production production-network))
            (node (production-network-production-node production-network)))
       (list :production-id (production-id production)
             :alpha-counts
             (mapcar (lambda (memory)
                       (length (alpha-memory-items memory)))
                     (production-network-alpha-memories production-network))
             :beta-counts
             (mapcar (lambda (memory)
                       (length (beta-memory-tokens memory)))
                     (production-network-beta-memories production-network))
             :terminal-activation-keys
             (mapcar (lambda (token)
                       (activation-key
                        (activation-from-beta-token production token)))
                     (beta-memory-tokens (production-node-beta-memory node))))))
   (incremental-network-production-networks network)))
