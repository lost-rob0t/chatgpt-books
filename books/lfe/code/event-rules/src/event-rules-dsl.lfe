(defmodule event-rules-dsl
  "Compile-time source layer for the Event Routing DSL."
  (export-macro routes))

(defmacro routes clauses
  "Compile declarative route clauses into the explicit data-first rule kernel."
  (compile-routes clauses))

(eval-when-compile
  (defun compile-routes (clauses)
    (cons 'list (compile-clauses clauses)))

  (defun compile-clauses
    ([()]
     ())
    ([(cons clause rest)]
     (cons (compile-clause clause)
           (compile-clauses rest))))

  (defun compile-clause
    ([(list 'when-level level destination)]
     `(tuple 'when-level ,level ,destination))
    ([(list 'when-service service destination)]
     `(tuple 'when-service ,service ,destination))
    ([(list 'otherwise destination)]
     `(tuple 'otherwise ,destination))
    ([bad-clause]
     (erlang:error (tuple 'bad-event-rule-syntax bad-clause)))))
