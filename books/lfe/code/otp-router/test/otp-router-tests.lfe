(defmodule otp-router-tests
  "Focused checks for the LFE gen_server callback boundary."
  (export (run 0)))

(defun expect (label expected actual)
  (case (=:= expected actual)
    ('true 'ok)
    ('false
     (erlang:error (tuple 'assertion-failed label expected actual)))))

(defun start-server (rules)
  (case (otp-router:start_link rules)
    ((tuple 'ok pid) pid)
    (other
     (erlang:error (tuple 'start-failed other)))))

(defun run ()
  (let* ((rules (event-rules:sample-rules))
         (event (event-rules:sample-event))
         (_pid (start-server rules)))
    (expect 'route-through-gen-server
            (tuple 'ok 'pager)
            (otp-router:route event 1000))

    (expect 'sys-sees-callback-state
            rules
            (sys:get_state 'otp-router))

    (let ((new-rules (list (tuple 'otherwise 'sink))))
      (expect 'replace-rules-ack
              (tuple 'ok 'replaced)
              (otp-router:replace-rules new-rules 1000))
      (expect 'callback-state-transition
              (tuple 'ok new-rules)
              (otp-router:get-rules 1000))
      (expect 'new-state-affects-routing
              (tuple 'ok 'sink)
              (otp-router:route event 1000)))

    (expect 'unknown-call-is-domain-error
            (tuple 'error (tuple 'bad-request 'wat))
            (otp-router:request 'wat 1000))

    (expect 'clean-gen-server-stop
            'ok
            (otp-router:stop))
    'ok))
