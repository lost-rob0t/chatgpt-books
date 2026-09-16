(defmodule event-rules-tests
  "Executable regression checks for the Event Routing DSL data kernel."
  (export (run 0)))

(defun expect
  (['critical-route (tuple 'ok 'pager)] 'ok)
  (['service-route (tuple 'ok 'billing-queue)] 'ok)
  (['fallback-route (tuple 'ok 'archive)] 'ok)
  (['first-match (tuple 'ok 'sink)] 'ok)
  (['no-route (tuple 'error 'no-route)] 'ok)
  (['bad-event (tuple 'error (tuple 'bad-event 'not-an-event))] 'ok)
  (['bad-rule (tuple 'error (tuple 'bad-rule (tuple 'wat 'nope)))] 'ok)
  ([label actual]
   (erlang:error (tuple 'assertion-failed label actual))))

(defun run ()
  (let ((rules (event-rules:sample-rules)))
    (expect 'critical-route
            (event-rules:route
             (tuple 'event 'critical 'edge '#"disk full")
             rules))
    (expect 'service-route
            (event-rules:route
             (tuple 'event 'warning 'billing '#"slow checkout")
             rules))
    (expect 'fallback-route
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             rules))
    (expect 'first-match
            (event-rules:route
             (tuple 'event 'critical 'edge '#"disk full")
             (list (tuple 'otherwise 'sink)
                   (tuple 'when-level 'critical 'pager))))
    (expect 'no-route
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             ()))
    (expect 'bad-event
            (event-rules:route 'not-an-event rules))
    (expect 'bad-rule
            (event-rules:route
             (tuple 'event 'info 'search '#"reindexed")
             (list (tuple 'wat 'nope))))
    'ok))
