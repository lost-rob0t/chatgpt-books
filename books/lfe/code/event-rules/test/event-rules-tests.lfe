(defmodule event-rules-tests
  "Executable regression checks for the Event Routing DSL kernel and macro surface."
  (export (run 0)))

;; Deliberately unsafe teaching macro. Chapter 7 uses this to make LFE's
;; documented non-hygienic behavior observable instead of merely warning about it.
(defmacro unsafe-with-value (expr body)
  `(let ((value ,expr))
     ,body))

(defun expect (label expected actual)
  (case (=:= expected actual)
    ('true 'ok)
    ('false
     (erlang:error (tuple 'assertion-failed label expected actual)))))

(defun capture-demo ()
  (let ((value 'caller))
    (unsafe-with-value 'macro value)))

(defun macro-expansion ()
  (let* ((env (lfe_env:new))
         (expr '(event-rules-dsl:routes
                 (when-level (quote critical) (quote pager))
                 (when-service (quote billing) (quote billing-queue))
                 (otherwise (quote archive))))
         ((tuple 'yes expanded) (lfe_macro:expand_expr_1 expr env)))
    expanded))

(defun run ()
  (let ((rules (event-rules:sample-rules)))
    (expect 'critical-route
            (tuple 'ok 'pager)
            (event-rules:route
             (tuple 'event 'critical 'edge '#"disk full")
             rules))
    (expect 'service-route
            (tuple 'ok 'billing-queue)
            (event-rules:route
             (tuple 'event 'warning 'billing '#"slow checkout")
             rules))
    (expect 'fallback-route
            (tuple 'ok 'archive)
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             rules))
    (expect 'first-match
            (tuple 'ok 'sink)
            (event-rules:route
             (tuple 'event 'critical 'edge '#"disk full")
             (list (tuple 'otherwise 'sink)
                   (tuple 'when-level 'critical 'pager))))
    (expect 'no-route
            (tuple 'error 'no-route)
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             ()))
    (expect 'bad-event
            (tuple 'error (tuple 'bad-event 'not-an-event))
            (event-rules:route 'not-an-event rules))
    (expect 'bad-rule
            (tuple 'error (tuple 'bad-rule (tuple 'wat 'nope)))
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             (list (tuple 'wat 'nope))))
    (expect 'macro-compiled-rules
            rules
            (event-rules-example:compiled-rules))
    (expect 'macro-routes-through-kernel
            (tuple 'ok 'pager)
            (event-rules-example:route-critical))
    (expect 'one-step-macro-expansion
            '(list
              (tuple (quote when-level) (quote critical) (quote pager))
              (tuple (quote when-service) (quote billing) (quote billing-queue))
              (tuple (quote otherwise) (quote archive)))
            (macro-expansion))
    ;; Because LFE macros are not hygienic, the macro-introduced binding named
    ;; value captures the caller's reference to value in the macro body.
    (expect 'documented-capture-hazard
            'macro
            (capture-demo))
    'ok))
