(in-package #:symbolic-ai.search.tests)

;;; Metamorphic/regression oracles for relationships between search algorithms.
;;; These tests intentionally reuse the public teaching API instead of reaching
;;; into frontier internals.

(deftest unit-cost-bfs-and-uniform-cost-agree-on-controlled-problem
  (let* ((table `((s ,(edge 'a :s-a) ,(edge 'b :s-b))
                  (a ,(edge 'g :a-g))
                  (b ,(edge 'c :b-c))
                  (c ,(edge 'g :c-g))))
         (problem (problem-from-table 's 'g table))
         (bfs (breadth-first-search problem))
         (ucs (uniform-cost-search problem)))
    ;; AIMA notes that uniform-cost search reduces to breadth-first search when
    ;; every step cost is equal.  On this deterministic problem we can assert
    ;; the stronger observable result as a regression oracle.
    (is-equal (search-result-path bfs) (search-result-path ucs))
    (is-equal (search-result-actions bfs) (search-result-actions ucs))
    (is (= (search-result-cost bfs) (search-result-cost ucs)))
    (is (= 2 (search-result-cost ucs)))))

(deftest zero-heuristic-a-star-matches-uniform-cost
  (let* ((table `((s ,(edge 'g :direct 12) ,(edge 'a :s-a 2)
                     ,(edge 'b :s-b 8))
                  (a ,(edge 'c :a-c 2))
                  (c ,(edge 'g :c-g 2))
                  (b ,(edge 'g :b-g 1))))
         (problem (problem-from-table 's 'g table :heuristic (constantly 0)))
         (ucs (uniform-cost-search problem))
         (astar (a-star-search problem)))
    ;; With h(n)=0, A* uses f(n)=g(n), exactly the UCS priority.  Because this
    ;; implementation also shares best-g, stale-entry, and stable serial tie
    ;; handling, every exposed result field below should agree.
    (is-equal (search-result-path ucs) (search-result-path astar))
    (is-equal (search-result-actions ucs) (search-result-actions astar))
    (is (= (search-result-cost ucs) (search-result-cost astar)))
    (is (= (search-result-expanded ucs) (search-result-expanded astar)))
    (is (= (search-result-generated ucs) (search-result-generated astar)))
    (is (= (search-result-duplicate-pruned ucs)
           (search-result-duplicate-pruned astar)))
    (is (= (search-result-stale-popped ucs)
           (search-result-stale-popped astar)))
    (is (= (search-result-max-frontier ucs)
           (search-result-max-frontier astar)))
    (is (= 6 (search-result-cost astar)))))

(deftest initial-goal-is-a-zero-step-solution-for-every-search
  (let ((successor-calls 0))
    (flet ((successors (state)
             (declare (ignore state))
             (incf successor-calls)
             (error "Goal root must not be expanded.")))
      (let* ((problem (make-problem 'goal
                                    (lambda (state) (eql state 'goal))
                                    #'successors
                                    :heuristic (constantly 0)))
             (results (list (depth-first-search problem)
                            (breadth-first-search problem)
                            (uniform-cost-search problem)
                            (a-star-search problem))))
        (dolist (result results)
          (is (eq :found (search-result-status result)))
          (is-equal '(goal) (search-result-path result))
          (is (null (search-result-actions result)))
          (is (zerop (search-result-cost result)))
          (is (zerop (search-result-expanded result)))
          (is (= 1 (search-result-generated result))))
        (is (zerop successor-calls))))))
