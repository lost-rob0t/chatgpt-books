(defmodule actor-router-tests
  "Regression checks for the pre-OTP Actor Application milestone."
  (export (run 0)
          (silent-loop 0)))

(defun expect (label expected actual)
  (case (=:= expected actual)
    ('true 'ok)
    ('false
     (erlang:error (tuple 'assertion-failed label expected actual)))))

(defun receive-stale-reply (ref)
  (receive
    ((tuple 'reply reply-ref 'stale)
     (when (=:= reply-ref ref))
     'ok)
    (after 0
      (erlang:error 'expected-stale-reply))))

(defun silent-loop ()
  (receive
    (_message
     (silent-loop))))

(defun run ()
  (let* ((rules (event-rules:sample-rules))
         (event (event-rules:sample-event))
         (pid (actor-router:start rules)))
    (expect 'route-through-process
            (tuple 'ok 'pager)
            (actor-router:route pid event 1000))

    ;; Receive-clause pattern variables are fresh bindings in LFE. Correlation
    ;; against the outer request ref therefore belongs in an explicit guard.
    ;; A stale look-alike reply must remain in the caller mailbox.
    (let ((stale-ref (erlang:make_ref)))
      (! (self) (tuple 'reply stale-ref 'stale))
      (expect 'selective-receive-correlation
              (tuple 'ok 'pager)
              (actor-router:route pid event 1000))
      (receive-stale-reply stale-ref))

    (let ((new-rules (list (tuple 'otherwise 'sink))))
      (expect 'replace-rules-ack
              (tuple 'ok 'replaced)
              (actor-router:replace-rules pid new-rules 1000))
      (expect 'state-transition-visible
              (tuple 'ok new-rules)
              (actor-router:get-rules pid 1000))
      (expect 'new-state-affects-routing
              (tuple 'ok 'sink)
              (actor-router:route pid event 1000)))

    (expect 'bad-request-is-protocol-error
            (tuple 'error (tuple 'bad-request 'wat))
            (actor-router:request pid 'wat 1000))

    ;; Same sender -> same destination signal order is guaranteed. Queue two
    ;; requests before receiving either reply; the route must observe the rule
    ;; replacement that was sent first.
    (let* ((ordered-rules (list (tuple 'otherwise 'ordered)))
           (replace-ref (erlang:make_ref))
           (route-ref (erlang:make_ref)))
      (! pid (tuple 'call (self) replace-ref
                    (tuple 'replace-rules ordered-rules)))
      (! pid (tuple 'call (self) route-ref
                    (tuple 'route event)))
      (receive
        ((tuple 'reply reply-ref (tuple 'ok 'replaced))
         (when (=:= reply-ref replace-ref))
         'ok)
        (after 1000
          (erlang:error 'replace-reply-timeout)))
      (receive
        ((tuple 'reply reply-ref result)
         (when (=:= reply-ref route-ref))
         (expect 'same-sender-order
                 (tuple 'ok 'ordered)
                 result))
        (after 1000
          (erlang:error 'route-reply-timeout))))

    ;; Timeout is a caller-side observation, not proof that the target died or
    ;; that a request was cancelled. This sink stays alive and ignores calls.
    (let ((sink (spawn 'actor-router-tests 'silent-loop ())))
      (expect 'request-timeout
              (tuple 'error 'timeout)
              (actor-router:request sink 'ignored 20))
      (erlang:exit sink 'kill))

    (expect 'clean-stop
            'ok
            (actor-router:stop pid 1000))
    'ok))
