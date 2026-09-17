(in-package #:symbolic-ai.planner.tests)

;; These are finite teaching oracles, not a second planner or a public solver API.
;; All search is delegated to the accepted Search Library.  The explicit fact
;; vocabulary makes a model escape an error rather than a silently pruned edge.
(define-condition lab-vocabulary-escape (error)
  ((fact :initarg :fact :reader lab-vocabulary-escape-fact))
  (:report (lambda (condition stream)
             (format stream "Heuristic lab fact is outside its finite vocabulary: ~S"
                     (lab-vocabulary-escape-fact condition)))))

(defun check-lab-vocabulary (facts vocabulary)
  (dolist (fact facts)
    (unless (member fact vocabulary :test #'equal)
      (error 'lab-vocabulary-escape :fact fact)))
  facts)

(defun lab-relaxed-successors (schemas vocabulary state)
  (loop for schema in schemas append
    (loop for action in (instantiate-applicable-actions schema state)
          for next = (canonical-state
                      (append (ground-action-add-effects action) state))
          collect
          (symbolic-ai.search:make-transition
           (check-lab-vocabulary next vocabulary)
           :action (ground-action-name action)
           :cost (ground-action-cost action)))))

(defun solve-lab-relaxation (initial goals schemas vocabulary)
  "Solve a declared finite delete-relaxed fixture exactly with existing UCS.

The two constructor calls below reuse the public ground-fact/schema validation;
no second validator, unifier, heap, or search loop is introduced.  VOCABULARY is a
finite ground-fact list, not a depth bound.  A fact outside it raises an error;
this function never disguises a truncated model as exhaustive search."
  (make-planning-problem initial goals schemas)
  (make-planning-problem vocabulary '() '())
  (let ((initial (canonical-state initial))
        (goals (canonical-state goals))
        (vocabulary (canonical-state vocabulary)))
    (check-lab-vocabulary initial vocabulary)
    (check-lab-vocabulary goals vocabulary)
    (symbolic-ai.search:uniform-cost-search
     (symbolic-ai.search:make-problem
      initial
      (lambda (state) (goal-satisfied-p state goals))
      (lambda (state) (lab-relaxed-successors schemas vocabulary state))
      :key #'identity))))

(defun heuristic-lab-case (name)
  "Return INITIAL, GOALS, SCHEMAS, VOCABULARY for one synthetic lab case."
  (ecase name
    (:warehouse
     (values (warehouse-initial-state) (warehouse-goals) (warehouse-schemas)
             '((at robot dock) (at robot hall) (at robot office)
               (at package-17 dock) (at package-17 hall) (at package-17 office)
               (empty robot) (carrying robot package-17) (carrying robot robot)
               (connected dock hall) (connected hall office))))
    (:independent
     (values '((ready)) '((left-done) (right-done))
             (list (make-action-schema 'left '() '((ready))
                                       '((left-done)) '() :cost 2)
                   (make-action-schema 'right '() '((ready))
                                       '((right-done)) '() :cost 3))
             '((ready) (left-done) (right-done))))
    (:shared
     (values '((ready)) '((done))
             (list (make-action-schema 'prepare '() '((ready))
                                       '((a) (b)) '() :cost 3)
                   (make-action-schema 'finish '() '((a) (b))
                                       '((done)) '() :cost 1))
             '((ready) (a) (b) (done))))
    (:consumable
     (values '((token)) '((left-done) (right-done))
             (list (make-action-schema 'left '() '((token))
                                       '((left-done)) '((token)))
                   (make-action-schema 'right '() '((token))
                                       '((right-done)) '((token))))
             '((token) (left-done) (right-done))))))

(defun lab-cost-or-status (result)
  (ecase (symbolic-ai.search:search-result-status result)
    (:found (symbolic-ai.search:search-result-cost result))
    (:not-found :not-found)))

(defun measure-heuristic-lab (name)
  (multiple-value-bind (initial goals schemas vocabulary) (heuristic-lab-case name)
    (let ((analysis (analyze-hmax-relaxation initial goals schemas))
          (relaxed (solve-lab-relaxation initial goals schemas vocabulary))
          (real (solve-plan initial goals schemas :algorithm :uniform-cost)))
      (unless (eq :reached (relaxed-analysis-status analysis))
        (error "Expected a converged heuristic in lab ~S, got ~S."
               name (relaxed-analysis-status analysis)))
      (list :case name
            :hmax (relaxed-analysis-estimate analysis)
            :relaxed-cost (lab-cost-or-status relaxed)
            :real-cost (lab-cost-or-status real)))))

(defun late-support-schemas ()
  ;; The declaration order intentionally delays cheap support across passes.
  (list (make-action-schema 'direct '() '((ready)) '((done)) '() :cost 10)
        (make-action-schema 'finish '() '((middle)) '((done)) '())
        (make-action-schema 'advance '() '((started)) '((middle)) '())
        (make-action-schema 'start '() '((ready)) '((started)) '())))

(defun lab-fact-cost (fact analysis)
  (let ((entry (assoc fact (relaxed-analysis-fact-costs analysis) :test #'equal)))
    (unless entry
      (error "No diagnostic fact cost for ~S." fact))
    (cdr entry)))

(deftest lab-warehouse-separates-max-from-exact-relaxation
  (is-equal '(:case :warehouse :hmax 3 :relaxed-cost 4 :real-cost 4)
            (measure-heuristic-lab :warehouse)))

(deftest lab-independent-work-is-lost-even-with-no-deletes
  (is-equal '(:case :independent :hmax 3 :relaxed-cost 5 :real-cost 5)
            (measure-heuristic-lab :independent)))

(deftest lab-shared-work-makes-naive-summing-overestimate
  (is-equal '(:case :shared :hmax 4 :relaxed-cost 4 :real-cost 4)
            (measure-heuristic-lab :shared))
  (multiple-value-bind (initial goals schemas vocabulary) (heuristic-lab-case :shared)
    (declare (ignore vocabulary))
    (let* ((analysis (analyze-hmax-relaxation initial goals schemas))
           (wrong-sum (+ 1 (lab-fact-cost '(a) analysis)
                           (lab-fact-cost '(b) analysis)))
           (real (solve-plan initial goals schemas :algorithm :uniform-cost)))
      (is (= 7 wrong-sum))
      (is (> wrong-sum (symbolic-ai.search:search-result-cost real))))))

(deftest lab-relaxed-solvability-does-not-imply-real-solvability
  (is-equal '(:case :consumable :hmax 1 :relaxed-cost 2 :real-cost :not-found)
            (measure-heuristic-lab :consumable)))

(deftest lab-relaxed-path-is-not-a-real-explanation
  (multiple-value-bind (initial goals schemas vocabulary)
      (heuristic-lab-case :consumable)
    (let ((result (solve-lab-relaxation initial goals schemas vocabulary)))
      (is (eq :found (symbolic-ai.search:search-result-status result)))
      (signals invalid-plan-trace (explain-plan-result schemas result)))))

(deftest lab-oracle-preserves-inputs-and-real-delete-semantics
  (multiple-value-bind (initial goals schemas vocabulary)
      (heuristic-lab-case :consumable)
    (let ((saved (copy-tree initial)))
      (solve-lab-relaxation initial goals schemas vocabulary)
      (is-equal saved initial)
      (let* ((action (first (instantiate-applicable-actions (first schemas) initial)))
             (next (apply-ground-action initial action)))
        (is (not (member '(token) next :test #'equal)))
        (is-equal '((token)) (ground-action-delete-effects action))))))

(deftest lab-first-goal-support-is-not-a-converged-estimate
  (let* ((schemas (late-support-schemas))
         (bounded (analyze-hmax-relaxation '((ready)) '((done)) schemas
                                           :max-iterations 1))
         (real (solve-plan '((ready)) '((done)) schemas :algorithm :uniform-cost)))
    (is (eq :bounded (relaxed-analysis-status bounded)))
    (is (null (relaxed-analysis-estimate bounded)))
    (is (= 10 (lab-fact-cost '(done) bounded)))
    (is (= 3 (symbolic-ai.search:search-result-cost real)))
    (is (> (lab-fact-cost '(done) bounded)
           (symbolic-ai.search:search-result-cost real)))
    (is (= 0 (funcall (make-hmax-heuristic '((done)) schemas :max-iterations 1)
                      '((ready)))))))

(deftest lab-fixedpoint-requires-a-no-change-pass
  (let* ((schemas (late-support-schemas))
         (third (analyze-hmax-relaxation '((ready)) '((done)) schemas
                                         :max-iterations 3))
         (fourth (analyze-hmax-relaxation '((ready)) '((done)) schemas
                                          :max-iterations 4)))
    (is (= 3 (lab-fact-cost '(done) third)))
    (is (eq :bounded (relaxed-analysis-status third)))
    (is (null (relaxed-analysis-estimate third)))
    (is (eq :reached (relaxed-analysis-status fourth)))
    (is (= 3 (relaxed-analysis-estimate fourth)))
    (is (= 4 (relaxed-analysis-iterations fourth)))
    (let ((support (cdr (assoc '(done) (relaxed-analysis-supports fourth)
                               :test #'equal))))
      (is-equal '(finish) (relaxed-support-action-name support)))))

(deftest lab-order-changes-propagation-passes-not-this-final-value
  (let* ((schemas (late-support-schemas))
         (forward (analyze-hmax-relaxation '((ready)) '((done)) schemas))
         (reverse (analyze-hmax-relaxation '((ready)) '((done)) (reverse schemas))))
    (is (eq :reached (relaxed-analysis-status forward)))
    (is (eq :reached (relaxed-analysis-status reverse)))
    (is (= 3 (relaxed-analysis-estimate forward) (relaxed-analysis-estimate reverse)))
    (is (= 4 (relaxed-analysis-iterations forward)))
    (is (= 2 (relaxed-analysis-iterations reverse)))))

(deftest lab-zero-cost-cycle-does-not-replace-equal-support-forever
  (let* ((schemas (list (make-action-schema 'wake '() '((ready)) '((awake)) '() :cost 0)
                        (make-action-schema 'back '() '((awake)) '((ready)) '() :cost 0)
                        (make-action-schema 'finish '() '((awake)) '((done)) '() :cost 2)))
         (analysis (analyze-hmax-relaxation '((ready)) '((done)) schemas
                                           :max-iterations 8)))
    (is (eq :reached (relaxed-analysis-status analysis)))
    (is (= 2 (relaxed-analysis-estimate analysis)))
    (is (= 0 (lab-fact-cost '(awake) analysis)))))

(deftest lab-zero-budget-distinguishes-initial-goal-from-no-analysis
  (let ((solved (analyze-hmax-relaxation '((ready)) '((ready))
                                        (late-support-schemas) :max-iterations 0))
        (bounded (analyze-hmax-relaxation '((ready)) '((done))
                                         (late-support-schemas) :max-iterations 0)))
    (is (eq :reached (relaxed-analysis-status solved)))
    (is (= 0 (relaxed-analysis-estimate solved)))
    (is (= 0 (relaxed-analysis-iterations solved)))
    (is (eq :bounded (relaxed-analysis-status bounded)))
    (is (null (relaxed-analysis-estimate bounded)))))

(deftest lab-vocabulary-escape-is-an-error-not-an-unreachable-result
  (let* ((x (v 'x))
         (grow (make-action-schema 'grow (list x) `((seed ,x))
                                    `((seed (next ,x))) '())))
    (signals lab-vocabulary-escape
      (solve-lab-relaxation '((seed zero)) '((done)) (list grow)
                            '((seed zero) (done)))))
  (signals lab-vocabulary-escape
    (solve-lab-relaxation '((ready)) '((done)) '() '((ready)))))

(defun run-heuristic-labs ()
  "Print computed rows, never a hard-coded transcript or timing benchmark."
  (dolist (name '(:warehouse :independent :shared :consumable))
    (let ((row (measure-heuristic-lab name)))
      (format t "~(~A~): hmax=~A; exact-relaxed=~A; real=~A~%"
              name (getf row :hmax) (getf row :relaxed-cost) (getf row :real-cost))))
  (dolist (limit '(0 1 2 3 4))
    (let* ((analysis (analyze-hmax-relaxation '((ready)) '((done))
                                            (late-support-schemas)
                                            :max-iterations limit))
           (entry (assoc '(done) (relaxed-analysis-fact-costs analysis) :test #'equal)))
      (format t "limit=~D: status=~S; estimate=~S; diagnostic-goal-cost=~S~%"
              limit (relaxed-analysis-status analysis) (relaxed-analysis-estimate analysis)
              (if entry (cdr entry) :absent))))
  t)
